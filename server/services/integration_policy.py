"""Which catalog integrations a workspace may use, as set by the platform admin.

An app is available to a workspace when its per-workspace override says so, or,
with no override, when the platform switch is on (no row = on). The check is
applied wherever an integration can be reached: the catalog, connect and
activate, connection setup, the tools offered to the model and the router that
executes them. When the policy cannot be read the answer is "off" for every app,
never "on".
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import Any

from server.utils.logger import logger

_TTL_SECONDS = 30
_MAX_TENANTS = 2048
_platform_cache: tuple[float, dict[str, bool]] | None = None
_tenant_cache: OrderedDict[str, tuple[float, dict[str, bool]]] = OrderedDict()


def _norm(app: str) -> str:
    from server.services.tool_schema_registry import _normalize

    return _normalize(str(app or ""))


def catalog_apps() -> list[str]:
    from server.routes.integrations_catalog import CATALOG_INTEGRATIONS

    return [_norm(row["id"]) for row in CATALOG_INTEGRATIONS]


def _factory(factory: Any) -> Any:
    if factory is not None:
        return factory
    from server.db.connection import get_session_factory

    return get_session_factory()


async def platform_switches(factory: Any = None) -> dict[str, bool]:
    """Explicit platform switches only; an app without a row is on."""
    global _platform_cache
    now = time.monotonic()
    if _platform_cache and now - _platform_cache[0] < _TTL_SECONDS:
        return dict(_platform_cache[1])
    from sqlalchemy import select

    from server.db.models.integration_models import PlatformIntegrationSetting

    async with _factory(factory)() as session:
        rows = (await session.execute(select(PlatformIntegrationSetting))).scalars().all()
    switches = {_norm(r.app_name): bool(r.enabled) for r in rows}
    _platform_cache = (now, switches)
    return dict(switches)


async def tenant_overrides(tenant_id: str, factory: Any = None) -> dict[str, bool]:
    key = str(tenant_id)
    now = time.monotonic()
    hit = _tenant_cache.get(key)
    if hit and now - hit[0] < _TTL_SECONDS:
        return dict(hit[1])
    from sqlalchemy import select

    from server.db.models.integration_models import TenantIntegrationOverride

    async with _factory(factory)() as session:
        rows = (await session.execute(select(TenantIntegrationOverride).where(
            TenantIntegrationOverride.tenant_id == uuid.UUID(key),
        ))).scalars().all()
    overrides = {_norm(r.app_name): bool(r.enabled) for r in rows}
    _tenant_cache[key] = (now, overrides)
    _tenant_cache.move_to_end(key)
    while len(_tenant_cache) > _MAX_TENANTS:
        _tenant_cache.popitem(last=False)
    return dict(overrides)


async def disabled_apps(tenant_id: str, factory: Any = None) -> set[str]:
    """Catalog apps this workspace may not use. Fails closed: all, on error."""
    apps = catalog_apps()
    try:
        platform = await platform_switches(factory)
        overrides = await tenant_overrides(tenant_id, factory)
    except Exception as exc:  # noqa: BLE001 - an unreadable policy must not open access
        if _policy_tables_missing(exc):
            # Before migration 052 no admin can have switched anything off.
            logger.warning("[INTEGRATION_POLICY] Policy tables missing; run migrations. Treating as no restrictions.")
            return set()
        logger.warning("[INTEGRATION_POLICY] Policy unavailable, integrations off: %s", type(exc).__name__)
        return set(apps)
    return {app for app in apps if not overrides.get(app, platform.get(app, True))}


def _policy_tables_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(t in text for t in ("platform_integration_settings", "tenant_integration_overrides")) and (
        "does not exist" in text or "no such table" in text or "undefinedtable" in text)


async def is_enabled(tenant_id: str, app: str, factory: Any = None) -> bool:
    return _norm(app) not in await disabled_apps(tenant_id, factory)


def invalidate(tenant_id: str | None = None) -> None:
    """Drop cached policy (one workspace, or all) and the tool lists built on it."""
    global _platform_cache
    from server.services import tenant_tool_cache

    if tenant_id is None:
        _platform_cache = None
        _tenant_cache.clear()
        tenant_tool_cache.invalidate_all()
    else:
        _tenant_cache.pop(str(tenant_id), None)
        tenant_tool_cache.invalidate(str(tenant_id))
