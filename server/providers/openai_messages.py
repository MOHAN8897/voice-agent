"""Convert OpenAI Responses-API input messages into chat / Gemini shapes."""
from __future__ import annotations

from typing import Any


def message_text(msg: dict[str, Any] | None) -> str:
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content or "")


def to_chat_messages(input_messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Keep the compiled brain as `system` — never drop developer blocks."""
    out: list[dict[str, str]] = []
    for msg in input_messages or []:
        text = message_text(msg).strip()
        if not text:
            continue
        role = str(msg.get("role") or "user")
        if role in ("developer", "system"):
            chat_role = "system"
        elif role == "assistant":
            chat_role = "assistant"
        else:
            chat_role = "user"
        if out and out[-1]["role"] == chat_role:
            out[-1]["content"] = f"{out[-1]['content']}\n\n{text}"
        else:
            out.append({"role": chat_role, "content": text})
    return out


def openai_input_to_gemini(
    input_messages: list[dict[str, Any]] | None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Brain (developer) → Gemini system_instruction (stable cache prefix).
    Memory / summary / history / transcript stay in contents (dynamic).
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for msg in input_messages or []:
        text = message_text(msg).strip()
        if not text:
            continue
        role = str(msg.get("role") or "user")
        if role in ("developer", "system"):
            system_parts.append(text)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        if contents and contents[-1]["role"] == gemini_role:
            prev = contents[-1]["parts"][0]["text"]
            contents[-1]["parts"][0]["text"] = f"{prev}\n\n{text}"
        else:
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
    return "\n\n".join(system_parts).strip(), contents
