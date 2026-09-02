"""Dev Portal Exotel test routes — handshake, numbers, outbound connect."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.services.exotel_call_registry import exotel_call_registry
from server.services.exotel_client import (
    ExotelApiError,
    ExotelClient,
    ExotelConfigError,
    build_stream_ws_url,
    cached_handshake,
    exotel_enabled,
    public_webhook_urls,
    webhook_base_url,
)
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
    caller_id: str | None = Field(None, alias="callerId")
    agent_id: str = Field(..., alias="agentId")
    tier: str | None = None
    mode: str = "voice_ai"  # voice_ai | bridge

    model_config = {"populate_by_name": True}


async def _status_payload() -> dict[str, Any]:
    settings = get_settings()
    urls = public_webhook_urls()
    enabled = exotel_enabled()
    configured = False
    handshake_ok = False
    handshake_error: str | None = None
    balance: str | None = None
    account_sid = None

    try:
        client = ExotelClient()
        configured = True
        account_sid = client.cfg["account_sid"]
        hs = await cached_handshake(client)
        handshake_ok = bool(hs.get("ok"))
        balance = hs.get("balance")
    except Exception as e:
        handshake_error = str(e)[:300]

    assignments = phone_assignments_store.snapshot()
    return {
        "ok": True,
        "enabled": enabled,
        "configured": configured,
        "handshake_ok": handshake_ok,
        "handshake_error": handshake_error,
        "balance": balance,
        "account_sid": account_sid,
        "webhook_base": webhook_base_url(),
        "exophone": settings.exotel_exophone,
        "subdomain": settings.exotel_subdomain,
        **urls,
        "assignments": assignments,
        "ready": enabled and configured and handshake_ok and bool(urls.get("status_callback_url")),
        "recent_calls": exotel_call_registry.list_recent(10),
    }


@router.get("/api/dev/exotel/status")
async def dev_exotel_status(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    return await _status_payload()


@router.post("/api/dev/exotel/handshake")
async def dev_exotel_handshake(session: SessionData = Depends(require_dev_session)):
    """Explicit credential check — calls Exotel Balance API."""
    require_permission(session, "dev.stack.read")
    if not exotel_enabled():
        return {"ok": False, "error": {"code": "exotel_disabled", "message": "ENABLE_EXOTEL is false"}}
    try:
        client = ExotelClient()
        hs = await cached_handshake(client, force=True)
        return {"ok": True, "handshake": hs, "webhooks": public_webhook_urls()}
    except ExotelConfigError as e:
        return {"ok": False, "error": {"code": "not_configured", "message": str(e)}}
    except ExotelApiError as e:
        return {
            "ok": False,
            "error": {
                "code": "exotel_api_error",
                "message": str(e),
                "status_code": e.status_code,
                "payload": e.payload,
            },
        }


@router.get("/api/dev/exotel/calls")
async def dev_exotel_calls(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    return {"ok": True, "calls": exotel_call_registry.list_recent(30)}


@router.get("/api/dev/exotel/calls/{call_sid}")
async def dev_exotel_call_detail(call_sid: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    local = exotel_call_registry.get(call_sid)
    remote = None
    remote_error = None
    if exotel_enabled():
        try:
            remote = await ExotelClient().get_call(call_sid)
        except Exception as e:
            remote_error = str(e)[:300]
    return {"ok": True, "local": local, "remote": remote, "remote_error": remote_error}


@router.get("/api/dev/exotel/numbers")
async def dev_exotel_numbers(session: SessionData = Depends(require_dev_session)):
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
                        "provider_number_id": row.plivo_number_id,
                        "source": "database",
                    }
                )
    assignments = phone_assignments_store.snapshot()
    for n in db_numbers:
        n["assigned_agent_id"] = assignments.get(n["e164"])
    settings = get_settings()
    exophone = settings.exotel_exophone
    api_numbers: list[dict[str, Any]] = []
    api_error: str | None = None
    if exotel_enabled():
        try:
            api_numbers = await ExotelClient().list_incoming_numbers()
        except Exception as e:
            api_error = str(e)[:200]

    seen = {n["e164"] for n in db_numbers}
    for n in api_numbers:
        if n["e164"] not in seen:
            n["assigned_agent_id"] = assignments.get(n["e164"])
            db_numbers.append(n)
            seen.add(n["e164"])

    if exophone and exophone not in seen:
        db_numbers.insert(
            0,
            {
                "e164": exophone,
                "status": "exophone",
                "source": "env",
                "assigned_agent_id": assignments.get(exophone),
            },
        )
    return {
        "ok": True,
        "numbers": db_numbers,
        "assignments": assignments,
        "exophone": exophone,
        "api_numbers_count": len(api_numbers),
        "api_error": api_error,
    }


@router.post("/api/dev/exotel/numbers")
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


@router.put("/api/dev/exotel/numbers/assign")
async def dev_assign_number(body: AssignNumberBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    assignments = phone_assignments_store.assign(body.e164, body.agent_id)
    return {"ok": True, "e164": body.e164, "agent_id": body.agent_id, "assignments": assignments}


@router.delete("/api/dev/exotel/numbers/assign")
async def dev_unassign_number(e164: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    assignments = phone_assignments_store.unassign(e164)
    return {"ok": True, "assignments": assignments}


@router.post("/api/dev/exotel/outbound")
async def dev_outbound_test(body: OutboundTestBody, session: SessionData = Depends(require_dev_session)):
    """Outbound test — voice_ai (AgentStream) or bridge (connect two numbers)."""
    require_permission(session, "dev.stack.write")
    if not exotel_enabled():
        return {"ok": False, "error": {"code": "exotel_disabled", "message": "ENABLE_EXOTEL is false"}}
    urls = public_webhook_urls()
    if not urls.get("status_callback_url"):
        return {
            "ok": False,
            "error": {
                "code": "webhook_missing",
                "message": "Set EXOTEL_WEBHOOK_BASE_URL (public tunnel URL) for status callbacks",
            },
        }
    settings = get_settings()
    caller_id = (body.caller_id or settings.exotel_exophone or "").strip()
    to_number = body.to_e164.strip()
    mode = (body.mode or "voice_ai").strip().lower()
    if not caller_id:
        return {
            "ok": False,
            "error": {
                "code": "caller_id_missing",
                "message": "Set EXOTEL_EXOPHONE or callerId — no ExoPhones found on your Exotel account",
            },
        }
    if not to_number:
        return {"ok": False, "error": {"code": "numbers_missing", "message": "Destination (To) number required"}}

    phone_assignments_store.assign(caller_id, body.agent_id)
    custom_field = f"agent:{body.agent_id};tier:{body.tier or 'medium'}"

    try:
        client = ExotelClient()
        stream_url: str | None = None
        if mode == "bridge":
            from_number = (body.from_e164 or "").strip()
            if not from_number:
                return {
                    "ok": False,
                    "error": {"code": "from_missing", "message": "Bridge mode requires From (agent handset) number"},
                }
            result = await client.connect_two_numbers(
                from_number=from_number,
                to_number=to_number,
                caller_id=caller_id,
                status_callback=urls["status_callback_url"],
                custom_field=custom_field,
            )
        else:
            stream_url = build_stream_ws_url(agent_id=body.agent_id, tier=body.tier)
            if not stream_url:
                return {
                    "ok": False,
                    "error": {"code": "stream_url_missing", "message": "Cannot build WSS stream URL — check webhook base"},
                }
            result = await client.connect_voice_ai(
                to_number=to_number,
                caller_id=caller_id,
                stream_url=stream_url,
                status_callback=urls["status_callback_url"],
                custom_field=custom_field,
            )
        call_sid = result.get("call_sid")
        if call_sid:
            exotel_call_registry.upsert(
                str(call_sid),
                {
                    "status": result.get("status") or "queued",
                    "from": to_number if mode != "bridge" else body.from_e164,
                    "to": to_number if mode == "bridge" else None,
                    "direction": "outbound-api",
                    "agent_id": body.agent_id,
                    "tier": body.tier,
                    "mode": mode,
                    "stream_url": stream_url if mode != "bridge" else None,
                    "last_event": "outbound-initiated",
                },
            )
        return {
            "ok": True,
            "call_sid": call_sid,
            "status": result.get("status"),
            "to": to_number,
            "caller_id": caller_id,
            "agent_id": body.agent_id,
            "tier": body.tier,
            "mode": mode,
            "stream_url": stream_url if mode != "bridge" else None,
        }
    except ExotelConfigError as e:
        return {"ok": False, "error": {"code": "not_configured", "message": str(e)}}
    except ExotelApiError as e:
        return {
            "ok": False,
            "error": {
                "code": "exotel_api_error",
                "message": str(e),
                "status_code": e.status_code,
                "payload": e.payload,
            },
        }
