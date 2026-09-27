"""LLM-assisted script draft for SaaS agent onboarding."""
from __future__ import annotations

import logging
import re
from typing import Any

from server.services.saas.script_variables import merge_variables, normalize_variable_key

logger = logging.getLogger(__name__)

VARIABLE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "description": {"type": "string"},
        "source": {"type": "string"},
        "example": {"type": "string"},
    },
    "required": ["key", "label", "description", "source"],
}

ONBOARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "employee_name": {"type": "string"},
        "suggested_role": {"type": "string"},
        "greeting": {"type": "string"},
        "script": {"type": "string"},
        "variables": {"type": "array", "items": VARIABLE_ITEM_SCHEMA},
    },
    "required": ["greeting", "script", "variables"],
}


def _fallback_greeting(
    name: str,
    role: str,
    business: str,
    *,
    language: str = "en-IN",
    direction: str = "inbound",
) -> str:
    who = (name or "our team").strip()
    outbound = direction == "outbound"
    lang = (language or "en-IN").strip().lower()
    if lang.startswith("te"):
        if outbound:
            return (
                f"Namaskaram, nenu {{{{business_name}}}} nunchi {who}. "
                "Konchem time unda?"
            )
        return (
            f"Namaskaram, {{{{business_name}}}} ki call chesaru. Nenu {who}. "
            "Ela help cheyagalanu?"
        )
    if outbound:
        return (
            f"Hello, this is {who} from {{{{business_name}}}}. "
            "Do you have a moment?"
        )
    return (
        f"Hello, thanks for calling {{{{business_name}}}}. "
        f"You're speaking with {who}. How can I help you today?"
    )


def _fallback_script(
    *,
    name: str,
    role: str,
    language: str,
    business: str,
    goals: str,
    brief: str,
) -> str:
    biz = (business or brief or "this business").strip()
    goal = (goals or "help callers clearly").strip()
    agent = (name or "the voice agent").strip()
    return f"""You are {agent}, an AI phone agent ({role}) for {{business_name}}.

Business context:
{biz[:1500]}

Goals:
- {goal}

Language:
- Primary: {language}. Stay in this language unless the caller explicitly asks to switch.

Call flow:
1. Greet and confirm you represent {{business_name}}.
2. Ask {{caller_name}} how you can help.
3. Collect {{callback_phone}} if a follow-up is needed.
4. Confirm next steps before ending the call.

Rules:
- Do not invent prices, policies, or appointments.
- If unsure, offer a callback.
- Confirm names, numbers, and times by repeating them back."""


def _infer_name_from_brief(brief: str) -> str:
    text = (brief or "").strip()
    if not text:
        return ""
    m = re.search(r"(?:i am|i'm|name is|this is)\s+([A-Z][a-z]{2,20})", text, re.I)
    return m.group(1) if m else ""


async def compose_agent_onboarding(
    *,
    name: str,
    role: str,
    language: str,
    business_summary: str,
    goals: str,
    extra_notes: str = "",
    brief: str = "",
    mode: str = "instant_lead",
    industry: str = "",
    telugu_enhance: bool = False,
    natural_spoken_style: bool | None = None,
) -> dict[str, Any]:
    """Return greeting, script, variables, and metadata for brain publish."""
    lang = (language or "en-IN").strip()
    biz = (business_summary or brief or "").strip()
    goal_text = (goals or "").strip()
    notes = (extra_notes or "").strip()
    agent_name = (name or _infer_name_from_brief(brief) or "").strip()
    mode_label = "outbound lead qualification" if mode == "bulk" else "inbound / instant lead calls"

    spoken_style = natural_spoken_style if natural_spoken_style is not None else telugu_enhance
    from server.services.dev_runtime import openai_enabled

    if openai_enabled() and biz:
        try:
            import asyncio

            from server.config.env import get_settings
            from server.providers.base import LLMConfig
            from server.providers.openai_llm import OpenAILLMAdapter
            from server.realtime.models import http_openai_model

            settings = get_settings()
            adapter = OpenAILLMAdapter()
            style_note = ""
            if spoken_style and lang.startswith("te"):
                style_note = (
                    " Write natural spoken Telugu where appropriate; code-mix English only for proper nouns."
                )
            elif spoken_style:
                style_note = f" Use natural conversational phrasing for {lang}."
            system = (
                "You are an expert voice-AI onboarding writer (like Retell, Vapi, Bland). "
                "From the user's brief, produce:\n"
                "1) greeting — one short spoken opening line\n"
                "2) script — numbered call flow + rules for the live phone agent\n"
                "3) variables — tags the agent will fill on calls\n\n"
                "Use double-brace tags {{key}} in greeting and script for any value that is NOT fixed "
                "in the brief (caller name, budget, appointment time, configuration, etc.). "
                "Use snake_case keys (caller_name, budget_inr, site_visit_date). "
                "Include business_name as a business-sourced tag when a company name appears. "
                "source must be one of: caller, business, runtime.\n"
                "Do not invent prices unless stated. Never instruct the agent to read phone numbers aloud."
                f"{style_note}"
            )
            user = (
                f"Call mode: {mode_label}\n"
                f"Industry: {industry or 'general'}\n"
                f"Agent display name: {agent_name or '(choose a friendly name)'}\n"
                f"Role: {role or 'customer support'}\n"
                f"Primary language/locale: {lang}\n"
                f"User brief:\n{biz}\n\n"
                f"Goals: {goal_text or 'qualify, help, and book next steps'}\n"
                f"Notes: {notes or '(none)'}\n"
            )

            async def _run():
                return await adapter.structured_completion(
                    input_messages=[
                        {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                        {"role": "user", "content": [{"type": "input_text", "text": user}]},
                    ],
                    schema=ONBOARD_SCHEMA,
                    config=LLMConfig(provider="openai", model=http_openai_model(settings)),
                    schema_name="agent_onboarding",
                    max_output_tokens=2000,
                )

            payload = await asyncio.wait_for(_run(), timeout=25)
            greeting = str(payload.get("greeting") or "").strip()
            script = str(payload.get("script") or "").strip()
            vars_raw = payload.get("variables")
            if greeting and script:
                variables = merge_variables(vars_raw if isinstance(vars_raw, list) else None, greeting, script)
                for v in variables:
                    v["key"] = normalize_variable_key(v["key"])
                return {
                    "greeting": greeting,
                    "script": script,
                    "variables": variables,
                    "employeeName": str(payload.get("employee_name") or agent_name).strip(),
                    "role": str(payload.get("suggested_role") or role).strip(),
                    "source": "llm",
                }
        except Exception:
            logger.exception("agent onboarding LLM compose failed; using fallback")

    direction = "outbound" if mode == "bulk" else "inbound"
    greeting = _fallback_greeting(
        agent_name, role, biz, language=lang, direction=direction
    )
    script = _fallback_script(
        name=agent_name,
        role=role,
        language=lang,
        business=biz,
        goals=goal_text,
        brief=brief,
    )
    variables = merge_variables(None, greeting, script)
    return {
        "greeting": greeting,
        "script": script,
        "variables": variables,
        "employeeName": agent_name or "AI Employee",
        "role": role or "Customer Support",
        "source": "template",
    }
