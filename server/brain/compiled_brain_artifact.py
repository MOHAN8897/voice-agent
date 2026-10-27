"""
Unified compiled brain — one assembly for all compile entry points; one render for live voice.

Section 5 (telecaller audit): core + one language pack + business script + static policy,
then a small provider/call-context overlay at connect time (no duplicate language packs).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.agent_voice_rules import (
    call_end_policy_section,
    language_runtime_footer,
    normalize_compile_language,
    spoken_pack_for,
)
from server.prompts.brain_prompt import SECTION_SAFETY
from server.prompts.voice_defaults import style_for_language

SCHEMA_VERSION = "1"
CORE_VERSION = "section_safety_v3"
LANGUAGE_PACK_VERSION = "spoken_packs_v7"
TOOL_CONTRACT_VERSION = "realtime_voice_v2"

_SPOKEN_HEADER = re.compile(r"---\s*SPOKEN LANGUAGE\s*\(", re.I)
_STATIC_HEADER = re.compile(r"---\s*STATIC OUTPUT RULES\s*---", re.I)


@dataclass
class CompiledBrainArtifact:
    schema_version: str
    language: str
    direction: str | None
    core_version: str
    language_pack_version: str
    final_instructions: str
    checksum: str
    opening_text: str = ""
    business_version: str | None = None
    section_token_estimates: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def checksum_instructions(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def is_unified_compiled_brain(text: str | None) -> bool:
    """True when the string already contains platform assembly (pack + static rules)."""
    raw = (text or "").strip()
    if not raw:
        return False
    has_spoken = bool(_SPOKEN_HEADER.search(raw))
    static = STATIC_OUTPUT_RULES.strip()
    has_static = bool(_STATIC_HEADER.search(raw)) or (static and static in raw)
    return has_spoken and has_static


def refresh_platform_sections(text: str | None, language: str) -> str:
    """Refresh platform-owned blocks at render time without changing saved business scripts."""
    raw = (text or "").strip()
    if not is_unified_compiled_brain(raw) and not _SPOKEN_HEADER.search(raw):
        return sanitize_closing_instructions(raw)
    from server.brain.fact_canon import canonicalize_superseded_facts

    # A corrected price must not survive in a stored publication either, and a
    # legacy CLOSING block must not compete with the platform's farewell owner.
    raw = canonicalize_superseded_facts(strip_closing_section(raw))
    from server.prompts.agent_voice_rules import (
        build_recording_disclosure_instruction,
    )

    lang = normalize_compile_language(language)
    from server.brain.script_entities import patch_calling_script_language_markers

    previous = re.search(r"---\s*SPOKEN LANGUAGE\s*\(([^)]+)\)", raw, re.IGNORECASE)
    previous_language = normalize_compile_language(previous.group(1)) if previous else lang
    locale_changed = previous_language != lang
    # A stored publication keeps its old `--- LANGUAGE ---` marker and @language
    # tags as separate sections, so align the whole document before the section
    # loop rebuilds the platform blocks. Without this a language change left the
    # brain naming two packs and validation rejected it as contradictory.
    raw = patch_calling_script_language_markers(raw, lang)
    if locale_changed and "### RECORDING DISCLOSURE POLICY" in raw:
        old_disclosure = build_recording_disclosure_instruction(language=previous_language).strip()
        if old_disclosure not in raw:
            raise ValueError("Custom recording disclosure must be reviewed for the selected language")
        raw = raw.replace(old_disclosure, build_recording_disclosure_instruction(language=lang).strip())
    header = re.compile(r"(?m)^---\s*(.+?)\s*---[ \t]*\n")
    sections = list(header.finditer(raw))
    chunks = [raw[:sections[0].start()]] if sections else [raw]
    for index, match in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(raw)
        title = match.group(1).strip().upper()
        if title == "SAFETY":
            block = SECTION_SAFETY
        elif title == "STATIC OUTPUT RULES":
            old = raw[match.start():end]
            footer = re.search(r"(?m)^Language:\s*", old)
            suffix = old[footer.start():] if footer else ""
            previous_language = re.match(r"Language:\s*([^\s.]+)", suffix)
            if locale_changed or (previous_language and normalize_compile_language(previous_language.group(1)) != normalize_compile_language(language)):
                suffix = re.sub(r"^Language:[^\n]*", lambda _: language_runtime_footer(
                    language, style_for_language(None, language), include_language_lock=False,
                ), suffix, count=1)
            block = STATIC_OUTPUT_RULES + ("\n\n" + suffix if suffix else "")
        elif title.startswith("SPOKEN LANGUAGE ("):
            block = spoken_pack_for(language, include_brevity=False, core_only=True)
        elif title == "CALL CAPABILITIES":
            from server.brain.capabilities import render_capabilities_section
            old = raw[match.start():end]
            block = old if "capabilities_source: runtime_tools_v1" in old else render_capabilities_section(raw)
        elif title == "CALL END POLICY":
            old = raw[match.start():end]
            from server.call.call_end_policy import policy_from_brain

            policy = policy_from_brain(old, lang) or {}
            if locale_changed and policy.get("farewellSource") == "tenant":
                raise ValueError("Custom farewell must be reviewed for the selected language")
            block = call_end_policy_section(lang, policy)
        elif title == "CALLING SCRIPT":
            # A stored script keeps the LANGUAGE marker it was generated under.
            # The edit-language picker changes the session pack without rewriting
            # the script, so refresh that marker or the validation pass sees two
            # different packs in one brain.
            block = patch_calling_script_language_markers(raw[match.start():end], lang)
        else:
            block = raw[match.start():end]
        chunks.append(block.strip())
    refreshed = "\n\n".join(chunk for chunk in chunks if chunk.strip())
    return sanitize_closing_instructions(_ensure_capabilities_section(refreshed))


def _ensure_capabilities_section(text: str) -> str:
    """Insert the contract into publications stored before it existed."""
    from server.brain.capabilities import (
        capabilities_section_present,
        render_capabilities_section,
    )

    if capabilities_section_present(text):
        return text
    anchor = re.search(r"(?m)^--- (?:CALL END POLICY|STATIC OUTPUT RULES) ---", text)
    if not anchor or not re.search(r"(?m)^--- CALLING SCRIPT ---", text):
        return text
    section = render_capabilities_section(text)
    return f"{text[:anchor.start()].rstrip()}\n\n{section}\n\n{text[anchor.start():]}"


def business_from_unified_brain(text: str) -> str:
    """Unwrap the approved business body of legacy full-assembly publications."""
    start = re.search(r"(?m)^--- CALLING SCRIPT ---\s*\n", text)
    if not start:
        raise ValueError("Legacy publication is missing its calling script")
    body = text[start.end():]
    end = re.search(
        r"(?m)^--- (?:CALL CAPABILITIES|PLATFORM CALL RULES|CALL END POLICY|STATIC OUTPUT RULES) ---",
        body,
    )
    return body[:end.start()].strip() if end else body.strip()


def strip_section_markers(script: str | None) -> str:
    """Drop `<!-- section:type:uuid -->` bookkeeping from the compiled artifact.

    The markers let the optimizer and the section editor find their boundaries in
    the raw and optimized business prompts, where they are load-bearing. In the
    compiled brain they are dead weight the model pays to read on every call, so
    they are removed here — after both consumers have run.
    """
    cleaned = re.sub(r"(?m)^[ \t]*<!--\s*section:.*?-->[ \t]*\n?", "", script or "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


_CLOSING_HEADER = re.compile(
    r"^\s*-{2,}\s*(?:CLOSING|CLOSE|FAREWELL)\s*-{2,}\s*$", re.I
)
_SECTION_HEADER = re.compile(r"^\s*-{2,}\s*[A-Z][A-Z0-9 &/()'.,-]{1,60}\s*-{2,}\s*$")


def sanitize_closing_instructions(text: str | None) -> str:
    """Eliminate contradictory closing instructions from saved scripts and prompts.

    Enforces exactly one rule: the model makes the close decision; the server
    plays the approved farewell.
    """
    raw = str(text or "")
    if not raw:
        return ""
    # 1. "confirm, thank, farewell, and close — no extra pitch" (with any dash or encoding)
    raw = re.sub(
        r"confirm,\s*thank,\s*farewell,\s*and\s*close\s*[-—–\ufffd]?\s*(?:no\s+extra\s+pitch\.?)?",
        "confirm, thank, and make the close decision — no extra pitch. Never speak the farewell yourself; the platform speaks it after approval.",
        raw,
        flags=re.IGNORECASE,
    )
    # 2. "Confirm in one line, thank them, short farewell, end_call. Then stop — ..."
    raw = re.sub(
        r"Confirm\s+in\s+one\s+line,\s*thank\s+them,\s*short\s+farewell,\s*end_call\.\s*Then\s+stop\s*[-—–\ufffd]?[^\n.]*",
        "Confirm in one line, thank them, and make the close decision. Never speak the farewell yourself — the server plays the approved farewell.",
        raw,
        flags=re.IGNORECASE,
    )
    # 3. "say a farewell and (call )?end_call"
    raw = re.sub(
        r"(?:say|speak)\s+a\s+farewell\s+and\s+(?:call\s+)?end_call",
        "make the close decision; never speak the farewell yourself — the server plays the approved farewell",
        raw,
        flags=re.IGNORECASE,
    )
    # 4. "Speak the farewell AND call end_call (should_end true)"
    raw = re.sub(
        r"speak\s+the\s+farewell\s+and\s+call\s+end_call(?:\s*\([^)]*\))?",
        "make the close decision; never speak the farewell yourself — the server plays the approved farewell",
        raw,
        flags=re.IGNORECASE,
    )
    # 5. "Thank them, say goodbye once, then stop"
    raw = re.sub(
        r"thank\s+them,\s*say\s+goodbye(?:\s+once)?,\s*then\s+stop",
        "thank them and make the close decision; never speak the farewell yourself — the platform disconnects when farewell finishes",
        raw,
        flags=re.IGNORECASE,
    )
    # 6. "short farewell, end_call"
    raw = re.sub(
        r"short\s+farewell,\s*end_call",
        "make the close decision; never speak the farewell yourself — the server plays the approved farewell",
        raw,
        flags=re.IGNORECASE,
    )
    # 7. "short farewell plus/ + end_call"
    raw = re.sub(
        r"short\s+farewell\s*(?:plus|\+)\s*(?:request_)?end_call",
        "make the close decision; never speak the farewell yourself",
        raw,
        flags=re.IGNORECASE,
    )
    # 8. "in the SAME turn as a short farewell"
    raw = re.sub(
        r"in\s+the\s+same\s+turn\s+as\s+a\s+short\s+farewell",
        "when closing; never speak the farewell yourself",
        raw,
        flags=re.IGNORECASE,
    )
    # 9. bare "farewell + tool" or "farewell + request_end_call"
    raw = re.sub(
        r"\bfarewell\s*\+\s*(?:tool|request_end_call|end_call)\b",
        "make the close decision",
        raw,
        flags=re.IGNORECASE,
    )
    # 10. "say goodbye (or have a great day), and invoke the tool"
    raw = re.sub(
        r"say\s+goodbye(?:\s*\([^)]*\))?,\s*and\s+invoke\s+the\s+tool",
        "make the close decision and invoke the tool (never speak the farewell yourself)",
        raw,
        flags=re.IGNORECASE,
    )
    return raw


def strip_closing_section(script: str | None) -> str:
    """Drop a model-authored closing block; the platform owns the farewell.

    Stored scripts from before the 2026-10-25 audit still carry a CLOSING such
    as "Thank you ... Have a wonderful day. Goodbye." Assembling it next to the
    platform's "never speak a goodbye" policy gives the model two owners.
    """
    out: list[str] = []
    skipping = False
    for line in (script or "").splitlines():
        if _CLOSING_HEADER.match(line):
            skipping = True
            continue
        if skipping and _SECTION_HEADER.match(line):
            skipping = False
        if not skipping:
            out.append(line)
    cleaned = sanitize_closing_instructions("\n".join(out))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def assemble_unified_brain(
    *,
    language: str,
    script: str,
    style: str | None = None,
    call_end_policy: dict[str, Any] | None = None,
    platform_call_rules: str = "",
    extra_pad: str = "",
    core_safety: str | None = None,
) -> str:
    """Canonical compile output used by brief, session, factory, and SaaS paths."""
    lang = normalize_compile_language(language)
    style_val = style_for_language(style, lang)
    from server.brain.capabilities import render_capabilities_section
    from server.brain.fact_canon import canonicalize_superseded_facts
    from server.brain.script_entities import patch_calling_script_language_markers

    # The script's own LANGUAGE section is platform bookkeeping, not user prose.
    # It must name the pack this brain is compiled with even when the agent's
    # language was changed after the script was generated.
    aligned_script = patch_calling_script_language_markers(script, lang)
    business = sanitize_closing_instructions(canonicalize_superseded_facts(strip_closing_section(strip_section_markers(aligned_script))))
    # Permissions come from the authored brief alone. Reading them here, at
    # compile time, keeps platform safety text (which also names orders) from
    # ever granting or denying a business capability.
    calling = f"--- CALLING SCRIPT ---\n{business}\n\n{render_capabilities_section(business)}\n\n"
    platform = (platform_call_rules or "").strip()
    if platform:
        calling += f"--- PLATFORM CALL RULES ---\n{platform.strip()}\n\n"
    core = (core_safety or SECTION_SAFETY).strip()
    # The brevity bands and the language lock each already ship in full inside
    # STATIC_OUTPUT_RULES and the spoken pack, so the pack and footer are asked
    # for their lean forms here. `core_only` drops the phone block and worked
    # examples while preserving locale-specific number phrasing.
    # Without this the same guidance was sent two or three times
    # in every compiled brain.
    body = (
        f"{core}\n\n"
        f"{spoken_pack_for(lang, include_brevity=False, core_only=True)}\n\n"
        f"{calling}"
        f"{call_end_policy_section(lang, call_end_policy)}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"{language_runtime_footer(lang, style_val, include_language_lock=False)}"
    )
    if extra_pad:
        return f"{body}\n\n{extra_pad.strip()}"
    return body


def build_artifact(
    *,
    language: str,
    script: str,
    style: str | None = None,
    call_end_policy: dict[str, Any] | None = None,
    platform_call_rules: str = "",
    direction: str | None = None,
    opening_text: str = "",
    business_version: str | None = None,
) -> CompiledBrainArtifact:
    from server.agent.brain_prompt_composer import estimate_tokens

    lang = normalize_compile_language(language)
    final = assemble_unified_brain(
        language=lang,
        script=script,
        style=style,
        call_end_policy=call_end_policy,
        platform_call_rules=platform_call_rules,
    )
    core_t = estimate_tokens(SECTION_SAFETY)
    pack_t = estimate_tokens(spoken_pack_for(lang, include_brevity=False, core_only=True))
    biz_t = estimate_tokens(strip_section_markers(script))
    return CompiledBrainArtifact(
        schema_version=SCHEMA_VERSION,
        language=lang,
        direction=direction,
        core_version=CORE_VERSION,
        language_pack_version=LANGUAGE_PACK_VERSION,
        final_instructions=final,
        checksum=checksum_instructions(final),
        opening_text=(opening_text or "").strip(),
        business_version=business_version,
        section_token_estimates={
            "core": core_t,
            "language_pack": pack_t,
            "business_script": biz_t,
            "platform_overhead": max(0, estimate_tokens(final) - biz_t),
            "total": estimate_tokens(final),
        },
    )


def session_brain_body(
    *,
    behaviour: str,
    business: str,
) -> str:
    """Dual-editor body inside CALLING SCRIPT."""
    return f"--- BEHAVIOUR ---\n{behaviour.strip()}\n\n--- BUSINESS ---\n{business.strip()}"


def platform_body_for_agent_language(platform_body: str, language: str) -> str:
    """Drop legacy CORE_SYSTEM_PROMPT (safety + fixed Telugu pack) before re-assembly."""
    from server.prompts.brain_prompt import CORE_SYSTEM_PROMPT

    pb = (platform_body or "").strip()
    if not pb:
        return ""
    if pb == CORE_SYSTEM_PROMPT.strip():
        return ""
    # Platform draft still embedding only te-IN voice — unified assembler adds the right pack.
    if _SPOKEN_HEADER.search(pb) and SECTION_SAFETY.strip() in pb:
        return ""
    return pb
