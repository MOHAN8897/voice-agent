"""Operator-authored merchandising for the public tier prices.

Tags ("Most chosen", "Best value"), the featured/visible switches and the
featured-card style preset live in the same append-only ConfigVersion store as
other platform configuration, so price changes in the rate tables do not require
touching marketing code. Tiers are addressed by the ids configured in the voice
stack, so operator-created stacks are merchandised alongside the standard three;
unknown tiers are rejected rather than silently stored.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import desc, func, select

from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion

RESOURCE_TYPE = "tier_merchandising"
RESOURCE_ID = "global"
PUBLIC_TIERS = ("low", "medium", "premium")
TONES = ("neutral", "accent", "success", "warning")
# Featured-card treatments are presentation presets; the public page owns the pixels.
FEATURED_STYLES = ("graphite", "ivory", "forest", "midnight")
DEFAULT_FEATURED_STYLE = "graphite"
MAX_TAGS_PER_TIER = 3
MAX_TAG_LENGTH = 32
_CACHE_TTL_SEC = 5.0
_WRITE_LOCK = asyncio.Lock()
_cache: tuple[float, dict[str, Any]] | None = None
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class MerchandisingError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _default_tier() -> dict[str, Any]:
    return {"tags": [], "featured": False, "visible": True}


def default_merchandising() -> dict[str, Any]:
    return {
        "version": 0,
        "featuredStyle": DEFAULT_FEATURED_STYLE,
        "tiers": {tier: _default_tier() for tier in PUBLIC_TIERS},
        "updatedAt": None,
        "updatedBy": None,
    }


def _clean_tag_label(raw: Any) -> str:
    from server.services.saas.voice_stack_profiles import _PRIVATE_LABEL_RE

    if not isinstance(raw, str):
        raise MerchandisingError("invalid_tag", "Each tag needs a text label.")
    label = " ".join(raw.split())
    if not label:
        raise MerchandisingError("invalid_tag", "A tag label cannot be empty.")
    if len(label) > MAX_TAG_LENGTH:
        raise MerchandisingError("invalid_tag", f"Tag labels are limited to {MAX_TAG_LENGTH} characters.")
    if _CONTROL_CHARS.search(label):
        raise MerchandisingError("invalid_tag", "Tag labels cannot contain control characters.")
    if _PRIVATE_LABEL_RE.search(label):
        raise MerchandisingError("invalid_tag", "Tag labels cannot mention vendors, carriers, or links.")
    return label


def _clean_tier(tier: str, raw: Any) -> dict[str, Any]:
    if raw is None:
        return _default_tier()
    if not isinstance(raw, dict):
        raise MerchandisingError("invalid_tier_config", f"Tier '{tier}' must be an object.")
    unknown = set(raw) - {"tags", "featured", "visible"}
    if unknown:
        raise MerchandisingError("invalid_tier_config", f"Tier '{tier}' contains unsupported fields.")
    tags_raw = raw.get("tags", [])
    if not isinstance(tags_raw, list):
        raise MerchandisingError("invalid_tags", "Tags must be a list.")
    if len(tags_raw) > MAX_TAGS_PER_TIER:
        raise MerchandisingError("too_many_tags", f"Each tier allows at most {MAX_TAGS_PER_TIER} tags.")
    tags: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in tags_raw:
        if not isinstance(item, dict):
            raise MerchandisingError("invalid_tag", "Each tag must be an object with a label.")
        unknown_tag = set(item) - {"label", "tone"}
        if unknown_tag:
            raise MerchandisingError("invalid_tag", "Tags only accept a label and a tone.")
        label = _clean_tag_label(item.get("label"))
        key = label.casefold()
        if key in seen:
            raise MerchandisingError("duplicate_tag", f"The tag '{label}' is repeated.")
        seen.add(key)
        tone = item.get("tone", "neutral")
        if tone not in TONES:
            raise MerchandisingError("invalid_tag_tone", "Choose a supported tag style.")
        tags.append({"label": label, "tone": tone})
    featured = raw.get("featured", False)
    visible = raw.get("visible", True)
    if not isinstance(featured, bool) or not isinstance(visible, bool):
        raise MerchandisingError("invalid_tier_config", "Featured and visible must be booleans.")
    return {"tags": tags, "featured": featured, "visible": visible}


def validate_merchandising(
    tiers: Any, *, allowed_tiers: Iterable[str] | None = None
) -> dict[str, dict[str, Any]]:
    if not isinstance(tiers, dict):
        raise MerchandisingError("invalid_payload", "tiers must be an object keyed by tier.")
    allowed = tuple(dict.fromkeys(allowed_tiers or PUBLIC_TIERS))
    unknown = set(tiers) - set(allowed)
    if unknown:
        raise MerchandisingError("unknown_tier", "Only tiers configured in the voice stack can be merchandised.")
    cleaned = {tier: _clean_tier(tier, tiers.get(tier)) for tier in allowed}
    featured = [tier for tier, config in cleaned.items() if config["featured"]]
    if len(featured) > 1:
        raise MerchandisingError("multiple_featured", "Only one tier can be featured at a time.")
    if featured and not cleaned[featured[0]]["visible"]:
        raise MerchandisingError("featured_hidden", "A hidden tier cannot be featured.")
    return cleaned


def validate_featured_style(raw: Any) -> str:
    if raw is None:
        return DEFAULT_FEATURED_STYLE
    if not isinstance(raw, str) or raw not in FEATURED_STYLES:
        raise MerchandisingError(
            "invalid_featured_style",
            "Choose one of the available featured card styles.",
        )
    return raw


def _from_row(row: ConfigVersion) -> dict[str, Any]:
    payload = row.payload or {}
    stored = payload.get("tiers") if isinstance(payload.get("tiers"), dict) else {}
    view = default_merchandising()
    view["version"] = int(row.version or 0)
    stored_style = payload.get("featuredStyle")
    # Older rows predate the style field; they keep the current default treatment.
    view["featuredStyle"] = stored_style if stored_style in FEATURED_STYLES else DEFAULT_FEATURED_STYLE
    view["updatedAt"] = payload.get("savedAt") or (row.created_at.isoformat() if row.created_at else None)
    view["updatedBy"] = payload.get("actor")
    for tier, entry in stored.items():
        if isinstance(entry, dict):
            view["tiers"][tier] = {
                "tags": entry.get("tags") if isinstance(entry.get("tags"), list) else [],
                "featured": entry.get("featured") is True,
                "visible": entry.get("visible") is not False,
            }
    return view


async def load_tier_merchandising(*, force: bool = False) -> dict[str, Any]:
    """Read merchandising; the public page keeps working if the store is down."""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_SEC:
        return _cache[1]
    view = default_merchandising()
    factory = get_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                result = await session.execute(
                    select(ConfigVersion)
                    .where(
                        ConfigVersion.resource_type == RESOURCE_TYPE,
                        ConfigVersion.resource_id == RESOURCE_ID,
                    )
                    .order_by(desc(ConfigVersion.version), desc(ConfigVersion.created_at))
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    view = _from_row(row)
        except Exception:
            view = default_merchandising()
    _cache = (now, view)
    return view


async def save_tier_merchandising(
    *,
    tiers: Any,
    expected_version: int,
    actor: str,
    allowed_tiers: Iterable[str] | None = None,
    featured_style: Any = None,
) -> dict[str, Any]:
    global _cache
    cleaned = validate_merchandising(tiers, allowed_tiers=allowed_tiers)
    requested_style = validate_featured_style(featured_style) if featured_style is not None else None
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
        raise MerchandisingError("invalid_version", "expectedVersion must be a nonnegative integer.")
    factory = get_session_factory()
    if factory is None:
        raise MerchandisingError(
            "durable_store_unavailable", "Tier merchandising requires the database configuration store.", 503,
        )
    saved_at = datetime.now(timezone.utc).isoformat()
    async with _WRITE_LOCK:
        async with factory() as session:
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(
                    select(func.pg_advisory_xact_lock(func.hashtext(f"{RESOURCE_TYPE}:{RESOURCE_ID}")))
                )
            result = await session.execute(
                select(ConfigVersion)
                .where(
                    ConfigVersion.resource_type == RESOURCE_TYPE,
                    ConfigVersion.resource_id == RESOURCE_ID,
                )
                .order_by(desc(ConfigVersion.version), desc(ConfigVersion.created_at))
                .limit(1)
                .with_for_update()
            )
            latest = result.scalar_one_or_none()
            version = int(latest.version or 0) if latest is not None else 0
            if version != expected_version:
                raise MerchandisingError(
                    "version_conflict",
                    "Pricing tags changed in another session. Reload before saving.",
                    409,
                )
            row = ConfigVersion(
                id=uuid.uuid4(),
                resource_type=RESOURCE_TYPE,
                resource_id=RESOURCE_ID,
                version=version + 1,
                payload={
                    "tiers": cleaned,
                    # A caller that does not choose a style keeps the saved treatment.
                    "featuredStyle": requested_style
                    or (_from_row(latest)["featuredStyle"] if latest is not None else DEFAULT_FEATURED_STYLE),
                    "savedAt": saved_at,
                    "actor": actor,
                },
            )
            session.add(row)
            await session.commit()
            view = _from_row(row)
    _cache = (time.monotonic(), view)
    return view


def clear_merchandising_cache() -> None:
    global _cache
    _cache = None
