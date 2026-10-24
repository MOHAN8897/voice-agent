"""Verified Indian locale voices shared by the stack catalog and Test Studio."""
from __future__ import annotations

import re
import time
from typing import Any


# Compatibility exports: no invented/offline speakers.
_FALLBACK_VOICES: list[dict[str, Any]] = []
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_last_refresh = 0.0


def _normalize_voice(raw: dict[str, Any]) -> dict[str, Any] | None:
    from server.providers.voice_inventory import normalize_cartesia_voice

    row = normalize_cartesia_voice(raw)
    return {**row, "name": row["label"]} if row else None


def cartesia_voice_ids() -> set[str]:
    from server.providers.voice_inventory import inventory

    return {row["id"] for row in inventory().get("cartesia", {}).get("voices", [])}


def is_cartesia_voice_id(value: str) -> bool:
    # Classification only; model/language validation is mandatory before synthesis.
    return bool(_UUID_RE.fullmatch(str(value or ""))) or value in cartesia_voice_ids()


async def fetch_cartesia_voices(*, force: bool = False) -> list[dict[str, Any]]:
    global _last_refresh
    from server.providers.voice_inventory import refresh_inventory

    if force or time.monotonic() - _last_refresh >= 3600:
        await refresh_inventory()
        _last_refresh = time.monotonic()
    return voices_for_catalog()


def voices_for_catalog(model: str = "sonic-3.5") -> list[dict[str, Any]]:
    from server.providers.voice_inventory import voices_for_model

    return [{**row, "name": row["label"]} for row in voices_for_model("cartesia", model)]


def voices_grouped_for_ui(model: str = "sonic-3.5") -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in voices_for_catalog(model):
        for language in row["languages"]:
            groups.setdefault(language, []).append(row)
    return {"groups": [{"id": language, "label": language, "voices": rows} for language, rows in sorted(groups.items())], "source": "provider"}


async def warm_cartesia_voices() -> None:
    try:
        await fetch_cartesia_voices()
    except (OSError, ValueError):
        from server.utils.logger import logger
        logger.warning("Voice catalog refresh failed; the last verified inventory remains available.")
