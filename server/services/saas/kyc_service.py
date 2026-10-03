"""Didit KYC: create a verification session and apply the verified webhook decision.

Two responsibilities, deliberately split:

1. `create_session` — server-side only. The API key never leaves this module and
   never reaches the browser. Returns the hosted-flow `url` plus our session id.
2. `apply_webhook` — the single source of truth for the decision. Runs only after
   the X-Signature-V2 HMAC and the 300s timestamp check have passed.

The browser's return trip and the SDK's onComplete callback are UI hints. Nothing
in this module ever treats them as approval.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import KycVerification

logger = logging.getLogger(__name__)

DIDIT_BASE = "https://verification.didit.me"
#: Didit retries on 5xx/404, and the outbound timeout is 5s.
SIGNATURE_MAX_AGE_SEC = 300

#: Exactly Didit's literals, compared case-sensitively.
STATUS_NOT_STARTED = "Not Started"
STATUS_IN_PROGRESS = "In Progress"
STATUS_AWAITING_USER = "Awaiting User"
STATUS_IN_REVIEW = "In Review"
STATUS_APPROVED = "Approved"
STATUS_DECLINED = "Declined"
STATUS_RESUBMITTED = "Resubmitted"
STATUS_ABANDONED = "Abandoned"
STATUS_EXPIRED = "Expired"
STATUS_KYC_EXPIRED = "Kyc Expired"

#: Deliveries already applied, so a retried webhook cannot double-apply.
_applied_events: set[str] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KycNotConfigured(RuntimeError):
    pass


class KycSignatureError(ValueError):
    pass


# --------------------------------------------------------------------------
# Canonicalisation for X-Signature-V2
#
# Didit ships no official verify helper: this re-serialisation IS the supported
# approach. Do not replace it with a naive json.dumps of the parsed body.
# --------------------------------------------------------------------------


def shorten_floats(value: Any) -> Any:
    """1.0 -> 1, recursively. Matches Didit's server-side canonicalisation."""
    if isinstance(value, list):
        return [shorten_floats(v) for v in value]
    if isinstance(value, dict):
        return {k: shorten_floats(v) for k, v in value.items()}
    if isinstance(value, float) and not value.is_integer():
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def sort_keys(value: Any) -> Any:
    """Recursive lexicographic key sort; array order is preserved."""
    if isinstance(value, list):
        return [sort_keys(v) for v in value]
    if isinstance(value, dict):
        return {k: sort_keys(value[k]) for k in sorted(value)}
    return value


def canonical_body(raw: str | bytes) -> str:
    """The exact string the HMAC is computed over."""
    parsed = json.loads(raw)
    return json.dumps(sort_keys(shorten_floats(parsed)), ensure_ascii=False, separators=(",", ":"))


def verify_signature(raw: str | bytes, signature: str, timestamp: str | None) -> None:
    """Replay check -> canonicalise -> constant-time compare. Raises on failure."""
    if not signature or not timestamp:
        raise KycSignatureError("missing_signature")
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        raise KycSignatureError("bad_timestamp") from None
    # 1. Freshness. Anything older/newer is a replay or a stale retry.
    if abs(int(_utcnow().timestamp()) - ts) > SIGNATURE_MAX_AGE_SEC:
        raise KycSignatureError("stale")
    secret = get_settings().didit_webhook_secret
    if not secret:
        raise KycSignatureError("secret_not_configured")
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical_body(raw).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    # 2. Constant-time compare; length mismatch must not short-circuit a compare.
    if len(expected) != len(signature) or not hmac.compare_digest(expected, signature):
        raise KycSignatureError("bad_signature")


# --------------------------------------------------------------------------
# Session creation
# --------------------------------------------------------------------------


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.didit_api_key and settings.didit_workflow_id)


async def create_session(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Didit session server-side and persist our row for it."""
    import httpx

    settings = get_settings()
    if not is_configured():
        raise KycNotConfigured("Identity verification is not configured.")

    # KYC is once per user — never open a new Didit flow or overwrite Approved.
    existing = await get_status(user_id)
    if existing.get("approved"):
        # Logged deliberately: "verification returned no URL" otherwise looks
        # identical to "verification never started", which is the exact question
        # this log exists to answer.
        from server.services.saas.activity_log import record_event

        await record_event(
            action="kyc.session.skipped_already_approved",
            resource_type="kyc",
            resource_id=str(user_id),
            actor=email or str(user_id),
            tenant_id=tenant_id,
            payload={"sessionId": existing.get("sessionId")},
            source="subscriber",
        )
        return {
            "url": None,
            "session_id": existing.get("sessionId"),
            "status": STATUS_APPROVED,
            "approved": True,
        }

    body: dict[str, Any] = {
        # workflow_id is per-session config, never an env var.
        "workflow_id": settings.didit_workflow_id,
        # Our stable internal user id — this is what the webhook reports back.
        "vendor_data": str(user_id),
        # Set explicitly rather than inheriting the workflow's region. The
        # account was configured for India, so an unset value produced an
        # Indian flow for a customer buying a US number.
        "country_of_residence": (settings.didit_country or "US").strip().upper(),
        "language": settings.didit_language or "en",
    }
    if settings.didit_callback_url:
        body["callback"] = settings.didit_callback_url
    if email:
        body["contact_details"] = {"email": email, "send_notification_emails": False}
    if metadata:
        body["metadata"] = metadata

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{DIDIT_BASE}/v3/session/",
            json=body,
            headers={"x-api-key": settings.didit_api_key, "Content-Type": "application/json"},
        )
    if not response.is_success:
        # 403 means a missing/invalid/revoked key; do not echo secrets.
        detail = ""
        try:
            detail = (response.text or "")[:200]
        except Exception:
            detail = ""
        logger.error(
            "[KYC] session create failed status=%s body=%s",
            response.status_code,
            detail,
        )
        raise RuntimeError(f"kyc_session_create_failed:{response.status_code}")

    data = response.json()
    session_id = str(data.get("session_id") or data.get("sessionId") or "")
    url = str(data.get("url") or data.get("verification_url") or data.get("session_url") or "")
    if not url:
        logger.error("[KYC] session create returned no url keys=%s", list(data.keys())[:20])
        raise RuntimeError("kyc_session_create_failed:no_url")
    await _upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        status=str(data.get("status") or STATUS_NOT_STARTED),
    )
    # "Verification never started" is the complaint this log has to answer, so the
    # moment a session is created is the row to look for.
    from server.services.saas.activity_log import record_event

    await record_event(
        action="kyc.session.created",
        resource_type="kyc",
        resource_id=str(user_id),
        actor=email or str(user_id),
        tenant_id=tenant_id,
        payload={"sessionId": session_id, "workflowId": settings.didit_workflow_id},
        source="subscriber",
    )
    # Return ONLY what the browser needs. session_token is for native SDKs.
    return {"url": url, "session_id": session_id, "status": data.get("status")}


async def _upsert(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session_id: str,
    status: str,
    decision: dict[str, Any] | None = None,
    verified_at: datetime | None = None,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        row = await session.get(KycVerification, user_id)
        if row is None:
            row = KycVerification(user_id=user_id, tenant_id=tenant_id, created_at=_utcnow())
            session.add(row)
        row.tenant_id = tenant_id
        row.status = status
        if session_id:
            row.didit_session_id = session_id
        if decision is not None:
            row.decision = decision
        if verified_at is not None:
            row.verified_at = verified_at
        if decided_at is not None:
            row.decided_at = decided_at
        row.updated_at = _utcnow()
        await session.commit()
        return _public(row)


def _public(row: KycVerification) -> dict[str, Any]:
    return {
        "userId": str(row.user_id),
        "status": row.status,
        "approved": row.status == STATUS_APPROVED and row.verified_at is not None,
        "verifiedAt": row.verified_at.isoformat() if row.verified_at else None,
        "decidedAt": row.decided_at.isoformat() if row.decided_at else None,
        "sessionId": row.didit_session_id,
    }


async def get_status(user_id: uuid.UUID) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        return {"status": STATUS_NOT_STARTED, "approved": False, "verifiedAt": None}
    async with factory() as session:
        row = await session.get(KycVerification, user_id)
        return _public(row) if row is not None else {
            "status": STATUS_NOT_STARTED,
            "approved": False,
            "verifiedAt": None,
            "sessionId": None,
        }


# --------------------------------------------------------------------------
# Webhook — the only authority on the decision
# --------------------------------------------------------------------------


def already_applied(event_id: str) -> bool:
    return bool(event_id) and event_id in _applied_events


def mark_applied(event_id: str) -> None:
    if event_id:
        # Bounded: a long-lived process must not grow this without limit.
        if len(_applied_events) > 5000:
            _applied_events.clear()
        _applied_events.add(event_id)


async def _log_decision(
    *,
    user_id: uuid.UUID,
    status: str,
    decision: Any,
    event_id: str,
    severity: str = "info",
) -> bool:
    """Put every identity decision in the activity log.

    A declined or expired verification is the single most common reason a paying
    customer cannot buy a number, and it arrives on a webhook nobody was watching.
    Logging it is the difference between "the gate is broken" and a diagnosis.
    """
    from server.services.saas.activity_log import record_event

    await record_event(
        action="kyc.decision",
        resource_type="kyc",
        resource_id=str(user_id),
        actor="didit",
        payload={"status": status, "eventId": event_id, "decision": decision},
        source="webhook",
        outcome="ok",
        severity=severity,
    )
    return True


def _log_decision_sync_soon(
    user_id: uuid.UUID, status: str, decision: Any, event_id: str, *, severity: str
) -> None:
    """Fire-and-forget the log write from a sync-looking call site."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        _log_decision(
            user_id=user_id, status=status, decision=decision, event_id=event_id, severity=severity
        )
    )


async def apply_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "")
    if already_applied(event_id):
        return {"ok": True, "duplicate": True}
    mark_applied(event_id)

    vendor_data = str(payload.get("vendor_data") or "")
    if not vendor_data:
        logger.warning("[KYC] webhook without vendor_data event=%s", event_id)
        return {"ok": True, "ignored": "no_vendor_data"}
    try:
        user_id = uuid.UUID(vendor_data)
    except ValueError:
        logger.warning("[KYC] webhook vendor_data is not a uuid: %r", vendor_data)
        return {"ok": True, "ignored": "bad_vendor_data"}

    status = str(payload.get("status") or "")
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else None
    now = _utcnow()

    if status == STATUS_APPROVED:
        return {"ok": True, "status": status, "state": await _upsert(
            user_id=user_id,
            tenant_id=await _tenant_for(user_id),
            session_id=str(payload.get("session_id") or ""),
            status=status,
            decision=decision,
            verified_at=now,
            decided_at=now,
        ), "logged": await _log_decision(
            user_id=user_id, status=status, decision=decision, event_id=event_id
        )}

    if status == STATUS_KYC_EXPIRED:
        # A previously verified user has aged out: clear the approval so the gate
        # reopens rather than letting a stale pass keep working.
        # A lapsed approval blocks a paying customer's next purchase, so it is
        # recorded as a warning rather than routine info.
        _log_decision_sync_soon(user_id, status, decision, event_id, severity="warning")
        return {"ok": True, "status": status, "state": await _upsert(
            user_id=user_id,
            tenant_id=await _tenant_for(user_id),
            session_id=str(payload.get("session_id") or ""),
            status=status,
            decision=decision,
            verified_at=None,
            decided_at=now,
        )}

    if status in {
        STATUS_DECLINED,
        STATUS_IN_REVIEW,
        STATUS_IN_PROGRESS,
        STATUS_AWAITING_USER,
        STATUS_RESUBMITTED,
        STATUS_ABANDONED,
        STATUS_EXPIRED,
    }:
        # Every non-terminal status that reached a reviewer clears approval;
        # NOT_STARTED and the pure-progress statuses keep the current value
        # because they carry no decision.
        return {"ok": True, "status": status, "state": await _upsert(
            user_id=user_id,
            tenant_id=await _tenant_for(user_id),
            session_id=str(payload.get("session_id") or ""),
            status=status,
            decision=decision,
            verified_at=None if status != STATUS_NOT_STARTED else None,
            decided_at=now if status in {STATUS_DECLINED, STATUS_IN_REVIEW} else None,
        )}

    # "Not Started" and anything unknown: recorded, never treated as a decision.
    logger.info("[KYC] webhook status=%s event=%s (no decision applied)", status, event_id)
    return {"ok": True, "status": status, "ignored": "no_decision"}


async def _tenant_for(user_id: uuid.UUID) -> uuid.UUID:
    from server.db.models.saas_models import TenantMembership

    factory = get_session_factory()
    if factory is None:
        return user_id
    async with factory() as session:
        row = (
            await session.execute(
                select(TenantMembership).where(TenantMembership.user_id == user_id).limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        return user_id
    return row.tenant_id


async def is_approved(user_id: uuid.UUID | None) -> bool:
    """The gate. Only a verified webhook can make this True."""
    if user_id is None:
        return False
    state = await get_status(user_id)
    return bool(state.get("approved"))


async def admin_set_status(
    *,
    user_id: uuid.UUID,
    status: str,
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Manual override from the ops admin panel (Approve / Decline / reset).

    Used when Didit stalls, a webhook is missed, or an operator needs to clear a
    false decline after reviewing documents offline. Still records a decision
    blob so the audit trail shows who flipped the switch.
    """
    if status not in {
        STATUS_APPROVED,
        STATUS_DECLINED,
        STATUS_NOT_STARTED,
        STATUS_IN_REVIEW,
        STATUS_EXPIRED,
    }:
        raise ValueError(f"unsupported_status:{status}")
    now = _utcnow()
    decision = {
        "source": "admin_override",
        "actor": actor,
        "reason": (reason or "").strip() or None,
        "at": now.isoformat(),
    }
    return await _upsert(
        user_id=user_id,
        tenant_id=await _tenant_for(user_id),
        session_id="",
        status=status,
        decision=decision,
        verified_at=now if status == STATUS_APPROVED else None,
        decided_at=now,
    )


async def list_verifications(*, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Ops list: KYC rows joined with user email for the admin verification page."""
    from server.db.models.saas_models import User

    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        stmt = (
            select(KycVerification, User)
            .join(User, User.user_id == KycVerification.user_id, isouter=True)
            .order_by(KycVerification.updated_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(KycVerification.status == status)
        rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for row, user in rows:
        item = _public(row)
        item["email"] = user.email if user is not None else None
        item["fullName"] = user.full_name if user is not None else None
        item["tenantId"] = str(row.tenant_id)
        item["updatedAt"] = row.updated_at.isoformat() if row.updated_at else None
        item["decision"] = row.decision
        out.append(item)
    return out