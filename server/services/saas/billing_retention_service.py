"""Statutory retention of billing documents after a workspace is deleted.

GST law requires tax invoices, credit notes and the ledger behind them to be
kept for eight years, which outlives the workspace that issued them. Deleting a
workspace therefore cannot delete its invoices: the documents are re-parented
to one fixed archive tenant, the buyer's contact identity is erased, and every
amount, tax split, serial and payment reference is left exactly as issued.

The archive tenant is not a customer. It has no members, no agents and no
wallet; it exists only so retained rows keep a valid `tenant_id`.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update

ARCHIVE_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "dialtact:billing-retention")
ARCHIVE_TENANT_NAME = "Billing Archive (retained)"
ANONYMIZED_CUSTOMER_NAME = "Deleted customer"


def anonymize_buyer_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Replace a buyer block with a PII-free copy that keeps the tax facts.

    The GSTIN is a public registration and the state decides CGST/SGST versus
    IGST, so both stay on the document. Name, email and address are erased.
    """
    source = snapshot or {}
    return {
        "legalName": ANONYMIZED_CUSTOMER_NAME,
        "gstin": source.get("gstin"),
        "email": None,
        "addressLine1": None,
        "addressLine2": None,
        "city": None,
        "stateName": source.get("stateName"),
        "stateCode": source.get("stateCode"),
        "postalCode": None,
        "countryCode": source.get("countryCode") or "IN",
        "customerType": source.get("customerType") or "individual",
        "anonymized": True,
    }


async def _ensure_archive_tenant(conn) -> uuid.UUID:
    """Create the archive tenant once, tolerating two deletions racing."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from server.db.models.entities import Tenant

    await conn.execute(
        pg_insert(Tenant.__table__)
        .values(
            tenant_id=ARCHIVE_TENANT_ID,
            name=ARCHIVE_TENANT_NAME,
            plan="archive",
            status="active",
            billing_source="archive",
            limits={},
        )
        .on_conflict_do_nothing(index_elements=["tenant_id"])
    )
    return ARCHIVE_TENANT_ID


async def archive_billing_records(conn, tenant_id: uuid.UUID) -> dict[str, int]:
    """Move retained financial rows off a tenant that is about to be deleted.

    Runs on the same connection/transaction as the tenant deletion, so either
    the records are archived and the workspace goes, or nothing changes.
    """
    from server.db.models.saas_models import (
        BillingInvoice,
        BillingWalletTransaction,
        CreditNote,
        RazorpayOrder,
        RazorpayRefund,
        TenantBillingProfile,
    )

    archive_id = await _ensure_archive_tenant(conn)
    counts: dict[str, int] = {}

    invoice_rows = (
        await conn.execute(
            select(BillingInvoice.invoice_id, BillingInvoice.buyer_snapshot).where(
                BillingInvoice.tenant_id == tenant_id
            )
        )
    ).all()
    for row in invoice_rows:
        await conn.execute(
            update(BillingInvoice)
            .where(BillingInvoice.invoice_id == row.invoice_id)
            .values(
                tenant_id=archive_id,
                buyer_snapshot=anonymize_buyer_snapshot(row.buyer_snapshot),
            )
        )
    counts["invoices"] = len(invoice_rows)

    note_rows = (
        await conn.execute(
            select(CreditNote.credit_note_id, CreditNote.buyer_snapshot).where(
                CreditNote.tenant_id == tenant_id
            )
        )
    ).all()
    for row in note_rows:
        await conn.execute(
            update(CreditNote)
            .where(CreditNote.credit_note_id == row.credit_note_id)
            .values(
                tenant_id=archive_id,
                buyer_snapshot=anonymize_buyer_snapshot(row.buyer_snapshot),
                created_by=None,
            )
        )
    counts["credit_notes"] = len(note_rows)

    order_rows = (
        await conn.execute(
            select(RazorpayOrder.order_id, RazorpayOrder.buyer_snapshot).where(
                RazorpayOrder.tenant_id == tenant_id
            )
        )
    ).all()
    for row in order_rows:
        await conn.execute(
            update(RazorpayOrder)
            .where(RazorpayOrder.order_id == row.order_id)
            .values(
                tenant_id=archive_id,
                buyer_snapshot=anonymize_buyer_snapshot(row.buyer_snapshot),
            )
        )
    counts["orders"] = len(order_rows)

    refund_res = await conn.execute(
        update(RazorpayRefund)
        .where(RazorpayRefund.tenant_id == tenant_id)
        .values(tenant_id=archive_id, created_by=None)
    )
    counts["refunds"] = refund_res.rowcount or 0

    tx_res = await conn.execute(
        update(BillingWalletTransaction)
        .where(BillingWalletTransaction.tenant_id == tenant_id)
        .values(tenant_id=archive_id, user_id=None)
    )
    counts["wallet_transactions"] = tx_res.rowcount or 0

    await conn.execute(
        TenantBillingProfile.__table__.delete().where(TenantBillingProfile.tenant_id == tenant_id)
    )

    return counts


async def anonymize_retained_documents(session, tenant_id: uuid.UUID) -> dict[str, int]:
    """Erase buyer identity on documents kept under a soft-deleted tenant.

    Used by the teardown worker, which leaves the tenant row in place. Idempotent:
    a snapshot that is already anonymized is rewritten with the same values.
    """
    from server.db.models.saas_models import (
        BillingInvoice,
        CreditNote,
        RazorpayOrder,
        TenantBillingProfile,
    )

    counts: dict[str, int] = {}

    invoices = (
        await session.execute(select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id))
    ).scalars().all()
    for invoice in invoices:
        invoice.buyer_snapshot = anonymize_buyer_snapshot(invoice.buyer_snapshot)
    counts["invoices"] = len(invoices)

    notes = (
        await session.execute(select(CreditNote).where(CreditNote.tenant_id == tenant_id))
    ).scalars().all()
    for note in notes:
        note.buyer_snapshot = anonymize_buyer_snapshot(note.buyer_snapshot)
        note.created_by = None
    counts["credit_notes"] = len(notes)

    orders = (
        await session.execute(select(RazorpayOrder).where(RazorpayOrder.tenant_id == tenant_id))
    ).scalars().all()
    for order in orders:
        order.buyer_snapshot = anonymize_buyer_snapshot(order.buyer_snapshot)
    counts["orders"] = len(orders)

    profile = await session.get(TenantBillingProfile, tenant_id)
    if profile is not None:
        await session.delete(profile)
        counts["billing_profile"] = 1

    return counts
