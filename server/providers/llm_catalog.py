"""LLM model catalogs for provider registry and Dev Stack UI."""
from __future__ import annotations

from typing import Any

from server.config.constants import constants
from server.config.env import Settings
from server.prompts.voice_defaults import DEFAULT_OPENAI_MODEL, OPENAI_MODEL_CATALOG
from server.realtime.models import is_realtime_llm_model


def llm_models_for_provider(provider_id: str, settings: Settings) -> list[dict[str, Any]]:
    """Return catalog rows for stack picker — intersected with env allowlists where applicable."""
    if provider_id == "openai":
        allowed = set(settings.allowed_openai_models)
        default_model = (settings.openai_model or DEFAULT_OPENAI_MODEL).strip()
        models: list[dict[str, Any]] = []
        for entry in OPENAI_MODEL_CATALOG:
            mid = entry["id"]
            if mid not in allowed:
                continue
            realtime = is_realtime_llm_model(mid)
            models.append(
                {
                    "id": mid,
                    "label": entry["label"],
                    "structured_output": not realtime,
                    "prompt_caching": True,
                    "realtime": realtime,
                    "pricing_key": f"openai:{mid}",
                    "tier": entry.get("tier"),
                    "default": mid == default_model,
                }
            )
        return models or [
            {
                "id": m,
                "label": m,
                "structured_output": not is_realtime_llm_model(m),
                "prompt_caching": True,
                "realtime": is_realtime_llm_model(m),
                "pricing_key": f"openai:{m}",
                "default": m == default_model,
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

    return []
