"""
Business brain section taxonomy — Phase 2.
Normative: architecture/data-models/brain-compilation.md
"""
from __future__ import annotations

from dataclasses import dataclass

from server.prompts.voice_defaults import (
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
)

SECTION_TYPES = (
    "identity_purpose",
    "facts",
    "actions_limits",
    "flow_qualification",
    "flow_callback",
    "scope_redirects",
    "guardrails",
    "faq",
    "custom",
)

SECTION_LABELS: dict[str, str] = {
    "identity_purpose": "Identity & Purpose",
    "facts": "Business Facts",
    "actions_limits": "Actions & Limits",
    "flow_qualification": "Qualification Flow",
    "flow_callback": "Callback / Appointment Flow",
    "scope_redirects": "Scope & Redirects",
    "guardrails": "Guardrails",
    "faq": "FAQ",
    "custom": "Custom",
}

SECTION_MAX_CHARS = 8_000
SECTION_REQUIRED_TYPES = ("identity_purpose", "facts", "guardrails")


@dataclass(frozen=True)
class DefaultSectionSeed:
    type: str
    title: str
    order: int
    raw_text: str
    enabled: bool = True


def default_section_seeds() -> list[DefaultSectionSeed]:
    return [
        DefaultSectionSeed("identity_purpose", SECTION_LABELS["identity_purpose"], 10, DEFAULT_BEHAVIOUR_INSTRUCTIONS.strip()),
        DefaultSectionSeed("facts", SECTION_LABELS["facts"], 20, DEFAULT_BUSINESS_INSTRUCTIONS.strip()),
        DefaultSectionSeed("actions_limits", SECTION_LABELS["actions_limits"], 30, "Answer only from provided business facts. Ask one clarifying question when needed."),
        DefaultSectionSeed("flow_qualification", SECTION_LABELS["flow_qualification"], 40, "Qualify budget, timeline, and location before recommending next steps."),
        DefaultSectionSeed("flow_callback", SECTION_LABELS["flow_callback"], 50, "Offer a callback or appointment when the user wants human follow-up."),
        DefaultSectionSeed("scope_redirects", SECTION_LABELS["scope_redirects"], 60, "Politely redirect off-topic requests back to the business purpose."),
        DefaultSectionSeed("guardrails", SECTION_LABELS["guardrails"], 70, "Never invent prices, policies, or prior conversations. Confirm unclear speech."),
        DefaultSectionSeed("faq", SECTION_LABELS["faq"], 80, ""),
    ]


STATIC_OUTPUT_RULES_VERSION = "sr_v1"
STATIC_OUTPUT_RULES = """--- STATIC OUTPUT RULES ---
- Reply in spoken Telugu (Unicode script) unless the user clearly uses another language.
- Default 1–2 short sentences; one question maximum per turn.
- Plain text only — no markdown, bullets, or URLs in voice replies.
- Use only facts from the business brain and current conversation.
- If unsure, ask a brief clarifying question instead of guessing."""
