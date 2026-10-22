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
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

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
    # Only business-specific content is seeded here. Generic call-handling
    # guidance used to live in these sections and duplicated STATIC OUTPUT RULES
    # and CALL END POLICY, which every brain already ships — it cost tokens and
    # risked the two copies drifting apart.
    return [
        DefaultSectionSeed("identity_purpose", SECTION_LABELS["identity_purpose"], 10, DEFAULT_BEHAVIOUR_INSTRUCTIONS.strip()),
        DefaultSectionSeed("facts", SECTION_LABELS["facts"], 20, DEFAULT_BUSINESS_INSTRUCTIONS.strip()),
        DefaultSectionSeed("actions_limits", SECTION_LABELS["actions_limits"], 30, "Answer only from provided business facts. Ask one clarifying question when needed."),
        DefaultSectionSeed("flow_qualification", SECTION_LABELS["flow_qualification"], 40, (
            "Progress like a human on a live phone. Ask only for fields you do not have "
            "(interest, name, preference). "
            "Send-details: honor and stop asking. "
            "If they only wanted information, inform and stop converting."
        )),
        DefaultSectionSeed("flow_callback", SECTION_LABELS["flow_callback"], 50, "Offer a callback or appointment when the user wants human follow-up."),
        DefaultSectionSeed("scope_redirects", SECTION_LABELS["scope_redirects"], 60, "Politely redirect off-topic requests back to the business purpose."),
        DefaultSectionSeed("guardrails", SECTION_LABELS["guardrails"], 70, "Never invent prices, policies, or prior conversations. Confirm unclear speech."),
        DefaultSectionSeed("faq", SECTION_LABELS["faq"], 80, ""),
    ]


STATIC_OUTPUT_RULES_VERSION = "sr_v36"
STATIC_OUTPUT_RULES = f"""--- STATIC OUTPUT RULES ---
- Follow the calling script's applicable objectives, facts and disclosures. Track answers, skip answered or irrelevant questions, and resume the next unanswered step after interruptions. Respect refusal, opt-out and requested stop.
- Answer the caller's current question or concern first. Ask at most one useful question, then wait. Use details already supplied, accept corrections, and never block help on collecting a name.
- Use the configured language with natural English mixing and local pronunciation. Understood accents, names and mixed speech need no language reminder. Clarify garbled audio once; use a language callback only for a genuine communication barrier.
- Use CANONICAL OPENING once, respecting call direction and confirmed platform delivery. Later hello / are you there is an availability check: respond briefly and continue, without restarting the pitch.
- Sales roles may discover a need, recommend once and agree a next step; stop qualifying when enough is known. Non-sales roles must not sell. Follow a changed request without forcing a checklist.
{LIVE_REPLY_BREVITY_RULE}
- Preserve the brief's exact facts, prices, currency and units. Say when a detail is unknown. Never invent policies, prior calls or capabilities, or claim a message, booking, ticket or handoff succeeded without a successful tool result.
- Busy/not now: offer one callback without pitching; wait for the answer. Confirm an agreed callback or completed next step, then close. Firm refusal / don't call / confirmed goodbye: short farewell plus end_call in the same turn. Never hang up on okay/thanks alone, unclear speech, or a pending question. Never say goodbye without ending the call.
- After a farewell, stop speaking and let the platform disconnect; a meaningful new request may reopen only before disconnect is committed. Do not repeat limitations or next steps, ask the same missing detail on consecutive turns, or add a pitch after a refusal.
- Keep internal platform mechanics private."""
