"""Tenant-wide PSTN admission and durable idempotency across API/worker hosts.

Ambiguous requests retain their capacity until a verified callback or explicit
operator reconciliation. A timeout is not evidence that the carrier did not dial.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, text

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Call, Tenant
from server.db.models.phase5_models import PstnDialRequest
from server.services.saas.voice_setup_errors import VOICE_SETUP_MESSAGES

ACTIVE = ("reserved", "accepted", "answered", "uncertain")
logger = logging.getLogger(__name__)
from server.services.call_setup_failures import VOICE_SERVICE_UNAVAILABLE, VOICE_SERVICE_UNAVAILABLE_MESSAGE

NO_DIAL_CODES = frozenset({"voice_preparation_failed", "live_transcription_unavailable", "predial_policy_changed",
                           VOICE_SERVICE_UNAVAILABLE, *VOICE_SETUP_MESSAGES})


def _now():
    return datetime.now(timezone.utc)


def _is_older_than(dt: datetime | None, delta: timedelta) -> bool:
    if dt is None:
        return False
    now = _now()
    if dt.tzinfo is None:
        return dt < now.replace(tzinfo=None) - delta
    return dt < now - delta


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
    if destination_hash and provider == "vobiz":
        try:
            await asyncio.wait_for(reconcile_ended_destination(tenant_id, destination_hash), timeout=6)
        except TimeoutError:
            logger.info("Call admission reconciliation deferred; retaining unconfirmed reservations")
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
        if destination_hash:
            candidates = (await db.execute(select(PstnDialRequest).where(
                PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.destination_hash == destination_hash,
                PstnDialRequest.status.in_(ACTIVE)).with_for_update())).scalars().all()
            from server.services.vobiz_client import vobiz_call_registry
            for row in candidates:
                # 1. Server-produced non-dial result or explicit failure
                resp = row.response or {}
                if (resp.get("code") in NO_DIAL_CODES or resp.get("ok") is False) and not row.media_claimed_at and not row.answered_at:
                    row.status = "failed"
                    row.updated_at = _now()
                    continue

                # 2. Auto-reconcile reservation if the linked call record has already terminated.
                if row.call_id:
                    call_status = (await db.execute(
                        select(Call.ended_at, Call.status).where(Call.call_id == row.call_id)
                    )).first()
                    if call_status is not None:
                        ended_at, status_val = call_status
                        if ended_at is not None or str(status_val or "").lower() in ("completed", "failed", "busy", "no-answer", "canceled", "ended"):
                            row.status = "ended"
                            row.updated_at = _now()
                            continue

                # 3. Auto-reconcile from carrier call registry
                if row.carrier_id:
                    reg_entry = vobiz_call_registry.get(row.carrier_id) or {}
                    if reg_entry.get("ended") is True or str(reg_entry.get("status") or "").lower() in ("completed", "failed", "busy", "no-answer", "canceled", "ended"):
                        row.status = "ended"
                        row.updated_at = _now()
                        continue

                # 4. If status is uncertain and created more than 20 seconds ago, fail it
                if row.status == "uncertain" and _is_older_than(row.created_at, timedelta(seconds=20)):
                    row.status = "failed"
                    row.updated_at = _now()
                    continue

                # 5. Auto-reconcile unlinked or unanswered reservations older than 45 seconds (ringing / dispatch timeout).
                if not row.carrier_id and not row.call_id and row.answered_at is None and _is_older_than(row.created_at, timedelta(seconds=45)):
                    row.status = "ended"
                    row.updated_at = _now()
                    continue
            await db.flush()
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
        # Channel cap: legacy limits until the admin configures channel pricing,
        # then included + paid channels within the platform's Vobiz capacity.
        from server.services.saas import concurrency_service as channels

        caps = await channels.channel_cap(db, tenant, settings=settings)
        active = await active_capacity(db, tenant_id)
        over = None
        if active >= caps["cap"]:
            over = "tenant"
        elif not caps["legacy"]:
            await channels.lock_platform(db)
            if await channels.platform_active_calls(db) >= caps["platformCapacity"]:
                over = "platform"
        if over:
            await db.rollback()
            # Campaign dials are re-queued by the runner; everything else is refused.
            queued = str(request_id).startswith("camp:")
            await channels.record_daily(factory, tenant_id, active=active, cap=caps["cap"],
                                        rejected=0 if queued else 1, queued=1 if queued else 0)
            raise channels.capacity_exception(over)
        db.add(PstnDialRequest(request_key=key, tenant_id=tenant_id, fingerprint=fingerprint,
            destination_hash=destination_hash, provider=provider, status="reserved", created_at=_now(), updated_at=_now()))
        await db.commit()
    await channels.record_daily(factory, tenant_id, active=active + 1, cap=caps["cap"], admitted=1)
    return key, None


def safe_response(result: dict) -> dict:
    # Carrier bridge responses contain internal stream URLs/tokens and history.
    response = {key: result[key] for key in ("ok", "call_id", "callId", "call_control_id", "code", "error", "status", "retry_after") if key in result}
    if not response.get("ok"):
        response["error"] = (VOICE_SETUP_MESSAGES.get(response.get("code")) or
                             (VOICE_SERVICE_UNAVAILABLE_MESSAGE if response.get("code") == VOICE_SERVICE_UNAVAILABLE else None) or
                             ("The agent could not get ready. No call was placed. Contact your administrator or try again."
                             if response.get("code") in NO_DIAL_CODES else
                             "The call could not be confirmed. Check the call status before retrying."))
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
                definitive_rejection = (
                    (400 <= status < 500 and status != 408)
                    or result.get("code") in NO_DIAL_CODES
                    or result.get("code") in ("dial_failed", "voice_preparation_failed", "voice_start_failed", "agent_paused", "dnc_blocked")
                )
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
        except Exception as exc:  # noqa: BLE001 -- retain ambiguity after cancellation
            logger.warning("Call admission finalization unavailable: %s", type(exc).__name__)
        raise


async def reconcile_ended_destination(tenant_id: uuid.UUID, destination_hash: str) -> int:
    """Release missed callbacks only after an exact, tenant-owned terminal CDR.

    An old timestamp, a closed media socket, a local ended flag, or a 404 is not
    enough: any of those can coexist with an actual live carrier call.
    """
    factory = get_session_factory()
    if factory is None:
        return 0
    async with factory() as db:
        rows = (await db.execute(select(PstnDialRequest).where(
            PstnDialRequest.tenant_id == tenant_id, PstnDialRequest.provider == "vobiz",
            PstnDialRequest.destination_hash == destination_hash, PstnDialRequest.status.in_(ACTIVE)).limit(20))).scalars().all()
    from server.call.call_ledger import call_ledger
    from server.services.saas.voice_kyc_service import vobiz_client_for_call
    from server.services.vobiz_client import vobiz_call_registry

    released = 0
    for row in rows:
        meta = (call_ledger.read_meta(str(row.call_id)) or {}) if row.call_id else {}
        if row.call_id and (str(meta.get("tenant_id") or "") != str(tenant_id) or not meta.get("ended_at")):
            continue
        call_uuid = str(meta.get("vobiz_call_uuid") or row.carrier_id or "")
        if not call_uuid:
            continue
        try:
            local = await asyncio.to_thread(vobiz_call_registry.get, call_uuid) or {}
            client = await vobiz_client_for_call({**local, **meta})
            payload = await asyncio.wait_for(client.get_call_cdr(call_uuid), timeout=4)
            data = payload.get("data", payload)
            if not isinstance(data, dict) or str(data.get("uuid") or "") != call_uuid:
                continue
            end = datetime.fromisoformat(str(data.get("end_time") or "").replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if end > _now() + timedelta(minutes=1):
                continue
            if meta.get("started_at"):
                started = datetime.fromisoformat(str(meta["started_at"]).replace("Z", "+00:00"))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                if end < started - timedelta(minutes=1):
                    continue
            await provider_event(tenant_id=tenant_id, key=row.request_key, status="ended")
            released += 1
        except Exception as exc:  # noqa: BLE001 -- any provider/storage error retains the reservation
            # Missing/ambiguous carrier evidence must continue to retain capacity.
            logger.info("Call admission carrier reconciliation unavailable: %s", type(exc).__name__)
            continue
    return released


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
        elif call_id:
            try:
                cid_u = uuid.UUID(str(call_id))
                query = query.where(PstnDialRequest.call_id == cid_u)
            except ValueError:
                return
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
