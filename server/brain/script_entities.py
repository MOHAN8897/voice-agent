"""Structured @entity tags in calling scripts — parse, render, and resolve for PSTN."""
from __future__ import annotations

import re
from typing import Any

ENTITY_SECTION_TITLE = "ENTITY TAGS"
ENTITY_SECTION_HEADER = f"--- {ENTITY_SECTION_TITLE} ---"

_KNOWN_KEYS = (
    "agent_name",
    "company_name",
    "work_scope",
    "role",
    "language",
    "direction",
    "opening_line",
)

_TAG_LINE = re.compile(
    r"^@(?P<key>[a-z_]+)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ENTITY_SECTION = re.compile(
    rf"(?:^|\n){re.escape(ENTITY_SECTION_HEADER)}\s*\n(.*?)(?=\n---\s*[^-\n]+\s*---|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def build_script_entities(
    *,
    agent_name: str = "",
    company_name: str = "",
    work_scope: str = "",
    role: str = "",
    language: str = "",
    direction: str = "",
    opening_line: str = "",
) -> dict[str, str]:
    out: dict[str, str] = {}
    if agent_name:
        out["agent_name"] = agent_name.strip()
    if company_name:
        out["company_name"] = company_name.strip()
    if work_scope:
        out["work_scope"] = work_scope.strip()
    if role:
        out["role"] = role.strip()
    if language:
        out["language"] = language.strip()
    if direction:
        out["direction"] = direction.strip().lower()
    if opening_line:
        out["opening_line"] = opening_line.strip()
    return out


def format_entity_tags_section(entities: dict[str, str]) -> str:
    lines = [
        ENTITY_SECTION_HEADER,
        "Machine-readable call entities (do not remove — used for voice opening and brain pins).",
    ]
    for key in _KNOWN_KEYS:
        val = (entities.get(key) or "").strip()
        if val:
            lines.append(f"@{key}: {val}")
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)


def parse_entity_tags(text: str | None) -> dict[str, str]:
    raw = text or ""
    block = _ENTITY_SECTION.search(raw)
    chunk = block.group(1) if block else raw
    out: dict[str, str] = {}
    for match in _TAG_LINE.finditer(chunk):
        key = match.group("key").lower()
        if key in _KNOWN_KEYS:
            out[key] = match.group("value").strip()
    return out


def strip_entity_tags_section(script: str) -> str:
    text = (script or "").strip()
    if not text:
        return ""
    cleaned = _ENTITY_SECTION.sub("", text, count=1)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def with_entity_tags_section(script: str, entities: dict[str, str]) -> str:
    body = strip_entity_tags_section(script)
    section = format_entity_tags_section(entities)
    if not section:
        return body
    if body:
        return f"{section}\n\n{body}"
    return section


def entities_for_prewarm(compiled_brain: str | None) -> dict[str, str]:
    """Prefer @entity tags, then fall back to empty dict."""
    return parse_entity_tags(compiled_brain or "")


def resolve_agent_company_from_brain(compiled_brain: str | None) -> tuple[str, str]:
    tags = parse_entity_tags(compiled_brain or "")
    name = tags.get("agent_name", "")
    company = tags.get("company_name", "")
    if name or company:
        return name, company
    from server.services.pstn_text_chunker import _parse_agent_identity

    return _parse_agent_identity(compiled_brain or "")


def entities_have_values(entities: dict[str, str] | None) -> bool:
    if not entities:
        return False
    return any((entities.get(k) or "").strip() for k in _KNOWN_KEYS)


def entity_tags_to_api(entities: dict[str, str]) -> dict[str, Any]:
    return {k: entities.get(k, "") for k in _KNOWN_KEYS}


def script_conflicts_with_brief(script: str, brief: str, *, language: str = "te-IN") -> bool:
    """True when saved script identity does not match the current brief (stale script)."""
    from server.brain.agent_script_compiler import (
        extract_agent_name_from_brief,
        extract_company_from_brief,
    )
    from server.services.pstn_text_chunker import _parse_agent_identity

    brief_name = (extract_agent_name_from_brief(brief) or "").strip().lower()
    brief_co = (extract_company_from_brief(brief) or "").strip().lower()
    if not brief_name and not brief_co:
        return False
    body = strip_entity_tags_section(script)
    tags = parse_entity_tags(script)
    parsed_name, parsed_co = _parse_agent_identity(body)
    script_name = (tags.get("agent_name") or "").strip().lower()
    script_co = (tags.get("company_name") or "").strip().lower()
    if not script_name:
        script_name = (parsed_name or "").strip().lower()
    if not script_co:
        script_co = (parsed_co or "").strip().lower()
    # Tags updated from brief but AGENT IDENTITY body still stale (common UI bug).
    if tags.get("agent_name") and parsed_name:
        if tags["agent_name"].strip().lower() != parsed_name.strip().lower():
            return True
    if tags.get("company_name") and parsed_co:
        tco = tags["company_name"].strip().lower()
        pco = parsed_co.strip().lower()
        if tco not in pco and pco not in tco:
            return True
    if brief_name and script_name and brief_name != script_name:
        return True
    if brief_co and script_co:
        if brief_co not in script_co and script_co not in brief_co:
            return True
    elif brief_co and script_co == "" and brief_co[:4] not in body.lower():
        return True
    return False


async def regenerate_calling_script_from_brief(
    brief: str,
    *,
    language: str = "te-IN",
    direction: str | None = None,
    style: str | None = None,
    budget_tokens: int = 3500,
    call_end_policy: dict | None = None,
    previous_compiled: str | None = None,
) -> tuple[str, str, object]:
    """Full replace user script + compiled brain from brief only."""
    from server.brain.agent_script_compiler import compile_agent_from_brief

    compiled, result, raw_est, comp_est, budget = await compile_agent_from_brief(
        brief=brief,
        language=language,
        style=style,
        budget_tokens=budget_tokens,
        previous_compiled=previous_compiled,
        call_end_policy=call_end_policy,
        interpret_brief=True,
    )
    return compiled, result.agent_script, result


def sync_entity_language_tag(entities: dict[str, str], language: str) -> dict[str, str]:
    """Keep @language aligned with the session/Test Studio dial language (LANG-1/LANG-2)."""
    from server.prompts.agent_voice_rules import normalize_compile_language, opening_line_for

    lang = normalize_compile_language(language or "te-IN")
    out = dict(entities)
    prev = normalize_compile_language(out.get("language") or "") if out.get("language") else ""
    if lang:
        out["language"] = lang
    if prev and prev != lang and (out.get("agent_name") or out.get("company_name")):
        out["opening_line"] = opening_line_for(
            lang,
            agent_name=(out.get("agent_name") or "Agent").strip(),
            company_name=(out.get("company_name") or "Company").strip(),
            work_scope=(out.get("work_scope") or "").strip(),
            direction=(out.get("direction") or "outbound").strip(),
        )
    return out


_CALLING_SCRIPT_MARKER = "--- CALLING SCRIPT ---"
_SPOKEN_LANG_HEADER = re.compile(r"--- SPOKEN LANGUAGE \([^)]+\) ---", re.IGNORECASE)


_CANONICAL_OPENING = re.compile(
    r"(--- CANONICAL OPENING ---\s*\n)(.*?)(?=\n---\s+[^-\n]+\s+---|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_SPEAK_THIS_WAY = re.compile(r"\nSpeak this way:[^\n]*\.", re.IGNORECASE)


def _patch_canonical_opening_from_tags(script: str, opening_line: str) -> str:
    line = (opening_line or "").strip()
    if not line:
        return script
    match = _CANONICAL_OPENING.search(script)
    if not match:
        return script
    body = (
        "After the callee speaks, say once (in the configured language):\n"
        f"{line}\n"
    )
    return script[: match.start()] + match.group(1) + body + script[match.end() :]


def _patch_role_speak_line(script: str, language: str) -> str:
    from server.prompts.agent_voice_rules import IDENTITY_SPEAK, normalize_compile_language

    lang = normalize_compile_language(language or "te-IN")
    speak = IDENTITY_SPEAK.get(lang) or IDENTITY_SPEAK.get("en-IN", "")
    if not speak:
        return script
    if _SPEAK_THIS_WAY.search(script):
        return _SPEAK_THIS_WAY.sub(f"\n{speak}", script, count=1)
    return script


def patch_calling_script_language_markers(script: str, language: str) -> str:
    """Fix stale SPOKEN LANGUAGE headers and @language tags inside the user script when dial language differs."""
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(language or "te-IN")
    if not script.strip():
        return script
    res = _SPOKEN_LANG_HEADER.sub(f"--- SPOKEN LANGUAGE ({lang}) ---", script, count=1)
    return re.sub(r"@language:\s*[a-z]{2}(?:-[a-z]{2})?", f"@language: {lang}", res, flags=re.I)


def realign_calling_script_for_session(
    script: str,
    language: str,
    *,
    brief: str = "",
    direction: str | None = None,
) -> str:
    """Sync entity tags + language markers on the user script before PSTN/live use."""
    aligned = backfill_entity_tags_in_script(
        script,
        brief=brief,
        language=language,
        direction=direction,
    )
    tags = parse_entity_tags(aligned)
    opening = (tags.get("opening_line") or "").strip()
    if opening:
        aligned = _patch_canonical_opening_from_tags(aligned, opening)
    aligned = _patch_role_speak_line(aligned, language)
    return patch_calling_script_language_markers(aligned, language)


def realign_compiled_brain_for_session(
    compiled: str,
    language: str,
    *,
    brief: str = "",
    direction: str | None = None,
) -> str:
    """LANG-1: align the CALLING SCRIPT block, spoken pack, and runtime footer inside a locked compiled brain."""
    text = (compiled or "").strip()
    if not text:
        return compiled or ""
    start = text.find(_CALLING_SCRIPT_MARKER)
    if start < 0:
        return compiled
    body_start = start + len(_CALLING_SCRIPT_MARKER)
    rest = text[body_start:].lstrip("\n")
    end = len(rest)
    for marker in (
        "--- PLATFORM CALL RULES ---",
        "--- CALL END POLICY",
        "--- STATIC OUTPUT RULES ---",
        "\n--- SAFETY ---",
    ):
        idx = rest.find(marker)
        if idx >= 0:
            end = min(end, idx)
    script = rest[:end].strip()
    suffix = rest[end:]
    aligned = realign_calling_script_for_session(
        script,
        language,
        brief=brief,
        direction=direction,
    )
    prefix = text[:start]

    from server.prompts.agent_voice_rules import (
        call_end_policy_section,
        language_runtime_footer,
        normalize_compile_language,
        spoken_pack_for,
    )
    from server.prompts.voice_defaults import style_for_language

    norm_lang = normalize_compile_language(language)

    # 1. Update the spoken language pack in prefix if a SPOKEN LANGUAGE header is present
    if re.search(r"---\s*SPOKEN LANGUAGE\s*\([^)]+\)", prefix, re.I):
        new_pack = spoken_pack_for(norm_lang, include_brevity=False, core_only=True)
        prefix = re.sub(
            r"---\s*SPOKEN LANGUAGE\s*\([^)]+\)[\s\S]*?\Z",
            f"{new_pack}\n\n",
            prefix,
            flags=re.I,
        )

    # 2. Update call end policy in suffix if present
    if re.search(r"---\s*CALL END POLICY", suffix, re.I):
        new_call_end = call_end_policy_section(norm_lang)
        suffix = re.sub(
            r"---\s*CALL END POLICY[\s\S]*?(?=\n---\s*STATIC OUTPUT RULES|\Z)",
            f"{new_call_end}\n\n",
            suffix,
            flags=re.I,
        )

    # 3. Update runtime footer at the end of suffix
    style_val = style_for_language(None, norm_lang)
    new_footer = language_runtime_footer(norm_lang, style_val, include_language_lock=False)
    if re.search(r"(?:^|\n)Language:\s*[a-z]{2}(?:-[a-z]{2})?[\s\S]*?\Z", suffix, re.I):
        suffix = re.sub(
            r"(?:^|\n)Language:\s*[a-z]{2}(?:-[a-z]{2})?[\s\S]*?\Z",
            f"\n\n{new_footer}",
            suffix,
            flags=re.I,
        )

    return f"{prefix}--- CALLING SCRIPT ---\n{aligned}\n\n{suffix.lstrip()}"


def backfill_entity_tags_in_script(
    script: str,
    *,
    brief: str = "",
    language: str = "te-IN",
    direction: str | None = None,
) -> str:
    """Add ENTITY TAGS when missing (legacy scripts) using brief + script sections."""
    existing = parse_entity_tags(script)
    if entities_have_values(existing):
        return with_entity_tags_section(script, sync_entity_language_tag(existing, language))
    from server.prompts.conversation_policy import infer_agent_role, infer_call_direction
    from server.services.pstn_text_chunker import extract_opening_greeting

    lang = (language or "te-IN").strip()
    dir_val = direction or infer_call_direction(f"{brief}\n{script}")
    d = "inbound" if str(dir_val).strip().lower() in ("inbound", "incoming") else "outbound"
    from server.brain.agent_script_compiler import resolve_script_identity

    agent_name, company_name, work_scope, opening_line = resolve_script_identity(
        (brief or script).strip(),
        language=lang,
        direction=d,
    )
    if not opening_line:
        opening_line = extract_opening_greeting(script, lang, direction=d) or ""
    role = infer_agent_role(f"{brief}\n{script}")
    entities = build_script_entities(
        agent_name=agent_name,
        company_name=company_name,
        work_scope=work_scope,
        role=role,
        language=lang,
        direction=d,
        opening_line=opening_line,
    )
    if not entities_have_values(entities):
        return script
    return with_entity_tags_section(script, entities)
