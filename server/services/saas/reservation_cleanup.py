"""Expire stale number reservations."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete

from server.db.connection import get_session_factory
from server.db.models.saas_models import NumberReservation


async def purge_expired_reservations() -> int:
    factory = get_session_factory()
    if factory is None:
        return 0
    now = datetime.now(timezone.utc)
    async with factory() as session:
        result = await session.execute(delete(NumberReservation).where(NumberReservation.expires_at < now))
        await session.commit()
        return int(result.rowcount or 0)
