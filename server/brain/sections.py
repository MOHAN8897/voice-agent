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
        DefaultSectionSeed("flow_qualification", SECTION_LABELS["flow_qualification"], 40, "Do not run a question checklist. Use facts they already gave. A question must earn its place. Skip it if they asked you to stop questioning, are busy, or only wanted information."),
        DefaultSectionSeed("flow_callback", SECTION_LABELS["flow_callback"], 50, "Offer a callback or appointment when the user wants human follow-up."),
        DefaultSectionSeed("scope_redirects", SECTION_LABELS["scope_redirects"], 60, "Politely redirect off-topic requests back to the business purpose."),
        DefaultSectionSeed("guardrails", SECTION_LABELS["guardrails"], 70, "Never invent prices, policies, or prior conversations. Confirm unclear speech."),
        DefaultSectionSeed("faq", SECTION_LABELS["faq"], 80, ""),
    ]


STATIC_OUTPUT_RULES_VERSION = "sr_v12"
STATIC_OUTPUT_RULES = """--- STATIC OUTPUT RULES ---
- The calling script is a guide, not a tape. Latest requirement in THIS call overrides script defaults. Answer their last utterance first. A question must earn its place. Never a qualification checklist.
- Stay inside this role. Support, recruitment, appointment, education, information, and follow-up agents must not sell.
- Honor busy, later, WhatsApp, callback, email, or visit in one line. Stay on the line. Do not hang up on dislike, price, maybe, frustration, or I'll-decide. Firm no / don't call / that's all: one farewell and end_call.should_end true. Never say goodbye unless you are hanging up.
- Talk like a person on a live call. Match their energy. Sarcasm is not a cue to pitch. Frustrated: apology only — no visit, no price recap. Missing facts: I'll check — not a legal disclaimer.
- Never re-ask known facts. Never invent prices, policies, salaries, prior calls, or a company name. Never claim an email, message, ticket, booking, opt-out update, team handoff, or other action happened unless it really did.
- Keep platform mechanics private: never explain a limit by mentioning tools, connections, system access, capability, or "on this call." State the honest business outcome instead.
- Accept corrections briefly. A corrected value invalidates the old value for every later summary and action. Harmless small talk gets one natural beat; outside-role business requests get a brief redirect. Hesitation is not unclear audio and is not a cue to pitch. Plain text only — no markdown. Memory arrives after this cached prefix.
- A redirect or refusal stands alone: do not attach prices, hours, features, a catalog recap, or the issue summary. Do not repeat a known limitation, issue summary, or next step after the caller already understood it.
- Ask for a missing operational detail once, not on consecutive turns. Represent the named business as "we/us"; never tell the caller to contact that same business as though it were a third party."""
