"""WhatsApp/SMS go to the caller's own number, or to one the caller said and confirmed.

The model writes the recipient number itself. A misheard digit, or a caller
asking "send it to my friend", would otherwise message someone who never
opted in. The caller's own number (the one on this call) needs no read-back.
Another number must appear in the caller's own words and is read back once,
like an email address; a number the caller never said is refused.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

PHONE_RECIPIENT = {"WHATSAPP_SEND_MESSAGE": "to", "TWILIO_SMS_SEND_MESSAGE": "to"}
_MAX_PENDING = 4096
_pending: OrderedDict[tuple[str, str], int] = OrderedDict()


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _same_number(a: str, b: str) -> bool:
    """Same subscriber number, ignoring country code and leading zeros."""
    return bool(a) and bool(b) and len(a) >= 8 and len(b) >= 8 and a[-10:] == b[-10:]


def check(call_id: str, tool_name: str, arguments: dict[str, Any], *, caller_phone: str = "") -> dict[str, Any] | None:
    """None when the message may go out; otherwise a result for the agent to act on."""
    field = PHONE_RECIPIENT.get(str(tool_name or "").upper())
    if not field or not call_id:
        return None
    target = _digits(arguments.get(field))
    if not target:
        return None
    if _same_number(target, _digits(caller_phone)):
        return None
    from server.services.recipient_guard import caller_turns

    turns = caller_turns(call_id)
    said = _digits(" ".join(turns))
    if target[-10:] not in said:
        return {"status": "error",
                "message": ("Nothing was sent. Messages go only to the caller's own number or to a number the caller "
                            "said on this call. Ask the caller which number to use.")}
    key = (str(call_id), target[-10:])
    asked = _pending.get(key)
    if asked is not None and len(turns) > asked:
        _pending.pop(key, None)
        return None
    _pending[key] = len(turns)
    _pending.move_to_end(key)
    while len(_pending) > _MAX_PENDING:
        _pending.popitem(last=False)
    spoken = " ".join(target[-10:])
    return {"status": "needs_confirmation",
            "message": (f"Nothing was sent yet. Read the number back to the caller ({spoken}) and ask if it is right. "
                        "If they say yes, do this again with exactly the same number.")}


def reset_for_tests() -> None:
    _pending.clear()
