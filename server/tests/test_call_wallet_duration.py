"""Tests verifying FIN-01: In-flight wallet balance duration cap and watchdog."""
from __future__ import annotations

import uuid
import pytest

from server.config.env import get_settings
from server.services.saas import billing_wallet_service as bws
from server.services.saas.billing_wallet_service import (
    max_allowed_call_duration_sec,
)


class FakeWallet:
    def __init__(self, *, cents: int = 0, paise: int = 0):
        self.balance_cents = cents
        self.balance_inr_paise = paise
        self.tenant_id = uuid.uuid4()


@pytest.fixture(autouse=True)
def _saas_on(monkeypatch):
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "true")
    monkeypatch.setenv("PSTN_RATE_USD_CENTS_PER_MIN", "15")  # 15 cents/min = 0.25 cents/sec
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_max_allowed_duration_derived_from_wallet_balance(monkeypatch):
    """FIN-01: Max duration must be bounded by wallet funds, not hardcoded to 900s."""
    tenant_id = uuid.uuid4()

    # 30 cents at 15 cents/min allows 2 minutes = 120 seconds
    wallet_120s = FakeWallet(cents=30, paise=0)
    monkeypatch.setattr(bws, "get_or_create_wallet", lambda _tid: _async(wallet_120s))

    dur_sec = await max_allowed_call_duration_sec(tenant_id, channel="pstn", global_cap_sec=900)
    assert dur_sec == 120, f"Expected 120s from $0.30 balance, got {dur_sec}"

    # Wallet with large balance ($10.00) caps at global 900s
    wallet_rich = FakeWallet(cents=1000, paise=0)
    monkeypatch.setattr(bws, "get_or_create_wallet", lambda _tid: _async(wallet_rich))
    dur_rich = await max_allowed_call_duration_sec(tenant_id, channel="pstn", global_cap_sec=900)
    assert dur_rich == 900


@pytest.mark.asyncio
async def test_call_lifecycle_attaches_wallet_duration_and_cleans_watchdog(monkeypatch):
    """FIN-01: Call lifecycle sets ctx.max_duration_sec and manages watchdog lifecycle."""
    from server.call.call_lifecycle_service import call_lifecycle_service, _max_duration_tasks
    from server.call.call_context import get as get_ctx
    from server.brain.agent_service import agent_service

    tenant_id = uuid.uuid4()
    agent_id = str(uuid.uuid4())
    wallet = FakeWallet(cents=30, paise=0)
    monkeypatch.setattr(bws, "get_or_create_wallet", lambda _tid: _async(wallet))
    monkeypatch.setattr(
        agent_service,
        "get_agent",
        lambda _aid: _async(
            {
                "agent_id": agent_id,
                "tenant_id": str(tenant_id),
                "languages": ["te-IN"],
                "default_tier": "medium",
            }
        ),
    )

    res = await call_lifecycle_service.start(agent_id=agent_id, session_id="test-dur-sess", channel="pstn")
    call_id = res["call_id"]
    ctx = get_ctx(call_id)
    assert ctx is not None
    assert ctx.max_duration_sec == 120
    assert call_id in _max_duration_tasks
    assert not _max_duration_tasks[call_id].done()

    await call_lifecycle_service.end(call_id, reason="user_stop")
    assert call_id not in _max_duration_tasks


async def _async(val):
    return val
