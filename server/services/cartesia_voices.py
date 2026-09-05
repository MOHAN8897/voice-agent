"""Cartesia voice catalog — live API pull + Indian (te/hi/en) curation for Test Studio."""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from server.config.constants import constants
from server.config.env import get_settings

# Minimal offline fallbacks when no API key
_FALLBACK_VOICES: list[dict[str, Any]] = [
    {"id": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "name": "Skylar", "gender": "feminine", "languages": ["en"], "region": "english", "description": "American English female (default)"},
    {"id": "79a125e8-cd45-4c13-8a67-0491c5ad1b8a", "name": "Maya", "gender": "feminine", "languages": ["en", "te", "hi"], "region": "indian_english", "description": "Indian English female"},
    {"id": "2ee87190-8f84-4925-97da-e756ad7d262d", "name": "Devansh", "gender": "masculine", "languages": ["en", "te", "hi"], "region": "indian_english", "description": "Indian English male"},
    {"id": "76961778-84da-4b51-8d42-2e8e6e6a5e8a", "name": "Bhavani", "gender": "feminine", "languages": ["te"], "region": "telugu", "description": "Telugu female"},
    {"id": "82c2afc8-4f0d-4c3e-9c3e-8e8e8e8e8e8e", "name": "Charan", "gender": "masculine", "languages": ["te"], "region": "telugu", "description": "Telugu male"},
    {"id": "9cebb910-d4b7-4a4a-85a4-12c79137724c", "name": "Aarti", "gender": "feminine", "languages": ["hi"], "region": "hindi", "description": "Hindi female"},
    {"id": "97303aad-0000-0000-0000-000000000001", "name": "Amrit", "gender": "masculine", "languages": ["hi"], "region": "hindi", "description": "Hindi male"},
]

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

_cache: dict[str, Any] = {
    "all_voices": list(_FALLBACK_VOICES),
    "studio_voices": list(_FALLBACK_VOICES),
    "groups": {},
    "fetched_at": 0.0,
    "source": "static",
}

_REGION_LABELS = {
    "telugu": "Telugu",
    "hindi": "Hindi",
    "indian_english": "Indian English",
    "english": "English (US/UK)",
}


def _text_blob(v: dict[str, Any]) -> str:
    parts = [
        str(v.get("name") or ""),
        str(v.get("description") or ""),
        str(v.get("tagline") or ""),
        str(v.get("accent") or ""),
    ]
    return " ".join(parts).lower()


def _infer_region(v: dict[str, Any]) -> str | None:
    langs = v.get("languages") or []
    if isinstance(langs, str):
        langs = [langs]
    lang_set = {str(x).lower().split("-")[0] for x in langs}
    blob = _text_blob(v)

    if "te" in lang_set or "telugu" in blob:
        return "telugu"
    if "hi" in lang_set or "hindi" in blob:
        return "hindi"
    if any(k in blob for k in ("indian", "india", "desi", "bharat")):
        return "indian_english"
    if "en" in lang_set or lang_set & {"en-in"}:
        # Pure English without Indian markers → general English bucket
        if any(k in blob for k in ("indian", "india", "hindi", "telugu")):
            return "indian_english"
        return "english"
    return None


def _normalize_voice(raw: dict[str, Any]) -> dict[str, Any] | None:
    vid = raw.get("id")
    if not vid:
        return None
    langs = raw.get("languages") or raw.get("language") or []
    if isinstance(langs, str):
        langs = [langs]
    desc = str(raw.get("description") or raw.get("tagline") or "").strip()
    gender = raw.get("gender") or "unknown"
    name = str(raw.get("name") or vid[:8]).strip()
    accent = ""
    if "indian" in desc.lower():
        accent = "Indian"
    elif "american" in desc.lower():
        accent = "American"
    elif "british" in desc.lower():
        accent = "British"

    voice = {
        "id": str(vid),
        "name": name,
        "gender": gender,
        "languages": [str(x) for x in langs] if langs else [],
        "accent": accent,
        "description": desc[:120],
    }
    region = _infer_region(voice)
    if region:
        voice["region"] = region
    return voice


def _build_studio_catalog(all_voices: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Keep Indian-focused voices + a capped English set for Test Studio."""
    groups: dict[str, list[dict[str, Any]]] = {
        "telugu": [],
        "hindi": [],
        "indian_english": [],
        "english": [],
    }
    seen: set[str] = set()

    for v in all_voices:
        region = v.get("region") or _infer_region(v)
        if not region or region not in groups:
            continue
        vid = v["id"]
        if vid in seen:
            continue
        seen.add(vid)
        entry = {**v, "region": region}
        groups[region].append(entry)

    # Sort each group: feminine/masculine then name
    def sort_key(x: dict[str, Any]) -> tuple:
        g = str(x.get("gender") or "")
        return (g, str(x.get("name") or "").lower())

    for key in groups:
        groups[key] = sorted(groups[key], key=sort_key)

    # Cap general English so the dropdown stays usable, but never drop fallbacks.
    # Skylar is the default UUID; an A–Z cap otherwise hides her and blanks the <select>.
    fallback_ids = {v["id"] for v in _FALLBACK_VOICES}
    pinned_en = [v for v in groups["english"] if v["id"] in fallback_ids]
    rest_en = [v for v in groups["english"] if v["id"] not in fallback_ids]
    groups["english"] = pinned_en + rest_en[: max(0, 24 - len(pinned_en))]

    studio: list[dict[str, Any]] = []
    for region in ("telugu", "hindi", "indian_english", "english"):
        studio.extend(groups[region])

    return studio, groups


def cartesia_voice_ids() -> set[str]:
    return {v["id"] for v in _cache.get("all_voices", _FALLBACK_VOICES)}


def is_cartesia_voice_id(value: str) -> bool:
    v = (value or "").strip()
    if _UUID_RE.match(v):
        return True
    return v.lower() in {x.lower() for x in cartesia_voice_ids()}


async def fetch_cartesia_voices(*, force: bool = False) -> list[dict[str, Any]]:
    """Pull full voice list from Cartesia API; rebuild Test Studio Indian catalog."""
    global _cache
    now = time.time()
    if not force and _cache.get("studio_voices") and now - float(_cache.get("fetched_at") or 0) < 3600:
        return list(_cache["studio_voices"])

    try:
        from server.services.dev_secrets_store import dev_secrets_store

        settings = get_settings()
        key = dev_secrets_store.effective_secret("cartesia_api_key") or settings.cartesia_api_key or ""
    except Exception:
        key = ""

    if not key or len(key) < 8:
        studio, groups = _build_studio_catalog(list(_FALLBACK_VOICES))
        _cache = {
            "all_voices": list(_FALLBACK_VOICES),
            "studio_voices": studio,
            "groups": groups,
            "fetched_at": now,
            "source": "static",
        }
        return studio

    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    cursor: str | None = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(20):
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["starting_after"] = cursor
                r = await client.get(
                    "https://api.cartesia.ai/voices",
                    headers={
                        "X-API-Key": key,
                        "Cartesia-Version": constants.CARTESIA_API_VERSION,
                    },
                    params=params,
                )
                if r.status_code != 200:
                    break
                body = r.json()
                items = body.get("data") if isinstance(body, dict) else body
                if not isinstance(items, list):
                    break
                for item in items:
                    norm = _normalize_voice(item)
                    if norm and norm["id"] not in seen_ids:
                        seen_ids.add(norm["id"])
                        collected.append(norm)
                has_more = body.get("has_more") if isinstance(body, dict) else False
                if not has_more:
                    break
                cursor = items[-1].get("id") if items else None
                if not cursor:
                    break
    except Exception:
        collected = []

    if not collected:
        studio, groups = _build_studio_catalog(list(_FALLBACK_VOICES))
        _cache = {
            "all_voices": list(_FALLBACK_VOICES),
            "studio_voices": studio,
            "groups": groups,
            "fetched_at": now,
            "source": "static",
        }
        return studio

    studio, groups = _build_studio_catalog(list(_FALLBACK_VOICES) + collected)
    _cache = {
        "all_voices": collected,
        "studio_voices": studio,
        "groups": groups,
        "fetched_at": now,
        "source": "api",
    }
    return studio


def voices_for_catalog() -> list[dict[str, Any]]:
    """Indian-focused voices for settings catalog (sync snapshot)."""
    grouped = voices_grouped_for_ui()
    studio: list[dict[str, Any]] = []
    for key in ("telugu", "hindi", "indian_english", "english"):
        studio.extend(grouped.get(key) or [])
    return studio or list(_FALLBACK_VOICES)


def voices_grouped_for_ui() -> dict[str, Any]:
    groups = _cache.get("groups") or {}
    telugu = list(groups.get("telugu") or [])
    hindi = list(groups.get("hindi") or [])
    indian_english = list(groups.get("indian_english") or [])
    english = list(groups.get("english") or [])
    _, fallback_groups = _build_studio_catalog(list(_FALLBACK_VOICES))
    fallback_ids = {v["id"] for v in _FALLBACK_VOICES}

    def _pin(key: str, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        have = {v["id"] for v in current}
        pinned = [v for v in fallback_groups[key] if v["id"] not in have]
        merged = pinned + current
        if key != "english":
            return merged
        pin = [v for v in merged if v["id"] in fallback_ids]
        rest = [v for v in merged if v["id"] not in fallback_ids]
        return pin + rest[: max(0, 24 - len(pin))]

    telugu = _pin("telugu", telugu)
    hindi = _pin("hindi", hindi)
    indian_english = _pin("indian_english", indian_english)
    english = _pin("english", english)
    if not (telugu or hindi or indian_english or english):
        telugu = fallback_groups["telugu"]
        hindi = fallback_groups["hindi"]
        indian_english = fallback_groups["indian_english"]
        english = fallback_groups["english"]
    return {
        "telugu": telugu,
        "hindi": hindi,
        "indian_english": indian_english,
        "english": english,
        "labels": _REGION_LABELS,
        "source": _cache.get("source", "static"),
        "total_pulled": len(_cache.get("all_voices") or []),
        "studio_count": len(_cache.get("studio_voices") or telugu + hindi + indian_english + english),
    }


async def warm_cartesia_voices() -> None:
    """Call on app startup so first catalog request is populated."""
    try:
        await fetch_cartesia_voices(force=True)
    except Exception:
        pass
