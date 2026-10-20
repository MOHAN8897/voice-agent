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
    from server.brain.agent_script_compiler import resolve_script_identity
    _, company, _, _ = resolve_script_identity(business, language=language, direction=direction)
    company = company or (business.strip() if re.fullmatch(r"\w[\w&.-]{1,79}", business.strip()) else "our team")
    outbound = direction == "outbound"
    lang = (language or "en-IN").strip().lower()
    if lang.startswith("te"):
        if outbound:
            return (
                f"Namaskaram, nenu {company} nunchi {who}. "
                "Konchem time unda?"
            )
        return (
            f"Namaskaram, {company} ki call chesaru. Nenu {who}. "
            "Ela help cheyagalanu?"
        )
    if outbound:
        return (
            f"Hello, this is {who} from {company}. "
            "Do you have a moment?"
        )
    return (
        f"Hello, thanks for calling {company}. "
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
    return f"""You are {agent}, an AI phone agent ({role}) for this business.

Business context:
{biz[:1500]}

Goals:
- {goal}

Language:
- Primary: {language}. Use natural professional speech with familiar English terms where appropriate.

Call flow:
1. Greet and introduce the business using the supplied context.
2. Use the supplied contact name when available. Ask how you can help.
3. For follow-up, use the known dialed number. Ask for a different number only if requested.
4. Confirm next steps before ending the call.

Rules:
- Do not invent prices, policies, or appointments.
- If unsure, offer a callback.
- Clarify uncertain names or times. Do not read phone numbers aloud."""


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
                "3) variables — only placeholders actually used by this script\n\n"
                "Use campaign contact data with {{contact.full_name}}, {{contact.phone}}, or "
                "{{contact.custom_fields.field_name}}. CSV columns are mapped to these exact fields before calls. "
                "Prefer the complete contact name; use {{contact.first_name}} only when supplied explicitly. "
                "Optional fields need a natural fallback, such as {{contact.full_name | there}}. "
                "Write known business names and facts literally. For details collected during a conversation, "
                "write a plain instruction to ask; do not create a pre-call placeholder for unknown answers. "
                "Do not add a variable legend or duplicate name variables. "
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
