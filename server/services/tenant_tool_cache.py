"""
Tenant Tool Cache - short-TTL in-process cache for active integration app names.

Avoids a DB round-trip on every call start for high-volume tenants.
TTL = 60 s so that a newly connected integration is picked up within a minute.
"""
from __future__ import annotations

import asyncio
import time
import uuid as _uuid
from collections import OrderedDict
from typing import Any
from weakref import WeakValueDictionary

from server.utils.logger import logger

_TTL_SECONDS = 60
_MAX_CACHED_TENANTS = 2048
_cache: OrderedDict[str, tuple[list[str], float]] = OrderedDict()
_lock = asyncio.Lock()
_flights: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_epoch = 0


async def get_active_app_names(tenant_id: str, session_factory: Any | None) -> list[str]:
    """
    Return app_names of ACTIVE integrations for a tenant.
    Results are cached for TTL_SECONDS per tenant_id.
    """
    flight = _flights.setdefault(tenant_id, asyncio.Lock())
    async with flight:
        async with _lock:
            cached_apps, cached_at = _cache.get(tenant_id, (None, 0.0))
            if cached_apps is not None and (time.monotonic() - cached_at) < _TTL_SECONDS:
                _cache.move_to_end(tenant_id)
                return list(cached_apps)
            _cache.pop(tenant_id, None)
            epoch = _epoch
        apps = await _query_db(tenant_id, session_factory)
        async with _lock:
            if epoch == _epoch:
                _cache[tenant_id] = (list(apps), time.monotonic())
                _cache.move_to_end(tenant_id)
                while len(_cache) > _MAX_CACHED_TENANTS:
                    _cache.popitem(last=False)
        return list(apps)


async def _query_db(tenant_id: str, session_factory: Any | None) -> list[str]:
    if not session_factory:
        return []
    try:
        from sqlalchemy import select
        from server.db.models.integration_models import TenantIntegration

        async with session_factory() as session:
            res = await session.execute(
                select(TenantIntegration).where(
                    TenantIntegration.tenant_id == _uuid.UUID(str(tenant_id)),
                    TenantIntegration.status == "ACTIVE",
                )
            )
            return [i.app_name for i in res.scalars().all() if (i.metadata_ or {}).get("gateway_verified") is True]
    except Exception as exc:
        logger.warning("[TENANT_TOOL_CACHE] DB query failed: %s", type(exc).__name__)
        return []


async def get_connection_id(tenant_id: str, app_name: str, session_factory: Any | None) -> str | None:
    """
    Return the stored Nango connection_id for a specific tenant + app combination.
    Used by nango_service.execute_in_call_tool to authenticate API calls.
    """
    if not session_factory:
        return None
    try:
        from sqlalchemy import func, or_, select
        from server.db.models.integration_models import TenantIntegration

        canonical = app_name.upper().replace("-", "_")
        stripped = canonical.replace("_", "")
        async with session_factory() as session:
            res = await session.execute(
                select(TenantIntegration).where(
                    TenantIntegration.tenant_id == _uuid.UUID(str(tenant_id)),
                    or_(
                        func.upper(TenantIntegration.app_name) == canonical,
                        func.upper(TenantIntegration.app_name) == stripped,
                        func.replace(func.upper(TenantIntegration.app_name), "-", "_") == canonical,
                        func.replace(func.replace(func.upper(TenantIntegration.app_name), "-", ""), "_", "") == stripped,
                    ),
                    TenantIntegration.status == "ACTIVE",
                )
            )
            record = res.scalar_one_or_none()
            return record.connection_id if record and (record.metadata_ or {}).get("gateway_verified") is True else None
    except Exception as exc:
        logger.warning("[TENANT_TOOL_CACHE] connection lookup failed: %s", type(exc).__name__)
        return None


def invalidate(tenant_id: str) -> None:
    """Invalidate a tenant's cache entry (call after integration connect/disconnect)."""
    global _epoch
    _epoch += 1
    _cache.pop(tenant_id, None)
