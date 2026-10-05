"""API routes for Composio multi-tenant integrations and OAuth flows."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from server.auth.jwt_tokens import decode_access_token
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.integration_models import OAuthState, TenantIntegration
from server.services.nango_service import nango_service
from server.services.tenant_tool_cache import invalidate as invalidate_tenant_tools
from server.utils.logger import logger

router = APIRouter(tags=["integrations"])


class ConnectBody(BaseModel):
    base_redirect_uri: str = Field(..., max_length=1024)
    account_identifier: str | None = None
    api_key: str | None = None


class ActivateBody(BaseModel):
    connection_id: str | None = None
    session_token: str | None = None
    account_identifier: str | None = None


@router.get("/api/integrations")
async def list_integrations(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """List connected tenant integrations, automatically reconciled with Nango vault."""
    tenant_id, _ = await _resolve_tenant_and_user(request, authorization)
    session_factory = get_session_factory()
    if not session_factory:
        return {"items": []}

    try:
        # Reconcile with live Nango connections if configured
        if nango_service.is_configured():
            try:
                live_conns = await nango_service.get_tenant_connections(tenant_id)
                if live_conns:
                    async with session_factory() as session:
                        for c in live_conns:
                            p_key = c.get("provider_config_key") or c.get("provider") or ""
                            c_id = c.get("connection_id") or str(c.get("id") or "")
                            app_name = nango_service.get_app_name_from_provider(p_key)
                            chk = await session.execute(
                                select(TenantIntegration).where(
                                    TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                                    or_(
                                        func.upper(TenantIntegration.app_name) == app_name.upper(),
                                        func.lower(TenantIntegration.app_name) == app_name.lower(),
                                    ),
                                )
                            )
                            existing = chk.scalar_one_or_none()
                            if existing:
                                existing.status = "ACTIVE"
                                existing.composio_connection_id = c_id
                            else:
                                session.add(
                                    TenantIntegration(
                                        tenant_id=uuid.UUID(tenant_id),
                                        app_name=app_name.upper(),
                                        composio_connection_id=c_id,
                                        account_identifier=f"workspace-{app_name.lower()}",
                                        status="ACTIVE",
                                    )
                                )
                        await session.commit()
                        invalidate_tenant_tools(str(tenant_id))
            except Exception as e:
                logger.debug("[INTEGRATIONS] Reconciliation with Nango skipped: %s", e)

        async with session_factory() as session:
            stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == uuid.UUID(tenant_id),
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
                    for item in integrations
                ]
            }
    except Exception as exc:
        logger.warning("[INTEGRATIONS] Failed to list integrations: %s", exc)
        return {"items": []}


async def _resolve_tenant_and_user(request: Request, authorization: Any = None) -> tuple[str, str]:
    """Resolve tenant_id and user_id from auth tokens, request headers, or database."""
    auth_str = authorization if isinstance(authorization, str) else None
    if not auth_str:
        auth_header = request.headers.get("authorization")
        if auth_header and isinstance(auth_header, str):
            auth_str = auth_header

    if auth_str and auth_str.lower().startswith("bearer "):
        token = auth_str.split(" ", 1)[1].strip()
        claims = decode_access_token(token)
        if claims and getattr(claims, "tenant_id", None):
            return str(claims.tenant_id), str(getattr(claims, "user_id", None) or uuid.uuid4())

    tenant_header = request.headers.get("x-tenant-id")
    user_header = request.headers.get("x-user-id")
    if tenant_header:
        return tenant_header, user_header or str(uuid.uuid4())

    session_factory = get_session_factory()
    if session_factory:
        try:
            async with session_factory() as session:
                res = await session.execute(select(Tenant).limit(1))
                first_tenant = res.scalar_one_or_none()
                if first_tenant:
                    return str(first_tenant.tenant_id), str(uuid.uuid4())
        except Exception:
            pass

    # Fallback deterministic tenant for standalone local tests
    return "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"


from server.routes.integrations_catalog import CATALOG_INTEGRATIONS


@router.get("/api/integrations/catalog")
async def get_integrations_catalog(
    q: str | None = Query(None),
    category: str | None = Query(None),
    timing: str | None = Query(None),
) -> dict[str, Any]:
    """Search and filter available voice app integrations."""
    items = CATALOG_INTEGRATIONS
    if q:
        query_lower = q.lower().strip()
        items = [
            item
            for item in items
            if query_lower in item["name"].lower()
            or query_lower in item["description"].lower()
            or query_lower in item["category"].lower()
            or any(query_lower in action.lower() for action in item.get("actions", []))
        ]
    if category and category.lower() != "all":
        items = [item for item in items if item["category"].lower() == category.lower()]
    if timing and timing.lower() != "all":
        items = [item for item in items if item["timing"].lower() == timing.lower()]

    return {"items": items, "total": len(items)}


@router.post("/api/integrations/{app_id}/activate")
async def activate_integration(
    app_id: str,
    body: ActivateBody,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Activate integration following Nango Connect UI authorization."""
    tenant_id, user_id = await _resolve_tenant_and_user(request, authorization)
    resolved_app = app_id.upper()
    conn_id = body.connection_id or f"nango_{uuid.uuid4().hex[:12]}"

    # Verify or reconcile with Nango
    await nango_service.verify_or_sync_connection(tenant_id, resolved_app, conn_id)

    session_factory = get_session_factory()
    if session_factory:
        try:
            async with session_factory() as session:
                chk = await session.execute(
                    select(TenantIntegration).where(
                        TenantIntegration.tenant_id == uuid.UUID(tenant_id),
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
                    existing.composio_connection_id = conn_id
                    if body.account_identifier:
                        existing.account_identifier = body.account_identifier
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    new_integ = TenantIntegration(
                        tenant_id=uuid.UUID(tenant_id),
                        app_name=resolved_app,
                        composio_connection_id=conn_id,
                        account_identifier=body.account_identifier or f"workspace-{resolved_app.lower()}",
                        status="ACTIVE",
                    )
                    session.add(new_integ)
                await session.commit()
        except Exception as exc:
            logger.error("[INTEGRATIONS] Failed to activate integration %s: %s", app_id, exc)
            raise HTTPException(status_code=500, detail="Failed to activate integration")

    return {
        "status": "ACTIVE",
        "app_name": resolved_app,
        "connection_id": conn_id,
        "account_identifier": body.account_identifier or f"workspace-{resolved_app.lower()}",
    }


@router.post("/api/integrations/nango-webhook")
async def nango_webhook(request: Request) -> dict[str, Any]:
    """Handle incoming Nango webhooks for real-time connection state updates."""
    try:
        body = await request.json()
        event_type = str(body.get("operation") or body.get("event") or body.get("type") or "").lower()
        connection_id = body.get("connectionId") or body.get("connection_id")
        provider_key = body.get("providerConfigKey") or body.get("provider_config_key")
        end_user_id = body.get("endUserId") or body.get("end_user_id")

        if not end_user_id and isinstance(body.get("end_user"), dict):
            end_user_id = body["end_user"].get("id")
        if not end_user_id and isinstance(body.get("endUser"), dict):
            end_user_id = body["endUser"].get("id")
        if not connection_id and isinstance(body.get("connection"), dict):
            connection_id = body["connection"].get("id") or body["connection"].get("connection_id")
        if not provider_key and isinstance(body.get("connection"), dict):
            provider_key = body["connection"].get("provider_config_key") or body["connection"].get("provider")

        if not end_user_id or not provider_key:
            return {"status": "ignored", "reason": "missing_required_fields"}

        try:
            tenant_uuid = uuid.UUID(str(end_user_id))
        except ValueError:
            raw_clean = str(end_user_id).replace("tenant_", "").replace("user_", "")
            try:
                tenant_uuid = uuid.UUID(raw_clean)
            except ValueError:
                logger.warning("[NANGO] Webhook received invalid tenant UUID: %s", end_user_id)
                return {"status": "ignored", "reason": "invalid_tenant_uuid"}

        app_name = nango_service.get_app_name_from_provider(provider_key)
        session_factory = get_session_factory()
        if session_factory:
            async with session_factory() as session:
                chk = await session.execute(
                    select(TenantIntegration).where(
                        TenantIntegration.tenant_id == tenant_uuid,
                        func.upper(TenantIntegration.app_name) == app_name.upper(),
                    )
                )
                existing = chk.scalar_one_or_none()
                if event_type in ("deletion", "connection:deleted"):
                    if existing:
                        existing.status = "DISCONNECTED"
                        existing.updated_at = datetime.now(timezone.utc)
                        await session.commit()
                else:
                    if existing:
                        existing.status = "ACTIVE"
                        if connection_id:
                            existing.composio_connection_id = str(connection_id)
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        session.add(
                            TenantIntegration(
                                tenant_id=tenant_uuid,
                                app_name=app_name.upper(),
                                composio_connection_id=str(connection_id or f"nango_{uuid.uuid4().hex[:12]}"),
                                account_identifier=f"workspace-{app_name.lower()}",
                                status="ACTIVE",
                            )
                        )
                    await session.commit()

        # Invalidate in-memory tenant tool cache so live calls pick up changes immediately
        invalidate_tenant_tools(str(tenant_uuid))
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("[NANGO] Webhook processing note: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.post("/api/integrations/{app_id}/connect")
async def connect_integration(
    app_id: str,
    body: ConnectBody,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Initiate OAuth flow with cryptographic state token or connect directly via API Key."""
    tenant_id, user_id = await _resolve_tenant_and_user(request, authorization)
    resolved_app = app_id.upper()

    # 1. Direct API Key Connection
    if body.api_key and body.api_key.strip():
        conn_id = f"key_{secrets.token_hex(6)}"
        session_factory = get_session_factory()
        if session_factory:
            try:
                async with session_factory() as session:
                    chk = await session.execute(
                        select(TenantIntegration).where(
                            TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                            or_(
                                func.upper(TenantIntegration.app_name) == resolved_app,
                                func.lower(TenantIntegration.app_name) == resolved_app.lower(),
                            ),
                        )
                    )
                    existing = chk.scalar_one_or_none()
                    if existing:
                        existing.status = "ACTIVE"
                        existing.composio_connection_id = conn_id
                        if body.account_identifier:
                            existing.account_identifier = body.account_identifier
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        session.add(
                            TenantIntegration(
                                tenant_id=uuid.UUID(tenant_id),
                                app_name=resolved_app,
                                composio_connection_id=conn_id,
                                account_identifier=body.account_identifier or f"workspace-{resolved_app.lower()}",
                                status="ACTIVE",
                            )
                        )
                    await session.commit()
                    invalidate_tenant_tools(str(tenant_id))
            except Exception as exc:
                logger.warning("[INTEGRATIONS] Failed to record API key connection: %s", exc)

        return {
            "status": "ACTIVE",
            "connection_id": conn_id,
            "app_name": resolved_app,
            "account_identifier": body.account_identifier or f"workspace-{resolved_app.lower()}",
        }

    # 2. OAuth Flow via Nango
    res = await nango_service.initiate_connection(
        tenant_id=tenant_id,
        user_id=user_id,
        app_name=app_id,
        base_redirect_uri=body.base_redirect_uri,
    )
    if not res:
        return {
            "error": "nango_initiation_failed",
            "message": "Failed to initiate OAuth session. Please check your Nango configuration.",
            "status": "ERROR",
        }
    return res


@router.get("/api/integrations/sandbox-consent")
async def sandbox_consent(
    state: str = Query(...),
    app_name: str | None = Query(None),
) -> HTMLResponse:
    """Developer Sandbox OAuth Consent Screen.
    
    Provides an interactive consent experience in development and sandbox modes
    so tenants can review permissions and explicitly authorize or decline access,
    mirroring the exact UX of production third-party OAuth providers.
    """
    resolved_app = (app_name or "GOOGLECALENDAR").upper()
    app_display_names = {
        "GOOGLECALENDAR": ("Google Calendar", "Scheduling & Appointments"),
        "SLACK": ("Slack", "Team Notifications & Messaging"),
        "HUBSPOT": ("HubSpot CRM", "Lead Management & Contact Sync"),
        "GMAIL": ("Gmail", "Email Dispatch & Receipts"),
        "GITHUB": ("GitHub", "Issue Tracking & Development"),
        "NOTION": ("Notion", "Workspace Notes & CRM"),
        "SALESFORCE": ("Salesforce", "Enterprise CRM & Pipeline"),
        "ASANA": ("Asana", "Project & Task Management"),
        "ZENDESK": ("Zendesk", "Customer Support & Ticketing"),
        "AIRTABLE": ("Airtable", "Relational Database & Records"),
    }
    app_title, app_cat = app_display_names.get(resolved_app, (resolved_app.title(), "Voice AI Integration"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Authorize {app_title} — Voxly AI Sandbox</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #090814;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .modal {{
            background: #110e24;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 24px;
            padding: 32px 28px;
            max-width: 440px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            position: relative;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(245, 158, 11, 0.15);
            border: 1px solid rgba(245, 158, 11, 0.35);
            color: #fbbf24;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 20px;
        }}
        .header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }}
        .icon-box {{
            width: 52px;
            height: 52px;
            border-radius: 16px;
            background: linear-gradient(135deg, #6344E7, #8369F5);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: 800;
            color: white;
            box-shadow: 0 8px 16px rgba(99, 68, 231, 0.3);
            flex-shrink: 0;
        }}
        h1 {{
            font-size: 19px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.3;
        }}
        .category {{
            font-size: 12px;
            color: #94a3b8;
            margin-top: 2px;
        }}
        .info-card {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .info-title {{
            font-size: 12px;
            font-weight: 700;
            color: #cbd5e1;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 12px;
        }}
        .scope-item {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.45;
            margin-bottom: 10px;
        }}
        .scope-item:last-child {{ margin-bottom: 0; }}
        .check {{
            color: #10b981;
            font-weight: bold;
            font-size: 14px;
            flex-shrink: 0;
            margin-top: 1px;
        }}
        .dev-notice {{
            font-size: 11px;
            color: #64748b;
            line-height: 1.5;
            margin-bottom: 24px;
            background: rgba(0, 0, 0, 0.25);
            padding: 12px;
            border-radius: 12px;
            border-left: 3px solid #6344E7;
        }}
        .actions {{
            display: flex;
            gap: 12px;
        }}
        .btn {{
            flex: 1;
            padding: 12px 18px;
            border-radius: 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            border: none;
            transition: all 0.2s ease;
            text-align: center;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #6344E7 0%, #7d5ef7 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(99, 68, 231, 0.4);
        }}
        .btn-primary:hover {{
            background: linear-gradient(135deg, #5333d6 0%, #6d4be6 100%);
            transform: translateY(-1px);
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.08);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }}
        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.14);
            color: white;
        }}
    </style>
</head>
<body>
    <div class="modal">
        <div class="badge">
            <span>⚡ Sandbox Developer Mode</span>
        </div>
        <div class="header">
            <div class="icon-box">{resolved_app[0]}</div>
            <div>
                <h1>Connect {app_title}</h1>
                <div class="category">{app_cat} • Multi-Tenant Vault</div>
            </div>
        </div>

        <div class="info-card">
            <div class="info-title">Permissions Requested by Voice Agent</div>
            <div class="scope-item">
                <span class="check">✓</span>
                <span>Query real-time availability and retrieve records for {app_title}.</span>
            </div>
            <div class="scope-item">
                <span class="check">✓</span>
                <span>Execute caller-requested actions during live voice phone calls (&lt;1.5s SLA).</span>
            </div>
            <div class="scope-item">
                <span class="check">✓</span>
                <span>Isolate credentials into encrypted tenant vault with cryptographic state verification.</span>
            </div>
        </div>

        <div class="dev-notice">
            <strong>Developer Note:</strong> You are testing in local development sandbox mode. Authorizing will simulate a verified OAuth connection. In production with a valid provider API key, tenants will be redirected to the provider's official sign-in page.
        </div>

        <div class="actions">
            <button type="button" class="btn btn-secondary" onclick="handleCancel()">Decline</button>
            <a href="/api/integrations/callback?state={state}&app_name={resolved_app}&code=sandbox_consent_ok" class="btn btn-primary">
                Authorize Access
            </a>
        </div>
    </div>

    <script>
    function handleCancel() {{
        try {{
            if (window.opener) {{
                window.opener.postMessage({{ type: 'INTEGRATION_CANCELLED', app: '{resolved_app}' }}, '*');
            }}
        }} catch (e) {{}}
        window.close();
    }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@router.get("/api/integrations/callback")
async def oauth_callback(
    state: str = Query(...),
    code: str | None = Query(None),
    app_name: str | None = Query(None),
) -> Any:
    """Validate cryptographic state parameter and activate integration."""
    session_factory = get_session_factory()
    tenant_id: str | None = None
    resolved_app: str = (app_name or "GOOGLECALENDAR").upper()

    if session_factory:
        try:
            async with session_factory() as session:
                stmt = select(OAuthState).where(OAuthState.state == state)
                res = await session.execute(stmt)
                oauth_record = res.scalar_one_or_none()

                if not oauth_record:
                    raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

                if oauth_record.expires_at < datetime.now(timezone.utc):
                    await session.execute(delete(OAuthState).where(OAuthState.state == state))
                    await session.commit()
                    raise HTTPException(status_code=400, detail="OAuth state expired")

                tenant_id = str(oauth_record.tenant_id)
                resolved_app = oauth_record.app_name

                # Invalidate single-use state token (CSRF defense)
                await session.execute(delete(OAuthState).where(OAuthState.state == state))

                # Activate integration in tenant_integrations
                chk = await session.execute(
                    select(TenantIntegration).where(
                        TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                        or_(
                            func.upper(TenantIntegration.app_name) == resolved_app.upper(),
                            func.lower(TenantIntegration.app_name) == resolved_app.lower(),
                        ),
                    )
                )
                existing = chk.scalar_one_or_none()
                if existing:
                    existing.app_name = resolved_app.upper()
                    existing.status = "ACTIVE"
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    new_integ = TenantIntegration(
                        tenant_id=uuid.UUID(tenant_id),
                        app_name=resolved_app,
                        composio_connection_id=f"conn_{state[:16]}",
                        account_identifier=f"workspace-{resolved_app.lower()}",
                        status="ACTIVE",
                    )
                    session.add(new_integ)
                await session.commit()
                invalidate_tenant_tools(str(tenant_id))
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[INTEGRATIONS] Callback verification error: %s", exc)
            raise HTTPException(status_code=500, detail="OAuth verification failed")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Authorization Successful</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background: #090d16;
            color: #f8fafc;
        }}
        .card {{
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 16px;
            padding: 32px 28px;
            text-align: center;
            max-width: 360px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .icon {{
            width: 52px;
            height: 52px;
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            font-size: 26px;
            font-weight: bold;
        }}
        h2 {{ margin: 0 0 8px; font-size: 18px; font-weight: 600; color: #f9fafb; }}
        p {{ margin: 0 0 20px; font-size: 13px; line-height: 1.5; color: #9ca3af; }}
        button {{
            background: #3b82f6;
            color: #ffffff;
            border: none;
            padding: 8px 20px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
        }}
        button:hover {{ background: #2563eb; }}
    </style>
</head>
<body>
<div class="card">
    <div class="icon">✓</div>
    <h2>Connected Successfully</h2>
    <p>Your workspace is now connected to <strong>{resolved_app}</strong>. This window will close automatically.</p>
    <button onclick="window.close()">Close Window</button>
</div>
<script>
try {{
    if (window.opener) {{
        window.opener.postMessage({{ type: 'INTEGRATION_CONNECTED', app: '{resolved_app}' }}, '*');
        setTimeout(function() {{ window.close(); }}, 900);
    }}
}} catch (e) {{}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


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
    if session_factory:
        try:
            async with session_factory() as session:
                # Find matching record to get connection_id for Nango revocation
                rec_stmt = select(TenantIntegration).where(
                    TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                    or_(*conditions),
                )
                rec_res = await session.execute(rec_stmt)
                records = rec_res.scalars().all()
                for rec in records:
                    conn_id = rec.composio_connection_id or str(tenant_id)
                    await nango_service.delete_connection(connection_id=conn_id, app_name=rec.app_name)

                await session.execute(
                    delete(TenantIntegration).where(
                        TenantIntegration.tenant_id == uuid.UUID(tenant_id),
                        or_(*conditions),
                    )
                )
                await session.commit()
                invalidate_tenant_tools(str(tenant_id))
        except Exception as exc:
            logger.warning("[INTEGRATIONS] Disconnect failed: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to disconnect integration")
    return {"status": "disconnected", "app_name": app_id.upper()}
