"""API routes for enterprise multi-tenant integrations and OAuth flows."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update

from server.auth.api_tenant import require_api_tenant
from server.auth.rbac import require_role_permission
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.integration_models import OAuthState, TenantIntegration
from server.db.models.entities import Tenant
from server.utils.rate_limiter import RateLimiter
from server.services.nango_service import nango_service
from server.services.tenant_tool_cache import invalidate as invalidate_tenant_tools
from server.utils.logger import logger

router = APIRouter(tags=["integrations"])
_connect_limiter = RateLimiter(max_requests=30, window_s=3600)


def _safe_tenant_uuid(raw_id: str | None) -> uuid.UUID:
    """Safely convert any raw tenant identifier into a deterministic UUID."""
    if not raw_id:
        return uuid.NAMESPACE_DNS
    try:
        return uuid.UUID(str(raw_id))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"tenant:{raw_id}")


class ConnectBody(BaseModel):
    base_redirect_uri: str = Field(..., max_length=1024)
    account_identifier: str | None = Field(None, max_length=255)
    api_key: str | None = Field(None, max_length=8192)


class ActivateBody(BaseModel):
    connection_id: str = Field(..., min_length=1, max_length=128)
    session_token: str | None = Field(None, max_length=4096)
    account_identifier: str | None = Field(None, max_length=255)


@router.get("/api/integrations")
async def list_integrations(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """List connected tenant integrations, automatically reconciled with Nango vault."""
    tenant_id, _ = await _resolve_tenant_and_user(request, authorization)
    session_factory = get_session_factory()
    if not session_factory:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")

    try:
        # Reconcile with live Nango connections if configured
        if nango_service.is_configured():
            try:
                live_conns = await nango_service.get_tenant_connections(tenant_id)
                if live_conns:
                    grouped: dict[str, list[dict]] = {}
                    for connection in live_conns:
                        name = nango_service.get_app_name_from_provider(connection.get("provider_config_key") or "")
                        try:
                            name = _catalog_app(name)
                        except HTTPException:
                            continue
                        if connection.get("connection_id"):
                            grouped.setdefault(name, []).append(connection)
                    async with session_factory() as session:
                        for candidates in grouped.values():
                            # Multiple accounts require an explicit selection in Connect UI.
                            if len(candidates) != 1:
                                continue
                            c = candidates[0]
                            p_key = c.get("provider_config_key") or c.get("provider") or ""
                            c_id = c.get("connection_id") or str(c.get("id") or "")
                            app_name = nango_service.get_app_name_from_provider(p_key)
                            chk = await session.execute(
                                select(TenantIntegration).where(
                                    TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                                    or_(
                                        func.upper(TenantIntegration.app_name) == app_name.upper(),
                                        func.lower(TenantIntegration.app_name) == app_name.lower(),
                                    ),
                                )
                            )
                            existing = chk.scalar_one_or_none()
                            if existing:
                                if existing.connection_id != c_id or existing.status in {"DISCONNECTED", "DISCONNECTING"}:
                                    continue
                                existing.status = "ACTIVE"
                                existing.metadata_ = {"gateway_verified": True}
                                existing.connection_id = c_id
                            else:
                                session.add(
                                    TenantIntegration(
                                        tenant_id=_safe_tenant_uuid(tenant_id),
                                        app_name=app_name.upper(),
                                        connection_id=c_id,
                                        account_identifier=f"workspace-{app_name.lower()}",
                                        status="ACTIVE",
                                        metadata_={"gateway_verified": True},
                                    )
                                )
                        await session.commit()
                        invalidate_tenant_tools(str(tenant_id))
            except Exception as e:
                logger.debug("[INTEGRATIONS] Reconciliation skipped: %s", type(e).__name__)

        async with session_factory() as session:
            stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                TenantIntegration.status == "ACTIVE",
            )
            res = await session.execute(stmt)
            integrations = res.scalars().all()
            return {
                "items": [
                    {
                        "id": str(item.id),
                        "app_name": item.app_name,
                        "account_identifier": item.account_identifier,
                        "status": item.status,
                        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                    }
                    for item in integrations if (item.metadata_ or {}).get("gateway_verified") is True
                ]
            }
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Failed to list integrations: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Integration storage unavailable") from None


async def _resolve_tenant_and_user(request: Request, authorization: Any = None) -> tuple[str, str]:
    """Use the same verified membership, tenant status and CSRF checks as SaaS APIs."""
    auth = authorization if isinstance(authorization, str) else request.headers.get("authorization")
    principal = await require_api_tenant(request, request.headers.get("x-csrf-token"), auth)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_role_permission(principal.role, "app.integrations")
    return str(principal.tenant_id), str(principal.subject)


from server.routes.integrations_catalog import CATALOG_INTEGRATIONS


def _catalog_app(app_id: str) -> str:
    from server.services.tool_schema_registry import _normalize, list_supported_apps
    app = _normalize(app_id)
    if app not in list_supported_apps():
        raise HTTPException(status_code=404, detail="Integration not supported")
    return app


def _validate_redirect(value: str) -> None:
    from urllib.parse import urlsplit
    settings = get_settings()
    candidate = urlsplit(value)
    configured = urlsplit(settings.voxly_frontend_url)
    local = settings.app_environment not in {"production", "staging"} and candidate.hostname in {"localhost", "127.0.0.1"}
    if candidate.scheme not in {"http", "https"} or candidate.username or candidate.password or (
        not local and (candidate.scheme, candidate.netloc) != (configured.scheme, configured.netloc)
    ):
        raise HTTPException(status_code=400, detail="Invalid connection return URL")



@router.get("/api/integrations/catalog")
async def get_integrations_catalog(
    request: Request,
    q: str | None = Query(None),
    category: str | None = Query(None),
    timing: str | None = Query(None),
) -> dict[str, Any]:
    """Search and filter available voice app integrations with live OAuth status."""
    await _resolve_tenant_and_user(request)
    try:
        configured_providers = await nango_service.get_configured_providers()
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Failed to query configured providers: %s", exc)
        configured_providers = set()

    items = CATALOG_INTEGRATIONS
    if q and isinstance(q, str):
        query_lower = q.lower().strip()
        items = [
            item
            for item in items
            if query_lower in item["name"].lower()
            or query_lower in item["description"].lower()
            or query_lower in item["category"].lower()
            or any(query_lower in action.lower() for action in item.get("actions", []))
        ]
    if category and isinstance(category, str) and category.lower() != "all":
        items = [item for item in items if item["category"].lower() == category.lower()]
    if timing and isinstance(timing, str) and timing.lower() != "all":
        items = [item for item in items if item["timing"].lower() == timing.lower()]

    annotated = []
    for item in items:
        p_key = nango_service.get_provider_key(item.get("id", "")).lower()
        is_ready = (
            p_key in configured_providers
            or f"{p_key}-api-key" in configured_providers
            or f"{p_key}-v2" in configured_providers
            or f"{p_key}-business" in configured_providers
            or f"{p_key}-bot" in configured_providers
        )
        annotated.append({
            **item,
            "oauth_ready": is_ready,
        })

    return {"items": annotated, "total": len(annotated)}



@router.post("/api/integrations/{app_id}/activate")
async def activate_integration(
    app_id: str,
    body: ActivateBody,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Activate integration following Nango Connect UI authorization."""
    tenant_id, user_id = await _resolve_tenant_and_user(request, authorization)
    resolved_app = _catalog_app(app_id)
    conn_id = body.connection_id

    # Verify or reconcile with Nango
    if not await nango_service.verify_or_sync_connection(tenant_id, resolved_app, conn_id):
        raise HTTPException(status_code=403, detail="Connection could not be verified for this workspace")

    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    if session_factory:
        try:
            async with session_factory() as session:
                chk = await session.execute(
                    select(TenantIntegration).where(
                        TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                        or_(
                            func.upper(TenantIntegration.app_name) == resolved_app,
                            func.lower(TenantIntegration.app_name) == resolved_app.lower(),
                        ),
                    )
                )
                existing = chk.scalar_one_or_none()
                if existing:
                    existing.app_name = resolved_app
                    existing.status = "ACTIVE"
                    existing.metadata_ = {"gateway_verified": True}
                    existing.connection_id = conn_id
                    if body.account_identifier:
                        existing.account_identifier = body.account_identifier
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    new_integ = TenantIntegration(
                        tenant_id=_safe_tenant_uuid(tenant_id),
                        app_name=resolved_app,
                        connection_id=conn_id,
                        account_identifier=body.account_identifier or f"workspace-{resolved_app.lower()}",
                        status="ACTIVE",
                        metadata_={"gateway_verified": True},
                    )
                    session.add(new_integ)
                await session.commit()
                invalidate_tenant_tools(str(tenant_id))
        except Exception as exc:
            logger.error("[INTEGRATIONS] Failed to activate integration: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Failed to activate integration")

    return {
        "status": "ACTIVE",
        "app_name": resolved_app,
        "account_identifier": body.account_identifier or f"workspace-{resolved_app.lower()}",
    }


@router.post("/api/integrations/nango-webhook")
async def nango_webhook(request: Request) -> dict[str, Any]:
    """Authenticate the raw payload and reconcile an exact live connection."""
    secret = get_settings().nango_webhook_signing_key
    if not secret:
        raise HTTPException(status_code=503, detail="Integration webhook verification not configured")
    signature = request.headers.get("x-nango-hmac-sha256") or ""
    if not signature:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(status_code=413, detail="Webhook too large")
    expected = hmac.new(secret.encode(), bytes(raw), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from None
    event_type = str(body.get("type") or "").lower()
    operation = str(body.get("operation") or "").lower()
    if event_type != "auth" or operation not in {"creation", "override", "deletion"}:
        return {"status": "ignored"}
    tags = body.get("tags") or {}
    end_user = body.get("endUser") or {}
    if not isinstance(tags, dict) or not isinstance(end_user, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook ownership")
    owner = tags.get("end_user_id") or end_user.get("endUserId")
    organization = tags.get("organization_id") or end_user.get("organizationId")
    try:
        tenant_id = str(uuid.UUID(str(owner)))
    except (ValueError, TypeError):
        return {"status": "ignored"}
    if organization and str(organization) != tenant_id:
        raise HTTPException(status_code=400, detail="Invalid webhook ownership")
    connection_id = body.get("connectionId")
    provider_key = body.get("providerConfigKey")
    if not isinstance(connection_id, str) or not connection_id or not isinstance(provider_key, str):
        raise HTTPException(status_code=400, detail="Missing connection metadata")
    app_name = _catalog_app(nango_service.get_app_name_from_provider(provider_key))
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    success = body.get("success") is True and operation != "deletion"
    if success and not await nango_service.verify_or_sync_connection(tenant_id, app_name, connection_id):
        raise HTTPException(status_code=503, detail="Connection verification pending")
    try:
        async with factory() as session:
            tenant = await session.get(Tenant, uuid.UUID(tenant_id))
            if tenant is None or tenant.status != "active":
                return {"status": "ignored"}
            result = await session.execute(select(TenantIntegration).where(
                TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                TenantIntegration.app_name == app_name,
            ).with_for_update())
            record = result.scalar_one_or_none()
            if success:
                if record is not None and (record.connection_id != connection_id or record.status in {"DISCONNECTED", "DISCONNECTING"}):
                    return {"status": "ignored"}
                if record is None:
                    record = TenantIntegration(tenant_id=uuid.UUID(tenant_id), app_name=app_name, connection_id=connection_id)
                    session.add(record)
                record.connection_id = connection_id
                record.status = "ACTIVE"
                record.metadata_ = {"gateway_verified": True}
            elif record is not None and record.connection_id == connection_id:
                record.status = "DISCONNECTED" if operation == "deletion" else "ERROR"
            await session.commit()
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Webhook persistence failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Connection update unavailable") from None
    invalidate_tenant_tools(tenant_id)
    return {"status": "ok"}

@router.post("/api/integrations/{app_id}/connect")
async def connect_integration(
    app_id: str, body: ConnectBody, request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Open the gateway's secure form for OAuth and provider-specific API keys."""
    tenant_id, user_id = await _resolve_tenant_and_user(request, authorization)
    resolved_app = _catalog_app(app_id)
    if get_session_factory() is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    if body.api_key:
        raise HTTPException(status_code=422, detail="Enter credentials in the secure connection form")
    _validate_redirect(body.base_redirect_uri)
    from server.utils.rate_limiter import raise_rate_limited
    allowed, retry = _connect_limiter.allow(tenant_id)
    if not allowed:
        raise_rate_limited(retry)
    try:
        result = await nango_service.initiate_connection(
            tenant_id=tenant_id, user_id=user_id, app_name=resolved_app,
            base_redirect_uri=body.base_redirect_uri,
        )
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Connection form unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Secure connection form unavailable") from None
    if not result or result.get("status") != "INITIATED" or not result.get("session_token"):
        raise HTTPException(status_code=503, detail="This connection is not configured. Contact your administrator.")
    return result

@router.get("/api/integrations/sandbox-consent")
async def sandbox_consent(state: str = Query(...), app_name: str | None = Query(None)) -> HTMLResponse:
    """A simulated consent must never authorize real tenant tools."""
    raise HTTPException(status_code=410, detail="Use the secure connection form to authorize this integration")

@router.get("/api/integrations/callback")
async def oauth_callback(
    state: str = Query(...), code: str | None = Query(None), app_name: str | None = Query(None),
) -> HTMLResponse:
    """Legacy return URL: state alone is never proof of provider authorization."""
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        result = await session.execute(select(OAuthState).where(OAuthState.state == state).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=400, detail="Invalid or expired connection state")
        expiry = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
        if expiry <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Connection state expired")
        tenant_id = str(record.tenant_id)
        resolved_app = _catalog_app(record.app_name)
        try:
            connections = await nango_service.get_tenant_connections(tenant_id)
        except Exception:
            raise HTTPException(status_code=503, detail="Connection verification unavailable") from None
        matches = [c for c in connections if c.get("provider_config_key") == nango_service.get_provider_key(resolved_app)
                   and nango_service.connection_belongs_to_tenant(c, tenant_id)]
        if len(matches) != 1 or not matches[0].get("connection_id"):
            raise HTTPException(status_code=409, detail="Complete authorization in the secure connection form")
        result = await session.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == record.tenant_id, TenantIntegration.app_name == resolved_app,
        ))
        integration = result.scalar_one_or_none()
        if integration is None:
            integration = TenantIntegration(tenant_id=record.tenant_id, app_name=resolved_app, connection_id=matches[0]["connection_id"])
            session.add(integration)
        integration.status = "ACTIVE"
        integration.connection_id = matches[0]["connection_id"]
        integration.metadata_ = {"gateway_verified": True}
        await session.execute(delete(OAuthState).where(OAuthState.state == state, OAuthState.tenant_id == record.tenant_id))
        await session.commit()
    invalidate_tenant_tools(tenant_id)
    return HTMLResponse("<!doctype html><title>Connected</title><p>Connection verified. You can close this window and refresh Integrations.</p>")

@router.delete("/api/integrations/{app_id}")
async def disconnect_integration(
    app_id: str,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Disconnect an authorized integration."""
    tenant_id, _ = await _resolve_tenant_and_user(request, authorization)
    clean_name = app_id.replace("_", "").replace("-", "").upper()
    raw_upper = app_id.upper()
    raw_lower = app_id.lower()

    conditions = [
        func.upper(TenantIntegration.app_name) == raw_upper,
        func.lower(TenantIntegration.app_name) == raw_lower,
        func.replace(func.replace(func.upper(TenantIntegration.app_name), "_", ""), "-", "") == clean_name,
    ]
    try:
        as_uuid = uuid.UUID(app_id)
        conditions.append(TenantIntegration.id == as_uuid)
    except ValueError:
        pass

    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    try:
        async with session_factory() as session:
            records = (await session.execute(select(TenantIntegration).where(
                TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id), or_(*conditions),
            ).with_for_update())).scalars().all()
            targets = [(record.id, record.app_name, record.connection_id) for record in records]
            # Disable dispatch before any network request, including on gateway outages.
            for record in records:
                record.status = "DISCONNECTING"
            await session.commit()
        invalidate_tenant_tools(str(tenant_id))
        if targets:
            live = await nango_service.get_tenant_connections(tenant_id)
            for _, app, connection_id in targets:
                owned = any(c.get("connection_id") == connection_id and
                            c.get("provider_config_key") == nango_service.get_provider_key(app) and
                            nango_service.connection_belongs_to_tenant(c, tenant_id) for c in live)
                if owned and not await nango_service.delete_connection(connection_id=connection_id, app_name=app):
                    raise RuntimeError("Revocation not confirmed")
            async with session_factory() as session:
                for record_id, _, connection_id in targets:
                    await session.execute(update(TenantIntegration).where(
                        TenantIntegration.id == record_id,
                        TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                        TenantIntegration.connection_id == connection_id,
                        TenantIntegration.status == "DISCONNECTING",
                    ).values(status="DISCONNECTED"))
                await session.commit()
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Disconnect incomplete: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Actions disabled. Could not confirm revocation; please retry.") from None
    return {"status": "disconnected", "app_name": app_id.upper()}
