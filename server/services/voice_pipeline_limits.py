"""Text chunking and live reply limits shared with web VOICE_PIPELINE_LIMITS (types.ts)."""

from __future__ import annotations

import re

MIN_CHUNK_CHARS = 14
FIRST_CHUNK_MIN_CHARS = 18
# Disabled: comma/semicolon splits caused mid-thought TTS pauses on PSTN and web.
CLAUSE_FLUSH_AT = 10_000
# Last-resort cap for unpunctuated runs; matches LIVE_REPLY_MAX_CHARS below.
FORCE_FLUSH_AT = 280

# Prompt tiers (TTS billed per char). Hard safety never unnecessarily approaches the ceiling.
LIVE_REPLY_SIMPLE_MAX = 55
LIVE_REPLY_NORMAL_MAX = 100
LIVE_REPLY_OBJECTION_MAX = 85
LIVE_REPLY_COMPLEX_MAX = 145
LIVE_REPLY_MIN_CHARS = 15
LIVE_REPLY_AIM_CHARS = 95
LIVE_REPLY_SOFT_MAX_CHARS = 200
# The model targets the soft limit. The larger runtime/schema ceiling gives it
# enough room to finish the current sentence instead of producing "pickup is."
LIVE_REPLY_MAX_CHARS = 280
# Realtime models burn tokens on punctuation/formatting; 96 was cutting mid-word ("lak.").
# Char clamp still enforces the ceiling at a sentence boundary. 240 leaves room for Telugu.
LIVE_MAX_OUTPUT_TOKENS = 240

_SENTENCE_END = re.compile(r"[.!?।](?=\s|$)")
_DANGLING_TAIL = re.compile(
    r"(?:[\s,]+|\b)(?:or|and|but|so|to|for|from|with|if|when|that|the|a|an)\.?$",
    re.I,
)
_GLUED_SENTENCE = re.compile(r"([.!?।])(?=[A-Za-z\u0C00-\u0C7F\u0900-\u097F])")
_GREETING_START = re.compile(
    r"^(?:hi|hello|hey|namaste|namaskar)\b.{0,80}?\b(?:this is|nenu|main)\b",
    re.I,
)
_VALID_SHORT_REPLY = re.compile(
    r"^(?:ok|okay|yes|no|sure|thanks|thank you|got it|noted|hello|hi|bye|goodbye|"
    r"sare|hmm|mm|aha|అవును|సరే|ठीक|हाँ)\.?$",
    re.I,
)
_MIDWORD_STUMP = re.compile(
    r"\b(?:lak|cro|rupee|from|with|and|or|the|we|i|to|for|a|an)\.$",
    re.I,
)


def is_incomplete_spoken_crumb(text: str) -> bool:
    """True for barge/token-cut fragments that must not be spoken or archived as a reply."""
    t = (text or "").strip()
    if not t:
        return True
    if _VALID_SHORT_REPLY.match(t):
        return False
    if _MIDWORD_STUMP.search(t) and len(t) < 100:
        return True
    words = t.split()
    # Finished short sentences ("Hello." / "Noted.") are valid — only flag unfinished crumbs.
    if len(t) < 20 and len(words) <= 3 and t[-1] in ".?!।":
        return False
    if len(t) < 20 and len(words) <= 3 and not re.search(r"[.!?।]\s+\S", t):
        if len(words) <= 2:
            return True
    return False

LIVE_REPLY_BREVITY_RULE = (
    "LENGTH (natural phone speech):\n"
    "- Primary rule: 1–2 concise spoken sentences, normally 8–25 words in English, "
    "or an equally concise spoken equivalent in Telugu or Hindi. Answer the immediate question first.\n"
    "- Avoid unnecessary explanations and monologues. Character bands below are secondary "
    "safety guidance, not a reason to break natural spoken phrasing.\n"
    f"- Simple (yes / ack / thanks / wait): {LIVE_REPLY_MIN_CHARS}–{LIVE_REPLY_SIMPLE_MAX} characters.\n"
    f"- Normal fact or answer: 30–{LIVE_REPLY_NORMAL_MAX} characters.\n"
    f"- Objection: 30–{LIVE_REPLY_OBJECTION_MAX} characters.\n"
    f"- Complex (ack + option + next step, or ack + one lead question): 70–{LIVE_REPLY_COMPLEX_MAX} characters.\n"
    f"- Finish naturally within {LIVE_REPLY_SOFT_MAX_CHARS} characters when possible. "
    f"Hard safety ceiling: {LIVE_REPLY_MAX_CHARS} characters; never cut a sentence merely to hit the soft target.\n"
    "Sound human: one or two short phone beats. "
    "A warm acknowledgment plus ONE next question is good sales talk — never two questions. "
    "Answer then stop — do not keep talking once the point is made. "
    "Decisive and professional: no monologues, no brochure dumps, no trailing extras after the question. "
    "After you ask something, end the turn and wait for their answer. "
    "Answer then progress — do not pad with catalog or disclaimer. "
    "Finish the thought (no trailing or/and/from). "
    "Never paste a greeting then restart with a second greeting in the same reply."
)

# One-line form for LIVE CALL GUIDE / compact pointers (same numbers as above).
LIVE_REPLY_BREVITY_COMPACT = (
    "1–2 concise spoken sentences; normally 8–25 English words, or a concise Telugu/Hindi equivalent. "
    "Answer first. Secondary character safety bands: "
    f"LENGTH: simple {LIVE_REPLY_MIN_CHARS}–{LIVE_REPLY_SIMPLE_MAX}; "
    f"normal 30–{LIVE_REPLY_NORMAL_MAX}; "
    f"objection 30–{LIVE_REPLY_OBJECTION_MAX}; "
    f"complex 70–{LIVE_REPLY_COMPLEX_MAX}; "
    f"soft target {LIVE_REPLY_SOFT_MAX_CHARS}, hard ceiling {LIVE_REPLY_MAX_CHARS}. "
    "Finish the sentence. Human phone speech — warm ack + at most one question."
)


def spoken_delta_after_collapse(prev: str, new_piece: str) -> tuple[str, str]:
    """Return (delta_to_speak, collapsed_accum) after de-duplicating model restarts."""
    piece = (new_piece or "").strip()
    if not piece:
        return "", (prev or "").strip()
    proposed = f"{prev} {piece}".strip() if prev else piece
    collapsed = collapse_repeated_spoken_reply(proposed)
    if not collapsed:
        return "", prev
    prior = (prev or "").strip()
    if not prior:
        return collapsed, collapsed
    if collapsed.startswith(prior):
        delta = collapsed[len(prior) :].strip()
        return delta, collapsed
    if prior in collapsed:
        idx = collapsed.find(prior)
        delta = collapsed[idx + len(prior) :].strip()
        if delta:
            return delta, collapsed
    return piece, collapsed


def collapse_repeated_spoken_reply(text: str) -> str:
    """
    Drop model 'restart' doubles: canned opening then a second take.

    Example:
      'Hi, this is Priya... help today?Hi, this is Priya... doing well... help today?'
    → keep the second (usually more complete) take.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    # Normalize "...today?Hi" → "...today? Hi" so prefix search works.
    spaced = _GLUED_SENTENCE.sub(r"\1 ", cleaned)
    if spaced != cleaned:
        cleaned = " ".join(spaced.split())

    n = len(cleaned)
    if n < 40:
        return cleaned

    if n % 2 == 0 and cleaned[: n // 2] == cleaned[n // 2 :]:
        half = cleaned[: n // 2].strip()
        # Require speech-like content (not "AAAA…AAAA" synthetic fills).
        if " " in half and re.search(r"[A-Za-z\u0C00-\u0C7F\u0900-\u097F]{3,}", half):
            return half

    for i, ch in enumerate(cleaned):
        if ch in ".?!" and i + 1 < n:
            left = cleaned[: i + 1].strip()
            right = cleaned[i + 1 :].strip()
            if len(left) >= 20 and left == right:
                return left

    min_prefix = 18
    max_prefix = min(90, n // 2)
    for plen in range(max_prefix, min_prefix - 1, -1):
        prefix = cleaned[:plen]
        if not re.search(r"[A-Za-z\u0C00-\u0C7F\u0900-\u097F]{3,}", prefix):
            continue
        # Prefer break at a word/punct boundary for the prefix tip.
        if plen < n and cleaned[plen - 1].isalnum() and cleaned[plen].isalnum():
            continue
        second_at = cleaned.find(prefix, plen)
        if second_at < plen:
            continue
        gap = cleaned[plen:second_at].strip()
        # Allow empty/punct gap, or one finished short sentence before the restart.
        if gap and gap[-1] not in ".?!।" and gap not in {".", "?", "!", "।"}:
            continue
        if gap and len(gap) > 90:
            continue
        first = cleaned[:second_at].strip()
        second = cleaned[second_at:].strip()
        if len(second) < 20:
            continue
        # Prefer the later take when it is at least ~80% as long (usually answers the caller).
        if len(second) >= max(24, int(len(first) * 0.8)):
            return second
        return first

    return cleaned


def clamp_live_spoken_reply(text: str, *, max_chars: int | None = None) -> str:
    """Hard safety trim at a sentence/word boundary — never leave a dangling mid-clause."""
    limit = int(max_chars or LIVE_REPLY_MAX_CHARS)
    cleaned = collapse_repeated_spoken_reply((text or "").strip())
    if len(cleaned) <= limit:
        return _strip_dangling_clause(cleaned)

    chunk = cleaned[:limit]
    last_sent = None
    for match in _SENTENCE_END.finditer(chunk):
        last_sent = match
    if last_sent is not None and last_sent.end() >= max(int(limit * 0.35), 24):
        out = _strip_dangling_clause(chunk[: last_sent.end()].strip())
    elif " " in chunk:
        trimmed = chunk.rsplit(" ", 1)[0].strip()
        if trimmed:
            prior = None
            for match in _SENTENCE_END.finditer(trimmed):
                prior = match
            if prior is not None and prior.end() >= 24:
                out = _strip_dangling_clause(trimmed[: prior.end()].strip())
            else:
                out = _strip_dangling_clause(trimmed)
        else:
            out = _strip_dangling_clause(chunk.strip())
    else:
        # No ASCII spaces (common for Telugu/Hindi runs) — back up from combining marks.
        cut = limit
        while cut > max(24, int(limit * 0.5)) and _is_indic_combining(cleaned[cut - 1]):
            cut -= 1
        out = _strip_dangling_clause(cleaned[:cut].strip())
    if len(out) > limit:
        out = out[:limit].rstrip(" .,;:")
        if out and out[-1] not in ".?!।":
            out = out[:-1].rstrip() if len(out) > 1 else out
    return out


def _is_indic_combining(ch: str) -> bool:
    """True for virama / vowel signs that must not start a clipped tail alone."""
    if not ch:
        return False
    o = ord(ch)
    # Telugu vowel signs / virama, Devanagari vowel signs / virama (common live-call scripts).
    return (
        0x0C3E <= o <= 0x0C4D
        or 0x093A <= o <= 0x094D
        or o in {0x0C01, 0x0C02, 0x0C03, 0x0901, 0x0902, 0x0903}
    )


def _strip_dangling_clause(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    stripped = _DANGLING_TAIL.sub("", cleaned).rstrip(" ,;")
    if not stripped:
        return cleaned
    last = None
    for match in _SENTENCE_END.finditer(stripped):
        last = match
    if last is not None:
        tail = stripped[last.end() :].strip()
        if tail and len(tail) < 18:
            return stripped[: last.end()].strip()
    if stripped[-1] not in ".?!।":
        return stripped + "."
    return stripped


class LiveReplyStreamCap:
    """Hard safety cap. Suppress only clear greeting restarts — not normal speech."""

    def __init__(self, *, max_chars: int | None = None) -> None:
        self.max_chars = int(max_chars or LIVE_REPLY_MAX_CHARS)
        self._emitted = ""
        self._suppress = False

    @property
    def emitted(self) -> str:
        return self._emitted

    @property
    def exhausted(self) -> bool:
        return self._suppress or len(self._emitted) >= self.max_chars

    def feed(self, delta: str) -> str:
        piece = str(delta or "")
        if not piece or self.exhausted:
            return ""
        combined = self._emitted + piece
        if len(combined) >= 40 and self._emitted:
            collapsed = collapse_repeated_spoken_reply(combined)
            if collapsed != combined:
                if collapsed.startswith(self._emitted):
                    out = collapsed[len(self._emitted) :]
                elif self._emitted and self._emitted in collapsed:
                    idx = collapsed.find(self._emitted)
                    out = collapsed[idx + len(self._emitted) :].lstrip()
                else:
                    # Hard restart — stop streaming; finalize() returns the collapsed reply.
                    self._emitted = clamp_live_spoken_reply(collapsed, max_chars=self.max_chars)
                    self._suppress = True
                    return ""
                self._emitted = clamp_live_spoken_reply(collapsed, max_chars=self.max_chars)
                if len(self._emitted) >= self.max_chars:
                    self._suppress = True
                return out
        if len(combined) <= self.max_chars:
            self._emitted = combined
            return piece
        allowed = clamp_live_spoken_reply(combined, max_chars=self.max_chars)
        if len(allowed) <= len(self._emitted):
            self._emitted = allowed
            self._suppress = True
            return ""
        out = allowed[len(self._emitted) :]
        self._emitted = allowed
        if len(self._emitted) >= self.max_chars:
            self._suppress = True
        return out

    def finalize(self, full_text: str) -> str:
        text = clamp_live_spoken_reply(full_text or self._emitted, max_chars=self.max_chars)
        if is_incomplete_spoken_crumb(text):
            self._emitted = ""
            return ""
        self._emitted = text
        return self._emitted
