"""
Env loader — server/config/env.py
Zod-style validation, fails fast, never logs secrets.
Industry standard: pydantic-settings + dotenv.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root (D:\Telugu Agent\.env)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


class ConfigError(Exception):
    """Typed error for missing/invalid env — maps to 500 with user-safe message."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Required secrets ---
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    sarvam_api_key: str = Field(..., alias="SARVAM_API_KEY")

    # --- Models & voices (configurable, verified against docs at build time) ---
    openai_model: str = Field("gpt-5.6-luna", alias="OPENAI_MODEL")
    openai_temperature: float = Field(0.5, alias="OPENAI_TEMPERATURE")
    sarvam_stt_model: str = Field("saaras:v3", alias="SARVAM_STT_MODEL")
    sarvam_tts_model: str = Field("bulbul:v3", alias="SARVAM_TTS_MODEL")
    sarvam_tts_speaker_te: str = Field("shubh", alias="SARVAM_TTS_SPEAKER_TE")
    sarvam_tts_pace: float = Field(1.08, alias="SARVAM_TTS_PACE")
    sarvam_tts_temperature: float = Field(0.4, alias="SARVAM_TTS_TEMPERATURE")

    # --- Logging (toggle per category; LOG_ENABLED=false silences all) ---
    log_enabled: bool = Field(True, alias="LOG_ENABLED")
    log_level: Literal["debug", "info", "warning", "error", "off"] = Field("info", alias="LOG_LEVEL")
    log_voice: bool = Field(True, alias="LOG_VOICE")
    log_stt: bool = Field(True, alias="LOG_STT")
    log_brain: bool = Field(True, alias="LOG_BRAIN")
    log_tts: bool = Field(True, alias="LOG_TTS")
    log_ws: bool = Field(True, alias="LOG_WS")
    log_perf: bool = Field(True, alias="LOG_PERF")
    log_client: bool = Field(True, alias="LOG_CLIENT")

    # --- Voice pipeline ---
    voice_http_tts_fallback: bool = Field(False, alias="VOICE_HTTP_TTS_FALLBACK")
    max_response_length: int = Field(320, alias="MAX_RESPONSE_LENGTH")
    max_context_messages: int = Field(4, alias="MAX_CONTEXT_MESSAGES")
    max_history_assistant_chars: int = Field(120, alias="MAX_HISTORY_ASSISTANT_CHARS")
    max_history_user_chars: int = Field(300, alias="MAX_HISTORY_USER_CHARS")
    request_timeout_ms: int = Field(15000, alias="REQUEST_TIMEOUT_MS")
    max_retries: int = Field(2, alias="MAX_RETRIES")

    # --- Brain prompt budget (single composed prompt) ---
    brain_prompt_budget_tokens: int = Field(1500, alias="BRAIN_PROMPT_BUDGET_TOKENS")
    brain_prompt_budget_min: int = Field(1500, alias="BRAIN_PROMPT_BUDGET_MIN")
    brain_prompt_budget_max: int = Field(5000, alias="BRAIN_PROMPT_BUDGET_MAX")

    # --- Prompt caching (GPT-5.6+) ---
    enable_prompt_caching: bool = Field(True, alias="ENABLE_PROMPT_CACHING")
    prompt_cache_ttl: str = Field("30m", alias="PROMPT_CACHE_TTL")
    prompt_cache_key_prefix: str = Field("telugu-voice:v5", alias="PROMPT_CACHE_KEY_PREFIX")
    prompt_cache_min_tokens: int = Field(1024, alias="PROMPT_CACHE_MIN_TOKENS")

    # --- Session memory (Phase 3) ---
    enable_session_summary: bool = Field(False, alias="ENABLE_SESSION_SUMMARY")
    summary_every_n_turns: int = Field(4, alias="SUMMARY_EVERY_N_TURNS")
    brain_context_turns: int = Field(2, alias="BRAIN_CONTEXT_TURNS")

    # --- Fine-tune allowlist (industry: restrict client-selectable models) ---
    allowed_openai_models_csv: str = Field(
        "gpt-5.5,gpt-5.4,gpt-5,gpt-5.6-luna",
        alias="OPENAI_ALLOWED_MODELS",
    )

    # --- App ---
    debug: bool = Field(False, alias="DEBUG")
    port: int = Field(8000, alias="PORT")
    client_url: str = Field("http://localhost:8000", alias="CLIENT_URL")

    @field_validator("openai_api_key", "sarvam_api_key")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("is required — set it in .env (see .env.example)")
        return v.strip()

    @field_validator("sarvam_tts_pace")
    @classmethod
    def _pace_range(cls, v: float) -> float:
        if not 0.5 <= v <= 2.0:
            raise ValueError("SARVAM_TTS_PACE must be 0.5–2.0")
        return v

    @field_validator("sarvam_tts_temperature")
    @classmethod
    def _tts_temp_range(cls, v: float) -> float:
        if not 0.01 <= v <= 1.0:
            raise ValueError("SARVAM_TTS_TEMPERATURE must be 0.01–1.0")
        return v

    @field_validator("openai_temperature")
    @classmethod
    def _temp_range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("OPENAI_TEMPERATURE must be 0.0–2.0")
        return v

    @property
    def allowed_openai_models(self) -> list[str]:
        return [m.strip() for m in self.allowed_openai_models_csv.split(",") if m.strip()]


def _safe_error_details(e: Exception) -> str:
    """Redact any secret values from pydantic error details."""
    raw = str(e)
    # Pydantic ValidationError includes input_value dict with actual key values — redact
    import re

    # Redact sk-... tokens
    raw = re.sub(r"sk-[A-Za-z0-9-_]{5,}", "***REDACTED***", raw)
    # Redact 'input_value': {'OPENAI_API_KEY': '...'} patterns — replace values
    raw = re.sub(r"'OPENAI_API_KEY': '[^']*'", "'OPENAI_API_KEY': '***REDACTED***'", raw)
    raw = re.sub(r"'SARVAM_API_KEY': '[^']*'", "'SARVAM_API_KEY': '***REDACTED***'", raw)
    raw = re.sub(r'"OPENAI_API_KEY": "[^"]*"', '"OPENAI_API_KEY": "***REDACTED***"', raw)
    raw = re.sub(r'"SARVAM_API_KEY": "[^"]*"', '"SARVAM_API_KEY": "***REDACTED***"', raw)
    return raw


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Call validate_env() at startup to fail fast."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        safe = _safe_error_details(e)
        raise ConfigError(
            "AI service configuration is invalid. Check .env — see .env.example. "
            f"Details: {safe}"
        ) from e


def validate_env() -> Settings:
    """Explicit fail-fast helper for app startup. Never logs secret values."""
    settings = get_settings()
    # Touch required fields to trigger validation
    _ = settings.openai_api_key
    _ = settings.sarvam_api_key
    return settings


def config_presence() -> dict[str, bool]:
    """For /api/config-check — returns presence booleans, never values."""
    # Bypass cache to reflect current env accurately for health checks
    return {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "SARVAM_API_KEY": bool(os.getenv("SARVAM_API_KEY")),
        "OPENAI_MODEL": bool(os.getenv("OPENAI_MODEL") or True),
        "SARVAM_STT_MODEL": bool(os.getenv("SARVAM_STT_MODEL") or True),
    }
