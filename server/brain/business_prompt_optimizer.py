"""
Business prompt optimizer — one-time LLM optimization on publish/optimize/save.
Never runs on live turn path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.agent.brain_prompt_composer import estimate_tokens, fit_text_to_tokens
from server.config.env import get_settings

OPTIMIZER_VERSION = "v2"
OPTIMIZER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "optimized_prompt": {"type": "string"},
        "preserved_facts": {"type": "array", "items": {"type": "string"}},
        "preserved_rules": {"type": "array", "items": {"type": "string"}},
        "deduplicated_items": {"type": "array", "items": {"type": "string"}},
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["severity", "description"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["optimized_prompt", "preserved_facts", "preserved_rules", "deduplicated_items", "conflicts"],
    "additionalProperties": False,
}


@dataclass
class OptimizerResult:
    optimized_business_prompt: str
    preserved_facts: list[str] = field(default_factory=list)
    preserved_rules: list[str] = field(default_factory=list)
    deduplicated_items: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    source_checksum: str = ""
    optimizer_model: str = "deterministic_v1"
    optimizer_version: str = OPTIMIZER_VERSION
    optimized_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_token_estimate: int = 0
    optimized_token_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimized_business_prompt": self.optimized_business_prompt,
            "preserved_facts": self.preserved_facts,
            "preserved_rules": self.preserved_rules,
            "deduplicated_items": self.deduplicated_items,
            "conflicts": self.conflicts,
            "source_checksum": self.source_checksum,
            "optimizer_model": self.optimizer_model,
            "optimizer_version": self.optimizer_version,
            "optimized_at": self.optimized_at,
            "raw_token_estimate": self.raw_token_estimate,
            "optimized_token_estimate": self.optimized_token_estimate,
            "tokens_saved": max(0, self.raw_token_estimate - self.optimized_token_estimate),
        }


def _extract_bullets(text: str) -> list[str]:
    lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
    return [ln for ln in lines if len(ln) > 3]


def _dedupe_lines(text: str) -> tuple[str, list[str]]:
    seen: set[str] = set()
    deduped: list[str] = []
    removed: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            removed.append(stripped)
            continue
        seen.add(key)
        deduped.append(stripped)
    return "\n".join(deduped), removed


def _deterministic_compress_dual(behaviour: str, business: str, *, max_tokens: int = 700) -> tuple[str, list[str]]:
    b_text, b_removed = _dedupe_lines(behaviour)
    z_text, z_removed = _dedupe_lines(business)
    parts = [
        "--- AGENT BEHAVIOUR ---",
        b_text,
        "--- BUSINESS CONTEXT ---",
        z_text,
    ]
    merged = "\n".join(parts)
    fitted = fit_text_to_tokens(merged, max_tokens)
    return fitted, b_removed + z_removed


async def _llm_compress_prompt(raw_prompt: str, *, budget_tokens: int) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.enable_openai:
        return None
    try:
        import asyncio

        from server.providers.base import LLMConfig
        from server.providers.openai_llm import OpenAILLMAdapter

        adapter = OpenAILLMAdapter()
        # User-editable slice only — static safety/voice stays outside this compress.
        target_words = max(80, min(400, int(budget_tokens * 0.22)))
        system = (
            "You compress voice-agent instructions for a Telugu phone assistant. "
            "Merge duplicate rules, remove repetition, and keep ALL facts, prices, names, "
            "policies, phone numbers, URLs, workflows, and guardrails exactly. "
            "Do not invent policy, pricing, or capabilities. "
            "Do not repeat Telugu-voice or safety rules that already exist in the platform prefix. "
            "Use concise section headers. Plain text only."
        )
        user = (
            f"Compress the following raw instructions to roughly {target_words} words or fewer "
            f"while preserving meaning:\n\n{raw_prompt}"
        )

        async def _run():
            return await adapter.structured_completion(
                input_messages=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
                schema=OPTIMIZER_SCHEMA,
                config=LLMConfig(
                    provider="openai",
                    model=settings.post_call_llm_model or settings.openai_model,
                ),
                schema_name="prompt_optimizer",
                max_output_tokens=min(900, budget_tokens),
            )

        payload = await asyncio.wait_for(_run(), timeout=12)
        if payload.get("optimized_prompt"):
            return payload
    except Exception:
        return None
    return None


async def optimize_session_dual_prompt(
    *,
    behaviour: str,
    business: str,
    raw_assembled: str,
    source_checksum: str,
    budget_tokens: int = 2500,
    previous_optimized: str | None = None,
) -> OptimizerResult:
    """Merge dev behaviour + client business into one concise cached core prompt."""
    settings = get_settings()
    raw_tokens = estimate_tokens(raw_assembled)
    llm_payload = await _llm_compress_prompt(raw_assembled, budget_tokens=budget_tokens)

    if llm_payload:
        optimized = str(llm_payload.get("optimized_prompt", "")).strip()
        model = settings.post_call_llm_model or settings.openai_model
        facts = list(llm_payload.get("preserved_facts") or [])[:12]
        rules = list(llm_payload.get("preserved_rules") or [])[:12]
        deduped = list(llm_payload.get("deduplicated_items") or [])[:12]
        conflicts = list(llm_payload.get("conflicts") or [])
    else:
        optimized, deduped = _deterministic_compress_dual(
            behaviour, business, max_tokens=max(220, int(budget_tokens * 0.35))
        )
        model = "deterministic_v1"
        facts = _extract_bullets(raw_assembled)[:6]
        rules = [ln for ln in facts if any(k in ln.lower() for k in ("never", "only", "must", "do not"))]
        conflicts = []

    if previous_optimized and previous_optimized.strip() == optimized.strip():
        conflicts.append(
            {
                "severity": "warning",
                "source_section_ids": [],
                "description": "Optimized prompt unchanged from previous version",
                "recommended_resolution": "Edit behaviour or business instructions before re-saving",
            }
        )

    opt_tokens = estimate_tokens(optimized)
    return OptimizerResult(
        optimized_business_prompt=optimized,
        preserved_facts=facts[:6],
        preserved_rules=rules[:6],
        deduplicated_items=deduped[:12],
        conflicts=conflicts,
        source_checksum=source_checksum,
        optimizer_model=model,
        optimizer_version=OPTIMIZER_VERSION,
        raw_token_estimate=raw_tokens,
        optimized_token_estimate=opt_tokens,
    )


async def optimize_business_prompt(
    raw_prompt: str,
    *,
    source_checksum: str,
    previous_optimized: str | None = None,
    budget_tokens: int = 2500,
) -> OptimizerResult:
    """
    One-time business prompt optimization for agent publish/optimize.
    Preserves section delimiters when using deterministic fallback.
    """
    settings = get_settings()
    raw_tokens = estimate_tokens(raw_prompt)
    llm_payload = await _llm_compress_prompt(raw_prompt, budget_tokens=budget_tokens)

    if llm_payload:
        optimized = str(llm_payload.get("optimized_prompt", "")).strip()
        model = settings.post_call_llm_model or settings.openai_model
        facts = list(llm_payload.get("preserved_facts") or [])[:12]
        rules = list(llm_payload.get("preserved_rules") or [])[:12]
        deduped = list(llm_payload.get("deduplicated_items") or [])[:12]
        conflicts = list(llm_payload.get("conflicts") or [])
    else:
        sections = re.split(r"(?=<!-- section:)", raw_prompt)
        normalized_parts = []
        for part in sections:
            if not part.strip():
                continue
            normalized_parts.append(part.rstrip())
        optimized = "\n\n".join(normalized_parts)
        model = "deterministic_v1"
        facts = _extract_bullets(raw_prompt)[:12]
        rules = [ln for ln in facts if any(k in ln.lower() for k in ("never", "only", "must", "do not"))]
        deduped = []
        conflicts = []

    if previous_optimized and previous_optimized.strip() == optimized.strip():
        conflicts.append(
            {
                "severity": "warning",
                "source_section_ids": [],
                "description": "Optimized prompt unchanged from previous version",
                "recommended_resolution": "Edit business sections before re-publishing",
            }
        )

    return OptimizerResult(
        optimized_business_prompt=optimized,
        preserved_facts=facts[:6],
        preserved_rules=rules[:6],
        deduplicated_items=deduped[:12],
        conflicts=conflicts,
        source_checksum=source_checksum,
        optimizer_model=model,
        optimizer_version=OPTIMIZER_VERSION,
        raw_token_estimate=raw_tokens,
        optimized_token_estimate=estimate_tokens(optimized),
    )
