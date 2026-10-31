"""Shared rules for manual wallet adjustments made by platform admins.

Both admin entry points (the admin panel's `/api/dev/admin/wallets/adjust` and the
older `/api/admin/credits`) post through these helpers so a manual adjustment is
always booked the same way:

* The ledger kind is fixed by the sign of the amount. The admin's free-text
  reason is kept in the audit log only; it never becomes the ledger kind, so an
  adjustment can't be booked as a paid top-up ("topup", "razorpay_topup") and
  show up as revenue or as money the tenant paid.
* A client-supplied idempotency key turns a retried request into a no-op
  instead of a second credit.
"""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.saas_models import BillingWalletTransaction

ADMIN_CREDIT_KIND = "admin_grant"
ADMIN_DEBIT_KIND = "admin_debit"

#: Characters allowed in a client idempotency key (a UUID fits).
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_-]{8,80}$"


def admin_adjust_kind(amount: int) -> str:
    return ADMIN_CREDIT_KIND if amount > 0 else ADMIN_DEBIT_KIND


def admin_adjust_reference(tenant_id: uuid.UUID, amount: int, idempotency_key: str | None) -> str:
    """Ledger reference for one adjustment; reference_id is varchar(64)."""
    prefix = "agr" if amount > 0 else "adb"
    if idempotency_key:
        tail = hashlib.sha256(f"{tenant_id.hex}:{amount}:{idempotency_key}".encode()).hexdigest()[:24]
    else:
        tail = uuid.uuid4().hex[:12]
    return f"{prefix}:{tenant_id.hex}:{tail}"


async def tenant_exists(tenant_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        return await session.get(Tenant, tenant_id) is not None


async def adjustment_already_posted(reference_id: str) -> bool:
    async with get_session_factory()() as session:
        row = await session.execute(
            select(BillingWalletTransaction.id).where(BillingWalletTransaction.reference_id == reference_id)
        )
        return row.first() is not None
