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
CORE_VERSION = "section_safety_v1"
LANGUAGE_PACK_VERSION = "spoken_packs_v2"
TOOL_CONTRACT_VERSION = "realtime_voice_v1"

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
    calling = f"--- CALLING SCRIPT ---\n{(script or '').strip()}\n\n"
    platform = (platform_call_rules or "").strip()
    if platform:
        calling += f"--- PLATFORM CALL RULES ---\n{platform.strip()}\n\n"
    core = (core_safety or SECTION_SAFETY).strip()
    body = (
        f"{core}\n\n"
        f"{spoken_pack_for(lang)}\n\n"
        f"{calling}"
        f"{call_end_policy_section(lang, call_end_policy)}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"{language_runtime_footer(lang, style_val)}"
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
    pack_t = estimate_tokens(spoken_pack_for(lang))
    biz_t = estimate_tokens(script)
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
