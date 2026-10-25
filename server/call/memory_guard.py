"""Facts only — a model may record what the caller said, never what it concluded.

Call outcomes belong to the close gate, a successful order tool, and the
post-call pipeline. A model-written "firm refusal" becomes a poisoned fact that
every later turn treats as settled truth.
"""
from __future__ import annotations

import re
from typing import Any

# Judgment about this call's intent/outcome. Allowed only on a gate-approved
# close turn, where the server itself established the conclusion.
_CALL_CONCLUSION_KEY = re.compile(
    r"(?:^|_)(?:outcome|disposition|status|close_reason|end_reason|decision|"
    r"firm_refusal|not_interested|closed|dnc|do_not_call|opt_out)(?:$|_)",
    re.I,
)
_CALL_CONCLUSION_VALUE = re.compile(
    r"\b(?:firm refusal|refused|declined|not interested|no interest|opted out|"
    r"do not call|dnc|completed_and_closed|completed and closed|"
    r"conversation (?:is )?closed|call (?:is )?closed|call (?:has )?ended|"
    r"no longer interested|will not buy|not a lead)\b|"
    r"(?:ఆసక్తి\s*లేదు|ఇంట్రెస్ట్\s*లేదు|కాల్\s*అవసరం\s*లేదు|కాల్\s*ముగిసింది)|"
    r"(?:दिलचस्पी\s*नहीं|रुचि\s*नहीं|कॉल\s*समाप्त)|"
    r"(?:ஆர்வம்\s*இல்லை|அழைப்பு\s*முடிந்தது)|"
    r"(?:ಆಸಕ್ತಿ\s*ಇಲ್ಲ|ಕರೆ\s*ಮುಗಿದಿದೆ)|"
    r"(?:ആസക്തി\s*ഇല്ല|കോൾ\s*അവസാനിച്ചു)",
    re.I,
)
# Commerce/lead conclusions. Allowed only when the matching server tool proved
# the action; conversion itself is a post-call decision and never live memory.
_COMMERCE_CONCLUSION_KEY = re.compile(
    r"(?:^|_)(?:converted|qualified|order_confirmed|booking_confirmed|"
    r"purchase|payment_confirmed)(?:$|_)",
    re.I,
)
_COMMERCE_CONCLUSION_VALUE = re.compile(
    r"\b(?:converted|qualified lead|lead (?:is )?(?:qualified|converted)|"
    r"order (?:is )?confirmed|booking (?:is )?confirmed|"
    r"callback (?:is )?(?:scheduled|booked|confirmed|completed)|"
    r"purchased|sale (?:is )?closed)\b",
    re.I,
)
_UPDATE_SUMMARY = "update_summary"

# The caller's current turn is open/positive; a stored decline is stale.
_CURRENT_INTEREST = re.compile(
    r"\b(?:yes|yeah|interested|tell me more|more details|how much|price|cost|"
    r"send (?:me )?(?:details|price|brochure)|whatsapp|visit|demo|book|order|"
    r"available|go ahead)\b|"
    r"(?:ఆసక్తి|ఇంట్రెస్ట్|చెప్పండి|ఎంత|వివరాలు|పంపండి|అవును|సరే)|"
    r"(?:दिलचस्पी|बताइए|कीमत|कितना|विवरण|हाँ|ठीक)|"
    r"(?:ஆர்வம்|சொல்லுங்க|விலை|விவரம்|ஆம்|சரி)",
    re.I,
)


def _calls_conclusion(key: str, value: str) -> bool:
    return bool(_CALL_CONCLUSION_KEY.search(key) or _CALL_CONCLUSION_VALUE.search(value))


def commerce_conclusion(key: str, value: str) -> bool:
    """A stored order/conversion judgement, not a fact the caller stated."""
    return bool(
        _COMMERCE_CONCLUSION_KEY.search(key) or _COMMERCE_CONCLUSION_VALUE.search(value)
    )


def sanitize_model_operations(
    operations: Any,
    *,
    close_approved: bool = False,
    order_proof: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep facts; reject conclusions the gate/tool has not proven."""
    ops = operations if isinstance(operations, list) else []
    kept: list[dict[str, Any]] = []
    rejected: list[str] = []
    for raw in ops:
        if not isinstance(raw, dict):
            continue
        op = str(raw.get("op") or "").strip()
        if op == _UPDATE_SUMMARY:
            rejected.append("model_update_summary")
            continue
        key = str(raw.get("key") or "")
        value = str(raw.get("value") or "")
        if commerce_conclusion(key, value):
            if not order_proof:
                rejected.append(f"commerce_conclusion:{key or op}")
                continue
        elif _calls_conclusion(key, value) and not close_approved:
            rejected.append(f"call_conclusion:{key or op}")
            continue
        kept.append(raw)
    return kept, rejected


def suppress_stale_conclusions(
    snapshot: dict[str, Any] | None,
    caller_text: str,
) -> dict[str, Any]:
    """Drop stored decline/close notes when the caller's current words are open."""
    snap = snapshot or {}
    text = caller_text or ""
    if not text.strip() or not _CURRENT_INTEREST.search(text):
        return snap
    # The caller is reaffirming the decline: the stored note is still current.
    if _CALL_CONCLUSION_VALUE.search(text):
        return snap
    filtered = dict(snap)
    for field_name in ("facts", "preferences"):
        values = snap.get(field_name)
        if not isinstance(values, dict):
            continue
        filtered[field_name] = {
            key: value
            for key, value in values.items()
            if not _calls_conclusion(str(key), str(value))
        }
    return filtered
