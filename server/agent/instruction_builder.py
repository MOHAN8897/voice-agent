"""
Brain request input builder — single developer message + history + transcript.
Phase 1+2: typed input_text blocks with optional prompt_cache_breakpoint.
"""
from __future__ import annotations

# Re-export sanitizers for backward compatibility
from server.agent.brain_prompt_composer import (  # noqa: F401
    MAX_BEHAVIOUR_CHARS,
    MAX_BUSINESS_CHARS,
    sanitize_behaviour,
    sanitize_business,
    sanitize_user_instructions,
)

# Legacy aliases
MAX_BEHAVIOUR_INSTRUCTIONS = MAX_BEHAVIOUR_CHARS
MAX_BUSINESS_INSTRUCTIONS = MAX_BUSINESS_CHARS

# Placed next to the live utterance (not in the cached brain) so the LLM
# re-reads listen/answer-first discipline on every turn.
LIVE_TURN_DISCIPLINE = (
    "[This turn — listen]\n"
    "Answer first if they asked a question. Use known facts — never re-ask. "
    "At most ONE new question, and only if it changes the recommendation or next step. "
    "If they dumped several facts or asked to send details / check later, acknowledge and progress — no checklist.\n"
    "Caller: "
)


def _message_content_block(role: str, text: str) -> dict:
    """Responses API: user/developer use input_text; assistant history uses output_text."""
    if role == "assistant":
        return {"type": "output_text", "text": str(text)}
    return {"type": "input_text", "text": str(text)}


def wrap_live_transcript(transcript: str) -> str:
    raw = str(transcript or "").strip()
    if not raw:
        return raw
    return f"{LIVE_TURN_DISCIPLINE}{raw}"


def build_brain_request_input(
    *,
    brain_prompt: str,
    history: list[dict],
    transcript: str,
    enable_cache: bool = False,
    session_summary: str | None = None,
    rolling_summary: str | None = None,
    memory_projection: str | None = None,
) -> list[dict]:
    """Responses API input: one cached developer block, optional memory C, summary, history, current turn."""
    content_block: dict = {
        "type": "input_text",
        "text": brain_prompt,
    }
    if enable_cache:
        content_block["prompt_cache_breakpoint"] = {"mode": "explicit"}

    messages: list[dict] = [
        {
            "type": "message",
            "role": "developer",
            "content": [content_block],
        }
    ]

    if memory_projection:
        messages.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"[Memory projection]\n{memory_projection}"}],
            }
        )

    rolling = (rolling_summary or "").strip() or None
    summary = (session_summary or "").strip() or None
    if rolling:
        messages.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"[Rolling summary]\n{rolling}"}],
            }
        )
    elif summary:
        messages.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"[Session summary]\n{summary}"}],
            }
        )

    for item in history:
        role = item.get("role", "user")
        text = item.get("content", "")
        if not text:
            continue
        messages.append(
            {
                "type": "message",
                "role": role,
                "content": [_message_content_block(role, text)],
            }
        )

    messages.append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": wrap_live_transcript(transcript)}],
        }
    )
    return messages


def build_live_input(
    *,
    compiled_brain_text: str,
    history: list[dict],
    transcript: str,
    enable_cache: bool = False,
    session_summary: str | None = None,
    rolling_summary: str | None = None,
    memory_projection: str | None = None,
) -> list[dict]:
    """
    Sole live LLM input builder.
    input[0] developer: compiled_brain_text [L2 cached]
    input[1] user: memory projection C [dynamic]
    input[2] user: rolling summary [optional — singularity vs C]
    """
    return build_brain_request_input(
        brain_prompt=compiled_brain_text,
        history=history,
        transcript=transcript,
        enable_cache=enable_cache,
        session_summary=session_summary,
        rolling_summary=rolling_summary,
        memory_projection=memory_projection,
    )


# --- Legacy API (delegates to composer) ---

def build_agent_instructions(
    *,
    core_instructions: str = "",
    behaviour_instructions: str = "",
    business_instructions: str = "",
    language: str = "te-IN",
    response_style: str | None = None,
) -> str:
    """Deprecated — use compose_brain_prompt(). Kept for tests/migration."""
    from server.agent.brain_prompt_composer import compose_brain_prompt

    return compose_brain_prompt(
        behaviour=behaviour_instructions,
        business=business_instructions,
        language=language,
        style=response_style,
    )


def build_input_messages(
    *,
    transcript: str,
    history: list[dict],
    developer_instructions: str,
    enable_cache: bool = False,
) -> list[dict]:
    """Deprecated — use build_brain_request_input()."""
    return build_brain_request_input(
        brain_prompt=developer_instructions,
        history=history,
        transcript=transcript,
        enable_cache=enable_cache,
    )
