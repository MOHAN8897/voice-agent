"""A text, WhatsApp message or email states only facts the agent was given.

The model fills in what it does not know: live tests sent a caller opening
hours ("Mon-Sat 9 AM to 7 PM") that appear nowhere in the business's script.
Spoken, that is a slip; written into a message it is a promise. Before a
message to the caller goes out during a call, each time, price or other number
in it must appear in the agent's instructions, the business answers looked up
this call, this call's action results, or what the caller said.

Words are not checked (an address can be rephrased); numbers cannot be, and
they are what a caller acts on.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Action -> the arguments holding the text that reaches the caller.
CHECKED_TEXT = {
    "TWILIO_SMS_SEND_MESSAGE": ("body",),
    "WHATSAPP_SEND_MESSAGE": ("message",),
    "GMAIL_SEND_EMAIL": ("subject", "body"),
    "SENDGRID_SEND_EMAIL": ("subject", "body"),
}

# Digit boundaries, not \b: a booking result writes "2026-11-07T11:00".
_TIME = re.compile(r"(?<!\d)(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?\s*m\b\.?", re.IGNORECASE)
# "T15:00" in an ISO timestamp is a 24-hour clock; a bare "3:00" is either half of the day.
_CLOCK = re.compile(r"(?<!\d)(T)?([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _times(text: str) -> set[str]:
    """Times as "HH:MM". A bare clock time of 1-11 (as in "3:00 - 3:30 PM") is
    "~HH:MM": it counts as supported by either half of the day."""
    found = set()
    for hour, minute, half in _TIME.findall(text):
        h = int(hour) % 12 + (12 if half.lower() == "p" else 0)
        found.add(f"{h:02d}:{int(minute or 0):02d}")
    for iso, hour, minute in _CLOCK.findall(_TIME.sub(" ", text)):
        h = int(hour)
        found.add(f"~{h:02d}:{minute}" if 1 <= h <= 11 and not iso else f"{h:02d}:{minute}")
    return found


def _numbers(text: str) -> set[str]:
    """Numbers of two or more digits, without separators (1,999 == 1999)."""
    without_times = _CLOCK.sub(" ", _TIME.sub(" ", text))
    out = set()
    for raw in _NUMBER.findall(without_times):
        digits = raw.replace(",", "").rstrip(".")
        if len(re.sub(r"\D", "", digits)) >= 2:
            out.add(digits.lstrip("0") or "0")
    return out


def facts(text: str) -> set[str]:
    return {f"time {t}" for t in _times(text)} | {f"number {n}" for n in _numbers(text)}


def grounding_text(ctx: Any, caller_turns: list[str], arguments: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Everything the agent was given or learned on this call."""
    parts = [str(getattr(ctx, "compiled_brain_text", "") or "")]
    parts.append(json.dumps(getattr(ctx, "business_answers", None) or [], ensure_ascii=False, default=str))
    parts.append(json.dumps(getattr(ctx, "turn_action_results", None) or [], ensure_ascii=False, default=str))
    parts.extend(caller_turns)
    # The recipient itself is not a claim about the business.
    parts.extend(str(v) for k, v in arguments.items() if k not in fields)
    return "\n".join(parts)


def unsupported(tool_name: str, arguments: dict[str, Any], ctx: Any, caller_turns: list[str]) -> list[str]:
    """Facts in the outgoing text that nothing on this call supports."""
    fields = CHECKED_TEXT.get(str(tool_name).upper())
    if not fields or ctx is None:
        return []
    text = "\n".join(str(arguments.get(f) or "") for f in fields)
    claimed = facts(text)
    if not claimed:
        return []
    known = facts(grounding_text(ctx, caller_turns, arguments, fields))

    def supported(fact: str) -> bool:
        if fact in known:
            return True
        if fact.startswith("time ~"):
            h, m = fact[6:].split(":")
            return any(f"time {x:02d}:{m}" in known or f"time ~{x:02d}:{m}" in known for x in (int(h), int(h) + 12))
        if fact.startswith("time "):
            h, m = fact[5:].split(":")
            return f"time ~{int(h) % 12:02d}:{m}" in known
        return False

    return sorted(f for f in claimed if not supported(f))


def check(call_id: str, tool_name: str, arguments: dict[str, Any], *, business_text: str = "") -> dict[str, Any] | None:
    """None when the message may go out; otherwise a result naming what was made up.

    ``business_text`` is what the business wrote for these messages on the
    Integrations page (a booking link, an address): it counts as given.
    """
    if str(tool_name).upper() not in CHECKED_TEXT or not call_id:
        return None
    from server.call import call_context
    from server.services.recipient_guard import caller_turns

    ctx = call_context.get(str(call_id))
    if ctx is None:
        return None  # Not a live call (a test or a replay): nothing to compare with.
    missing = unsupported(tool_name, arguments, ctx, [*caller_turns(str(call_id)), business_text])
    if not missing:
        return None
    shown = ", ".join(m.split(" ", 1)[1].lstrip("~") for m in missing[:4])
    return {
        "status": "error",
        "message": (f"Nothing was sent: the message states details you were not given ({shown}). Send only facts from "
                    "your instructions or this call. If you do not have what the caller asked for, say so and offer a follow-up."),
    }
