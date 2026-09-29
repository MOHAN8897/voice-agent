"""Reverse wallet rows created by the double-currency refund bug.

`refund_did_purchase` used to credit both the USD and INR legs even though a
purchase only ever debited one, so a failed provisioning run minted money. This
removes those phantom credits by pairing each `did_refund` with its `did_purchase`
and crediting back only what the refund added beyond the original debit.

Safe to re-run: it only touches refunds that exceed their matching debit.
"""
from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

from server.db.connection import get_session_factory, init_db  # noqa: E402
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction  # noqa: E402


async def main() -> int:
    if not await init_db():
        print("DATABASE_URL is not configured")
        return 2
    factory = get_session_factory()
    assert factory is not None

    fixed = 0
    async with factory() as session:
        refunds = (
            await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.kind == "did_refund"
                )
            )
        ).scalars().all()

        for refund in refunds:
            purchase_ref = str(refund.reference_id or "").replace("did_refund:", "did:")
            original = (
                await session.execute(
                    select(BillingWalletTransaction).where(
                        BillingWalletTransaction.reference_id == purchase_ref
                    )
                )
            ).scalar_one_or_none()
            if original is None:
                continue
            credited_cents = int(refund.amount_cents or 0)
            credited_paise = int(refund.amount_inr_paise or 0)
            should_cents = abs(int(original.amount_cents or 0))
            should_paise = abs(int(original.amount_inr_paise or 0))
            excess_cents = credited_cents - should_cents
            excess_paise = credited_paise - should_paise
            if excess_cents <= 0 and excess_paise <= 0:
                continue

            wallet = await session.get(BillingWallet, refund.tenant_id)
            if wallet is None:
                continue
            # Take back only the amount that was created from nothing.
            wallet.balance_cents = int(wallet.balance_cents or 0) - excess_cents
            wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) - excess_paise
            refund.amount_cents = should_cents
            refund.amount_inr_paise = should_paise
            print(
                f"purchase {purchase_ref}: removed {excess_cents} cents / "
                f"{excess_paise} paise of phantom credit"
            )
            fixed += 1

        if fixed:
            await session.commit()
            print(f"\nrepaired {fixed} refund row(s)")
        else:
            print("no phantom refunds found — nothing to repair")

        totals = (
            await session.execute(
                select(
                    BillingWallet.tenant_id,
                    BillingWallet.balance_cents,
                    BillingWallet.balance_inr_paise,
                )
            )
        ).all()
        print("\ncurrent wallets:")
        for tenant_id, cents, paise in totals:
            print(f"  {tenant_id}  ${(cents or 0) / 100:.2f}  INR {(paise or 0) / 100:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
