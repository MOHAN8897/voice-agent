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
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(0.5, alias="OPENAI_TEMPERATURE")
    sarvam_stt_model: str = Field("saaras:v3", alias="SARVAM_STT_MODEL")
    sarvam_tts_model: str = Field("bulbul:v3", alias="SARVAM_TTS_MODEL")
    sarvam_tts_speaker_te: str = Field("shubh", alias="SARVAM_TTS_SPEAKER_TE")
    sarvam_tts_pace: float = Field(1.0, alias="SARVAM_TTS_PACE")

    # --- Cost / context controls ---
    max_response_length: int = Field(600, alias="MAX_RESPONSE_LENGTH")
    max_context_messages: int = Field(12, alias="MAX_CONTEXT_MESSAGES")
    request_timeout_ms: int = Field(15000, alias="REQUEST_TIMEOUT_MS")
    max_retries: int = Field(2, alias="MAX_RETRIES")

    # --- Fine-tune allowlist (industry: restrict client-selectable models) ---
    allowed_openai_models_csv: str = Field(
        "gpt-4o-mini,gpt-4o,gpt-4.1-mini,gpt-4.1,gpt-5-mini,gpt-5",
        alias="OPENAI_ALLOWED_MODELS",
    )

    # --- App ---
    log_level: Literal["debug", "info", "warning", "error"] = Field("info", alias="LOG_LEVEL")
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
