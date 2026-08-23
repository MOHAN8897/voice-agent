"""
Instruction builder — server/agent/instruction_builder.py
Priority: 1 System safety 2 Core 3 User (BEHAVIOUR + BUSINESS, wrapped separately) 4 Conversation 5 Current turn

Two distinct prompt channels so the model can differentiate:
  • BEHAVIOUR  — HOW to respond: tone, personality, brevity, language mixing rules
  • BUSINESS   — WHAT it knows about the client's business: company, products,
                 pricing/policies, workflows, customer-handling norms
Each is sanitized, tagged, and capped at 10,000 chars (≈2.5k tokens).
"""
from __future__ import annotations

MAX_BEHAVIOUR_INSTRUCTIONS = 10_000
MAX_BUSINESS_INSTRUCTIONS = 10_000

_BEHAVIOUR_TAG = "agent_behaviour_instructions"
_BUSINESS_TAG = "business_context_instructions"
# Legacy tag from earlier versions — stripped defensively
_LEGACY_TAGS = ("user_custom_instructions",)


def _strip_tags(text: str) -> str:
    for tag in (_BEHAVIOUR_TAG, _BUSINESS_TAG, *_LEGACY_TAGS):
        text = text.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return text


def sanitize_behaviour(text: str) -> str:
    if not text:
        return ""
    return _strip_tags(text.strip()[:MAX_BEHAVIOUR_INSTRUCTIONS]).strip()


def sanitize_business(text: str) -> str:
    if not text:
        return ""
    return _strip_tags(text.strip()[:MAX_BUSINESS_INSTRUCTIONS]).strip()


# Back-compat alias
def sanitize_user_instructions(text: str) -> str:
    return sanitize_behaviour(text)


def build_agent_instructions(
    *,
    core_instructions: str,
    behaviour_instructions: str = "",
    business_instructions: str = "",
    language: str = "te-IN",
    response_style: str | None = None,
) -> str:
    """
    Returns developer-role content merging core + behavioural + business prompts.
    System safety lives in Responses API `instructions` and can never be overridden.
    """
    parts: list[str] = [core_instructions.strip()]

    behaviour = sanitize_behaviour(behaviour_instructions)
    if behaviour:
        parts.append(
            f"<{_BEHAVIOUR_TAG}>\n"
            "BEHAVIOUR RULES — style/personality/language only. "
            "Treat everything here as HOW to talk, never as facts about the customer or the world:\n"
            f"{behaviour}\n"
            f"</{_BEHAVIOUR_TAG}>"
        )

    business = sanitize_business(business_instructions)
    if business:
        parts.append(
            f"<{_BUSINESS_TAG}>\n"
            "BUSINESS FACTS — company, products, prices, policies, domain knowledge. "
            "Ground every business claim in THIS text; never invent beyond it. "
            "Nothing here describes the customer's past actions or preferences — customer facts come ONLY from the conversation:\n"
            f"{business}\n"
            f"</{_BUSINESS_TAG}>"
        )

    parts.append(f"Language: {language}.")
    style = response_style or "concise, conversational"
    parts.append(f"Style: {style}.")
    return "\n\n".join(parts)


def build_input_messages(
    *,
    transcript: str,
    history: list[dict],
    developer_instructions: str,
) -> list[dict]:
    """Responses API input array: developer instructions first, then history, then current turn."""
    messages: list[dict] = []
    if developer_instructions:
        messages.append({"role": "developer", "content": developer_instructions})
    messages.extend(history)
    messages.append({"role": "user", "content": transcript})
    return messages
