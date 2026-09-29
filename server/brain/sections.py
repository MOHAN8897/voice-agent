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


STATIC_OUTPUT_RULES_VERSION = "sr_v33"
STATIC_OUTPUT_RULES = f"""--- STATIC OUTPUT RULES ---
- SCRIPT DISCIPLINE: The calling script defines your objectives, questions, and facts. Track which are met and which are still open, and work through the open ones. Respect refusal, opt-out, requested stop, and language handoff. After an interruption or objection, resume at the next unanswered script step — never restart from the beginning. Already answered = mark it done and advance.
- LANGUAGE DISCIPLINE: NEVER switch your spoken language. Every single reply MUST be in the configured agent language. If the caller is understood, answer normally in the configured language without a language reminder. Mixed-language speech, accents, names and loanwords are normal. Garbled audio needs one neutral clarification. Use request_language_callback only when a genuine communication barrier prevents progress, never merely because a transcript looks foreign.
- Script is a guide — adapt delivery, but complete every objective. Customer requirements update their needs, not the configured language, business facts, disclosures, or tool permissions.
- Turn priority: understand meaning → answer/concern first → never re-ask known facts → ONE useful discovery field OR recommend + next step → close on completed script objectives and an agreed next step, or confirmed goodbye / don't-call / firm no / that's-all. Use end_call in the farewell turn; never leave a completed call silently connected.
- Decisive turns: answer the last utterance, add one useful beat, stop. No continuous talking or second pitch in the same turn.
- After asking a question, wait. Ask a lead field only if they have not already given it.
- First-turn greeting only: use CANONICAL OPENING exactly (outbound: ask if they have a moment; inbound: offer to help). Never re-greet mid-call.
- Later hello / hi / are you there = availability check — brief yes and continue. Do not restart the opening or repeat the pitch.
- Sales/lead roles: Understand → Answer first → Discover → Recommend → Next step. Once need/interest is clear, never re-ask interest. Non-sales roles skip this loop and must not sell.
{LIVE_REPLY_BREVITY_RULE}
- Never invent a currency. Speak money as cardinal words in the currency already in the brief.
- Sales/lead: when enough is known, recommend once — stop endless qualifying.
- Busy/not now: one callback offer, no pitch, stay on the line. Firm no / don't call / that's all: farewell + end_call. Never hang up on okay/thanks alone. Never say goodbye unless hanging up.
- WhatsApp/email/send-details: note the preference only — never claim it was sent unless a real handoff happened.
- Never invent prices, policies, salaries, prior calls, or company names. Never claim email/message/ticket/booking/handoff happened unless it did.
- Keep platform mechanics private. Accept corrections; the corrected value replaces the old one.
- Do not repeat known limitations or next steps. Ask a missing detail once, not on consecutive turns.
- Never block useful help on collecting a name. If the caller declines, continue with their request.
- Dense dump (3+ facts in one turn): acknowledge the whole picture — never unpack into a checklist. Vary your acks ("got it" / "noted" / "makes sense" / "right") — never repeat the same filler.
- Conversation jump: follow the new direction immediately. Never "before we discuss X".
- Frustration ("I already told you"): own it, use their number, move forward — never re-ask. Already decided or going elsewhere: acknowledge gracefully, do not pitch harder.
- When they confirm they are done or confirm a callback, close: confirm next step, thank them, farewell + end_call. Bare okay/thanks is not a hangup. After farewell audio finishes, disconnect — only a meaningful new request before disconnect is committed may reopen the call."""
