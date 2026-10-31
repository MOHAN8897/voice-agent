"""Deterministic do-not-call detection for when the brain cannot answer.

Normally the model reads the caller's words and records an opt-out through the
contact-preference path. During a model outage nothing reads them, so a caller
who said "never call me again" just before the failure would be dialled back by
the outage retry. This check is cheap, offline and multi-language; it only ever
*adds* a do-not-call record, and it never decides anything for a healthy call.

It reuses the live opt-out evidence (``close_decision.opt_out_evidence``) and
adds phrasings that evidence set does not cover: DND / unsubscribe wording,
"remove my number", and romanised Hindi / Telugu / Tamil.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_EXTRA_OPT_OUT = re.compile(
    # English
    r"\b(?:dnd|do\s+not\s+disturb|unsubscribe|opt\s*(?:me\s+)?out)\b|"
    r"\b(?:remove|delete|take\s+off)\s+(?:my|this)\s+(?:number|name|contact)|"
    r"\b(?:don'?t|do\s+not)\s+want\s+(?:any\s+)?(?:more\s+)?(?:calls|to\s+be\s+called)|"
    r"\bno\s+more\s+calls\b|\bstop\s+(?:calling|contacting)\b|"
    # Hindi (Devanagari + romanised)
    r"(?:नंबर|नम्बर).{0,24}(?:हटा|हटाओ|डिलीट|निकाल)|"
    r"\b(?:dobara|phir\s+se|kabhi)\s+(?:call|phone|fon)\s+(?:mat|nahi|na)\b|"
    r"\b(?:call|phone)\s+mat\s+(?:karna|karo|kijiye|kijie|karein|karen)\b|"
    r"\bnumber\s+(?:hata|delete|remove)|"
    # Telugu (script + romanised)
    r"(?:నంబర్|నెంబర్|నంబరు).{0,24}(?:తీసేయ|తొలగించ|డిలీట్)|"
    r"\b(?:call|phone)\s+(?:cheyyakandi|cheyakandi|cheyyodhu|cheyyoddu|cheyodhu|vaddu)\b|"
    # Tamil (script + romanised)
    r"(?:கால்|போன்|அழைக்க).{0,24}(?:பண்ணாதீங்க|பண்ணாதீர்கள்|பண்ணாத|செய்யாத)|"
    r"(?:நம்பர|எண்ணை|எண்).{0,24}(?:நீக்க|எடுத்துடுங்க|எடுத்து\s*விடுங்க)|"
    r"\b(?:call|phone)\s+(?:pannatheenga|pannadheenga|pannatheengo|panna\s+vendam|venda)\b",
    re.IGNORECASE,
)

# "Call me later / tomorrow" is a scheduling request, never an opt-out; "don't
# cut the call" asks the opposite. These win over every pattern above.
_NOT_OPT_OUT = re.compile(
    r"\b(?:tomorrow|later|evening|morning|after\s+\w+\s+(?:minutes|hours|days))\b|"
    r"\bkal\b|\bbaad\s+mein\b|\brepu\b|\bnaalai\b|"
    r"कल|बाद\s*में|రేపు|తర్వాత|நாளை|பிறகு|"
    r"\b(?:don'?t|do\s+not)\s+(?:cut|disconnect|hang\s*up)\b",
    re.IGNORECASE,
)
_PERMANENT = re.compile(r"\b(?:never|permanently|remove|dnd)\b|ఎప్పటికీ|कभी\s*नहीं|ஒருபோதும்", re.IGNORECASE)


def caller_opted_out(text: str | None) -> bool:
    """True only when the caller's own words ask to stop being contacted."""
    raw = (text or "").strip()
    if not raw:
        return False
    try:
        from server.call.close_decision import opt_out_evidence

        if opt_out_evidence(raw):
            return True
    except Exception:
        pass
    if _NOT_OPT_OUT.search(raw) and not _PERMANENT.search(raw):
        return False
    try:
        from server.call.caller_intent import is_negated_end

        if is_negated_end(raw):
            return False
    except Exception:
        pass
    return bool(_EXTRA_OPT_OUT.search(raw))


def opt_out_in_transcript(rows: Iterable[dict[str, Any]], *extra_user_text: str | None) -> str | None:
    """The first caller line that is an opt-out, scanning ledger rows then pending text."""
    for row in rows or ():
        if str(row.get("role") or "").lower() not in ("user", "caller"):
            continue
        text = str(row.get("text") or "")
        if caller_opted_out(text):
            return text
    for text in extra_user_text:
        if text and caller_opted_out(text):
            return str(text)
    return None


async def record_outage_opt_out(call_id: str | None, evidence: str) -> bool:
    """Persist the opt-out through the normal contact-preference path (DNC + queue suppression)."""
    if not call_id:
        return False
    from server.call.contact_preference import record_contact_preference
    from server.utils.logger import log_pstn

    try:
        value = await record_contact_preference(call_id, "do_not_call")
    except Exception as exc:
        log_pstn("outage.opt_out.record_failed", call_id=call_id, error_type=type(exc).__name__)
        return False
    try:
        from server.call.call_ledger import call_ledger

        meta = call_ledger.read_meta(call_id) or {}
        meta["outage_opt_out_detected"] = True
        meta["outage_opt_out_evidence"] = (evidence or "")[:200]
        call_ledger.write_meta(call_id, meta)
    except Exception:
        pass
    log_pstn("outage.opt_out.recorded", call_id=call_id, preference=value)
    return value == "do_not_call"
