"""Sentence buffering for streaming PSTN TTS (brain deltas → speakable chunks)."""
from __future__ import annotations

import re

from server.services.voice_pipeline_limits import (
    FORCE_FLUSH_AT,
    MIN_CHUNK_CHARS,
)

# End sentence on Latin/Telugu punctuation (not decimal points like 80.5), or newline.
_SENTENCE_END = re.compile(r"(?<=[.!?।])(?!\d)\s*|\n+")


def _last_word_boundary(text: str, max_index: int) -> int:
    slice_ = text[:max_index]
    sp = slice_.rfind(" ")
    return sp if sp > 0 else max_index


def drain_complete_sentences(
    buffer: str,
    *,
    min_chars: int = MIN_CHUNK_CHARS,
    allow_first_fast: bool = False,
) -> tuple[list[str], str]:
    """Return complete sentences from buffer; keep trailing partial text."""
    if not buffer.strip():
        return [], buffer

    complete: list[str] = []
    remainder = buffer
    # Kept for API compatibility. A first chunk now follows the same prosody-safe
    # boundaries as every other chunk: punctuation, a substantial clause, or the
    # force-flush guard. Arbitrary token arrival boundaries are not speech boundaries.
    _ = allow_first_fast

    while remainder.strip():
        parts = _SENTENCE_END.split(remainder, maxsplit=1)
        if len(parts) > 1:
            piece = parts[0].strip()
            if piece and len(piece) >= min_chars:
                complete.append(piece)
            remainder = parts[1]
            continue

        stripped = remainder.strip()
        if len(stripped) >= FORCE_FLUSH_AT:
            # Prefer a word/space boundary so compounds are not sliced mid-token.
            # If there is no space at all, flush the whole buffer (legacy safe path).
            if " " not in stripped[:FORCE_FLUSH_AT]:
                complete.append(stripped)
                remainder = ""
                break
            cut = _last_word_boundary(stripped, FORCE_FLUSH_AT)
            if cut < min_chars:
                complete.append(stripped)
                remainder = ""
                break
            piece = stripped[:cut].strip()
            if piece:
                complete.append(piece)
            remainder = stripped[cut:].lstrip()
            if not remainder:
                break
            continue

        break

    return complete, remainder


def join_speakable_chunks(chunks: list[str]) -> str:
    """One TTS utterance from sentences drained in the same token batch."""
    return " ".join(piece.strip() for piece in chunks if piece and piece.strip())


def resolve_stream_tts_tail(pending: str, full_text: str, *, spoke_from_stream: bool) -> str | None:
    """Return remaining PSTN TTS text after streaming deltas; avoid replaying full_text."""
    tail = pending.strip()
    if tail:
        return tail
    if spoke_from_stream:
        return None
    return (full_text or "").strip() or None


_OPENING_POLICY_HINT = re.compile(
    r"(?:never paste|spoken reply per turn|if you speak first|if the caller already|"
    r"do not dump|pstn/outbound|still identifies? you|canned opening|"
    r"one spoken reply|say that opening once)",
    re.IGNORECASE,
)
_EXAMPLE_OPENING = re.compile(
    r"^(?:example\s+(?:opening|first\s+line)|opening(?:_line(?:_te)?)?)\s*:\s*[\"']?(.+?)[\"']?\s*$",
    re.IGNORECASE,
)
_OPENING_SECTION = re.compile(
    r"(?:^|\n)---\s*(?:OPENING(?:\s+HINT)?|CANONICAL\s+OPENING)\s*---\s*\n(.*?)(?=\n---\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _spoken_opening_candidate(line: str) -> str | None:
    """Return a single speakable greeting line, or None for policy / junk."""
    raw = (line or "").strip().strip("-").strip()
    if not raw or raw.endswith(":"):
        return None
    upper = raw.upper()
    if upper.startswith(
        (
            "VOICE",
            "CONVERSATION",
            "GUARD",
            "SAY THIS",
            "WORK SCOPE",
            "--- ",
            "LIVE CALL",
            "SPEAK NATURAL",
            "INTRODUCE YOURSELF",
        )
    ):
        return None
    m = _EXAMPLE_OPENING.match(raw)
    if m:
        raw = m.group(1).strip().strip('"').strip("'")
    low = raw.lower()
    if low.startswith((
        "opening_line",
        "say this",
        "one spoken",
        "if you speak",
        "if the caller",
        # An all-caps imperative is an instruction to the model, never a greeting
        # the agent should speak. Labelled-opening extraction widened what reaches
        # here, so policy prose must be rejected here rather than read aloud.
        "never ",
        "do not ",
        "don't ",
        "always ",
        "you must ",
    )):
        return None
    if _OPENING_POLICY_HINT.search(raw):
        return None
    if len(raw) < 8:
        return None
    # One utterance only — cut at a second question if a bad script stacked beats.
    parts = re.split(r"(?<=[.!?])\s+", raw)
    if len(parts) > 2:
        raw = " ".join(parts[:2]).strip()
    return raw[:280]


def _parse_agent_identity(compiled_brain: str) -> tuple[str, str]:
    """@entity tags first, then --- AGENT IDENTITY --- (You are Name, calling from Co.)."""
    from server.brain.script_entities import parse_entity_tags

    tags = parse_entity_tags(compiled_brain)
    if tags.get("agent_name"):
        return tags["agent_name"].strip(), (tags.get("company_name") or "").strip()
    block = re.search(
        r"(?:^|\n)---\s*AGENT IDENTITY\s*---\s*\n(.*?)(?=\n---\s|\Z)",
        compiled_brain or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not block:
        return "", ""
    first = (block.group(1) or "").strip().splitlines()[0].strip()
    if not first:
        return "", ""
    m = re.match(r"You are\s+([^,]+),\s*calling from\s+([^.]+)\.", first, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m_rep = re.search(
        r"representing\s+([^.]+)\.",
        first,
        flags=re.IGNORECASE,
    )
    m2 = re.match(r"You are\s+([^,]+)", first, flags=re.IGNORECASE)
    if m2 and m_rep:
        return m2.group(1).strip(), m_rep.group(1).strip()
    m2 = re.match(r"You are\s+([^.,]+)", first, flags=re.IGNORECASE)
    if m2:
        return m2.group(1).strip(), ""
    return "", ""


def enrich_outbound_spoken_intro(
    compiled_brain: str | None,
    line: str | None,
    language: str = "te-IN",
) -> str | None:
    """Prewarm / deferred PCM: name + company + opening when the script only has a short time-check."""
    spoken = (line or "").strip()
    if not compiled_brain:
        return spoken or None
    name, company = _parse_agent_identity(compiled_brain)
    if not name:
        return spoken or None
    # If the line already introduces the agent, prepending a second intro doubles it
    # ("Hi, this is Priya calling from X. Hi, this is Priya. Do you have a moment?").
    # Length was not part of that question: any self-introduction counts.
    if name.lower() in spoken.lower():
        if company and company.lower() not in spoken.lower():
            # Already a self-introduction, only the company is missing. Add just that,
            # rather than a second full intro.
            first, sep, rest = spoken.partition(". ")
            if sep:
                return f"{first}, calling from {company}. {rest}"[:280]
        return spoken[:280]
    lang = (language or "te-IN").lower()
    if lang.startswith("te"):
        intro = f"Namaste andi, nenu {name}"
        intro += f", {company} nundi matladutunnanu." if company else " matladutunnanu."
    elif lang.startswith("hi"):
        intro = f"Namaste, main {name}"
        intro += f", {company} se bol raha hoon." if company else " bol raha hoon."
    else:
        intro = f"Hi, this is {name}"
        intro += f" calling from {company}." if company else "."
    if spoken and spoken.lower() not in intro.lower():
        return f"{intro} {spoken}"[:280]
    return (spoken or intro)[:280]


# Every brain writer on this platform stores the opening as a *labelled* line
# rather than a `--- OPENING ---` block: the SaaS studio writes
# "Opening greeting: ...", the brief compiler writes "Example opening: ...", and
# the Voxly console writes "OPENING LINE" followed by the greeting. Reading only
# the block form made those brains fall through to a generic default greeting, so
# outbound calls opened with "Hi, konchem time unda?" and no agent identity.
#
# The label set is deliberately narrow. Bare "Opening:" / "Greeting:" also appear as
# policy prose, and matching those would put instructions such as "NEVER read this
# aloud" into the agent's mouth.
_OPENING_LABELLED = re.compile(
    r"^[ \t]*(?:"
    r"example\s+(?:opening|first\s+line)"
    r"|opening\s+greeting"
    r"|canonical\s+opening"
    r"|opening\s+line(?:_te)?"
    r")\s*[:=]\s*(?P<inline>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# A bare header on its own line, with the greeting on the following line.
_OPENING_BARE_HEADER = re.compile(
    r"^[ \t]*(?:OPENING\s+LINE|CANONICAL\s+OPENING)\s*$\s*\n(?P<body>[^\n]+)",
    re.IGNORECASE | re.MULTILINE,
)


def _labelled_opening_candidates(compiled_brain: str) -> list[str]:
    """Speakable greetings from labelled lines, newest-style writers included."""
    text = compiled_brain or ""
    found: list[str] = []
    for match in _OPENING_LABELLED.finditer(text):
        candidate = _spoken_opening_candidate(match.group("inline"))
        if candidate and candidate not in found:
            found.append(candidate)
    for match in _OPENING_BARE_HEADER.finditer(text):
        candidate = _spoken_opening_candidate(match.group("body"))
        if candidate and candidate not in found:
            found.append(candidate)
    return found


def _opening_section_candidates(compiled_brain: str) -> list[str]:
    """Speakable lines from OPENING / CANONICAL OPENING sections, longest first."""
    text = compiled_brain or ""
    found: list[str] = list(_labelled_opening_candidates(text))
    section = _OPENING_SECTION.search(text)
    if section:
        for line in section.group(1).splitlines():
            candidate = _spoken_opening_candidate(line)
            if candidate:
                found.append(candidate)
    else:
        # Only when the fenced block is absent. Running this window over a brain that
        # already matched above pulled in the following 800 characters, so unrelated
        # policy lines ("RUNTIME TAGS", "{{callback_phone}}", step lists) outranked the
        # real greeting once sorted longest-first.
        for header in ("--- CANONICAL OPENING ---", "--- OPENING ---", "--- OPENING HINT ---", "## OPENING"):
            idx = text.upper().find(header.upper())
            if idx < 0:
                continue
            chunk = text[idx + len(header) : idx + len(header) + 800]
            for line in chunk.splitlines():
                candidate = _spoken_opening_candidate(line)
                if candidate and candidate not in found:
                    found.append(candidate)
            if found:
                break
    found.sort(key=len, reverse=True)
    return found


def extract_prewarm_greeting(
    compiled_brain: str | None,
    language: str = "te-IN",
    *,
    direction: str | None = None,
) -> str | None:
    """Outbound prewarm PCM: prefer full canonical intro (name + company), not a bare time check."""
    if not compiled_brain:
        return extract_opening_greeting(compiled_brain, language, direction=direction)
    from server.brain.script_entities import parse_entity_tags

    tags = parse_entity_tags(compiled_brain)
    tagged_open = (tags.get("opening_line") or "").strip()
    if tagged_open and len(tagged_open) >= 20:
        enriched = enrich_outbound_spoken_intro(compiled_brain, tagged_open, language)
        return (enriched or tagged_open)[:280]
    text = compiled_brain
    candidates = _opening_section_candidates(text)
    if candidates:
        best = candidates[0]
        if len(best) >= 36:
            enriched = enrich_outbound_spoken_intro(text, best, language)
            return (enriched or best)[:280]
        if len(candidates) >= 2 and len(best) < 36:
            merged = f"{candidates[0]} {candidates[1]}".strip()
            if len(merged) >= 20:
                enriched = enrich_outbound_spoken_intro(text, merged, language)
                return (enriched or merged)[:280]
        if len(best) >= 20:
            enriched = enrich_outbound_spoken_intro(text, best, language)
            return (enriched or best)[:280]
    quoted = re.search(
        r'opening_line(?:_te)?\s*:\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        line = _spoken_opening_candidate(quoted.group(1))
        if line and len(line) >= 20:
            return enrich_outbound_spoken_intro(text, line, language)
    short = extract_opening_greeting(compiled_brain, language, direction=direction)
    if short and candidates and len(short) < 28 and len(candidates[0]) > len(short):
        short = candidates[0]
    outbound = str(direction or "outbound").strip().lower() not in ("inbound", "incoming")
    if outbound:
        return enrich_outbound_spoken_intro(text, short, language)
    return short


def extract_opening_greeting(
    compiled_brain: str | None,
    language: str = "te-IN",
    *,
    direction: str | None = None,
) -> str | None:
    """Best-effort single opening line from compiled brain."""
    if not compiled_brain:
        return _default_greeting(language, direction=direction)
    text = compiled_brain
    quoted = re.search(
        r'opening_line(?:_te)?\s*:\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        line = _spoken_opening_candidate(quoted.group(1))
        if line:
            return line
    labelled = _labelled_opening_candidates(text)
    if labelled:
        return labelled[0]
    section = _OPENING_SECTION.search(text)
    if section:
        for line in section.group(1).splitlines():
            candidate = _spoken_opening_candidate(line)
            if candidate:
                return candidate
    else:
        # Same rationale as _opening_section_candidates: the free-text window is a
        # fallback for unfenced headers only, never a second pass over a matched block.
        for header in ("--- CANONICAL OPENING ---", "--- OPENING ---", "--- OPENING HINT ---", "## OPENING"):
            idx = text.upper().find(header.upper())
            if idx >= 0:
                chunk = text[idx + len(header) : idx + len(header) + 600]
                for line in chunk.splitlines():
                    candidate = _spoken_opening_candidate(line)
                    if candidate:
                        return candidate
                break
    return _default_greeting(language, direction=direction)


def _default_greeting(language: str, *, direction: str | None = None) -> str:
    outbound = str(direction or "outbound").strip().lower() not in ("inbound", "incoming")
    if language.startswith("te"):
        return (
            "Hi, konchem time unda?"
            if outbound
            else "నమస్కారం! నేను మీకు సహాయం చేస్తాను. మీకు ఎలా సహాయం కావాలి?"
        )
    if language.startswith("hi"):
        return (
            "Hi, kya aapke paas ek minute hai?"
            if outbound
            else "Namaste! Main aapki madad ke liye yahan hoon. Main aapki kaise madad karun?"
        )
    if outbound:
        return "Hi, this is a courtesy call. Do you have a moment?"
    return "Hi, thanks for calling. How can I help you today?"
