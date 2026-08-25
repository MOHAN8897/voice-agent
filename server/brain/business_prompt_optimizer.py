"""
Business prompt optimizer — one-time LLM optimization on publish/optimize.
Never runs on live turn path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.config.env import get_settings


@dataclass
class OptimizerResult:
    optimized_business_prompt: str
    preserved_facts: list[str] = field(default_factory=list)
    preserved_rules: list[str] = field(default_factory=list)
    deduplicated_items: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    source_checksum: str = ""
    optimizer_model: str = "deterministic_v1"
    optimizer_version: str = "v1"
    optimized_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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
        }


def _extract_bullets(text: str) -> list[str]:
    lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
    return [ln for ln in lines if len(ln) > 3]


async def optimize_business_prompt(
    raw_prompt: str,
    *,
    source_checksum: str,
    previous_optimized: str | None = None,
) -> OptimizerResult:
    """
    Deterministic optimizer for Phase 2 (no live-path LLM).
    Collapses excessive blank lines and preserves section delimiters byte-for-byte inside sections.
    """
    settings = get_settings()
    model = settings.openai_model if settings.enable_openai else "deterministic_v1"

    # Preserve delimiters and raw section bodies — only normalize outer whitespace between sections
    sections = re.split(r"(?=<!-- section:)", raw_prompt)
    normalized_parts = []
    for part in sections:
        if not part.strip():
            continue
        normalized_parts.append(part.rstrip())
    optimized = "\n\n".join(normalized_parts)

    facts = _extract_bullets(raw_prompt)[:12]
    rules = [ln for ln in facts if any(k in ln.lower() for k in ("never", "only", "must", "do not"))]

    conflicts: list[dict[str, Any]] = []
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
        deduplicated_items=[],
        conflicts=conflicts,
        source_checksum=source_checksum,
        optimizer_model=model,
    )
