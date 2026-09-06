"""
Provider catalog — server/providers/registry.py
Loads enabled providers from env; exposes safe metadata for catalog API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from server.config.constants import constants
from server.config.env import Settings, get_settings
from server.providers.base import LLMAdapter, STTAdapter, TTSAdapter
from server.providers.llm_catalog import llm_models_for_provider
from server.providers.openai_llm import OpenAILLMAdapter
from server.providers.sarvam_stt import SarvamSTTAdapter
from server.providers.sarvam_tts import SarvamTTSAdapter
from server.services.usage_pricing import build_pricing_metadata

_REGISTRY: "ProviderRegistry | None" = None

_PRICING_METADATA: dict[str, Any] = build_pricing_metadata(95.64)


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stt: dict[str, STTAdapter] = {}
        self._llm: dict[str, LLMAdapter] = {}
        self._tts: dict[str, TTSAdapter] = {}
        self._catalog: dict[str, Any] = {}
        self._build()

    def _build(self) -> None:
        s = self._settings
        from server.services.dev_secrets_store import dev_secrets_store

        enable_sarvam = bool(dev_secrets_store.effective("enable_sarvam", s.enable_sarvam))
        enable_openai = bool(dev_secrets_store.effective("enable_openai", s.enable_openai))
        enable_deepseek = bool(dev_secrets_store.effective("enable_deepseek", s.enable_deepseek))
        enable_gemini = bool(dev_secrets_store.effective("enable_gemini", s.enable_gemini))
        enable_cartesia = bool(dev_secrets_store.effective("enable_cartesia", s.enable_cartesia))

        sarvam_key = dev_secrets_store.effective_secret("sarvam_api_key") or s.sarvam_api_key
        openai_key = dev_secrets_store.effective_secret("openai_api_key") or s.openai_api_key
        deepseek_key = dev_secrets_store.effective_secret("deepseek_api_key") or s.deepseek_api_key
        cartesia_key = dev_secrets_store.effective_secret("cartesia_api_key") or s.cartesia_api_key
        gemini_key = dev_secrets_store.effective_secret("gemini_api_key") or s.gemini_api_key

        providers: list[dict[str, Any]] = []

        if enable_sarvam:
            self._stt["sarvam"] = SarvamSTTAdapter()
            self._tts["sarvam"] = SarvamTTSAdapter()
            entry = self._sarvam_provider_entry(s)
            entry["enabled"] = enable_sarvam
            entry["configured"] = bool(sarvam_key)
            providers.append(entry)

        if enable_openai:
            self._llm["openai"] = OpenAILLMAdapter()
            entry = self._openai_provider_entry(s)
            entry["enabled"] = enable_openai
            entry["configured"] = bool(openai_key)
            providers.append(entry)

        if enable_deepseek:
            if deepseek_key:
                from server.providers.deepseek_llm import DeepSeekLLMAdapter

                self._llm["deepseek"] = DeepSeekLLMAdapter()
            entry = self._deepseek_provider_entry(s)
            entry["enabled"] = enable_deepseek
            entry["configured"] = bool(deepseek_key)
            entry["adapter_available"] = bool(deepseek_key)
            providers.append(entry)

        if enable_gemini:
            adapter_ok = bool(gemini_key)
            if adapter_ok:
                from server.providers.gemini_llm import GeminiLLMAdapter

                self._llm["gemini"] = GeminiLLMAdapter()
            entry = self._gemini_provider_entry(s, adapter_ok)
            entry["enabled"] = enable_gemini
            entry["configured"] = adapter_ok
            providers.append(entry)

        if enable_cartesia or cartesia_key:
            if enable_cartesia and cartesia_key:
                from server.providers.cartesia_stt import CartesiaSTTAdapter
                from server.providers.cartesia_tts import CartesiaTTSAdapter

                self._stt["cartesia"] = CartesiaSTTAdapter()
                self._tts["cartesia"] = CartesiaTTSAdapter()
            providers.append(self._cartesia_provider_entry(s, bool(cartesia_key), enable_cartesia))

        config_mode = dev_secrets_store.effective("voice_agent_config_mode", s.voice_agent_config_mode)
        active_tier = dev_secrets_store.effective("voice_agent_tier", s.voice_agent_tier)

        self._catalog = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fx_rate_inr": s.fx_rate_inr,
            "config_mode": config_mode,
            "active_tier": active_tier,
            "tiers": list(constants.TIER_NAMES),
            "providers": providers,
            "pricing_metadata": build_pricing_metadata(s.fx_rate_inr),
        }

    def _sarvam_provider_entry(self, s: Settings) -> dict[str, Any]:
        stt_models = [
            {
                "id": m,
                "label": meta["label"],
                "realtime": bool(meta.get("realtime")) or m.endswith("-realtime"),
                "modes": meta.get("modes", []),
                "pricing_key": f"sarvam:{m}",
            }
            for m, meta in constants.STT_MODELS.items()
        ]
        return {
            "id": "sarvam",
            "label": "Sarvam AI",
            "stages": ["stt", "tts"],
            "enabled": True,
            "configured": bool(s.sarvam_api_key),
            "healthy": True,
            "languages": list(constants.SUPPORTED_LANGUAGES.keys()),
            "models": {
                "stt": stt_models,
                "tts": [
                    {"id": m, "label": meta["label"], "pricing_key": f"sarvam:{m}"}
                    for m, meta in constants.TTS_MODELS.items()
                ],
            },
            "capabilities": {"streaming": True, "realtime_stt": True, "realtime_tts": True},
        }

    def _deepseek_provider_entry(self, s: Settings) -> dict[str, Any]:
        models = llm_models_for_provider("deepseek", s)
        return {
            "id": "deepseek",
            "label": "DeepSeek",
            "stages": ["llm"],
            "enabled": s.enable_deepseek,
            "configured": bool(s.deepseek_api_key),
            "healthy": bool(s.deepseek_api_key),
            "adapter_available": bool(s.deepseek_api_key),
            "languages": ["multilingual"],
            "models": {"llm": models},
            "capabilities": {"streaming": True, "structured_output": True},
            "notes": "OpenAI-compatible API — https://api-docs.deepseek.com",
        }

    def _gemini_provider_entry(self, s: Settings, adapter_ok: bool) -> dict[str, Any]:
        models = llm_models_for_provider("gemini", s)
        return {
            "id": "gemini",
            "label": "Google Gemini",
            "stages": ["llm"],
            "enabled": s.enable_gemini,
            "configured": adapter_ok,
            "healthy": adapter_ok,
            "adapter_available": adapter_ok,
            "languages": ["multilingual"],
            "models": {"llm": models},
            "capabilities": {
                "streaming": True,
                "structured_output": True,
                "prompt_caching": True,
            },
            "notes": (
                "Live turns use the same structured JSON, working-memory ops, and "
                "compiled-brain prefix as OpenAI. Gemini 2.5+/3.x implicit-cache the "
                "system instruction when it stays stable across turns."
            ),
        }

    def _openai_provider_entry(self, s: Settings) -> dict[str, Any]:
        models = llm_models_for_provider("openai", s)
        return {
            "id": "openai",
            "label": "OpenAI",
            "stages": ["llm"],
            "enabled": True,
            "configured": bool(s.openai_api_key),
            "healthy": True,
            "languages": ["multilingual"],
            "models": {"llm": models},
            "capabilities": {"streaming": True, "structured_output": True, "prompt_caching": True},
        }

    def _cartesia_provider_entry(self, s: Settings, adapter_ok: bool, enabled: bool) -> dict[str, Any]:
        stt_models = [
            {
                "id": m,
                "label": meta["label"],
                "realtime": bool(meta.get("realtime")),
                "modes": meta.get("modes", []),
                "pricing_key": f"cartesia:{m}",
            }
            for m, meta in constants.CARTESIA_STT_MODELS.items()
        ]
        return {
            "id": "cartesia",
            "label": "Cartesia",
            "stages": ["stt", "tts"],
            "enabled": enabled,
            "configured": adapter_ok,
            "healthy": enabled and adapter_ok,
            "adapter_available": enabled and adapter_ok,
            "languages": ["en", "te", "hi", "multilingual"],
            "models": {
                "stt": stt_models,
                "tts": [
                    {"id": m, "label": meta["label"], "pricing_key": f"cartesia:{m}"}
                    for m, meta in constants.CARTESIA_TTS_MODELS.items()
                ],
            },
            "capabilities": {"streaming": True, "realtime_stt": True, "experimental": True},
            "notes": "Cartesia provides STT and TTS only — no LLM. Enable in Environment after saving API key.",
        }

    @staticmethod
    def _stub_provider_entry(
        provider_id: str,
        stages: list[str],
        *,
        enabled: bool,
        configured: bool,
        adapter_available: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": provider_id,
            "label": provider_id.title(),
            "stages": stages,
            "enabled": enabled,
            "configured": configured,
            "healthy": False,
            "adapter_available": adapter_available,
            "languages": [],
            "models": {},
            "capabilities": {},
        }

    def get_catalog(self) -> dict[str, Any]:
        return self._catalog

    def is_provider_enabled(self, provider_id: str, stage: str) -> bool:
        if stage == "stt":
            return provider_id in self._stt
        if stage == "llm":
            return provider_id in self._llm
        if stage == "tts":
            return provider_id in self._tts
        return False

    def is_model_allowed(self, provider_id: str, stage: str, model: str) -> bool:
        for p in self._catalog.get("providers", []):
            if p["id"] != provider_id:
                continue
            models = p.get("models", {}).get(stage, [])
            ids = {m["id"] for m in models}
            if model in ids:
                return True
        return False

    def get_stt(self, provider_id: str) -> STTAdapter:
        if provider_id not in self._stt:
            raise KeyError(f"STT provider not available: {provider_id}")
        return self._stt[provider_id]

    def get_llm(self, provider_id: str) -> LLMAdapter:
        if provider_id not in self._llm:
            raise KeyError(f"LLM provider not available: {provider_id}")
        return self._llm[provider_id]

    def get_tts(self, provider_id: str) -> TTSAdapter:
        if provider_id not in self._tts:
            raise KeyError(f"TTS provider not available: {provider_id}")
        return self._tts[provider_id]


def init_provider_registry(settings: Settings | None = None) -> ProviderRegistry:
    global _REGISTRY
    _REGISTRY = ProviderRegistry(settings or get_settings())
    return _REGISTRY


def get_provider_registry() -> ProviderRegistry:
    if _REGISTRY is None:
        return init_provider_registry()
    return _REGISTRY
