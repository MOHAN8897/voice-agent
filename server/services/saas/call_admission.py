"""Tenant-wide PSTN admission and durable idempotency across API/worker hosts.

Ambiguous requests retain their capacity until a verified callback or explicit
operator reconciliation. A timeout is not evidence that the carrier did not dial.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Call, Tenant
from server.db.models.phase5_models import PstnDialRequest

ACTIVE = ("reserved", "accepted", "answered", "uncertain")


def _now():
    return datetime.now(timezone.utc)


def request_key(tenant_id: uuid.UUID, request_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{request_id}".encode()).hexdigest()


async def lock_tenant(db, tenant_id: uuid.UUID):
    # SQLite is used only by isolated/local tests; BEGIN IMMEDIATE supplies its
    # missing SELECT FOR UPDATE semantics. PostgreSQL locks only this tenant.
    if db.bind.dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    tenant = (await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if tenant is None or tenant.status != "active" or tenant.deleted_at is not None:
        raise HTTPException(403, detail={"error": {"code": "tenant_inactive", "message": "Workspace is not active"}})
    return tenant


async def active_capacity(db, tenant_id: uuid.UUID) -> int:
    reservations = select(PstnDialRequest.call_id).where(
        PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.status.in_(ACTIVE), PstnDialRequest.call_id.is_not(None))
    tracked = (await db.execute(select(func.count()).select_from(PstnDialRequest).where(
        PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.status.in_(ACTIVE)))).scalar_one()
    untracked = (await db.execute(select(func.count()).select_from(Call).where(
        Call.tenant_id == tenant_id, Call.channel == "pstn", Call.ended_at.is_(None),
        Call.call_id.not_in(reservations)))).scalar_one()
    return int(tracked or 0) + int(untracked or 0)


async def reserve(tenant_id: uuid.UUID, request_id: str, *, provider: str, payload: dict) -> tuple[str, dict | None]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, detail={"error": {"code": "call_admission_unavailable", "message": "Call admission storage is unavailable"}})
    key = request_key(tenant_id, request_id)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    destination_hash = hashlib.sha256(f"{tenant_id}:{payload['to']}".encode()).hexdigest() if payload.get("to") else None
    async with factory() as db:
        tenant = await lock_tenant(db, tenant_id)
        previous = await db.get(PstnDialRequest, key)
        if previous is not None:
            if previous.fingerprint != fingerprint:
                raise HTTPException(409, detail={"error": {"code": "dial_request_conflict", "message": "This call request was already used with different settings"}})
            if previous.response is not None:
                return key, dict(previous.response)
            return key, {"ok": False, "code": "dial_pending", "error": "The existing call request is pending or uncertain; review it before redialing."}
        settings = get_settings()
        if destination_hash and (await db.execute(select(PstnDialRequest.request_key).where(
            PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.destination_hash == destination_hash,
            PstnDialRequest.status.in_(ACTIVE)).limit(1))).scalar_one_or_none():
            raise HTTPException(409, detail={"error": {"code": "dial_in_progress", "message": "A call to this destination is already active or awaiting review"}})
        if payload.get("to"):
            platform_cps = max(1, min(100, int(getattr(settings, "saas_max_outbound_cps", 1))))
            cps = max(1, min(platform_cps, int((tenant.limits or {}).get("max_outbound_cps") or platform_cps)))
            recent = (await db.execute(select(func.count()).select_from(PstnDialRequest).where(
                PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.provider == provider,
                PstnDialRequest.created_at > _now() - timedelta(seconds=1)))).scalar_one()
            if recent >= cps:
                raise HTTPException(429, detail={"error": {"code": "call_pacing", "message": "Calls are being paced. Please wait before starting another call.", "retry_after": 1}}, headers={"Retry-After": "1"})
        platform_cap = max(1, min(20, int(settings.saas_max_concurrent_pstn or 20)))
        tenant_cap = max(1, min(platform_cap, int((tenant.limits or {}).get("max_concurrent_pstn") or platform_cap)))
        if await active_capacity(db, tenant_id) >= tenant_cap:
            raise HTTPException(429, detail={"error": {"code": "concurrency_limit", "message": "All concurrent call slots are in use", "retry_after": 5}}, headers={"Retry-After": "5"})
        db.add(PstnDialRequest(request_key=key, tenant_id=tenant_id, fingerprint=fingerprint,
            destination_hash=destination_hash, provider=provider, status="reserved", created_at=_now(), updated_at=_now()))
        await db.commit()
    return key, None


def safe_response(result: dict) -> dict:
    # Carrier bridge responses contain internal stream URLs/tokens and history.
    response = {key: result[key] for key in ("ok", "call_id", "callId", "call_control_id", "code", "error", "status") if key in result}
    if not response.get("ok"):
        response["error"] = "The call could not be confirmed. Check the call status before retrying."
    return response


async def finish(key: str, tenant_id: uuid.UUID, *, result: dict | None = None, uncertain=False):
    factory = get_session_factory()
    async with factory() as db:
        row = (await db.execute(select(PstnDialRequest).where(
            PstnDialRequest.request_key == key, PstnDialRequest.tenant_id == tenant_id).with_for_update())).scalar_one()
        if uncertain:
            if row.status in ("reserved", "accepted"):
                row.status = "uncertain"
        elif result is not None:
            row.response = safe_response(result)
            carrier = result.get("call_control_id") or result.get("callId") or result.get("call_id")
            if carrier:
                row.carrier_id = str(carrier)[:128]
            # A callback can win the race with the POST response; never resurrect
            # an ended request or downgrade answered to accepted.
            if row.status == "reserved":
                try:
                    status = int(result.get("status") or 0)
                except (TypeError, ValueError):
                    status = 0
                # Only a definitive client rejection proves the POST did not
                # place a call. A malformed success or an HTTP timeout can
                # still leave a live carrier call and must retain its slot.
                definitive_rejection = 400 <= status < 500 and status != 408
                ambiguous = not result.get("ok") and not definitive_rejection
                row.status = "accepted" if result.get("ok") else "uncertain" if ambiguous else "failed"
        row.updated_at = _now()
        await db.commit()


async def execute(*, tenant_id: uuid.UUID, request_id: str, provider: str, payload: dict, operation):
    key, previous = await reserve(tenant_id, request_id, provider=provider, payload=payload)
    if previous is not None:
        return previous
    try:
        result = await asyncio.wait_for(operation(key), timeout=60)
        result = result if isinstance(result, dict) else {"ok": False, "code": "unknown_result", "error": "Call result requires review"}
        await finish(key, tenant_id, result=result)
        return safe_response(result)
    except BaseException:
        # Preserve ambiguity even when the caller disconnects during the request.
        try:
            await asyncio.shield(finish(key, tenant_id, uncertain=True))
        except Exception:
            pass
        raise


async def provider_event(*, tenant_id: uuid.UUID, key: str | None = None, carrier_ids=(), status: str, call_id: str | None = None):
    """Called only after provider authentication; every update remains tenant scoped."""
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as db:
        query = select(PstnDialRequest).where(PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.provider == "vobiz")
        if key:
            query = query.where(PstnDialRequest.request_key == key)
        elif carrier_ids:
            query = query.where(PstnDialRequest.carrier_id.in_([str(value) for value in carrier_ids if value]))
        else:
            return
        row = (await db.execute(query.with_for_update())).scalar_one_or_none()
        if row is None:
            return
        if status == "ended" or row.status != "ended":
            row.status = status
        if status == "answered" and row.answered_at is None:
            row.answered_at = _now()
        if call_id:
            row.call_id = uuid.UUID(str(call_id))
        row.updated_at = _now()
        await db.commit()


async def claim_media(tenant_id: uuid.UUID, key: str) -> bool:
    """Durable one-stream-per-call guard, including after Redis key expiry."""
    factory = get_session_factory()
    if factory is None:
        return False
    async with factory() as db:
        await lock_tenant(db, tenant_id)
        row = (await db.execute(select(PstnDialRequest).where(
            PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.request_key == key)
            .with_for_update())).scalar_one_or_none()
        if row is None or row.status not in ACTIVE or row.media_claimed_at is not None:
            return False
        row.media_claimed_at = _now()
        await db.commit()
        return True
