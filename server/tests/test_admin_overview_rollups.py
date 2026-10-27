import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY

from server.tests.test_integration_security_hardening import AID, FOREIGN, OTHER, TID
from server.tests.test_integration_security_hardening import db as shared_db

db = shared_db


@pytest.mark.asyncio
async def test_overview_excludes_practice_fills_days_and_keeps_both_currencies(db, monkeypatch):
    from server.db.models.entities import Base, Call, CallAttempt, Tenant
    from server.db.models.phase5_models import PhoneNumber
    from server.db.models.saas_models import (
        BillingWallet,
        BillingWalletTransaction,
        NumberPurchase,
        User,
    )
    from server.routes import dev_admin

    models = [Call, CallAttempt, BillingWallet, BillingWalletTransaction, NumberPurchase, User, PhoneNumber]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    now = datetime.now(timezone.utc)
    async with db() as session:
        for tenant in (await session.execute(select(Tenant))).scalars():
            tenant.name = "Same display name"
        session.add_all([
            Call(call_id=uuid.uuid4(), tenant_id=TID, agent_id=AID, combination_id="test", storage_path="synthetic",
                 channel="pstn", started_at=now, duration_sec=10, is_test=False, status="completed"),
            Call(call_id=uuid.uuid4(), tenant_id=OTHER, agent_id=FOREIGN, combination_id="test", storage_path="synthetic",
                 channel="pstn", started_at=now, duration_sec=20, is_test=False, status="completed"),
            Call(call_id=uuid.uuid4(), tenant_id=TID, agent_id=AID, combination_id="test", storage_path="synthetic",
                 channel="browser", started_at=now, duration_sec=9999, is_test=True, status="completed"),
            Call(call_id=uuid.uuid4(), tenant_id=TID, agent_id=AID, combination_id="test", storage_path="synthetic",
                 channel="pstn", started_at=now + timedelta(days=1), duration_sec=8888, is_test=False, status="completed"),
            BillingWallet(tenant_id=TID, balance_cents=500, balance_inr_paise=12300),
            BillingWalletTransaction(tenant_id=TID, amount_cents=200, amount_inr_paise=10000, kind="topup", created_at=now),
            BillingWalletTransaction(tenant_id=TID, amount_cents=999, amount_inr_paise=99900, kind="topup", created_at=now + timedelta(days=1)),
        ])
        await session.commit()
    monkeypatch.setattr(dev_admin, "get_session_factory", lambda: db)
    result = await dev_admin.admin_analytics(days=7, session=SimpleNamespace(role="developer", subject="test", kind="dev"))
    assert result["totals"]["calls"] == 2 and result["totals"]["seconds"] == 30
    assert result["totals"]["walletBalanceCents"] == 500
    assert result["totals"]["walletBalanceInrPaise"] == 12300
    assert len(result["callsByDay"]) == 7
    assert sum(row["calls"] for row in result["callsByDay"]) == 2
    assert len(result["topTenantsByCalls"]) == 2
    assert result["callsByStatus"] == {"completed": 2}
    assert result["topUpsByDay"][0]["inrPaise"] == 10000
    assert len(result["topUpsByDay"]) == 1
