"""Wallet minimum balance + PSTN debit idempotency."""
from __future__ import annotations

import pytest

from server.services.saas.billing_wallet_service import bill_pstn_call_if_applicable


@pytest.mark.asyncio
async def test_bill_pstn_noop_without_call():
    await bill_pstn_call_if_applicable("00000000-0000-0000-0000-000000000099")
