"""LLM model catalogs for provider registry and Dev Stack UI."""
from __future__ import annotations

from typing import Any

from server.config.constants import constants
from server.config.env import Settings
from server.prompts.voice_defaults import OPENAI_MODEL_CATALOG


def llm_models_for_provider(provider_id: str, settings: Settings) -> list[dict[str, Any]]:
    """Return catalog rows for stack picker — intersected with env allowlists where applicable."""
    if provider_id == "openai":
        allowed = set(settings.allowed_openai_models)
        models: list[dict[str, Any]] = []
        for entry in OPENAI_MODEL_CATALOG:
            mid = entry["id"]
            if mid not in allowed:
                continue
            models.append(
                {
                    "id": mid,
                    "label": entry["label"],
                    "structured_output": True,
                    "prompt_caching": str(mid).startswith("gpt-5.6"),
                    "pricing_key": f"openai:{mid}",
                    "tier": entry.get("tier"),
                }
            )
        return models or [
            {
                "id": m,
                "label": m,
                "structured_output": True,
                "prompt_caching": str(m).startswith("gpt-5.6"),
                "pricing_key": f"openai:{m}",
            }
            for m in settings.allowed_openai_models
        ]

    if provider_id == "deepseek":
        default_model = (settings.deepseek_model or "deepseek-chat").strip()
        rows: list[dict[str, Any]] = []
        for mid, meta in constants.DEEPSEEK_LLM_MODELS.items():
            rows.append(
                {
                    "id": mid,
                    "label": meta["label"],
                    "structured_output": bool(meta.get("structured_output", True)),
                    "prompt_caching": bool(meta.get("prompt_caching", False)),
                    "pricing_key": f"deepseek:{mid}",
                    "default": mid == default_model,
                }
            )
        if default_model and default_model not in constants.DEEPSEEK_LLM_MODELS:
            rows.insert(
                0,
                {
                    "id": default_model,
                    "label": f"{default_model} (from DEEPSEEK_MODEL)",
                    "structured_output": True,
                    "prompt_caching": False,
                    "pricing_key": f"deepseek:{default_model}",
                    "default": True,
                },
            )
        return rows

    if provider_id == "gemini":
        default_model = (getattr(settings, "gemini_model", None) or "gemini-3.5-flash-lite").strip()
        rows: list[dict[str, Any]] = []
        for mid, meta in constants.GEMINI_LLM_MODELS.items():
            rows.append(
                {
                    "id": mid,
                    "label": meta["label"],
                    "structured_output": bool(meta.get("structured_output", True)),
                    "prompt_caching": bool(meta.get("prompt_caching", False)),
                    "tier": meta.get("tier"),
                    "default": mid == default_model,
                }
            )
        if default_model and default_model not in constants.GEMINI_LLM_MODELS:
            rows.insert(
                0,
                {
                    "id": default_model,
                    "label": f"{default_model} (from GEMINI_MODEL)",
                    "structured_output": True,
                    "prompt_caching": True,
                    "default": True,
                },
            )
        return rows

    return []
