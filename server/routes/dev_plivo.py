"""Dev Portal Plivo test routes — status, numbers, assignments, outbound dial."""
from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.services.dev_secrets_store import dev_secrets_store
from server.services.phone_assignments_store import phone_assignments_store
from sqlalchemy import select

router = APIRouter()


class AssignNumberBody(BaseModel):
    e164: str
    agent_id: str = Field(..., alias="agentId")

    model_config = {"populate_by_name": True}


class RegisterNumberBody(BaseModel):
    e164: str


class OutboundTestBody(BaseModel):
    to_e164: str = Field(..., alias="toE164")
    from_e164: str | None = Field(None, alias="fromE164")
    agent_id: str = Field(..., alias="agentId")
    tier: str | None = None

    model_config = {"populate_by_name": True}


def _plivo_creds() -> tuple[str, str] | None:
    auth_id = dev_secrets_store.effective_secret("plivo_auth_id") or get_settings().plivo_auth_id
    auth_token = dev_secrets_store.effective_secret("plivo_auth_token") or get_settings().plivo_auth_token
    if not auth_id or not auth_token:
        return None
    return str(auth_id), str(auth_token)


def _plivo_enabled() -> bool:
    return bool(dev_secrets_store.effective("enable_plivo", get_settings().enable_plivo))


def _answer_url() -> str | None:
    settings = get_settings()
    base = dev_secrets_store.effective("plivo_webhook_base_url", settings.plivo_webhook_base_url) or settings.plivo_public_base_url
    if not base:
        return None
    return f"{str(base).rstrip('/')}/api/plivo/answer"


@router.get("/api/dev/plivo/status")
async def dev_plivo_status(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    creds = _plivo_creds()
    configured = creds is not None
    enabled = _plivo_enabled()
    default_number = settings.plivo_number
    assignments = phone_assignments_store.snapshot()
    return {
        "ok": True,
        "enabled": enabled,
        "configured": configured,
        "webhook_base": settings.plivo_webhook_base_url or None,
        "public_base": settings.plivo_public_base_url or None,
        "answer_url": _answer_url(),
        "default_number": default_number,
        "assignments": assignments,
        "ready": enabled and configured and _answer_url() is not None,
    }


@router.get("/api/dev/plivo/numbers")
async def dev_plivo_numbers(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    db_numbers: list[dict[str, Any]] = []
    factory = get_session_factory()
    if factory is not None:
        async with factory() as db:
            result = await db.execute(select(PhoneNumber))
            for row in result.scalars().all():
                db_numbers.append(
                    {
                        "id": str(row.id),
                        "e164": row.e164,
                        "status": row.status,
                        "plivo_number_id": row.plivo_number_id,
                        "source": "database",
                    }
                )

    plivo_numbers: list[dict[str, Any]] = []
    creds = _plivo_creds()
    if creds:
        auth_id, auth_token = creds
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"https://api.plivo.com/v1/Account/{auth_id}/Number/",
                    auth=(auth_id, auth_token),
                )
                if r.is_success:
                    payload = r.json()
                    for n in payload.get("objects", []):
                        plivo_numbers.append(
                            {
                                "e164": n.get("number"),
                                "alias": n.get("alias"),
                                "plivo_number_id": n.get("id"),
                                "source": "plivo_api",
                            }
                        )
        except httpx.HTTPError:
            pass

    assignments = phone_assignments_store.snapshot()
    merged: dict[str, dict[str, Any]] = {}
    for n in db_numbers:
        merged[n["e164"]] = {**n, "assigned_agent_id": assignments.get(n["e164"])}
    for n in plivo_numbers:
        e164 = n.get("e164")
        if not e164:
            continue
        if e164 in merged:
            merged[e164].update(n)
        else:
            merged[e164] = {**n, "assigned_agent_id": assignments.get(e164)}
    return {"ok": True, "numbers": list(merged.values()), "assignments": assignments}


@router.post("/api/dev/plivo/numbers")
async def dev_register_number(body: RegisterNumberBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.config.env import get_settings as gs

    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    tenant = uuid.UUID(gs().default_tenant_id)
    nid = uuid.uuid4()
    async with factory() as db:
        db.add(PhoneNumber(id=nid, tenant_id=tenant, e164=body.e164.strip(), status="connected"))
        await db.commit()
    return {"ok": True, "id": str(nid), "e164": body.e164.strip()}


@router.put("/api/dev/plivo/numbers/assign")
async def dev_assign_number(body: AssignNumberBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    assignments = phone_assignments_store.assign(body.e164, body.agent_id)
    return {"ok": True, "e164": body.e164, "agent_id": body.agent_id, "assignments": assignments}


@router.delete("/api/dev/plivo/numbers/assign")
async def dev_unassign_number(e164: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    assignments = phone_assignments_store.unassign(e164)
    return {"ok": True, "assignments": assignments}


@router.post("/api/dev/plivo/outbound")
async def dev_outbound_test(body: OutboundTestBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    if not _plivo_enabled():
        return {"ok": False, "error": {"code": "plivo_disabled", "message": "ENABLE_PLIVO is false"}}
    creds = _plivo_creds()
    if not creds:
        return {"ok": False, "error": {"code": "not_configured", "message": "Plivo credentials missing"}}
    answer_url = _answer_url()
    if not answer_url:
        return {
            "ok": False,
            "error": {"code": "webhook_missing", "message": "Set PLIVO_WEBHOOK_BASE_URL for answer URL"},
        }

    settings = get_settings()
    from_number = (body.from_e164 or dev_secrets_store.effective("plivo_number", settings.plivo_number) or "").strip()
    if not from_number:
        return {"ok": False, "error": {"code": "from_missing", "message": "Set from number or PLIVO_NUMBER"}}

    phone_assignments_store.assign(from_number, body.agent_id)
    auth_id, auth_token = creds
    payload = {
        "from": from_number,
        "to": body.to_e164.strip(),
        "answer_url": answer_url,
        "answer_method": "POST",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"https://api.plivo.com/v1/Account/{auth_id}/Call/",
                auth=(auth_id, auth_token),
                json=payload,
            )
            data = r.json() if r.content else {}
            if not r.is_success:
                return {
                    "ok": False,
                    "error": {
                        "code": "plivo_error",
                        "message": data.get("error") or r.text or "Plivo call failed",
                    },
                }
            return {
                "ok": True,
                "request_uuid": data.get("request_uuid") or data.get("message"),
                "from": from_number,
                "to": body.to_e164,
                "agent_id": body.agent_id,
                "tier": body.tier,
            }
    except httpx.HTTPError as e:
        return {"ok": False, "error": {"code": "network_error", "message": str(e)}}
