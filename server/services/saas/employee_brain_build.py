"""SaaS employee create — reviewed business script in the existing compiled brain."""
from __future__ import annotations

import json
from typing import Any

from server.agent.brain_prompt_composer import PromptBudgetExceeded, PromptSectionTooLong
from server.brain.agent_script_compiler import AgentScriptResult
from server.brain.brief_contract import BriefValidationError, brief_issue
from server.brain.employee_script_pipeline import ClarificationAnswer, compile_employee_script
from server.brain.compiled_brain_service import compiled_brain_service
from server.services.saas.script_variables import SAAS_SCRIPT_VARIABLES_TITLE, merge_variables

CALLING_SCRIPT_TITLE = "Calling script"


def draft_sections_for_saas_employee(
    *,
    user_script: str,
    language: str,
    platform_call_rules: str,
    variables: list[dict[str, str]],
    voice_config: dict[str, Any] | None = None,
    generation_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lang = (language or "en-IN").strip() or "en-IN"
    script_body = user_script
    voice_cfg = voice_config or {
        "realtimeVoice": "Puck",
        "voiceId": "Puck",
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
            "title": "saas_generation_config",
            "order": 1,
            "raw_text": json.dumps(generation_config or {}, ensure_ascii=False),
            "enabled": False,
        },
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
            "raw_text": "You are a professional live phone agent for this business. Follow the calling script and business facts within platform safety and tool permissions.",
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
    generation_config: dict[str, Any] | None = None,
    answers: list[ClarificationAnswer] | None = None,
) -> tuple[str, AgentScriptResult, list[dict[str, str]]]:
    lang = (language or "en-IN").strip() or "en-IN"
    try:
        compiled, script_result = await compile_employee_script(
            brief=brief.strip(),
            language=lang,
            generation_config=generation_config,
            answers=answers,
        )
    except (PromptBudgetExceeded, PromptSectionTooLong) as exc:
        raise BriefValidationError([brief_issue("input_limit_exceeded", str(exc))]) from exc
    variables = merge_variables(None, "", script_result.agent_script)
    return compiled, script_result, variables


async def publish_saas_employee_brain(
    agent_id: str,
    *,
    brief: str,
    language: str,
    voice_config: dict[str, Any] | None = None,
    generation_config: dict[str, Any] | None = None,
    compiled_artifact: tuple[str, AgentScriptResult, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    compiled, script_result, variables = compiled_artifact or await compile_brief_for_employee(
        brief=brief, language=language, generation_config=generation_config
    )
    report = script_result.to_dict()
    sections = draft_sections_for_saas_employee(
        user_script=script_result.agent_script,
        language=language,
        platform_call_rules=script_result.platform_call_rules,
        variables=variables,
        voice_config=voice_config,
        generation_config=report.get("generation_config") or generation_config,
    )
    snapshot = await compiled_brain_service.publish_agent_brain(
        agent_id,
        sections=sections,
        optimized_prompt=compiled,
        optimizer_report={
            **report,
            "saas_build": True,
            "compiled_brain": compiled,
        },
    )
    return {
        "compiled": compiled,
        "script": script_result.agent_script,
        "variables": variables,
        "employeeName": script_result.agent_name or "AI Employee",
        "role": script_result.role_summary or "Voice agent",
        "snapshot": snapshot,
        "generation": report,
    }
