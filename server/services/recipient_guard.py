"""An in-call email goes only to an address the caller gave.

The model writes the address from what it heard, and one wrong letter sends
the caller's booking or details to a stranger. Before an action that emails
someone runs during a call, the address must appear in the caller's own words
this call, or the agent must have read it back and the caller answered.
Drafts (reviewed by a person) and stored records (nothing is sent) are not
covered.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

# Action -> the argument whose address the provider emails right away.
MAIL_RECIPIENT = {
    "GMAIL_SEND_EMAIL": "to",
    "SENDGRID_SEND_EMAIL": "to",
    "GOOGLECALENDAR_CREATE_EVENT": "attendee_email",
    "CALENDLY_CREATE_INVITEE": "invitee_email",
    "CALCOM_CREATE_BOOKING": "email",
    "MAILCHIMP_ADD_SUBSCRIBER": "email",
    "ZENDESK_CREATE_TICKET": "requester_email",
    "FRESHDESK_CREATE_TICKET": "email",
}

_NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = {"twenty": 2, "thirty": 3, "forty": 4, "fifty": 5, "sixty": 6, "seventy": 7, "eighty": 8, "ninety": 9}
_SPOKEN = [
    (re.compile(r"\bat the rate( of)?\b"), "@"),
    (re.compile(r"\bat\b"), "@"),
    (re.compile(r"\b(dot|period|point)\b"), "."),
    (re.compile(r"\bunderscore\b"), "_"),
    (re.compile(r"\b(dash|hyphen)\b"), "-"),
    *[(re.compile(rf"\b{word}\b"), str(10 + n)) for n, word in enumerate(_TEENS)],
    *[(re.compile(rf"\b{tens}[\s-]+{unit}\b"), f"{d}{u}") for tens, d in _TENS.items()
      for u, unit in enumerate(_NUMBERS) if u],
    *[(re.compile(rf"\b{tens}\b"), f"{d}0") for tens, d in _TENS.items()],
    *[(re.compile(rf"\b{word}\b"), str(digit)) for digit, word in enumerate(_NUMBERS)],
    # Indian English "double nine", "triple seven" (the words are digits by now).
    (re.compile(r"\bdouble\s*(\S)"), r"\1\1"),
    (re.compile(r"\btriple\s*(\S)"), r"\1\1\1"),
]
_ADDRESS = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)
_MAX_PENDING = 4096
# (call, address) -> how many caller turns had been heard when the agent was told to read it back.
_pending: OrderedDict[tuple[str, str], int] = OrderedDict()


def spoken_form(text: str) -> str:
    """Caller speech as one run of characters: "mohan dot 99 at gmail dot com" -> "mohan.99@gmail.com"."""
    out = str(text or "").casefold()
    for pattern, symbol in _SPOKEN:
        out = pattern.sub(symbol, out)
    return re.sub(r"\s+", "", out)


def written_address(value: str) -> str:
    """An address as written, from what speech recognition heard; "" when it is not one."""
    candidate = spoken_form(value)
    return candidate if _ADDRESS.fullmatch(candidate) else ""


def spelled(address: str) -> str:
    local, _, domain = address.partition("@")
    letters = " ".join({".": "dot", "_": "underscore", "-": "dash"}.get(ch, ch) for ch in local)
    return f"{letters}, at {domain.replace('.', ' dot ')}" if domain else letters


def recipient(tool_name: str, arguments: dict[str, Any]) -> str:
    field = MAIL_RECIPIENT.get(str(tool_name).upper())
    value = arguments.get(field) if field and isinstance(arguments, dict) else None
    return value.strip() if isinstance(value, str) else ""


def caller_turns(call_id: str) -> list[str]:
    from server.call.call_ledger import call_ledger

    try:
        return [str(line.get("text") or "") for line in call_ledger.read_lines(call_id) if line.get("role") == "user"]
    except Exception:  # noqa: BLE001 - no transcript means nothing is confirmed
        return []


def check(call_id: str, tool_name: str, arguments: dict[str, Any], *, converted: bool = False) -> dict[str, Any] | None:
    """None when the email may go out; otherwise a result asking for a read-back.

    ``converted`` marks an address the server wrote from spoken words. It is
    always read back: a misheard letter cannot be caught against the very
    transcript it came from.
    """
    address = recipient(tool_name, arguments)
    if not address or not call_id:
        return None
    turns = caller_turns(call_id)
    if not converted and spoken_form(address) in spoken_form(" ".join(turns)):
        return None
    key = (str(call_id), address.casefold())
    asked = _pending.get(key)
    if asked is not None and len(turns) > asked:
        # Read back, and the caller has answered since: the model only repeats
        # the action when that answer was a yes.
        _pending.pop(key, None)
        return None
    _pending[key] = len(turns)
    _pending.move_to_end(key)
    while len(_pending) > _MAX_PENDING:
        _pending.popitem(last=False)
    return {
        "status": "needs_confirmation",
        "message": (f"Nothing was sent yet. Read the email address back to the caller ({spelled(address)}) "
                    "and ask if it is right. If they say yes, do this again with exactly the same address; "
                    "if not, ask them to spell it."),
    }


def reset_for_tests() -> None:
    _pending.clear()
