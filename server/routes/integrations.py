"""API routes for enterprise multi-tenant integrations and OAuth flows."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
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


def _verified(metadata: dict | None) -> dict:
    """A verified connection keeps the tenant's saved setup (channel, board ...)."""
    kept = {k: v for k, v in (metadata or {}).items() if k == "settings"}
    return {**kept, "gateway_verified": True}


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
                all_conns = await nango_service.get_tenant_connections(tenant_id, include_auth_errors=True)
                failed_ids = {c.get("connection_id") for c in all_conns if c.get("connection_id") and nango_service.connection_has_auth_error(c)}
                # The list is complete (a partial page raises), so a stored connection the
                # gateway no longer has (deleted in its dashboard, or a move to another
                # gateway) can no longer authenticate: ask for a reconnect.
                listed = {c.get("connection_id") for c in all_conns if c.get("connection_id")}
                async with session_factory() as session:
                    stored = (await session.execute(select(TenantIntegration.connection_id).where(
                        TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                        TenantIntegration.status == "ACTIVE",
                    ))).scalars().all()
                failed_ids |= {cid for cid in stored if cid and cid not in listed}
                live_conns = [c for c in all_conns if not nango_service.connection_has_auth_error(c)]
                if failed_ids:
                    async with session_factory() as session:
                        failed = (await session.execute(select(TenantIntegration).where(
                            TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                            TenantIntegration.status == "ACTIVE",
                            TenantIntegration.connection_id.in_(sorted(failed_ids)),
                        ))).scalars().all()
                        for record in failed:
                            # Saved setup survives; only the credentials need renewing.
                            record.status = "ERROR"
                            record.metadata_ = {**(record.metadata_ or {}), "gateway_verified": False, "needs_reauth": True}
                        await session.commit()
                    invalidate_tenant_tools(str(tenant_id))
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
                                existing.metadata_ = _verified(existing.metadata_)
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

        from server.services.integration_policy import disabled_apps
        from server.services.tool_schema_registry import _normalize

        off = await disabled_apps(tenant_id, session_factory)
        async with session_factory() as session:
            stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
                TenantIntegration.status.in_(("ACTIVE", "ERROR")),
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
                        # Agents cannot use an ERROR connection; the console
                        # shows it as "Reconnect needed" instead of hiding it.
                        "needs_reauth": item.status == "ERROR",
                        # Still connected, but agents cannot use it until the admin turns it back on.
                        "disabled_by_admin": _normalize(item.app_name) in off,
                        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                    }
                    for item in integrations
                    if (item.status == "ACTIVE" and (item.metadata_ or {}).get("gateway_verified") is True)
                    # A broken connection to a switched-off app cannot be reconnected, so it is not shown.
                    or (item.status == "ERROR" and (item.metadata_ or {}).get("needs_reauth") is True
                        and _normalize(item.app_name) not in off)
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


async def _require_enabled(tenant_id: str, app: str) -> None:
    """The platform admin can switch an app off for every workspace or one."""
    from server.services.integration_policy import is_enabled

    if not await is_enabled(tenant_id, app, get_session_factory()):
        raise HTTPException(status_code=403, detail="This integration is turned off for your workspace. Contact your administrator.")


def _trusted_console_origins() -> set[tuple[str, str]]:
    """Every origin the console is deliberately served from, never a wildcard."""
    from urllib.parse import urlsplit
    settings = get_settings()
    configured = [settings.dialtact_frontend_url, getattr(settings, "public_app_url", None)]
    configured += [o for o in (getattr(settings, "cors_origins", "") or "").split(",") if o.strip() != "*"]
    origins = set()
    for raw in configured:
        parts = urlsplit((raw or "").strip())
        if parts.scheme in {"http", "https"} and parts.netloc:
            origins.add((parts.scheme, parts.netloc.lower()))
    return origins


def _validate_redirect(value: str) -> None:
    from urllib.parse import urlsplit
    settings = get_settings()
    candidate = urlsplit(value)
    local = settings.app_environment not in {"production", "staging"} and candidate.hostname in {"localhost", "127.0.0.1"}
    if candidate.scheme not in {"http", "https"} or candidate.username or candidate.password or (
        not local and (candidate.scheme, candidate.netloc.lower()) not in _trusted_console_origins()
    ):
        raise HTTPException(status_code=400, detail="This console address is not allowed to connect integrations. Contact your administrator.")



@router.get("/api/integrations/catalog")
async def get_integrations_catalog(
    request: Request,
    q: str | None = Query(None),
    category: str | None = Query(None),
    timing: str | None = Query(None),
) -> dict[str, Any]:
    """Search and filter available voice app integrations with live OAuth status."""
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

    from server.services.integration_settings import missing_required, spec_for, tenant_settings

    from server.services.integration_policy import disabled_apps

    tenant_id, _ = await _resolve_tenant_and_user(request)
    saved = await tenant_settings(tenant_id, get_session_factory())
    off = await disabled_apps(tenant_id, get_session_factory())
    from server.services.tool_schema_registry import _normalize

    connected: set[str] = set()
    if off:
        async with get_session_factory()() as session:
            rows = (await session.execute(select(TenantIntegration).where(
                TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id), TenantIntegration.status == "ACTIVE",
            ))).scalars().all()
        connected = {_normalize(r.app_name) for r in rows if (r.metadata_ or {}).get("gateway_verified") is True}
    annotated = []
    for item in items:
        p_key = nango_service.get_provider_key(item.get("id", "")).lower()
        # Connect sends exactly this key, so readiness must not accept look-alike variants.
        is_ready = p_key in configured_providers
        from server.services.call_integrations import SETUP_REQUIRED, supported_modes

        app_key = _catalog_app(item.get("id", ""))
        if app_key in off and app_key not in connected:
            continue  # switched off and not connected: not offered at all
        fields = spec_for(app_key)
        missing = missing_required(app_key, saved.get(app_key))
        annotated.append({
            **item,
            "oauth_ready": is_ready,
            # What a call or campaign may attach this app for.
            "call_modes": list(supported_modes(item.get("id", ""))),
            "call_setup_note": SETUP_REQUIRED.get(app_key) if missing else None,
            "setup_fields": [{k: f.get(k) for k in ("key", "label", "help", "required")} | {"has_options": bool(f.get("resource"))}
                             for f in fields],
            "setup_missing": missing,
            "admin_disabled": app_key in off,
        })

    return {"items": annotated, "total": len(annotated)}


@router.get("/api/integrations/call-options")
async def get_call_integration_options(
    request: Request,
    agent_id: str = Query(..., alias="agentId", min_length=8, max_length=64),
) -> dict[str, Any]:
    """Integrations a single call or campaign for this agent may attach.

    Only connected, verified apps that the agent has not turned off are
    selectable; everything else is returned disabled with the reason.
    """
    from server.services.call_integrations import SelectionError, available_for_agent

    tenant_id, _ = await _resolve_tenant_and_user(request)
    try:
        items = await available_for_agent(tenant_id, agent_id)
    except SelectionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from None
    return {
        "items": items,
        "defaultBehaviour": "When none are chosen, the agent uses its saved integration settings.",
    }



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
    await _require_enabled(tenant_id, resolved_app)
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
                    existing.metadata_ = _verified(existing.metadata_)
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
        await _revoke_superseded_connection(tenant_id, resolved_app, conn_id)

    return {
        "status": "ACTIVE",
        "app_name": resolved_app,
        "account_identifier": body.account_identifier or f"workspace-{resolved_app.lower()}",
    }


async def _revoke_superseded_connection(tenant_id: str, app_name: str, keep_connection_id: str) -> None:
    """Best effort: delete every other gateway connection this tenant holds for
    the app, so an abandoned or replaced grant does not linger unused."""
    try:
        live = await nango_service.get_tenant_connections(tenant_id, include_auth_errors=True)
        provider = nango_service.get_provider_key(app_name)
        for c in live:
            other = c.get("connection_id")
            if other and other != keep_connection_id and c.get("provider_config_key") == provider:
                if not await nango_service.delete_connection(connection_id=other, app_name=app_name):
                    logger.warning("[INTEGRATIONS] Superseded connection not revoked for %s", app_name)
    except Exception as exc:  # noqa: BLE001 - activation already succeeded
        logger.warning("[INTEGRATIONS] Superseded connection cleanup skipped: %s", type(exc).__name__)


@router.post("/api/integrations/nango-webhook")
async def nango_webhook(request: Request) -> dict[str, Any]:
    """Authenticate the raw payload and reconcile an exact live connection."""
    secret = get_settings().nango_webhook_signing_key
    if not secret:
        raise HTTPException(status_code=503, detail="Integration webhook verification not configured")
    # Nango keeps signing with the old key for ~5 minutes after a rotation;
    # honour the same window when the previous key is configured.
    secrets_to_try = [secret] + [k for k in (os.environ.get("NANGO_WEBHOOK_SIGNING_KEY_PREVIOUS"),) if k]
    # Only X-Nango-Hmac-Sha256 is accepted. The legacy X-Nango-Signature is a
    # plain SHA-256 that Nango documents must not be used for verification.
    signature = (request.headers.get("x-nango-hmac-sha256") or "").strip().lower()
    if not signature:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(status_code=413, detail="Webhook too large")
    if not any(hmac.compare_digest(hmac.new(key.encode(), bytes(raw), hashlib.sha256).hexdigest(), signature) for key in secrets_to_try):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from None
    event_type = str(body.get("type") or "").lower()
    operation = str(body.get("operation") or "").lower()
    if event_type != "auth" or operation not in {"creation", "override", "refresh", "deletion"}:
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
        if operation == "refresh":
            # A recovery notice we cannot confirm yet keeps the tool disabled;
            # the next console visit or webhook reconciles it.
            return {"status": "ignored"}
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
            if operation == "refresh":
                # Refresh webhooks never create a record. A failure disables the
                # tool until credentials work again; a later success (sent only
                # after a prior failure) restores the same connection.
                if record is None or record.connection_id != connection_id or record.status in {"DISCONNECTED", "DISCONNECTING"}:
                    return {"status": "ignored"}
                if success:
                    if record.status == "ERROR":
                        record.status = "ACTIVE"
                        record.metadata_ = _verified(record.metadata_)
                else:
                    record.status = "ERROR"
                    record.metadata_ = {**(record.metadata_ or {}), "gateway_verified": False, "needs_reauth": True}
            elif success:
                if record is not None and (record.connection_id != connection_id or record.status in {"DISCONNECTED", "DISCONNECTING"}):
                    return {"status": "ignored"}
                if record is None:
                    record = TenantIntegration(tenant_id=uuid.UUID(tenant_id), app_name=app_name, connection_id=connection_id)
                    session.add(record)
                record.connection_id = connection_id
                record.status = "ACTIVE"
                record.metadata_ = _verified(record.metadata_)
            elif record is not None and record.connection_id == connection_id:
                record.status = "DISCONNECTED" if operation == "deletion" else "ERROR"
                if operation != "deletion":
                    record.metadata_ = {**(record.metadata_ or {}), "gateway_verified": False, "needs_reauth": True}
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
    await _require_enabled(tenant_id, resolved_app)
    if body.api_key:
        raise HTTPException(status_code=422, detail="Enter credentials in the secure connection form")
    _validate_redirect(body.base_redirect_uri)
    from server.utils.rate_limiter import raise_rate_limited
    allowed, retry = _connect_limiter.allow(tenant_id)
    if not allowed:
        raise_rate_limited(retry)
    reconnect_id = None
    async with get_session_factory()() as session:
        existing = (await session.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
            TenantIntegration.app_name == resolved_app, TenantIntegration.status == "ERROR",
        ))).scalar_one_or_none()
        if existing is not None and (existing.metadata_ or {}).get("needs_reauth"):
            reconnect_id = existing.connection_id
    try:
        result = await nango_service.initiate_connection(
            tenant_id=tenant_id, user_id=user_id, app_name=resolved_app,
            base_redirect_uri=body.base_redirect_uri, reconnect_connection_id=reconnect_id,
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
        integration.metadata_ = _verified(integration.metadata_)
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
            live = await nango_service.get_tenant_connections(tenant_id, include_auth_errors=True)
            for _, app, connection_id in targets:
                owned = any(c.get("connection_id") == connection_id and
                            c.get("provider_config_key") == nango_service.get_provider_key(app) and
                            nango_service.connection_belongs_to_tenant({**c, "errors": None}, tenant_id) for c in live)
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


# ------------------------------------------------------------ connection setup
class SettingsBody(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


async def _active_record(session: Any, tenant_id: str, app: str) -> TenantIntegration:
    record = (await session.execute(select(TenantIntegration).where(
        TenantIntegration.tenant_id == _safe_tenant_uuid(tenant_id),
        TenantIntegration.app_name == app, TenantIntegration.status == "ACTIVE",
    ))).scalar_one_or_none()
    if record is None or not (record.metadata_ or {}).get("gateway_verified"):
        raise HTTPException(status_code=404, detail="Connect this app first")
    return record


@router.get("/api/integrations/{app_id}/settings")
async def get_integration_settings(app_id: str, request: Request) -> dict[str, Any]:
    from server.services.integration_settings import missing_required, spec_for

    tenant_id, _ = await _resolve_tenant_and_user(request)
    app = _catalog_app(app_id)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        record = await _active_record(session, tenant_id, app)
        values = dict((record.metadata_ or {}).get("settings") or {})
    return {
        "app": app,
        "fields": [{k: f.get(k) for k in ("key", "label", "help", "required")} | {"has_options": bool(f.get("resource"))}
                   for f in spec_for(app)],
        "values": values,
        "missing": missing_required(app, values),
    }


@router.put("/api/integrations/{app_id}/settings")
async def save_integration_settings(app_id: str, body: SettingsBody, request: Request) -> dict[str, Any]:
    from server.services.integration_settings import clean_settings, missing_required, spec_for

    tenant_id, _ = await _resolve_tenant_and_user(request)
    app = _catalog_app(app_id)
    await _require_enabled(tenant_id, app)
    if not spec_for(app):
        raise HTTPException(status_code=404, detail="This app has nothing to set up")
    try:
        values = clean_settings(app, body.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        record = await _active_record(session, tenant_id, app)
        record.metadata_ = {**(record.metadata_ or {}), "settings": values}
        await session.commit()
    invalidate_tenant_tools(str(tenant_id))
    return {"app": app, "values": values, "missing": missing_required(app, values)}


@router.get("/api/integrations/{app_id}/options")
async def get_integration_options(app_id: str, request: Request, field: str = Query(..., max_length=64),
                                  values: str | None = Query(None, max_length=2000)) -> dict[str, Any]:
    """Choices for a setup field, read live from the tenant's own account.

    ``values`` carries the form's other, not yet saved fields as JSON (a tab
    list needs the spreadsheet just pasted); they pass the same checks as a save.
    """
    import httpx

    from server.services.integration_settings import clean_settings, list_resources, spec_for

    tenant_id, _ = await _resolve_tenant_and_user(request)
    app = _catalog_app(app_id)
    await _require_enabled(tenant_id, app)
    spec = next((f for f in spec_for(app) if f["key"] == field and f.get("resource")), None)
    if spec is None:
        raise HTTPException(status_code=404, detail="No choices for this field")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        record = await _active_record(session, tenant_id, app)
        connection_id, saved = record.connection_id, dict((record.metadata_ or {}).get("settings") or {})
    if values:
        try:
            draft = json.loads(values)
            saved.update(clean_settings(app, draft if isinstance(draft, dict) else {}))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "Those settings are not valid.") from None
    headers = {"Authorization": f"Bearer {nango_service.secret_key}", "Connection-Id": connection_id,
               "Provider-Config-Key": nango_service.get_provider_key(app)}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            options = await list_resources(spec["resource"], client, nango_service.base_url, headers, saved)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        message = ("The connection needs to be reconnected or lacks permission to list these." if code in (401, 403, 424)
                   else "Could not load choices from the app. Enter the value instead.")
        raise HTTPException(status_code=502, detail=message) from None
    except ValueError as exc:
        if str(exc) == "spreadsheet_required":
            raise HTTPException(status_code=422, detail="Paste the spreadsheet link first, then load its tabs.") from None
        logger.warning("[INTEGRATIONS] Options unavailable for %s: %s", app, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not load choices from the app. Enter the value instead.") from None
    except Exception as exc:  # noqa: BLE001 - provider shapes vary; the field stays editable
        logger.warning("[INTEGRATIONS] Options unavailable for %s: %s", app, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not load choices from the app. Enter the value instead.") from None
    return {"field": field, "options": options[:200]}


# ------------------------------------------------------------ per-agent rules
class AgentRule(BaseModel):
    app: str = Field(..., min_length=2, max_length=40)
    enabled: bool = True
    timing: str = Field("in_call", pattern="^(in_call|post_call)$")
    actions: list[str] = Field(default_factory=list, max_length=20)


class AgentRulesBody(BaseModel):
    rules: list[AgentRule] = Field(default_factory=list, max_length=40)


async def _owned_agent(session: Any, tenant_id: str, agent_id: str) -> uuid.UUID:
    from server.db.models.entities import Agent

    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found") from None
    owned = (await session.execute(select(Agent.agent_id).where(
        Agent.agent_id == aid, Agent.tenant_id == _safe_tenant_uuid(tenant_id),
    ))).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return aid


@router.get("/api/integrations/agent-rules")
async def get_agent_rules(request: Request, agent_id: str = Query(..., alias="agentId", min_length=8, max_length=64)) -> dict[str, Any]:
    """Each connected app with this agent's rule (or the catalog default)."""
    from server.db.models.integration_models import AgentIntegration
    from server.services.call_integrations import CALL_INTEGRATION_PROFILES, POST_CALL_DEFAULT_ACTION, SETUP_REQUIRED, display_name
    from server.services.integration_settings import is_configured, tenant_settings
    from server.services.tenant_tool_cache import get_active_app_names
    from server.services.tool_schema_registry import (HIDDEN_FROM_MODEL, MAX_MODEL_TOOLS, _SCHEMAS, _normalize,
                                                      default_action_timing)

    tenant_id, _ = await _resolve_tenant_and_user(request)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        aid = await _owned_agent(session, tenant_id, agent_id)
        rules = (await session.execute(select(AgentIntegration).where(
            AgentIntegration.tenant_id == _safe_tenant_uuid(tenant_id), AgentIntegration.agent_id == aid,
        ))).scalars().all()
        compiled_text = ""
        try:
            from server.db.models.brain_models import CompiledBrainSnapshot
            from server.db.models.entities import Agent

            version = (await session.execute(select(Agent.active_compiled_brain_version).where(Agent.agent_id == aid))).scalar_one_or_none()
            snapshot = await session.get(CompiledBrainSnapshot, version) if version else None
            compiled_text = (snapshot.compiled_text if snapshot else "") or ""
        except Exception:  # noqa: BLE001 - without a script the note is simply omitted
            compiled_text = ""
    from server.brain.capabilities import script_uses_scheduling

    never_books = script_uses_scheduling(compiled_text) is False if compiled_text else False
    connected = [_normalize(a) for a in await get_active_app_names(tenant_id, factory)]
    settings = await tenant_settings(tenant_id, factory)
    by_app = {_normalize(r.app_name): r for r in rules}
    from server.brain.capabilities import SCHEDULING_APPS

    # Matches get_tools_for_agent: a calendar the tenant turned on replaces the
    # default one; otherwise only the first calendar without a rule is offered.
    chosen_calendar = any(_normalize(r.app_name) in SCHEDULING_APPS and r.enabled and r.timing_mode == "in_call" for r in rules)
    default_calendar = None if chosen_calendar else next((_normalize(r["id"]) for r in CATALOG_INTEGRATIONS if _normalize(r["id"]) in SCHEDULING_APPS
                             and _normalize(r["id"]) in connected and _normalize(r["id"]) not in by_app
                             and is_configured(_normalize(r["id"]), settings.get(_normalize(r["id"])))), None)
    items = []
    for row in CATALOG_INTEGRATIONS:
        app = _normalize(row["id"])
        if app not in connected:
            continue
        profile = CALL_INTEGRATION_PROFILES.get(app) or {}
        rule = by_app.get(app)
        default_timing = default_action_timing(app)
        items.append({
            "app": app, "name": display_name(app), "iconName": row.get("iconName"),
            "configured": is_configured(app, settings.get(app)),
            "setupNote": None if is_configured(app, settings.get(app)) else SETUP_REQUIRED.get(app),
            # Agent settings cannot add a calendar to a script that never books;
            # picking it when launching a call still can.
            "scriptNote": ("This employee's script never books appointments, so calendar actions are not offered on "
                           "its calls. Add booking to the script, or pick this app when starting a call.")
            if never_books and app in SCHEDULING_APPS else None,
            "modes": [{"mode": m, "description": profile[m]} for m in ("in_call", "post_call") if m in profile],
            "actions": [{"name": t["name"], "description": t["description"]} for t in _SCHEMAS.get(app, [])
                        if t["name"] not in HIDDEN_FROM_MODEL],
            "postCallAction": POST_CALL_DEFAULT_ACTION.get(app),
            "rule": {"enabled": rule.enabled, "timing": rule.timing_mode, "actions": [a.upper() for a in rule.action_whitelist or []]}
            if rule else None,
            # What happens with no rule: in-call apps are on during calls, after-call apps never run on their own.
            "default": {"enabled": default_timing == "in_call" and "in_call" in profile
                        and (app not in SCHEDULING_APPS or app == default_calendar), "timing": default_timing},
        })
    return {"items": items, "toolLimit": MAX_MODEL_TOOLS - 3}


@router.put("/api/integrations/agent-rules")
async def save_agent_rules(body: AgentRulesBody, request: Request,
                           agent_id: str = Query(..., alias="agentId", min_length=8, max_length=64)) -> dict[str, Any]:
    from server.db.models.integration_models import AgentIntegration
    from server.services.call_integrations import supported_modes
    from server.services.tool_schema_registry import tool_definition

    tenant_id, _ = await _resolve_tenant_and_user(request)
    cleaned: dict[str, AgentRule] = {}
    for rule in body.rules:
        app = _catalog_app(rule.app)
        if rule.enabled and rule.timing not in supported_modes(app):
            raise HTTPException(status_code=422, detail=f"{app} cannot run at that time.")
        actions = sorted({a.upper() for a in rule.actions})
        if any((tool_definition(a) or ("",))[0] != app for a in actions):
            raise HTTPException(status_code=422, detail="An action does not belong to its app.")
        cleaned[app] = AgentRule(app=app, enabled=rule.enabled, timing=rule.timing, actions=actions)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Integration storage unavailable")
    async with factory() as session:
        aid = await _owned_agent(session, tenant_id, agent_id)
        await session.execute(delete(AgentIntegration).where(
            AgentIntegration.tenant_id == _safe_tenant_uuid(tenant_id), AgentIntegration.agent_id == aid,
        ))
        for app, rule in cleaned.items():
            session.add(AgentIntegration(tenant_id=_safe_tenant_uuid(tenant_id), agent_id=aid, app_name=app,
                                         enabled=rule.enabled, timing_mode=rule.timing, action_whitelist=rule.actions))
        await session.commit()
    invalidate_tenant_tools(str(tenant_id))
    return {"status": "saved", "rules": [r.model_dump() for r in cleaned.values()]}
