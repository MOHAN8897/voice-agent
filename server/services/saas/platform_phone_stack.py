"""Universal live-phone stack — configured in dev panel, applied to all SaaS calls."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.realtime.models import DEFAULT_GEMINI_LIVE_MODEL, default_gemini_live_voice
from server.services.pstn_stack import normalize_pstn_stack_override

logger = logging.getLogger(__name__)

_STACK_FILE = "saas_universal_phone_stack.json"


def _stack_path() -> Path:
    return get_settings().data_path / _STACK_FILE


def load_universal_phone_stack_raw() -> dict[str, Any] | None:
    path = _stack_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        logger.warning("could not read %s", path)
        return None


def save_universal_phone_stack_raw(stack: dict[str, Any]) -> dict[str, Any]:
    path = _stack_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(stack, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    return stack


async def mirror_universal_phone_stack_to_db(stack: dict[str, Any]) -> bool:
    import uuid
    from server.db.connection import get_session_factory
    from server.db.models.entities import ConfigVersion

    factory = get_session_factory()
    if not factory:
        return False
    try:
        async with factory() as session:
            session.add(
                ConfigVersion(
                    id=uuid.uuid4(),
                    resource_type="universal_phone_stack",
                    resource_id="saas_phone",
                    version=1,
                    payload=stack,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning("Could not persist universal phone stack to DB (%s)", type(exc).__name__)
        raise RuntimeError("Could not persist the universal phone stack to the database") from None


async def hydrate_universal_phone_stack_from_db() -> bool:
    """Restore the newest stack from Postgres, while keeping a newer disk-only save."""
    from sqlalchemy import select
    from server.db.connection import get_session_factory
    from server.db.models.entities import ConfigVersion

    path = _stack_path()
    disk = load_universal_phone_stack_raw()

    factory = get_session_factory()
    if not factory:
        return disk is not None
    try:
        async with factory() as session:
            result = await session.execute(
                select(ConfigVersion)
                .where(
                    ConfigVersion.resource_type == "universal_phone_stack",
                    ConfigVersion.resource_id == "saas_phone",
                )
                .order_by(ConfigVersion.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row and isinstance(row.payload, dict):
                disk_updated = _stack_updated_at(disk)
                db_updated = _stack_updated_at(row.payload) or _as_utc(row.created_at)
                if disk is not None and disk_updated and db_updated and disk_updated > db_updated:
                    return True
                save_universal_phone_stack_raw(row.payload)
                logger.info("[VOICE] Restored universal phone stack from database")
                return True
    except Exception as e:
        logger.warning("Could not hydrate universal phone stack from DB (%s)", type(e).__name__)
    return disk is not None


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _stack_updated_at(stack: dict[str, Any] | None) -> datetime | None:
    raw = str((stack or {}).get("updated_at") or "").strip()
    if not raw:
        return None
    try:
        return _as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def resolve_platform_phone_stack_sync(language: str = "te-IN") -> dict[str, Any]:
    """Resolve the admin-saved stack, defaulting to Gemini Live until changed by admin."""
    lang = (language or "te-IN").strip() or "te-IN"
    stored = load_universal_phone_stack_raw()
    if stored and stored.get("stack_override"):
        base = dict(stored["stack_override"])
        # Provider/voice defaults are global; spoken language belongs to this agent.
        base["language"] = lang
        normalized, _ = normalize_pstn_stack_override(
            base, language=lang, tier="medium", default_provider="gemini"
        )
        return normalized or base

    if stored and stored.get("pipeline") == "realtime_voice":
        normalized, _ = normalize_pstn_stack_override(
            {**stored, "language": lang}, language=lang, tier="medium", default_provider="gemini"
        )
        return normalized or stored

    # No admin selection exists yet; use Gemini Live rather than inheriting an
    # environment tier that may silently choose OpenAI.
    raw: dict[str, Any] = {
        "pipeline": "realtime_voice",
        "voice_flow": "realtime_e2e",
        "language": lang,
        "llm": {"provider": "gemini", "model": DEFAULT_GEMINI_LIVE_MODEL},
        "realtime_voice": {
            "voice": default_gemini_live_voice(lang),
            "turn_detection": "semantic_vad",
            "vad_eagerness": "high",
            "noise_reduction": "far_field",
            "speed": 1.0,
            "silence_ms": 250,
        },
    }
    normalized, _ = normalize_pstn_stack_override(
        raw, language=lang, tier="medium", default_provider="gemini"
    )
    return normalized or raw


async def resolve_platform_phone_stack(language: str = "te-IN") -> dict[str, Any]:
    return resolve_platform_phone_stack_sync(language)
