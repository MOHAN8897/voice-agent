"""Convert OpenAI Responses-API input messages into chat / Gemini shapes."""
from __future__ import annotations

import copy
import json
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
    call_ids: dict[str, str | None] = {}
    for msg in input_messages or []:
        role = str(msg.get("role") or "user")
        native = msg.get("_gemini_content")
        if role == "assistant" and isinstance(native, dict):
            # Preserve every part, including opaque thought signatures. They
            # are bound to their original function parts in Gemini 3+.
            contents.append(copy.deepcopy(native))
            functions = [part["functionCall"] for part in native.get("parts", [])
                         if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)]
            for call, function in zip(msg.get("tool_calls") or [], functions):
                call_ids[str(call.get("id") or "")] = function.get("id")
            continue
        if role == "tool":
            internal_id = str(msg.get("tool_call_id") or "")
            if internal_id not in call_ids:
                raise ValueError("Gemini tool response has no matching native function call")
            try:
                result = json.loads(message_text(msg))
            except (ValueError, TypeError):
                result = {"result": message_text(msg)}
            if not isinstance(result, dict):
                result = {"result": result}
            response = {"name": str(msg.get("name") or ""), "response": result}
            if call_ids[internal_id]:
                response["id"] = call_ids[internal_id]
            part = {"functionResponse": response}
            if contents and contents[-1]["role"] == "user":
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
            continue
        if role == "assistant" and msg.get("tool_calls"):
            raise ValueError("Gemini tool history is missing its native signed content")
        text = message_text(msg).strip()
        if not text:
            continue
        if role in ("developer", "system"):
            system_parts.append(text)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        if (contents and contents[-1]["role"] == gemini_role
                and set(contents[-1]["parts"][-1]) == {"text"}):
            prev = contents[-1]["parts"][-1]["text"]
            contents[-1]["parts"][-1]["text"] = f"{prev}\n\n{text}"
        else:
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
    return "\n\n".join(system_parts).strip(), contents
