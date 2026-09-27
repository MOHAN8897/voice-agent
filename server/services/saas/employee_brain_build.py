"""SaaS employee create — same script compiler + cached brain as dev Test Studio."""
from __future__ import annotations

import json
from typing import Any

from server.brain.agent_script_compiler import AgentScriptResult, compile_agent_from_brief
from server.brain.business_brain_store import assemble_raw_business_prompt, business_brain_store
from server.brain.compiled_brain_service import compiled_brain_service
from server.call.call_end_policy import normalize_call_end_policy
from server.services.saas.script_variables import SAAS_SCRIPT_VARIABLES_TITLE, merge_variables

CALLING_SCRIPT_TITLE = "Calling script"


def _append_variable_legend(script: str, variables: list[dict[str, str]]) -> str:
    if not variables:
        return script
    lines = ["", "--- RUNTIME TAGS (fill when known; never read empty tags aloud) ---"]
    for v in variables:
        key = v.get("key", "")
        if not key:
            continue
        desc = v.get("description") or v.get("label") or key
        lines.append(f"{{{{{key}}}}}: {desc}")
    return (script.rstrip() + "\n" + "\n".join(lines)).strip()


def draft_sections_for_saas_employee(
    *,
    user_script: str,
    language: str,
    platform_call_rules: str,
    variables: list[dict[str, str]],
    voice_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lang = (language or "en-IN").strip() or "en-IN"
    script_body = _append_variable_legend(user_script, variables)
    voice_cfg = voice_config or {
        "realtimeVoice": "marin",
        "voiceId": "marin",
        "speed": 1.0,
        "language": lang,
        "turnDetection": "semantic_vad",
        "noiseReduction": "far_field",
    }
    rules = (platform_call_rules or "").strip() or (
        "Answer only from the calling script. Do not invent prices or policies."
    )
    return [
        {
            "type": "custom",
            "title": "saas_voice_config",
            "order": 2,
            "raw_text": json.dumps(voice_cfg, indent=0),
            "enabled": False,
        },
        {
            "type": "custom",
            "title": SAAS_SCRIPT_VARIABLES_TITLE,
            "order": 3,
            "raw_text": json.dumps({"version": 1, "variables": variables}, indent=2),
            "enabled": False,
        },
        {
            "type": "identity_purpose",
            "title": "Identity & Purpose",
            "order": 10,
            "raw_text": "You are a live phone agent for this business. Follow the Calling script section exclusively.",
            "enabled": True,
        },
        {
            "type": "facts",
            "title": CALLING_SCRIPT_TITLE,
            "order": 20,
            "raw_text": script_body,
            "enabled": True,
        },
        {
            "type": "guardrails",
            "title": "Guardrails",
            "order": 30,
            "raw_text": rules[:12000],
            "enabled": True,
        },
    ]


async def compile_brief_for_employee(
    *,
    brief: str,
    language: str,
) -> tuple[str, AgentScriptResult, list[dict[str, str]]]:
    lang = (language or "en-IN").strip() or "en-IN"
    policy = normalize_call_end_policy(None, language=lang)
    try:
        compiled, script_result, *_rest = await compile_agent_from_brief(
            brief=brief.strip(),
            language=lang,
            interpret_brief=True,
            call_end_policy=policy,
        )
    except Exception:
        compiled, script_result, *_rest = await compile_agent_from_brief(
            brief=brief.strip(),
            language=lang,
            interpret_brief=True,
            call_end_policy=policy,
            use_llm=False,
        )
    variables = merge_variables(None, "", script_result.agent_script)
    return compiled, script_result, variables


async def publish_saas_employee_brain(
    agent_id: str,
    *,
    brief: str,
    language: str,
    voice_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compiled, script_result, variables = await compile_brief_for_employee(
        brief=brief, language=language
    )
    sections = draft_sections_for_saas_employee(
        user_script=script_result.agent_script,
        language=language,
        platform_call_rules=script_result.platform_call_rules,
        variables=variables,
        voice_config=voice_config,
    )
    await business_brain_store.save_draft_sections(agent_id, sections)
    _raw, checksum = assemble_raw_business_prompt(sections)
    await business_brain_store.save_published_version(
        agent_id,
        optimized_prompt=compiled,
        source_checksum=checksum,
        optimizer_report={
            **script_result.to_dict(),
            "saas_build": True,
            "compiled_brain": compiled,
        },
    )
    snapshot = await compiled_brain_service.compile_for_agent(agent_id)
    return {
        "compiled": compiled,
        "script": script_result.agent_script,
        "variables": variables,
        "employeeName": script_result.agent_name or "AI Employee",
        "role": script_result.role_summary or "Voice agent",
        "snapshot": snapshot,
    }
