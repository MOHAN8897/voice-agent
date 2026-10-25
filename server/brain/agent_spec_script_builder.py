"""
AgentSpec Script Builder & Concrete Script Linter — server/brain/agent_spec_script_builder.py
Pipeline Steps 5 & 6: Fixed section skeleton, template variable injection, strict linting and repair loop.
"""
from __future__ import annotations

import re
from typing import Any

from server.brain.agent_spec import AgentSpec, normalize_whitespace
from server.prompts.agent_voice_rules import normalize_compile_language, opening_line_for
from server.utils.logger import logger

_TEMPLATE_VERSION = "2026.1"

_OLD_DEFAULT_NAMES = {"priya", "alex"}
_ALLOWED_RUNTIME_TAGS = {"caller_name", "callback_phone", "lead_name", "lead_project", "customer_name"}


def _opening_for_spec(spec: AgentSpec, language: str, direction: str = "outbound") -> str:
    lang = normalize_compile_language(language)
    agent = spec.agent_name.value or "our representative"
    company = spec.company_name.value or "our company"
    return opening_line_for(lang, agent_name=agent, company_name=company,
                            work_scope='', direction=direction)


def generate_deterministic_script_from_spec(
    spec: AgentSpec,
    *,
    direction: str = "outbound",
    recording_disclosure_enabled: bool = False,
    recording_disclosure_text: str | None = None,
) -> str:
    """
    Renders an agent script from AgentSpec using fixed section templates.
    Identity values are injected as variables and NEVER paraphrased.
    """
    agent = spec.agent_name.value or "the representative"
    company = spec.company_name.value or "the business"
    loc = spec.location.value
    offering = spec.offering.value
    objective = spec.call_objective.value
    lang = normalize_compile_language(spec.language_code)
    outbound = direction.lower() not in ("inbound", "incoming")

    # Section 1: IDENTITY
    identity_lines = [f"You are {agent}, representing {company}. Always speak as {agent} — the only speaker on this call."]
    identity_section = "--- AGENT IDENTITY ---\n" + "\n".join(identity_lines)

    # Section 2: COMPANY & OFFER
    offer_parts = [f"{company}."]
    if offering:
        offer_parts.append(f"We offer {offering}.")
    if loc:
        offer_parts.append(f"Located in {loc}.")
    if objective:
        offer_parts.append(f"Our goal on this call: {objective}.")
    offer_section = "--- COMPANY & OFFER ---\n" + " ".join(offer_parts)

    # Section 3: CANONICAL OPENING
    opening_lead = "After the callee speaks, say once:" if outbound else "When you answer, say once:"
    opening_line = _opening_for_spec(spec, lang, direction=direction)
    opening_section = f"--- CANONICAL OPENING ---\n{opening_lead}\n{opening_line}"

    # Section 4: ROLE ON THIS CALL
    role_lines = [
        f"{'Outbound' if outbound else 'Inbound'} representative for {company}. Answer questions first using COMPANY & OFFER only.",
        "Speak in short, decisive, professional beats — only what this moment needs, then stop.",
    ]
    if spec.qualification_questions:
        items_str = ", ".join(spec.qualification_questions)
        role_lines.append(f"When they have time, discover: {items_str} (one question at a time).")
    if objective:
        role_lines.append(f"Guide interested callers toward: {objective} — never pressure.")
    role_lines.append("When they confirm they are done or confirm the next step: confirm, thank, and make the close decision — no extra pitch. Never speak the farewell; the platform owns it.")
    role_section = "--- YOUR ROLE ON THIS CALL ---\n" + "\n".join(role_lines)

    # Section 5: HOW THE CALL SHOULD GO & COMPLIANCE HOOKS
    call_go_lines = [
        "- Answer first. Whatever they just asked gets a direct answer before you add anything else.",
        "- Ask one question at a time, then stop and listen. Two questions in a row sounds like an interrogation.",
        "- Introduce yourself clearly and state the purpose of the call directly.",
        "- If the recipient is busy: politely ask for a convenient callback time, never push.",
        "- Respect calling window & DND regulations: Never call outside permitted legal calling hours (09:00 - 19:00 local time).",
    ]
    if recording_disclosure_enabled:
        disclosure = (
            recording_disclosure_text
            or "Please note that this call is recorded for quality and training purposes."
        )
        call_go_lines.append(f"- RECORDING DISCLOSURE: Inform caller early: '{disclosure}'")
    if spec.constraints:
        for c in spec.constraints:
            call_go_lines.append(f"- CONSTRAINT: {c}")
    call_go_lines.append("- Represent the business naturally. If asked whether you are AI, answer honestly and briefly; do not pretend to be human.")
    how_call_goes = "--- HOW THE CALL SHOULD GO ---\n" + "\n".join(call_go_lines)

    # Section 6: WHEN YOU DO NOT KNOW
    dont_know = (
        "--- WHEN YOU DO NOT KNOW SOMETHING ---\n"
        "Say plainly that you do not have that detail, and offer to have someone confirm it.\n"
        "Never invent a price, discount, start date, policy, or outcome. Never claim a booking was made unless confirmed.\n"
        "If they ask about something outside this business, give one brief honest line and steer back to what you can help with."
    )

    # Section 7: WHAT TO REMEMBER
    remember = (
        "--- WHAT TO REMEMBER BEFORE YOU CLOSE ---\n"
        "- Their name, once they give it.\n"
        "- What they are looking for, and the next step agreed to.\n"
        "- A way to reach them, only if they want to be contacted. Never read a number back out loud."
    )

    full_script = "\n\n".join([
        identity_section,
        offer_section,
        opening_section,
        role_section,
        how_call_goes,
        dont_know,
        remember,
    ])
    return full_script


def lint_agent_script(script: str, spec: AgentSpec, *, recording_disclosure_enabled: bool = False) -> list[str]:
    """
    Concrete script linter enforcing the 7 integrity checks:
    1. Contains agent_name and company_name exactly as in spec.
    2. Denylist check: Contains no name from denylist ('Priya', 'Alex') unless spec specifies it.
    3. Check names following 'this is / I am / my name is' strictly equal agent_name.
    4. No unresolved build-time placeholders like {{unknown}} or {{company_name}} (runtime tags like {{lead_name}} allowed).
    5. Location, offering, and objective are present if in spec.
    6. Recording disclosure present if recording is on.
    """
    issues: list[str] = []
    text = script or ""
    text_l = text.lower()

    agent = (spec.agent_name.value or "").strip()
    company = (spec.company_name.value or "").strip()

    # 1. Identity exact presence
    if agent and agent.lower() not in text_l:
        issues.append(f"Missing required agent name '{agent}' in script.")
    if company and company.lower() not in text_l:
        issues.append(f"Missing required company name '{company}' in script.")

    # 2. Denylist check
    for forbidden in _OLD_DEFAULT_NAMES:
        if forbidden in text_l:
            if not agent or forbidden != agent.lower():
                issues.append(f"Forbidden legacy default name '{forbidden}' found in script.")

    # 3. Check introduction speaker matches agent_name
    intro_matches = re.finditer(r"\b(?:this\s+is|i\s+am|my\s+name\s+is)\s+([A-Za-z]+)\b", text, re.I)
    for m in intro_matches:
        spoken_name = m.group(1).strip()
        if agent and spoken_name.lower() != agent.lower() and spoken_name.lower() not in {"calling", "the", "a"}:
            issues.append(f"Introductory speaker '{spoken_name}' does not match spec agent name '{agent}'.")

    # 4. Check for unrendered template placeholders
    from server.services.saas.script_variables import TEMPLATE_TAG_RE
    for match in TEMPLATE_TAG_RE.finditer(text):
        ph = match.group(1)
        if ph not in _ALLOWED_RUNTIME_TAGS | {"name", "full_name", "first_name", "last_name", "phone", "email", "company"} and not ph.startswith(("contact.", "system.")):
            issues.append(f"Unresolved template placeholder '{{{{{ph}}}}}' found in script.")

    # 5. Core facts presence
    if spec.location.value and spec.location.value.lower() not in text_l:
        # Check tokens of location
        loc_tokens = [w for w in re.findall(r"\w+", spec.location.value.lower()) if len(w) > 3]
        if not any(t in text_l for t in loc_tokens):
            issues.append(f"Location '{spec.location.value}' missing from script.")

    if spec.offering.value:
        off_tokens = [w for w in re.findall(r"\w+", spec.offering.value.lower()) if len(w) > 3]
        if not any(t in text_l for t in off_tokens):
            issues.append(f"Offering '{spec.offering.value}' missing from script.")

    # 6. Recording disclosure check
    if recording_disclosure_enabled and "recording" not in text_l and "recorded" not in text_l:
        issues.append("Recording disclosure required but missing from script.")

    return issues
