"""Dev-only overlay for API keys and platform toggles — persisted under data/dev_secrets.json."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings

_SECRET_FIELDS = frozenset(
    {
        "openai_api_key",
        "sarvam_api_key",
        "deepseek_api_key",
        "cartesia_api_key",
        "gemini_api_key",
        "plivo_auth_id",
        "plivo_auth_token",
    }
)

_TOGGLE_FIELDS = frozenset(
    {
        "enable_sarvam",
        "enable_openai",
        "enable_deepseek",
        "enable_gemini",
        "enable_cartesia",
        "enable_plivo",
        "voice_agent_config_mode",
        "voice_agent_tier",
        "app_environment",
    }
)

ALLOWED_PATCH_KEYS = _SECRET_FIELDS | _TOGGLE_FIELDS


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}…{value[-4:]}"


class DevSecretsStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._overlay: dict[str, Any] = {}
        self._load()

    def _path(self) -> Path:
        return get_settings().data_path / "dev_secrets.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            self._overlay = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._overlay = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            self._overlay = {}

    def reload(self) -> None:
        with self._lock:
            self._load()

    def get_overlay(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._overlay)

    def effective(self, field: str, default: Any = None) -> Any:
        settings = get_settings()
        with self._lock:
            if field in self._overlay and self._overlay[field] is not None:
                val = self._overlay[field]
                if field in _SECRET_FIELDS and val == "":
                    pass
                else:
                    return val
        return getattr(settings, field, default)

    def effective_secret(self, field: str) -> str | None:
        val = self.effective(field)
        if val is None:
            return None
        text = str(val).strip()
        return text or None

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in patch.items():
            if key not in ALLOWED_PATCH_KEYS:
                continue
            if key in _SECRET_FIELDS:
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                clean[key] = str(value).strip()
            elif key in _TOGGLE_FIELDS:
                clean[key] = value

        with self._lock:
            self._overlay.update(clean)
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._overlay, indent=2), encoding="utf-8")

        from server.providers import init_provider_registry

        get_settings.cache_clear()
        init_provider_registry()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        settings = get_settings()
        overlay = self.get_overlay()
        groups = {
            "platform": [
                self._platform_row("APP_ENVIRONMENT", "app_environment", settings, overlay),
                self._platform_row("VOICE_AGENT_CONFIG_MODE", "voice_agent_config_mode", settings, overlay),
                self._platform_row("VOICE_AGENT_TIER", "voice_agent_tier", settings, overlay),
                {
                    "env_name": "USE_PROVIDER_REGISTRY",
                    "field": "use_provider_registry",
                    "value": settings.use_provider_registry,
                    "source": "env",
                    "type": "toggle",
                },
            ],
            "provider_keys": [
                self._secret_row("OPENAI_API_KEY", "openai_api_key", settings, overlay),
                self._secret_row("SARVAM_API_KEY", "sarvam_api_key", settings, overlay),
                self._secret_row("DEEPSEEK_API_KEY", "deepseek_api_key", settings, overlay),
                self._secret_row("CARTESIA_API_KEY", "cartesia_api_key", settings, overlay),
                self._secret_row("GEMINI_API_KEY", "gemini_api_key", settings, overlay),
            ],
            "provider_toggles": [
                self._toggle_row("ENABLE_SARVAM", "enable_sarvam", settings, overlay),
                self._toggle_row("ENABLE_OPENAI", "enable_openai", settings, overlay),
                self._toggle_row("ENABLE_DEEPSEEK", "enable_deepseek", settings, overlay),
                self._toggle_row("ENABLE_CARTESIA", "enable_cartesia", settings, overlay),
                self._toggle_row("ENABLE_GEMINI", "enable_gemini", settings, overlay),
            ],
            "telephony": [
                self._toggle_row("ENABLE_PLIVO", "enable_plivo", settings, overlay),
                self._secret_row("PLIVO_AUTH_ID", "plivo_auth_id", settings, overlay),
                self._secret_row("PLIVO_AUTH_TOKEN", "plivo_auth_token", settings, overlay),
            ],
        }
        return {"groups": groups, "overlay_keys": list(overlay.keys())}

    @staticmethod
    def _platform_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        source = "overlay" if field in overlay else "env"
        val = overlay.get(field) if field in overlay else getattr(settings, field)
        return {"env_name": env_name, "field": field, "value": val, "source": source, "type": "string"}

    @staticmethod
    def _secret_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        source = "overlay" if field in overlay else "env"
        effective = overlay.get(field) if field in overlay else getattr(settings, field, None)
        effective = str(effective or "").strip()
        return {
            "env_name": env_name,
            "field": field,
            "configured": bool(effective),
            "masked": _mask_secret(effective) if effective else "",
            "source": source,
            "type": "secret",
        }

    @staticmethod
    def _toggle_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        source = "overlay" if field in overlay else "env"
        val = overlay.get(field) if field in overlay else getattr(settings, field)
        return {"env_name": env_name, "field": field, "value": bool(val), "source": source, "type": "toggle"}


dev_secrets_store = DevSecretsStore()
