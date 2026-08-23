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

_TTL_SECONDS = 24 * 60 * 60


class SettingsValidationError(Exception):
    pass


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class RuntimeSettingsStore:
    """sessionId -> overrides dict. Only non-None keys override env defaults."""

    ALLOWED_KEYS = {
        # STT
        "sttModel", "sttMode", "sttLanguage", "sttStreamType",
        "sttSilenceMs", "sttThreshold",
        # TTS
        "ttsModel", "ttsSpeaker", "ttsPace", "ttsTemperature",
        "ttsCodec", "ttsBitrate", "ttsSampleRate", "ttsMinBuffer", "ttsMaxChunk",
        # OpenAI brain
        "openaiModel", "openaiTemperature", "openaiMaxTokens",
    }

    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()

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
            for key, val in patch.items():
                if key not in self.ALLOWED_KEYS:
                    raise SettingsValidationError(f"Unknown setting: {key}")
                if val is None:
                    values.pop(key, None)
                    continue
                values[key] = self._validate(key, val)
                # Cross-field validation
                self._cross_validate(values)
            entry["updatedAt"] = time.time()
            return dict(values)

    def _validate(self, key: str, val):
        if key == "sttModel":
            if val not in constants.STT_MODELS:
                raise SettingsValidationError(f"sttModel must be one of {list(constants.STT_MODELS)}")
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
        if key == "ttsModel":
            if val not in constants.TTS_MODELS:
                raise SettingsValidationError(f"ttsModel must be one of {list(constants.TTS_MODELS)}")
            return val
        if key == "ttsSpeaker":
            v = str(val).lower()  # docs: case-sensitive lowercase
            if v not in constants.TTS_SPEAKERS_V3 and v not in constants.TTS_SPEAKERS_V2:
                raise SettingsValidationError("Unknown speaker")
            return v
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
        if key == "openaiMaxTokens":
            v = int(val)
            if not 50 <= v <= 4000:
                raise SettingsValidationError("openaiMaxTokens range 50-4000")
            return v
        raise SettingsValidationError(f"Unhandled key {key}")

    def _cross_validate(self, values: dict) -> None:
        model = values.get("ttsModel")
        spk = values.get("ttsSpeaker")
        if model and spk:
            ok = spk in constants.TTS_SPEAKERS_V3 if model == "bulbul:v3" else spk in constants.TTS_SPEAKERS_V2
            if not ok:
                raise SettingsValidationError(f"Speaker '{spk}' incompatible with {model}")
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


runtime_settings = RuntimeSettingsStore()
