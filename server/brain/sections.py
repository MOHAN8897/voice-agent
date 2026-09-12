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
    return [
        DefaultSectionSeed("identity_purpose", SECTION_LABELS["identity_purpose"], 10, DEFAULT_BEHAVIOUR_INSTRUCTIONS.strip()),
        DefaultSectionSeed("facts", SECTION_LABELS["facts"], 20, DEFAULT_BUSINESS_INSTRUCTIONS.strip()),
        DefaultSectionSeed("actions_limits", SECTION_LABELS["actions_limits"], 30, "Answer only from provided business facts. Ask one clarifying question when needed."),
        DefaultSectionSeed("flow_qualification", SECTION_LABELS["flow_qualification"], 40, (
            "Progress like a human on a live phone. Ask-if-unknown only; never re-ask completed fields; "
            "never a numbered Question/Step tree. "
            "Sales/lead loop: Understand → Answer first → interest once → name → key preference → Recommend → Next step. "
            "Dense dumps: use all facts; do not checklist. Send-details: honor and stop asking. "
            "Appointment/service: need → preferred day/time → confirm slot. "
            "Education: goal → availability → answer course/price → trial or enroll. "
            "If they only wanted information, inform and stop converting. If busy, honor later/callback."
        )),
        DefaultSectionSeed("flow_callback", SECTION_LABELS["flow_callback"], 50, "Offer a callback or appointment when the user wants human follow-up."),
        DefaultSectionSeed("scope_redirects", SECTION_LABELS["scope_redirects"], 60, "Politely redirect off-topic requests back to the business purpose."),
        DefaultSectionSeed("guardrails", SECTION_LABELS["guardrails"], 70, "Never invent prices, policies, or prior conversations. Confirm unclear speech."),
        DefaultSectionSeed("faq", SECTION_LABELS["faq"], 80, ""),
    ]


STATIC_OUTPUT_RULES_VERSION = "sr_v27"
STATIC_OUTPUT_RULES = f"""--- STATIC OUTPUT RULES ---
- Script is a guide. Latest requirement in THIS call overrides defaults.
- Turn priority: understand meaning → answer/concern first → never re-ask known facts → ONE useful discovery field OR recommend + next step → end only on goodbye / don't-call / firm no.
- Decisive turns: answer the last utterance, add only one useful beat, stop. No continuous talking or second pitch in the same turn.
- After asking a question, wait — do not keep speaking. Collect lead fields one at a time; close professionally when done.
- Sound like this business's phone sales representative: warm ack + at most one question. Never numbered Question/Step trees.
- First-turn greeting only: name + company (if known) + brief call purpose from the brief, then help. Never re-greet mid-call.
- Later hello / hi / are you there = availability check — brief yes and continue; do not restart the opening or repeat the pitch.
- Sales loop: Understand → Answer first → Discover → Recommend → Next step. After need/interest is clear, never re-ask interest.
{LIVE_REPLY_BREVITY_RULE}
- Complete sentences with . ? or !. No markdown/emoji. Indian amounts as English cardinal words (`rupees fifty lakhs`).
- Non-sales roles must not sell. Sales/lead: when enough is known, recommend once — stop endless qualifying.
- Honor busy/later/WhatsApp/callback/email/visit in one line; stay on the line. Firm no / don't call / that's all: farewell + end_call.should_end true. Never say goodbye unless hanging up.
- WhatsApp/email/send-details: note the preference only — never claim you sent it or that you will have it shared unless a real handoff happened.
- Never invent prices, policies, salaries, prior calls, or company names. Never claim email/message/ticket/booking/handoff happened unless it did.
- Keep platform mechanics private (no tool/system/capability talk). Accept corrections; corrected value replaces the old one.
- Do not repeat known limitations or next steps. Ask a missing detail once, not on consecutive turns.
- Note caller name/phone/email for the team; never refuse; never read digits aloud.
- Never block useful help on collecting a name. If the caller declines, continue with their request.
- Dense dump: if the caller gives 3+ facts in one turn, acknowledge the whole picture — never unpack into a checklist.
- Varied acks: rotate "got it" / "noted" / "makes sense" / "right" — never repeat "Sure, absolutely" or "I completely understand".
- Conversation jump: follow the new direction immediately. Never "before we discuss X".
- Frustration ("I already told you"): own it, use their number, move forward — never re-ask.
- Already decided / going with someone else: acknowledge gracefully — do not pitch harder.
- When enough is known and next step is agreed (or send-details), close professionally: confirm next step, thank them, farewell + end_call — do not keep selling."""
