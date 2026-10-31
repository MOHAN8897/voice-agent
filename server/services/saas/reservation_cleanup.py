"""Expire stale number reservations."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select

from server.db.connection import get_session_factory
from server.db.models.saas_models import NumberPurchase, NumberReservation

#: A purchase in one of these states has taken the customer's money and may still
#: become a carrier order. Its reservation is the database-level guard (unique on
#: e164) that stops a second tenant buying the same DID, so it must outlive the
#: checkout TTL until the provision worker settles the purchase.
IN_FLIGHT_PURCHASE_STATUSES = ("paid", "provisioning", "needs_attention")


def expired_reservations_statement(now: datetime):
    """Expired holds whose purchase is no longer in flight."""
    return delete(NumberReservation).where(
        NumberReservation.expires_at < now,
        NumberReservation.purchase_id.not_in(
            select(NumberPurchase.id).where(
                NumberPurchase.status.in_(IN_FLIGHT_PURCHASE_STATUSES)
            )
        ),
    )


async def purge_expired_reservations() -> int:
    factory = get_session_factory()
    if factory is None:
        return 0
    now = datetime.now(timezone.utc)
    async with factory() as session:
        result = await session.execute(expired_reservations_statement(now))
        await session.commit()
        return int(result.rowcount or 0)
