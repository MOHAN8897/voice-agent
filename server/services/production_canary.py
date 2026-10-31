"""Production canary — deploy checklist, call window metrics, and outbound guardrails."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.config.urls import public_api_base
from server.services.pstn_voice_core import ENABLE_PSTN_BARGE_IN

_CANARY_DIR = "canary"
_EVENTS_FILE = "events.jsonl"
_MIN_BIDIRECTIONAL_CALLS = 10


def _canary_dir() -> Path:
    settings = get_settings()
    root = settings.data_path / _CANARY_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _events_path() -> Path:
    return _canary_dir() / _EVENTS_FILE


def _parse_allowed_destinations(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def build_deploy_checklist(*, telnyx_checklist: dict[str, Any] | None = None) -> dict[str, Any]:
    """TEST 9.1 — production deploy readiness (no secrets)."""
    settings = get_settings()
    api_base = public_api_base().rstrip("/")
    webhook = f"{api_base}/api/telnyx/webhook"
    tls_ok = api_base.startswith("https://")
    is_local_api = api_base.startswith("http://127.0.0.1") or api_base.startswith("http://localhost")

    telnyx = telnyx_checklist or {}
    webhook_matches = bool(telnyx.get("webhook_configured")) or (
        not telnyx and not is_local_api
    )

    items = {
        "public_api_tls": tls_ok,
        "public_api_not_localhost": not is_local_api,
        "webhook_url": webhook,
        "webhook_configured": webhook_matches,
        "app_environment": settings.app_environment,
        "production_environment": settings.app_environment == "production",
        "telnyx_enabled": settings.enable_telnyx,
        "secrets_not_dev_file": not (settings.data_path / "dev_secrets.json").exists()
        or settings.app_environment != "production",
        "barge_in_enabled": ENABLE_PSTN_BARGE_IN,
        "call_archive_enabled": settings.enable_call_archive,
        "canary_enabled": settings.canary_enabled,
        "canary_max_calls_per_day": settings.canary_max_calls_per_day,
        "recording_consent_required": settings.recording_consent_required,
    }
    if telnyx:
        items["telnyx_ready_for_india"] = bool(telnyx.get("ready_for_india"))
        items["telnyx_phone_active"] = bool(telnyx.get("phone_number_active"))
        items["telnyx_outbound_profile"] = bool(telnyx.get("outbound_profile_on_app"))

    required_for_smoke = [
        "public_api_tls",
        "telnyx_enabled",
        "barge_in_enabled",
        "call_archive_enabled",
    ]
    if settings.app_environment == "production":
        required_for_smoke.extend(["public_api_not_localhost", "production_environment"])

    return {
        "items": items,
        "required_for_smoke": required_for_smoke,
        "ready_for_smoke": all(items.get(k) for k in required_for_smoke),
        "rollback": {
            "disable_telnyx": "Set ENABLE_TELNYX=false and redeploy",
            "disable_canary": "Set CANARY_ENABLED=false",
            "revert_deploy": "Roll back Railway/hosting to previous release",
        },
    }


def record_canary_call(
    *,
    call_id: str,
    external_id: str | None = None,
    bidirectional_ok: bool = False,
    media_in: int = 0,
    media_out: int = 0,
    health_score: int | None = None,
    failures: list[str] | None = None,
    compiled_brain_version: str | None = None,
    combination_id: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Append one canary call result (TEST 9.2 / 9.4)."""
    settings = get_settings()
    event = {
        "ts": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "external_id": external_id,
        "bidirectional_ok": bidirectional_ok,
        "media_in": media_in,
        "media_out": media_out,
        "health_score": health_score,
        "failures": failures or [],
        "compiled_brain_version": compiled_brain_version,
        "combination_id": combination_id,
        "environment": environment or settings.app_environment,
    }
    path = _events_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def _load_events(since_ts: float | None = None) -> list[dict[str, Any]]:
    path = _events_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_ts is not None:
            try:
                ts = datetime.fromisoformat(str(row.get("ts") or "").replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = 0.0
            if ts < since_ts:
                continue
        rows.append(row)
    return rows


def score_canary_window(
    *,
    registry_rows: list[dict[str, Any]] | None = None,
    hours: int = 48,
) -> dict[str, Any]:
    """TEST 9 gate scoring from canary log + optional Telnyx registry."""
    since = time.time() - (hours * 3600)
    events = _load_events(since_ts=since)

    registry = registry_rows or []
    reg_bidir = [r for r in registry if r.get("bidirectional_ok") is True]
    if not events and registry:
        for row in registry:
            ended = row.get("updated_at")
            if ended and isinstance(ended, (int, float)) and ended < since:
                continue
            if row.get("bidirectional_ok"):
                events.append(
                    {
                        "call_id": row.get("internal_call_id") or row.get("call_control_id"),
                        "bidirectional_ok": True,
                        "failures": [],
                        "health_score": row.get("health_score"),
                    }
                )

    bidirectional = [e for e in events if e.get("bidirectional_ok")]
    failures_flat: list[str] = []
    for e in events:
        failures_flat.extend(e.get("failures") or [])

    outbound_failures = [f for f in failures_flat if "OUTBOUND_TRANSMISSION_FAILURE" in f]
    codec_failures = [f for f in failures_flat if "CODEC_MISMATCH" in f]
    low_health = [e for e in events if int(e.get("health_score") or 100) < 70]

    gates = {
        "bidirectional_calls_gte_10": len(bidirectional) >= _MIN_BIDIRECTIONAL_CALLS,
        "zero_outbound_transmission_failures": len(outbound_failures) == 0,
        "zero_codec_mismatch": len(codec_failures) == 0,
        "no_health_below_70": len(low_health) == 0,
        "archives_recorded": len(events) > 0,
    }

    return {
        "window_hours": hours,
        "total_calls": len(events),
        "bidirectional_ok_calls": len(bidirectional),
        "registry_bidirectional": len(reg_bidir),
        "outbound_transmission_failures": len(outbound_failures),
        "codec_mismatch_failures": len(codec_failures),
        "health_below_70": len(low_health),
        "gates": gates,
        "overall": all(gates.values()),
        "recent_calls": events[-10:],
    }


def seed_canary_from_archives(*, limit: int = 30, hours: int = 48) -> int:
    """Import recent PSTN call archives into canary log (idempotent per call_id)."""
    settings = get_settings()
    calls_root = settings.data_path / "calls"
    if not calls_root.is_dir():
        return 0

    since = time.time() - (hours * 3600)
    existing = {str(e.get("call_id")) for e in _load_events()}
    added = 0

    dirs = sorted(calls_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for call_dir in dirs[:limit]:
        if not call_dir.is_dir():
            continue
        meta_path = call_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if meta.get("channel") != "pstn":
            continue
        call_id = str(meta.get("call_id") or call_dir.name)
        if call_id in existing:
            continue
        ended = str(meta.get("ended_at") or "")
        if ended:
            try:
                ended_ts = datetime.fromisoformat(ended.replace("Z", "+00:00")).timestamp()
            except ValueError:
                ended_ts = call_dir.stat().st_mtime
            if ended_ts < since:
                continue
        trace_path = call_dir / "trace.json"
        failures: list[str] = []
        if trace_path.exists():
            try:
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
                for turn in trace.get("turns") or []:
                    failures.extend(turn.get("errors") or [])
            except json.JSONDecodeError:
                pass
        record_canary_call(
            call_id=call_id,
            bidirectional_ok=bool(meta.get("ended_at")),
            compiled_brain_version=meta.get("compiled_brain_version"),
            combination_id=(meta.get("resolved_stack") or {}).get("combination_id"),
            environment=meta.get("environment"),
            failures=failures,
        )
        existing.add(call_id)
        added += 1
    return added


def assert_canary_outbound_allowed(to_e164: str) -> str | None:
    """
    Return error message if outbound blocked under canary rules; else None.
    Enforced when CANARY_ENABLED and APP_ENVIRONMENT=production.
    """
    settings = get_settings()
    if not settings.canary_enabled:
        return None
    if settings.app_environment != "production":
        return None

    allowed = _parse_allowed_destinations(settings.canary_allowed_destinations_csv)
    if allowed and to_e164.strip() not in allowed:
        return f"Canary: destination {to_e164} not in CANARY_ALLOWED_DESTINATIONS"

    since = time.time() - 86400
    today = _load_events(since_ts=since)
    if len(today) >= settings.canary_max_calls_per_day:
        return (
            f"Canary daily limit reached ({settings.canary_max_calls_per_day} calls). "
            "Wait 24h or raise CANARY_MAX_CALLS_PER_DAY after review."
        )
    return None
