"""Server-owned order proof — the only authority for "your order is confirmed".

The model may offer, clarify and read back an order, but it may not confirm one.
Confirmation is a fact the server records only after a successful CONFIRM_ORDER
tool call that validated quantity, customer name and delivery address. Speech,
live memory and the post-call outcome all consult this record.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from server.call.paths import call_dir
from server.utils.logger import logger

CONFIRM_ORDER_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "CONFIRM_ORDER",
    "description": (
        "Record an order the caller has explicitly confirmed. Collect the quantity, "
        "the caller's name and the full delivery address first; never guess a value. "
        "Before calling this, read the product, quantity, total and address back once and "
        "wait for the caller's yes; supplying an address alone is not that confirmation. "
        "Do not tell the caller the order is confirmed until this returns status ok. "
        "The server carries the successful receipt; never invent a confirmation."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "quantity": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "Confirmed quantity as a positive whole number",
            },
            "customer_name": {
                "type": "string",
                "minLength": 2,
                "maxLength": 120,
                "description": "Name the caller gave for the order",
            },
            "delivery_address": {
                "type": "string",
                "minLength": 4,
                "maxLength": 400,
                "description": "Full delivery address the caller gave",
            },
            "product": {
                "type": "string",
                "maxLength": 160,
                "description": "Product or service being ordered, if stated",
            },
        },
        "required": ["quantity", "customer_name", "delivery_address"],
    },
}

# The order tool is a capability of order-taking businesses, not of every
# agent. The compiler records that permission as typed metadata in the
# compiled brain (server/brain/capabilities.py); a probe over the whole prompt
# used to offer it to a Telugu quote-only brief merely because a minimum-order
# sentence contains the noun "ఆర్డర్" (2026-10-25 audit F10).
def order_workflow_active(compiled_text: str | None) -> bool:
    """True only when the compiled capability contract allows order confirmation."""
    from server.brain.capabilities import order_confirmation_allowed

    return order_confirmation_allowed(compiled_text)


# Past-tense confirmation claims, English and Indic. A question ("shall I
# confirm?") is not a claim; a bare future promise ("I will confirm") is not
# either. Used only server-side to block unproven speech.
_ORDER_CONFIRMATION_CLAIM = re.compile(
    r"\b(?:order|booking|purchase)\b[^.!?]{0,60}\b(?:confirmed|placed|booked|done|complete[d]?)\b|"
    r"\b(?:confirmed|placed|booked)\b[^.!?]{0,40}\b(?:order|booking|purchase)\b|"
    r"(?:ఆర్డర్|బుకింగ్)[^.!?]{0,40}(?:నిర్ధార|పూర్తి)|"
    r"(?:ऑर्डर|बुकिंग)[^.!?]{0,40}(?:पुष्टि|पूरा)|"
    r"(?:ஆர்டர்|முன்பதிவு)[^.!?]{0,40}(?:உறுதி|முடிந்த)|"
    r"(?:ಆರ್ಡರ್|ಬುಕಿಂಗ್)[^.!?]{0,40}(?:ದೃಢೀಕರಿಸ|ಪೂರ್ಣಗೊಂಡ)|"
    r"(?:ഓർഡർ|ബുക്കിംഗ്)[^.!?]{0,40}(?:സ്ഥിരീകരിച്ച|പൂർത്തിയായ)",
    re.I,
)

def order_unconfirmed_line_for(language: str | None) -> str:
    from server.call.action_proof import action_unconfirmed_line_for

    return action_unconfirmed_line_for(language)


def order_proof_path(call_id: str):
    return call_dir(call_id) / "order_confirmation.json"


def claims_order_confirmation(text: str) -> bool:
    from server.call.action_proof import (
        PROOF_APPOINTMENT_CONFIRMED,
        PROOF_ORDER_CONFIRMED,
        unproven_claim,
    )

    return unproven_claim(text, ()) in {PROOF_ORDER_CONFIRMED, PROOF_APPOINTMENT_CONFIRMED}


def _clean(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _quantity(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
    else:
        return None
    return value if 1 <= value <= 1_000_000 else None


def validate_order_arguments(arguments: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Return (normalized fields, error code). Codes only; never echo caller values."""
    args = arguments if isinstance(arguments, dict) else {}
    quantity = _quantity(args.get("quantity"))
    if quantity is None:
        return None, "invalid_quantity"
    name = _clean(args.get("customer_name"), 120)
    if len(name) < 2:
        return None, "missing_customer_name"
    address = _clean(args.get("delivery_address"), 400)
    if len(address) < 4:
        return None, "missing_delivery_address"
    product = _clean(args.get("product"), 160) or None
    return {
        "quantity": quantity,
        "customer_name": name,
        "delivery_address": address,
        "product": product,
    }, None


_ORDER_TOOL_MESSAGES: dict[str, str] = {
    "invalid_quantity": "Ask the caller for the quantity as a positive whole number, then try again.",
    "missing_customer_name": "Ask the caller for the name on the order, then try again.",
    "missing_delivery_address": "Ask the caller for the full delivery address, then try again.",
}


def read_order_proof(call_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
    """The confirmed order for this call, or None. Never raises into the call path."""
    if not call_id:
        return None
    try:
        path = order_proof_path(call_id)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        logger.warning("[ORDER] proof unreadable call=%s err=%s", call_id, type(exc).__name__)
        return None
    if not isinstance(record, dict):
        return None
    if tenant_id is not None and str(record.get("tenant_id") or "") != str(tenant_id):
        return None
    return record


def order_details_present(proof: dict[str, Any] | None) -> bool:
    if not isinstance(proof, dict) or proof.get("status") != "confirmed":
        return False
    if _quantity(proof.get("quantity")) is None:
        return False
    return len(_clean(proof.get("customer_name"), 120)) >= 2 and len(
        _clean(proof.get("delivery_address"), 400)
    ) >= 4


def has_order_proof(call_id: str | None) -> bool:
    return bool(call_id) and order_details_present(read_order_proof(str(call_id)))


def record_order_confirmation(
    *,
    call_id: str,
    tenant_id: str | None,
    agent_id: str | None,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate and persist the order proof. Idempotent per call.

    A second call returns the first confirmed order untouched, so a retry or a
    duplicate tool call cannot replace a verified order with new values.
    """
    if not call_id or not tenant_id or not agent_id:
        return {"status": "error", "code": "unauthorized", "message": "This action is unavailable."}
    existing = read_order_proof(call_id, tenant_id=tenant_id)
    if order_details_present(existing):
        return {
            "status": "ok",
            "order_confirmed": True,
            "already_confirmed": True,
            "quantity": existing.get("quantity"),
        }
    fields, code = validate_order_arguments(arguments)
    if code or fields is None:
        return {
            "status": "error",
            "code": code or "invalid_order",
            "message": _ORDER_TOOL_MESSAGES.get(code or "", "Collect the missing details and try again."),
        }
    record = {
        "version": 1,
        "call_id": call_id,
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
        "status": "confirmed",
        "quantity": fields["quantity"],
        "customer_name": fields["customer_name"],
        "delivery_address": fields["delivery_address"],
        "product": fields["product"],
        "confirmed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        path = order_proof_path(call_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except (ValueError, OSError) as exc:
        logger.warning("[ORDER] proof write failed call=%s err=%s", call_id, type(exc).__name__)
        return {
            "status": "unknown",
            "code": "proof_write_failed",
            "message": "The order could not be recorded. Do not tell the caller it is confirmed.",
        }
    # Counts only: the address and name stay in the access-controlled call record.
    logger.info(
        "[ORDER] confirmed call=%s quantity=%s product=%s",
        call_id,
        fields["quantity"],
        "yes" if fields["product"] else "no",
    )
    return {
        "status": "ok",
        "order_confirmed": True,
        "already_confirmed": False,
        "quantity": fields["quantity"],
    }


def enforce_order_proof(
    outcome: dict[str, Any],
    proof: dict[str, Any] | None,
) -> str | None:
    """Downgrade an unproven conversion/order claim. Returns a reason code.

    `qualified` is a normal CRM judgement for non-order businesses, so it is
    only gated when the outcome itself asserts an order/booking was confirmed.
    `converted` always means the goal was achieved and needs the proof.
    """
    from server.call.memory_guard import commerce_conclusion

    disposition = str(outcome.get("disposition") or "").strip().lower()
    verified = order_details_present(proof)
    reason: str | None = None
    if disposition == "converted" and not verified:
        outcome["disposition"] = "interested"
        reason = "order_proof_missing"
    elif disposition == "qualified" and not verified:
        narrative = " ".join(
            str(outcome.get(key) or "")
            for key in ("summary_en", "summary_te", "next_action", "notes")
        )
        if claims_order_confirmation(narrative):
            outcome["disposition"] = "interested"
            reason = "order_proof_missing"
    if not verified:
        for field_name in ("facts", "extracted_fields"):
            values = outcome.get(field_name)
            if not isinstance(values, dict):
                continue
            outcome[field_name] = {
                key: value
                for key, value in values.items()
                if not commerce_conclusion(str(key), str(value))
            }
    return reason
