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
    openai_model: str = Field("gpt-realtime-2.1-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(0.625, alias="OPENAI_TEMPERATURE")
    sarvam_stt_model: str = Field("saaras:v3", alias="SARVAM_STT_MODEL")
    sarvam_tts_model: str = Field("bulbul:v3", alias="SARVAM_TTS_MODEL")
    sarvam_tts_speaker_te: str = Field("shubh", alias="SARVAM_TTS_SPEAKER_TE")
    sarvam_tts_pace: float = Field(1.0, alias="SARVAM_TTS_PACE")
    sarvam_tts_temperature: float = Field(0.70, alias="SARVAM_TTS_TEMPERATURE")

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
    log_pstn: bool = Field(True, alias="LOG_PSTN")

    # --- Voice pipeline ---
    voice_http_tts_fallback: bool = Field(False, alias="VOICE_HTTP_TTS_FALLBACK")
    max_response_length: int = Field(320, alias="MAX_RESPONSE_LENGTH")
    max_context_messages: int = Field(4, alias="MAX_CONTEXT_MESSAGES")
    max_history_assistant_chars: int = Field(120, alias="MAX_HISTORY_ASSISTANT_CHARS")
    max_history_user_chars: int = Field(300, alias="MAX_HISTORY_USER_CHARS")
    request_timeout_ms: int = Field(15000, alias="REQUEST_TIMEOUT_MS")
    max_retries: int = Field(2, alias="MAX_RETRIES")

    # --- Brain prompt budget (single composed prompt) ---
    brain_prompt_budget_tokens: int = Field(6000, alias="BRAIN_PROMPT_BUDGET_TOKENS")
    brain_prompt_budget_min: int = Field(1500, alias="BRAIN_PROMPT_BUDGET_MIN")
    brain_prompt_budget_max: int = Field(10000, alias="BRAIN_PROMPT_BUDGET_MAX")

    # --- Prompt caching (GPT-5.6+) ---
    enable_prompt_caching: bool = Field(True, alias="ENABLE_PROMPT_CACHING")
    prompt_cache_ttl: str = Field("30m", alias="PROMPT_CACHE_TTL")
    prompt_cache_key_prefix: str = Field("telugu-voice:v5", alias="PROMPT_CACHE_KEY_PREFIX")
    prompt_cache_min_tokens: int = Field(1024, alias="PROMPT_CACHE_MIN_TOKENS")

    # --- Session memory (legacy Phase 3; superseded by working memory) ---
    enable_session_summary: bool = Field(False, alias="ENABLE_SESSION_SUMMARY")
    summary_every_n_turns: int = Field(4, alias="SUMMARY_EVERY_N_TURNS")
    brain_context_turns: int = Field(2, alias="BRAIN_CONTEXT_TURNS")

    # --- Phase 4: Working memory (A/B/C) + post-call ---
    enable_working_memory: bool = Field(True, alias="ENABLE_WORKING_MEMORY")
    working_memory_max_chars: int = Field(2000, alias="WORKING_MEMORY_MAX_CHARS")
    memory_projection_max_tokens: int = Field(150, alias="MEMORY_PROJECTION_MAX_TOKENS")
    rolling_summary_max_tokens: int = Field(150, alias="ROLLING_SUMMARY_MAX_TOKENS")
    rolling_summary_interval_turns: int = Field(5, alias="ROLLING_SUMMARY_INTERVAL_TURNS")
    memory_extraction_fallback: bool = Field(False, alias="ENABLE_MEMORY_EXTRACTION_FALLBACK")
    memory_extraction_max_output_tokens: int = Field(400, alias="MEMORY_EXTRACTION_MAX_OUTPUT_TOKENS")
    post_call_llm_model: str = Field("gpt-5.6-luna", alias="POST_CALL_LLM_MODEL")
    post_call_max_retries: int = Field(3, alias="POST_CALL_MAX_RETRIES")

    # --- Fine-tune allowlist (industry: restrict client-selectable models) ---
    allowed_openai_models_csv: str = Field(
        "gpt-realtime-2.1-mini,gpt-realtime-2.1,gpt-realtime-2,gpt-5.5,gpt-5.4,gpt-5,gpt-5.6-luna",
        alias="OPENAI_ALLOWED_MODELS",
    )

    # --- App ---
    debug: bool = Field(False, alias="DEBUG")
    port: int = Field(8000, alias="PORT")
    client_url: str = Field("http://localhost:3000", alias="CLIENT_URL")
    public_tunnel_url: str | None = Field(None, alias="PUBLIC_TUNNEL_URL")
    public_app_url: str | None = Field(None, alias="PUBLIC_APP_URL")

    # --- Phase 1: Provider platform ---
    voice_agent_config_mode: Literal["env", "frontend"] = Field("frontend", alias="VOICE_AGENT_CONFIG_MODE")
    voice_agent_tier: Literal["low", "medium", "premium"] = Field("medium", alias="VOICE_AGENT_TIER")
    app_environment: Literal["development", "staging", "production"] = Field("development", alias="APP_ENVIRONMENT")

    enable_sarvam: bool = Field(True, alias="ENABLE_SARVAM")
    enable_openai: bool = Field(True, alias="ENABLE_OPENAI")
    enable_deepseek: bool = Field(False, alias="ENABLE_DEEPSEEK")
    enable_gemini: bool = Field(False, alias="ENABLE_GEMINI")
    enable_cartesia: bool = Field(False, alias="ENABLE_CARTESIA")

    voice_pipeline_mode: Literal["classic", "realtime_text"] = Field(
        "realtime_text", alias="VOICE_PIPELINE_MODE"
    )

    use_provider_registry: bool = Field(True, alias="USE_PROVIDER_REGISTRY")
    use_versioned_brains: bool = Field(False, alias="USE_VERSIONED_BRAINS")
    allow_publish_during_calls: bool = Field(False, alias="ALLOW_PUBLISH_DURING_CALLS")
    enable_benchmarks: bool = Field(False, alias="ENABLE_BENCHMARKS")
    fx_rate_inr: float = Field(95.64, alias="FX_RATE_INR")

    database_url: str | None = Field(None, alias="DATABASE_URL")

    # --- Phase 3: Call lifecycle ---
    call_auto_end_on_start: bool = Field(True, alias="CALL_AUTO_END_ON_START")
    call_retention_days: int = Field(90, alias="CALL_RETENTION_DAYS")
    data_dir: str = Field("data", alias="DATA_DIR")
    enable_call_archive: bool = Field(True, alias="ENABLE_CALL_ARCHIVE")
    call_idle_timeout_sec: int = Field(300, alias="CALL_IDLE_TIMEOUT_SEC")
    call_stale_heartbeat_sec: int = Field(120, alias="CALL_STALE_HEARTBEAT_SEC")

    # --- Phase 5: Production platform ---
    session_secret: str = Field("dev-session-secret-change-in-production", alias="SESSION_SECRET")
    dev_portal_username: str | None = Field(None, alias="DEV_PORTAL_USERNAME")
    dev_portal_password: str | None = Field(None, alias="DEV_PORTAL_PASSWORD")
    app_console_username: str | None = Field(None, alias="APP_CONSOLE_USERNAME")
    app_console_password: str | None = Field(None, alias="APP_CONSOLE_PASSWORD")
    default_tenant_id: str = Field("00000000-0000-4000-8000-000000000001", alias="DEFAULT_TENANT_ID")
    serve_client_static: bool = Field(True, alias="SERVE_CLIENT_STATIC")
    redis_url: str | None = Field(None, alias="REDIS_URL")

    enable_exotel: bool = Field(False, alias="ENABLE_EXOTEL")
    exotel_api_key: str | None = Field(None, alias="EXOTEL_API_KEY")
    exotel_api_token: str | None = Field(None, alias="EXOTEL_API_TOKEN")
    exotel_account_sid: str | None = Field(None, alias="EXOTEL_ACCOUNT_SID")
    exotel_subdomain: str = Field("api.exotel.com", alias="EXOTEL_SUBDOMAIN")
    exotel_exophone: str | None = Field(None, alias="EXOTEL_EXOPHONE")
    exotel_webhook_base_url: str | None = Field(None, alias="EXOTEL_WEBHOOK_BASE_URL")

    telephony_provider: str = Field("exotel", alias="TELEPHONY_PROVIDER")
    enable_telnyx: bool = Field(False, alias="ENABLE_TELNYX")
    telnyx_api_key: str | None = Field(None, alias="TELNYX_API_KEY")
    telnyx_public_key: str | None = Field(None, alias="TELNYX_PUBLIC_KEY")
    telnyx_connection_id: str | None = Field(None, alias="TELNYX_CONNECTION_ID")
    telnyx_phone_number: str | None = Field(None, alias="TELNYX_PHONE_NUMBER")
    telnyx_outbound_voice_profile_id: str | None = Field(None, alias="TELNYX_OUTBOUND_VOICE_PROFILE_ID")
    telnyx_webhook_tolerance_sec: int = Field(300, alias="TELNYX_WEBHOOK_TOLERANCE_SEC")
    telnyx_max_concurrent_calls: int = Field(50, alias="TELNYX_MAX_CONCURRENT_CALLS")
    enable_plivo: bool = Field(False, alias="ENABLE_PLIVO")
    plivo_auth_id: str | None = Field(None, alias="PLIVO_AUTH_ID")
    plivo_auth_token: str | None = Field(None, alias="PLIVO_AUTH_TOKEN")
    plivo_phone_number: str | None = Field(None, alias="PLIVO_PHONE_NUMBER")
    campaign_max_concurrency: int = Field(5, alias="CAMPAIGN_MAX_CONCURRENCY")
    campaign_default_retry_attempts: int = Field(3, alias="CAMPAIGN_DEFAULT_RETRY_ATTEMPTS")
    recording_consent_required: bool = Field(False, alias="RECORDING_CONSENT_REQUIRED")

    # --- Production canary (TEST 9) ---
    canary_enabled: bool = Field(False, alias="CANARY_ENABLED")
    canary_max_calls_per_day: int = Field(20, alias="CANARY_MAX_CALLS_PER_DAY")
    canary_allowed_destinations_csv: str = Field("", alias="CANARY_ALLOWED_DESTINATIONS")
    deepseek_api_key: str | None = Field(None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field("https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field("deepseek-chat", alias="DEEPSEEK_MODEL")
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-3.5-flash-lite", alias="GEMINI_MODEL")
    cartesia_api_key: str | None = Field(None, alias="CARTESIA_API_KEY")
    cartesia_stt_model: str = Field("ink-whisper", alias="CARTESIA_STT_MODEL")
    cartesia_tts_model: str = Field("sonic-3.5", alias="CARTESIA_TTS_MODEL")
    cartesia_tts_voice_id: str | None = Field(None, alias="CARTESIA_TTS_VOICE_ID")
    cartesia_api_version: str = Field("2026-08-14", alias="CARTESIA_API_VERSION")
    # Director-style delivery (not an LLM text prompt) — sonic-3 / sonic-3.5 generation_config.
    cartesia_tts_emotion: str = Field("calm", alias="CARTESIA_TTS_EMOTION")
    cartesia_tts_speed: float = Field(1.0, alias="CARTESIA_TTS_SPEED")
    cartesia_tts_volume: float = Field(1.0, alias="CARTESIA_TTS_VOLUME")

    # LOW tier bundle
    voice_low_stt_provider: str = Field("sarvam", alias="VOICE_LOW_STT_PROVIDER")
    voice_low_stt_model: str = Field("saaras:v3", alias="VOICE_LOW_STT_MODEL")
    voice_low_llm_provider: str = Field("openai", alias="VOICE_LOW_LLM_PROVIDER")
    voice_low_llm_model: str = Field("gpt-realtime-2.1-mini", alias="VOICE_LOW_LLM_MODEL")
    voice_low_tts_provider: str = Field("sarvam", alias="VOICE_LOW_TTS_PROVIDER")
    voice_low_tts_model: str = Field("bulbul:v3", alias="VOICE_LOW_TTS_MODEL")

    # MEDIUM tier bundle
    voice_medium_stt_provider: str = Field("sarvam", alias="VOICE_MEDIUM_STT_PROVIDER")
    voice_medium_stt_model: str = Field("saaras:v3-realtime", alias="VOICE_MEDIUM_STT_MODEL")
    voice_medium_llm_provider: str = Field("openai", alias="VOICE_MEDIUM_LLM_PROVIDER")
    voice_medium_llm_model: str = Field("gpt-realtime-2.1-mini", alias="VOICE_MEDIUM_LLM_MODEL")
    voice_medium_tts_provider: str = Field("sarvam", alias="VOICE_MEDIUM_TTS_PROVIDER")
    voice_medium_tts_model: str = Field("bulbul:v3", alias="VOICE_MEDIUM_TTS_MODEL")

    # PREMIUM tier bundle
    voice_premium_stt_provider: str = Field("sarvam", alias="VOICE_PREMIUM_STT_PROVIDER")
    voice_premium_stt_model: str = Field("saaras:v3-realtime", alias="VOICE_PREMIUM_STT_MODEL")
    voice_premium_llm_provider: str = Field("openai", alias="VOICE_PREMIUM_LLM_PROVIDER")
    voice_premium_llm_model: str = Field("gpt-realtime-2.1-mini", alias="VOICE_PREMIUM_LLM_MODEL")
    voice_premium_tts_provider: str = Field("sarvam", alias="VOICE_PREMIUM_TTS_PROVIDER")
    voice_premium_tts_model: str = Field("bulbul:v3", alias="VOICE_PREMIUM_TTS_MODEL")

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

    @field_validator("cartesia_tts_speed")
    @classmethod
    def _cartesia_speed_range(cls, v: float) -> float:
        if not 0.6 <= v <= 1.5:
            raise ValueError("CARTESIA_TTS_SPEED must be 0.6–1.5")
        return v

    @field_validator("cartesia_tts_volume")
    @classmethod
    def _cartesia_volume_range(cls, v: float) -> float:
        if not 0.5 <= v <= 2.0:
            raise ValueError("CARTESIA_TTS_VOLUME must be 0.5–2.0")
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
        models = [m.strip() for m in self.allowed_openai_models_csv.split(",") if m.strip()]
        from server.realtime.models import DEFAULT_HTTP_LLM_MODEL, DEFAULT_REALTIME_MODEL

        for extra in (DEFAULT_REALTIME_MODEL, self.post_call_llm_model or DEFAULT_HTTP_LLM_MODEL):
            if extra and extra not in models:
                models.append(extra)
        return models

    @property
    def working_memory_enabled(self) -> bool:
        """ENABLE_WORKING_MEMORY is canonical; legacy ENABLE_SESSION_SUMMARY maps only when unset."""
        raw = os.getenv("ENABLE_WORKING_MEMORY")
        if raw is not None:
            return self.enable_working_memory
        if os.getenv("ENABLE_SESSION_SUMMARY", "").strip().lower() in ("true", "1", "yes"):
            return True
        return self.enable_working_memory

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else PROJECT_ROOT / p


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
        "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
        "OPENAI_MODEL": bool(os.getenv("OPENAI_MODEL") or True),
        "SARVAM_STT_MODEL": bool(os.getenv("SARVAM_STT_MODEL") or True),
    }
