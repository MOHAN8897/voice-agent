"""Razorpay webhook — the authoritative, provider-pushed payment state.

Checkout verification is best effort: the browser can close after a successful
payment, or the user's network can fail between Razorpay and us. This endpoint
is what makes a captured payment eventually credit the wallet regardless.

Security posture:

* The raw body is verified against `X-Razorpay-Signature` before it is parsed.
  A missing endpoint secret disables the route (503) rather than trusting it.
* Every delivery is written to a durable inbox keyed by the provider event id,
  so retries and duplicate deliveries cannot double-credit.
* Transient failures (database, provider) return 5xx so Razorpay retries.
  Business-level "not our order" events are recorded as ignored, and
  permanent rejections (amount/currency mismatch, impossible refund) are
  recorded as rejected and alerted on. Both are acknowledged with 200: a
  retry can never succeed, and repeated 5xx makes Razorpay disable the
  webhook for every tenant.
* The per-IP rate limiter does not apply here (see `RateLimitMiddleware`):
  the HMAC signature is the gate, and Razorpay delivers from shared IPs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.services.saas.razorpay_service import (
    apply_refund,
    capture_authorized_payment,
    credit_provider_payment,
    handle_dispute_event,
    mark_order_failed,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_WEBHOOK_BYTES = 512 * 1024

#: Codes that no retry can fix: the event is inconsistent with what we sold.
PERMANENT_ERRORS = frozenset(
    {
        "payment_amount_mismatch",
        "payment_currency_mismatch",
        "invalid_refund_amount",
        "refund_currency_mismatch",
    }
)
#: Codes meaning the event is not about anything we can act on.
IGNORED_ERRORS = frozenset({"order_not_found", "payment_order_mismatch", "payment_id_mismatch"})
#: Statuses after which a redelivery is acknowledged without re-running.
_FINAL_STATUSES = ("handled", "ignored", "rejected")


def _entity(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    node = payload.get("payload")
    if not isinstance(node, dict):
        return {}
    leaf = node.get(kind)
    if not isinstance(leaf, dict):
        return {}
    entity = leaf.get("entity")
    return entity if isinstance(entity, dict) else {}


def _event_identity(event_type: str, payload: dict[str, Any], raw: bytes, header_id: str | None) -> str:
    if header_id:
        return header_id[:128]
    for kind in ("payment", "order", "refund", "dispute"):
        entity = _entity(payload, kind)
        if entity.get("id"):
            return f"{event_type}:{entity['id']}"[:128]
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return f"{event_type}:{payload.get('created_at') or digest}"[:128]


async def _handle_event(event_type: str, payload: dict[str, Any]) -> str:
    if event_type in ("payment.captured", "order.paid"):
        payment = _entity(payload, "payment")
        if not payment:
            return "ignored"
        await credit_provider_payment(payment, source="webhook")
        return "handled"

    if event_type == "payment.authorized":
        payment = _entity(payload, "payment")
        if not payment:
            return "ignored"
        await capture_authorized_payment(payment, source="webhook")
        return "handled"

    if event_type == "payment.failed":
        payment = _entity(payload, "payment")
        if not payment:
            return "ignored"
        await mark_order_failed(payment, source="webhook")
        return "handled"

    if event_type == "refund.processed":
        refund = _entity(payload, "refund")
        if not refund:
            return "ignored"
        result = await apply_refund(
            refund_id=str(refund.get("id") or ""),
            payment_id=str(refund.get("payment_id") or ""),
            amount_minor=int(refund.get("amount") or 0),
            currency=str(refund.get("currency") or "INR"),
            reason=str((refund.get("notes") or {}).get("reason") or "Refund processed by Razorpay"),
            created_by=None,
            status="processed",
        )
        return "handled" if not result.get("ignored") else "ignored"

    if event_type.startswith("payment.dispute."):
        return await handle_dispute_event(
            event_type, _entity(payload, "dispute"), _entity(payload, "payment")
        )

    if event_type == "refund.failed":
        refund = _entity(payload, "refund")
        if not refund:
            return "ignored"
        await apply_refund(
            refund_id=str(refund.get("id") or ""),
            payment_id=str(refund.get("payment_id") or ""),
            amount_minor=int(refund.get("amount") or 0),
            currency=str(refund.get("currency") or "INR"),
            reason=str((refund.get("notes") or {}).get("reason") or "Refund failed at the bank"),
            created_by=None,
            status="failed",
        )
        return "handled"

    return "ignored"


@router.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    settings = get_settings()
    secret = (settings.razorpay_webhook_secret or "").strip()
    if not secret:
        # Fail closed: an unverified payment webhook is an open wallet credit.
        raise HTTPException(status_code=503, detail="webhook_not_configured")
    from server.config.env import razorpay_refused

    if razorpay_refused(settings):
        # Production with a reused secret or test keys: logged at startup.
        raise HTTPException(status_code=503, detail="webhook_not_configured")

    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="payload_too_large")
    signature = request.headers.get("X-Razorpay-Signature")
    if not verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=400, detail="invalid_signature")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid_payload") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    event_type = str(payload.get("event") or "").strip()
    if not event_type:
        raise HTTPException(status_code=400, detail="invalid_payload")
    event_id = _event_identity(event_type, payload, raw, request.headers.get("X-Razorpay-Event-Id"))

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="database_unavailable")
    from server.db.models.saas_models import RazorpayWebhookEvent

    async with factory() as session:
        existing = await session.get(RazorpayWebhookEvent, event_id)
        if existing is not None:
            if existing.status in _FINAL_STATUSES:
                return {"ok": True, "duplicate": True, "status": existing.status}
            existing.attempts = int(existing.attempts or 1) + 1
            existing.status = "processing"
            existing.error = None
        else:
            session.add(
                RazorpayWebhookEvent(
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                    status="processing",
                )
            )
        await session.commit()

    try:
        status = await _handle_event(event_type, payload)
    except ValueError as exc:
        code = str(exc)
        if code in IGNORED_ERRORS:
            status = "ignored"
        elif code in PERMANENT_ERRORS:
            await _record_rejection(event_id, event_type, code, payload)
            return {"ok": True, "status": "rejected", "error": code}
        else:
            await _record_failure(event_id, code)
            raise HTTPException(status_code=503, detail="event_processing_failed") from None
    except Exception as exc:  # transient database/provider failure: let Razorpay retry
        logger.error("razorpay webhook handler failed event=%s error_type=%s", event_type, type(exc).__name__)
        await _record_failure(event_id, type(exc).__name__)
        raise HTTPException(status_code=503, detail="event_processing_failed") from None

    await _record_success(event_id, status)
    return {"ok": True, "status": status}


async def _record_success(event_id: str, status: str) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    from datetime import datetime, timezone

    from server.db.models.saas_models import RazorpayWebhookEvent

    async with factory() as session:
        row = await session.get(RazorpayWebhookEvent, event_id, with_for_update=True)
        if row is None:
            return
        row.status = status
        row.processed_at = datetime.now(timezone.utc)
        row.error = None
        await session.commit()


async def _record_failure(event_id: str, error: str) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    from server.db.models.saas_models import RazorpayWebhookEvent

    async with factory() as session:
        row = await session.get(RazorpayWebhookEvent, event_id, with_for_update=True)
        if row is None:
            return
        row.status = "failed"
        row.error = error[:2000]
        await session.commit()


async def _record_rejection(event_id: str, event_type: str, code: str, payload: dict[str, Any]) -> None:
    """Acknowledge a permanently invalid event, and make sure a human sees it."""
    payment = _entity(payload, "payment")
    refund = _entity(payload, "refund")
    logger.error(
        "razorpay webhook rejected event=%s code=%s payment=%s order=%s refund=%s",
        event_type,
        code,
        payment.get("id") or refund.get("payment_id"),
        payment.get("order_id"),
        refund.get("id"),
    )
    factory = get_session_factory()
    if factory is not None:
        from datetime import datetime, timezone

        from server.db.models.saas_models import RazorpayWebhookEvent

        async with factory() as session:
            row = await session.get(RazorpayWebhookEvent, event_id, with_for_update=True)
            if row is not None:
                row.status = "rejected"
                row.error = code[:2000]
                row.processed_at = datetime.now(timezone.utc)
                await session.commit()
    from server.services.saas.activity_log import record_event

    await record_event(
        action="wallet.webhook.rejected",
        resource_type="payment_order",
        resource_id=str(payment.get("order_id") or refund.get("payment_id") or event_id),
        actor="razorpay",
        payload={
            "eventId": event_id,
            "eventType": event_type,
            "code": code,
            "paymentId": payment.get("id") or refund.get("payment_id"),
            "refundId": refund.get("id"),
        },
        source="webhook",
        outcome="error",
        severity="error",
    )
