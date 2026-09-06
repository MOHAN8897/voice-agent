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
        "exotel_api_key",
        "exotel_api_token",
        "telnyx_api_key",
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
        "enable_exotel",
        "enable_telnyx",
        "enable_plivo",
        "enable_benchmarks",
    }
)

_STRING_FIELDS = frozenset(
    {
        "voice_agent_config_mode",
        "voice_agent_tier",
        "app_environment",
        "telephony_provider",
        "exotel_account_sid",
        "exotel_subdomain",
        "exotel_exophone",
        "exotel_webhook_base_url",
        "telnyx_connection_id",
        "telnyx_phone_number",
        "telnyx_outbound_voice_profile_id",
        "plivo_phone_number",
    }
)

ALLOWED_PATCH_KEYS = _SECRET_FIELDS | _TOGGLE_FIELDS | _STRING_FIELDS


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
        self._mtime: float = 0.0
        self._load()

    def _path(self) -> Path:
        return get_settings().data_path / "dev_secrets.json"

    def _maybe_reload(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime != self._mtime:
            self._load()

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            self._overlay = {}
            self._mtime = 0.0
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            self._overlay = raw if isinstance(raw, dict) else {}
            self._mtime = path.stat().st_mtime
        except (json.JSONDecodeError, OSError):
            self._overlay = {}
            self._mtime = 0.0
        self._sync_provider_toggles_from_keys()

    def _sync_provider_toggles_from_keys(self) -> None:
        """Auto-enable provider toggles when a dev overlay API key is present."""
        pairs = [
            ("cartesia_api_key", "enable_cartesia"),
            ("deepseek_api_key", "enable_deepseek"),
            ("gemini_api_key", "enable_gemini"),
            ("telnyx_api_key", "enable_telnyx"),
            ("exotel_api_key", "enable_exotel"),
            ("plivo_auth_id", "enable_plivo"),
        ]
        changed = False
        for secret_key, toggle_key in pairs:
            secret = self._overlay.get(secret_key)
            if secret and str(secret).strip() and toggle_key not in self._overlay:
                self._overlay[toggle_key] = True
                changed = True
        if changed:
            try:
                path = self._path()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(self._overlay, indent=2), encoding="utf-8")
            except OSError:
                pass

    def reload(self) -> None:
        with self._lock:
            self._load()

    def get_overlay(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._overlay)

    def effective(self, field: str, default: Any = None) -> Any:
        settings = get_settings()
        with self._lock:
            self._maybe_reload()
            if field in self._overlay:
                val = self._overlay[field]
                if val is None:
                    return getattr(settings, field, default)
                if field in (_SECRET_FIELDS | _STRING_FIELDS) and val == "":
                    return ""
                return val
        return getattr(settings, field, default)

    def effective_secret(self, field: str) -> str | None:
        val = self.effective(field)
        if val is None:
            return None
        text = str(val).strip()
        return text or None

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        applied: list[str] = []
        rejected: list[dict[str, str]] = []
        clean: dict[str, Any] = {}

        for key, value in patch.items():
            if key not in ALLOWED_PATCH_KEYS:
                rejected.append({"field": key, "reason": "not_allowed"})
                continue
            if key in _SECRET_FIELDS:
                if value is None:
                    rejected.append({"field": key, "reason": "null_secret"})
                    continue
                if isinstance(value, str) and not value.strip():
                    clean[key] = ""
                    continue
                clean[key] = str(value).strip()
                if key == "cartesia_api_key" and "enable_cartesia" not in patch:
                    clean["enable_cartesia"] = True
                elif key == "deepseek_api_key" and "enable_deepseek" not in patch:
                    clean["enable_deepseek"] = True
                elif key == "gemini_api_key" and "enable_gemini" not in patch:
                    clean["enable_gemini"] = True
                elif key == "telnyx_api_key" and "enable_telnyx" not in patch:
                    clean["enable_telnyx"] = True
                elif key == "exotel_api_key" and "enable_exotel" not in patch:
                    clean["enable_exotel"] = True
                elif key == "plivo_auth_id" and "enable_plivo" not in patch:
                    clean["enable_plivo"] = True
            elif key in _TOGGLE_FIELDS:
                clean[key] = bool(value)
            elif key in _STRING_FIELDS:
                if value is None:
                    rejected.append({"field": key, "reason": "null_value"})
                    continue
                if isinstance(value, str) and not value.strip():
                    clean[key] = ""
                    continue
                clean[key] = str(value).strip()

        with self._lock:
            self._overlay.update(clean)
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._overlay, indent=2), encoding="utf-8")
            applied = list(clean.keys())

        from server.services.dev_runtime import notify_dev_overlay_changed

        notify_dev_overlay_changed()
        snapshot = self.snapshot()
        snapshot["applied_keys"] = applied
        snapshot["rejected"] = rejected
        return snapshot

    def remove_overlay_key(self, field: str) -> dict[str, Any]:
        if field not in ALLOWED_PATCH_KEYS:
            return {"ok": False, "error": "not_allowed", "environment": self.snapshot()}
        with self._lock:
            removed = field in self._overlay
            if removed:
                del self._overlay[field]
                path = self._path()
                path.write_text(json.dumps(self._overlay, indent=2), encoding="utf-8")

        from server.services.dev_runtime import notify_dev_overlay_changed

        notify_dev_overlay_changed()
        snap = self.snapshot()
        snap["removed"] = field if removed else None
        return snap

    def snapshot(self) -> dict[str, Any]:
        settings = get_settings()
        overlay = self.get_overlay()
        groups = {
            "platform": [
                self._platform_row("APP_ENVIRONMENT", "app_environment", settings, overlay),
                self._platform_row("VOICE_AGENT_CONFIG_MODE", "voice_agent_config_mode", settings, overlay),
                self._platform_row("VOICE_AGENT_TIER", "voice_agent_tier", settings, overlay),
                self._toggle_row("ENABLE_BENCHMARKS", "enable_benchmarks", settings, overlay),
                {
                    "env_name": "USE_PROVIDER_REGISTRY",
                    "field": "use_provider_registry",
                    "value": settings.use_provider_registry,
                    "source": "env",
                    "type": "toggle",
                    "editable": False,
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
                self._string_row("TELEPHONY_PROVIDER", "telephony_provider", settings, overlay),
                self._toggle_row("ENABLE_EXOTEL", "enable_exotel", settings, overlay),
                self._secret_row("EXOTEL_API_KEY", "exotel_api_key", settings, overlay),
                self._secret_row("EXOTEL_API_TOKEN", "exotel_api_token", settings, overlay),
                self._string_row("EXOTEL_ACCOUNT_SID", "exotel_account_sid", settings, overlay),
                self._string_row("EXOTEL_SUBDOMAIN", "exotel_subdomain", settings, overlay),
                self._string_row("EXOTEL_EXOPHONE", "exotel_exophone", settings, overlay),
                self._string_row("EXOTEL_WEBHOOK_BASE_URL", "exotel_webhook_base_url", settings, overlay),
                self._toggle_row("ENABLE_TELNYX", "enable_telnyx", settings, overlay),
                self._secret_row("TELNYX_API_KEY", "telnyx_api_key", settings, overlay),
                self._string_row("TELNYX_CONNECTION_ID", "telnyx_connection_id", settings, overlay),
                self._string_row("TELNYX_PHONE_NUMBER", "telnyx_phone_number", settings, overlay),
                self._string_row("TELNYX_OUTBOUND_VOICE_PROFILE_ID", "telnyx_outbound_voice_profile_id", settings, overlay),
                self._toggle_row("ENABLE_PLIVO", "enable_plivo", settings, overlay),
                self._secret_row("PLIVO_AUTH_ID", "plivo_auth_id", settings, overlay),
                self._secret_row("PLIVO_AUTH_TOKEN", "plivo_auth_token", settings, overlay),
                self._string_row("PLIVO_PHONE_NUMBER", "plivo_phone_number", settings, overlay),
            ],
        }
        return {
            "groups": groups,
            "overlay_keys": list(overlay.keys()),
            "allowed_patch_keys": sorted(ALLOWED_PATCH_KEYS),
        }

    @staticmethod
    def _platform_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        source = "overlay" if field in overlay else "env"
        val = overlay.get(field) if field in overlay else getattr(settings, field)
        return {
            "env_name": env_name,
            "field": field,
            "value": val,
            "source": source,
            "type": "string",
            "editable": True,
        }

    @staticmethod
    def _string_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        if field in overlay:
            source = "overlay"
            raw = overlay[field]
            text = "" if raw == "" else str(raw or "").strip()
        else:
            source = "env"
            text = str(getattr(settings, field, None) or "").strip()
        return {
            "env_name": env_name,
            "field": field,
            "value": text,
            "configured": bool(text),
            "source": source,
            "type": "string",
            "editable": True,
            "cleared": field in overlay and overlay.get(field) == "",
        }

    @staticmethod
    def _secret_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        if field in overlay:
            source = "overlay"
            raw = overlay[field]
            if raw == "":
                effective = ""
            else:
                effective = str(raw or "").strip()
        else:
            source = "env"
            effective = str(getattr(settings, field, None) or "").strip()
        return {
            "env_name": env_name,
            "field": field,
            "configured": bool(effective),
            "masked": _mask_secret(effective) if effective else "",
            "source": source,
            "type": "secret",
            "editable": True,
            "cleared": field in overlay and overlay.get(field) == "",
        }

    @staticmethod
    def _toggle_row(env_name: str, field: str, settings: Any, overlay: dict[str, Any]) -> dict[str, Any]:
        source = "overlay" if field in overlay else "env"
        val = overlay.get(field) if field in overlay else getattr(settings, field)
        return {
            "env_name": env_name,
            "field": field,
            "value": bool(val),
            "source": source,
            "type": "toggle",
            "editable": True,
        }


dev_secrets_store = DevSecretsStore()
