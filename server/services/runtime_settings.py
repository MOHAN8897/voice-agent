"""
Runtime settings — server/services/runtime_settings.py
Per-session fine-tuning overrides (STT/TTS/OpenAI), validated against catalogs.
Industry standard: allowlist models, clamp ranges, TTL, thread-safe.
Keys stay in .env — never settable from client.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from server.config.constants import constants
from server.prompts.voice_defaults import (
    DEFAULT_VOICE_PRESET_ID,
    VOICE_PIPELINE_PRESET_IDS,
    voice_preset_values,
)
from server.services.session_persist import session_persist

_TTL_SECONDS = 24 * 60 * 60


class SettingsValidationError(Exception):
    pass


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# Keys bundled into voicePresetId — cannot be changed individually (industry: tune as one unit).
VOICE_PRESET_BUNDLED_KEYS = frozenset({
    "ttsPace", "ttsTemperature", "sttSilenceMs", "sttThreshold", "sttStreamType",
    "bargeMinWords", "bargeRequireVad", "ttsMinBuffer", "ttsMaxChunk",
})


class RuntimeSettingsStore:
    """sessionId -> overrides dict. Only non-None keys override env defaults."""

    ALLOWED_KEYS = {
        # Voice pipeline preset (bundles STT/VAD/barge/TTS tuning)
        "voicePresetId",
        # STT
        "sttModel", "sttMode", "sttLanguage", "sttStreamType",
        "sttSilenceMs", "sttThreshold", "bargeMinWords", "bargeRequireVad",
        # TTS
        "ttsModel", "ttsSpeaker", "ttsPace", "ttsTemperature",
        "ttsCodec", "ttsBitrate", "ttsSampleRate", "ttsMinBuffer", "ttsMaxChunk",
        # OpenAI brain
        "openaiModel", "openaiTemperature", "openaiReasoningEffort", "openaiMaxTokens", "brainPromptBudgetTokens",
        # CRM / integrations (future-ready)
        "crmEnabled", "crmProvider", "crmWebhook", "crmFields", "crmNotes", "crmAutoSync",
    }

    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._hydrate_from_disk()

    def _hydrate_from_disk(self) -> None:
        with self._lock:
            for sid, entry in session_persist.all_runtime().items():
                values = entry.get("values")
                if isinstance(values, dict):
                    self._store[sid] = {
                        "values": dict(values),
                        "updatedAt": float(entry.get("updatedAt") or 0) or time.time(),
                    }

    def _persist(self, session_id: str) -> None:
        entry = self._store.get(session_id)
        if entry:
            session_persist.set_runtime(session_id, entry)

    def _evict_locked(self) -> None:
        now = time.time()
        stale = [k for k, v in self._store.items() if now - v["updatedAt"] > _TTL_SECONDS]
        for k in stale:
            del self._store[k]

    def update(self, session_id: str, patch: dict) -> dict:
        with self._lock:
            self._evict_locked()
            entry = self._store.setdefault(session_id, {"values": {}, "updatedAt": time.time()})
            values: dict = entry["values"]
            snapshot = dict(values)
            loose = VOICE_PRESET_BUNDLED_KEYS & patch.keys()
            if loose and "voicePresetId" not in patch:
                raise SettingsValidationError(
                    f"Change voicePresetId instead of individual pipeline settings: {sorted(loose)}"
                )
            if patch.get("voicePresetId") is not None:
                pid = self._validate("voicePresetId", patch["voicePresetId"])
                bundled = voice_preset_values(pid)
                patch = {k: v for k, v in patch.items() if k not in VOICE_PRESET_BUNDLED_KEYS}
                patch = {**patch, "voicePresetId": pid, **bundled}
            try:
                for key, val in patch.items():
                    if key not in self.ALLOWED_KEYS:
                        raise SettingsValidationError(f"Unknown setting: {key}")
                    if val is None:
                        values.pop(key, None)
                        continue
                    values[key] = self._validate(key, val)
                    self._cross_validate(values)
            except Exception:
                entry["values"] = snapshot
                raise
            entry["updatedAt"] = time.time()
            self._persist(session_id)
            return dict(values)

    def _validate(self, key: str, val):
        if key == "voicePresetId":
            if val not in VOICE_PIPELINE_PRESET_IDS:
                raise SettingsValidationError(f"voicePresetId must be one of {VOICE_PIPELINE_PRESET_IDS}")
            return val
        if key == "sttModel":
            allowed = list(constants.STT_MODELS) + list(constants.CARTESIA_STT_MODELS)
            if val not in allowed:
                raise SettingsValidationError(f"sttModel must be one of {allowed}")
            return val
        if key == "sttMode":
            model = None  # resolved at use-time; mode must be in global list
            if val not in constants.STT_MODES:
                raise SettingsValidationError(f"sttMode must be one of {constants.STT_MODES}")
            return val
        if key == "sttLanguage":
            if val not in list(constants.SUPPORTED_LANGUAGES) + ["unknown"]:
                raise SettingsValidationError("sttLanguage must be te-IN/hi-IN/en-IN/unknown")
            return val
        if key == "sttStreamType":
            if val not in constants.STT_STREAM_TYPES:
                raise SettingsValidationError(f"sttStreamType must be one of {constants.STT_STREAM_TYPES}")
            return val
        if key == "sttSilenceMs":
            try:
                v = int(val)
            except Exception:
                raise SettingsValidationError("sttSilenceMs must be int")
            if not 100 <= v <= 2000:
                raise SettingsValidationError("sttSilenceMs range 100-2000")
            return v
        if key == "sttThreshold":
            return _clamp(float(val), 0.0, 1.0)
        if key == "bargeMinWords":
            try:
                v = int(val)
            except Exception:
                raise SettingsValidationError("bargeMinWords must be int")
            if not 2 <= v <= 4:
                raise SettingsValidationError("bargeMinWords range 2-4")
            return v
        if key == "bargeRequireVad":
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("1", "true", "yes", "on")
        if key == "ttsModel":
            allowed = list(constants.TTS_MODELS) + list(constants.CARTESIA_TTS_MODELS)
            if val not in allowed:
                raise SettingsValidationError(f"ttsModel must be one of {allowed}")
            return val
        if key == "ttsSpeaker":
            v = str(val).strip()
            from server.services.cartesia_voices import is_cartesia_voice_id

            if is_cartesia_voice_id(v):
                return v
            v_lower = v.lower()
            if v_lower in constants.TTS_SPEAKERS_V3 or v_lower in constants.TTS_SPEAKERS_V2:
                return v_lower
            raise SettingsValidationError("Unknown speaker — use Sarvam speaker id or Cartesia voice UUID")
        if key == "ttsPace":
            return _clamp(float(val), 0.3, 3.0)  # per-model clamped at use
        if key == "ttsTemperature":
            return _clamp(float(val), 0.01, 1.0)  # bulbul:v3 only
        if key == "ttsCodec":
            if val not in constants.TTS_CODECS:
                raise SettingsValidationError(f"ttsCodec must be one of {constants.TTS_CODECS}")
            return val
        if key == "ttsBitrate":
            if val not in constants.TTS_BITRATES:
                raise SettingsValidationError(f"ttsBitrate must be one of {constants.TTS_BITRATES}")
            return val
        if key == "ttsSampleRate":
            v = int(val)
            if v not in constants.TTS_SAMPLE_RATES:
                raise SettingsValidationError(f"ttsSampleRate must be one of {constants.TTS_SAMPLE_RATES}")
            return v
        if key == "ttsMinBuffer":
            return max(10, min(500, int(val)))
        if key == "ttsMaxChunk":
            return max(50, min(500, int(val)))
        if key == "openaiModel":
            from server.config.env import get_settings
            allowed = get_settings().allowed_openai_models
            if val not in allowed:
                raise SettingsValidationError(f"openaiModel must be one of {allowed}")
            return val
        if key == "openaiTemperature":
            return _clamp(float(val), 0.0, 2.0)
        if key == "openaiReasoningEffort":
            from server.prompts.voice_defaults import OPENAI_REASONING_EFFORTS
            v = str(val).strip().lower()
            if v not in OPENAI_REASONING_EFFORTS:
                raise SettingsValidationError(f"openaiReasoningEffort must be one of {OPENAI_REASONING_EFFORTS}")
            return v
        if key == "openaiMaxTokens":
            v = int(val)
            if not 50 <= v <= 800:
                raise SettingsValidationError("openaiMaxTokens range 50-800")
            return v
        if key == "brainPromptBudgetTokens":
            from server.config.env import get_settings
            s = get_settings()
            v = int(val)
            lo = int(s.brain_prompt_budget_min)
            hi = int(s.brain_prompt_budget_max)
            if not lo <= v <= hi:
                raise SettingsValidationError(f"brainPromptBudgetTokens range {lo}-{hi}")
            return v
        if key == "crmEnabled":
            return bool(val) if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
        if key == "crmProvider":
            allowed = {"", "hubspot", "zoho", "salesforce", "custom", "pipedrive", "freshsales"}
            v = str(val).lower()
            if v not in allowed:
                raise SettingsValidationError(f"crmProvider must be one of {sorted(allowed - {''})} or empty")
            return v
        if key == "crmWebhook":
            v = str(val).strip()
            if v and not (v.startswith("http://") or v.startswith("https://")):
                raise SettingsValidationError("crmWebhook must be http(s) URL")
            return v
        if key == "crmFields":
            return str(val).strip()[:500]
        if key == "crmNotes":
            return str(val).strip()[:2000]
        if key == "crmAutoSync":
            return bool(val) if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
        raise SettingsValidationError(f"Unhandled key {key}")

    def _cross_validate(self, values: dict) -> None:
        model = values.get("ttsModel")
        spk = values.get("ttsSpeaker")
        if model and spk:
            sarvam_ok = spk in constants.TTS_SPEAKERS_V3 if model == "bulbul:v3" else spk in constants.TTS_SPEAKERS_V2
            cartesia_ok = model in constants.CARTESIA_TTS_MODELS
            if model in constants.TTS_MODELS and not sarvam_ok:
                raise SettingsValidationError(f"Speaker '{spk}' incompatible with {model}")
            if cartesia_ok:
                from server.services.cartesia_voices import is_cartesia_voice_id

                if not is_cartesia_voice_id(spk):
                    raise SettingsValidationError(f"Cartesia voice id required for {model}")
        pace = values.get("ttsPace")
        if model == "bulbul:v3" and pace is not None:
            values["ttsPace"] = _clamp(pace, 0.5, 2.0)

    def get(self, session_id: str) -> dict:
        with self._lock:
            self._evict_locked()
            entry = self._store.get(session_id)
            return dict(entry["values"]) if entry else {}

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
        session_persist.delete_runtime(session_id)


runtime_settings = RuntimeSettingsStore()
