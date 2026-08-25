"""Object C — deterministic compact render of B for the live LLM."""
from __future__ import annotations

from typing import Any

from server.agent.brain_prompt_composer import estimate_tokens
from server.config.env import get_settings


def build(
    snapshot: dict[str, Any] | None,
    *,
    include_summary: bool = False,
    max_tokens: int | None = None,
) -> str:
    """
    Render live projection C.
    If rolling summary is sent as a separate input[2], pass include_summary=False
    so C stays structured slots only (singularity rule).
    """
    snap = snapshot or {}
    cap = max_tokens if max_tokens is not None else get_settings().memory_projection_max_tokens
    cap = max(40, min(int(cap), 300))

    facts = snap.get("facts") or {}
    prefs = snap.get("preferences") or {}
    context = str(snap.get("important_context") or "").strip()
    summary = str(snap.get("summary") or "").strip()

    sections: list[tuple[str, str]] = []
    if facts:
        fact_line = " | ".join(f"{k}: {v}" for k, v in facts.items() if v)
        if fact_line:
            sections.append(("facts", f"[Facts]\n{fact_line}"))
    if prefs:
        pref_line = " | ".join(f"{k}: {v}" for k, v in prefs.items() if v)
        if pref_line:
            sections.append(("prefs", f"[Preferences]\n{pref_line}"))
    if context:
        sections.append(("context", f"[Context]\n{context}"))
    if include_summary and summary:
        sections.append(("summary", f"[Summary]\n{summary}"))

    if not sections:
        return ""

    priority = ["facts", "prefs", "context", "summary"]
    kept: list[str] = []
    for name in priority:
        piece = next((text for n, text in sections if n == name), None)
        if not piece:
            continue
        candidate = "\n".join(kept + [piece]).strip()
        if estimate_tokens(candidate) <= cap:
            kept.append(piece)
            continue
        truncated = _truncate_to_tokens(piece, max(20, cap - estimate_tokens("\n".join(kept))))
        if truncated:
            kept.append(truncated)
        break
    return "\n".join(kept).strip()


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text
    # chars/4 heuristic used by estimate_tokens
    limit = max(16, max_tokens * 4)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
