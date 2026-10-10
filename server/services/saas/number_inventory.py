"""Platform number inventory — unassigned DIDs owned by the admin pool.

Industry model:
- Numbers already on the Telnyx account live in a Platform inventory tenant until a
  customer buys them. They are NOT offered as Telnyx "available" orders.
- Buying an inventory DID debits the workspace wallet and transfers ownership —
  no carrier order, so a low Telnyx prepaid balance cannot fail the purchase.
- Releasing a number returns it to inventory (still on Telnyx), not a hard delete.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import PhoneNumber

INVENTORY_TENANT_NAME = "Platform inventory"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_platform_inventory_tenant() -> uuid.UUID:
    """Idempotent: one inventory tenant for all unassigned account DIDs."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        row = (
            await session.execute(select(Tenant).where(Tenant.name == INVENTORY_TENANT_NAME).limit(1))
        ).scalar_one_or_none()
        if row is not None:
            return row.tenant_id
        tid = uuid.uuid4()
        session.add(
            Tenant(
                tenant_id=tid,
                name=INVENTORY_TENANT_NAME,
                status="active",
                plan="platform",
                limits={"max_numbers": 10000},
                created_at=_utcnow(),
            )
        )
        await session.commit()
        return tid


async def move_to_inventory(
    *,
    e164: str | None = None,
    number_id: uuid.UUID | None = None,
    telnyx_number_id: str | None = None,
    plivo_number_id: str | None = None,
) -> dict:
    """Park a DID in the admin inventory pool (clears agent binding)."""
    inventory_tid = await ensure_platform_inventory_tenant()
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    e164_n = (e164 or "").strip()
    async with factory() as session:
        pn: PhoneNumber | None = None
        if number_id is not None:
            pn = await session.get(PhoneNumber, number_id)
        elif e164_n:
            pn = (
                await session.execute(
                    select(PhoneNumber).where(
                        PhoneNumber.e164 == e164_n,
                        PhoneNumber.released_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if pn is None:
            if not e164_n:
                raise ValueError("number_not_found")
            pn = PhoneNumber(
                tenant_id=inventory_tid,
                e164=e164_n,
                status="available",
                billing_source="inventory",
                telnyx_number_id=telnyx_number_id,
                plivo_number_id=plivo_number_id,
                agent_id=None,
                inbound_enabled=False,
                outbound_enabled=False,
                created_at=_utcnow(),
            )
            session.add(pn)
        else:
            pn.tenant_id = inventory_tid
            pn.status = "available"
            pn.billing_source = "inventory"
            pn.agent_id = None
            pn.released_at = None
            pn.inbound_enabled = False
            pn.outbound_enabled = False
            if telnyx_number_id:
                pn.telnyx_number_id = telnyx_number_id
            if plivo_number_id:
                pn.plivo_number_id = plivo_number_id
        await session.commit()
        await session.refresh(pn)
        return {
            "numberId": str(pn.id),
            "e164": pn.e164,
            "tenantId": str(pn.tenant_id),
            "status": pn.status,
            "telnyxNumberId": pn.telnyx_number_id,
            "plivoNumberId": pn.plivo_number_id,
        }


async def list_inventory_for_sale(*, country: str | None = None) -> list[dict]:
    """Inventory DIDs customers can buy (not yet assigned to a workspace)."""
    inventory_tid = await ensure_platform_inventory_tenant()
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        rows = (
            await session.execute(
                select(PhoneNumber).where(
                    PhoneNumber.tenant_id == inventory_tid,
                    PhoneNumber.status == "available",
                    PhoneNumber.released_at.is_(None),
                )
            )
        ).scalars().all()
    out: list[dict] = []
    country_u = (country or "").upper()
    for pn in rows:
        # Rough country filter from E.164 prefix; US/CA share +1.
        if country_u and country_u not in {"US", "CA"}:
            dial = {"GB": "+44", "AU": "+61", "IE": "+353", "NZ": "+64", "SG": "+65", "IN": "+91", "ZA": "+27", "PH": "+63"}.get(
                country_u
            )
            if dial and not pn.e164.startswith(dial):
                continue
        elif country_u in {"US", "CA"} and not pn.e164.startswith("+1"):
            continue
        out.append(
            {
                "e164": pn.e164,
                "phone_number": pn.e164,
                "formatted": pn.e164,
                "country": country_u or "US",
                "type": "Local DID",
                "source": "inventory",
                "numberId": str(pn.id),
                "telnyxNumberId": pn.telnyx_number_id,
                "features": ["Voice"],
            }
        )
    return out


async def get_inventory_number(e164: str) -> PhoneNumber | None:
    inventory_tid = await ensure_platform_inventory_tenant()
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        return (
            await session.execute(
                select(PhoneNumber).where(
                    PhoneNumber.e164 == e164,
                    PhoneNumber.tenant_id == inventory_tid,
                    PhoneNumber.released_at.is_(None),
                )
            )
        ).scalar_one_or_none()
