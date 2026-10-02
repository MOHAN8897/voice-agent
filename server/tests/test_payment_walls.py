"""Payment walls: the rules that decide whether money moves.

Two things must hold, and they pull in opposite directions:
  * an unfunded workspace must not be able to dial, or have its calls answered;
  * no configuration or database fault may ever stop a funded workspace from
    receiving calls.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from server.config.env import get_settings
from server.services.saas import billing_wallet_service as bws


class FakeWallet:
    def __init__(self, *, cents: int = 0, paise: int = 0, currency: str = "usd"):
        self.balance_cents = cents
        self.balance_inr_paise = paise
        self.currency = currency
        self.tenant_id = uuid.uuid4()
        self.updated_at = None


@pytest.fixture(autouse=True)
def _saas_on(monkeypatch):
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _use_wallet(monkeypatch, wallet: FakeWallet):
    monkeypatch.setattr(bws, "get_or_create_wallet", lambda _tenant: _async(wallet))


async def _async(value):
    return value


# --------------------------------------------------------------------------
# Balance minimum
# --------------------------------------------------------------------------


async def test_outbound_blocked_below_minimum(monkeypatch):
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=0, currency="usd"))
    with pytest.raises(HTTPException) as exc:
        await bws.assert_wallet_allows_pstn(uuid.uuid4())
    assert exc.value.status_code == 402
    assert exc.value.detail["error"]["code"] == "insufficient_balance"


async def test_outbound_allowed_above_minimum(monkeypatch):
    _use_wallet(monkeypatch, FakeWallet(cents=500, paise=0, currency="usd"))
    await bws.assert_wallet_allows_pstn(uuid.uuid4())


async def test_inr_wallet_uses_the_inr_minimum(monkeypatch):
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=6000, currency="inr"))
    await bws.assert_wallet_allows_pstn(uuid.uuid4())


async def test_razorpay_inr_credit_counts_even_if_currency_still_usd(monkeypatch):
    """Razorpay used to leave currency=usd while only balance_inr_paise grew."""
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=6000, currency="usd"))
    await bws.assert_wallet_allows_pstn(uuid.uuid4())
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is True


async def test_no_wall_when_saas_auth_is_off(monkeypatch):
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=0))
    await bws.assert_wallet_allows_pstn(uuid.uuid4())
    # Inbound must also stay open when billing is not in play.
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is True


# --------------------------------------------------------------------------
# Inbound wall
# --------------------------------------------------------------------------


async def test_inbound_blocked_when_wallet_is_empty(monkeypatch):
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=0, currency="usd"))
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is False


async def test_inbound_allowed_when_funded(monkeypatch):
    _use_wallet(monkeypatch, FakeWallet(cents=500, paise=0, currency="usd"))
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is True


async def test_inbound_fails_open_on_a_database_error(monkeypatch):
    """A DB fault must never drop a live call — answering is the safe default."""
    get_settings.cache_clear()

    async def _boom(_tenant):
        raise RuntimeError("database is down")

    monkeypatch.setattr(bws, "get_or_create_wallet", _boom)
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is True


async def test_inbound_fails_open_for_an_unknown_tenant(monkeypatch):
    assert await bws.wallet_allows_inbound(None) is True


async def test_inbound_wall_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("PSTN_ENFORCE_WALLET_ON_INBOUND", "false")
    get_settings.cache_clear()
    _use_wallet(monkeypatch, FakeWallet(cents=0, paise=0))
    assert await bws.wallet_allows_inbound(uuid.uuid4()) is True


# --------------------------------------------------------------------------
# Top-up bounds
# --------------------------------------------------------------------------


def test_three_dollar_topup_is_allowed(monkeypatch):
    """$3 is the smallest payment a workspace may make."""
    assert get_settings().topup_min_usd == 3.0


def test_topup_catalog_reports_the_server_price():
    from server.routes.app_billing import billing_catalog
    import asyncio

    catalog = asyncio.run(billing_catalog())
    assert catalog["topupMinUsd"] == 3.0
    assert catalog["topupMaxUsd"] == 500.0
    # A phone number is $4 per month, and the console must quote this value.
    assert catalog["numberSkus"][0]["monthlyCents"] == 400
    assert catalog["rates"]["numberMonthlyUsd"] == 4.0
    assert catalog["rates"]["minBalanceUsd"] == 0.5


def test_topup_body_allows_three_dollars():
    from server.routes.app_billing import TopupBody

    assert TopupBody(amountUsd=3).amountUsd == 3
    with pytest.raises(Exception):
        TopupBody(amountUsd=2.99)
    with pytest.raises(Exception):
        TopupBody(amountUsd=501)


# --------------------------------------------------------------------------
# Number purchase charging
# --------------------------------------------------------------------------


def _fake_session(wallet: FakeWallet, existing_refs: set[str] | None = None):
    """Minimal AsyncSession stand-in over one wallet row."""
    refs = existing_refs or set()
    added = []

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, _model, _pk):
            return wallet

        async def execute(self, stmt, *args, **kwargs):
            # The duplicate check is a bound-parameter equality, so read the value
            # the same way SQLAlchemy would rather than guessing from the kwargs.
            bound = list(stmt.compile().params.values())
            ref = bound[0] if bound else None
            return _Result("dup" if ref in refs else None)

        def add(self, row):
            added.append(row)

        async def commit(self):
            return None

        async def flush(self):
            return None

    return _Session(), added


def _use_session(monkeypatch, session, factory_returned=None):
    class _Factory:
        def __call__(self):
            return session

    monkeypatch.setattr(bws, "get_session_factory", lambda: _Factory())


@pytest.fixture(autouse=True)
def _pinned_number_price(monkeypatch):
    """Pin the number rental for these tests.

    The price is admin-configurable at runtime, so a literal assertion would fail
    whenever someone changes it in the panel — which is exactly what these tests
    are meant to catch. Pin it and assert against the pin.
    """
    from server.services.saas import billing_rates

    monkeypatch.setattr(
        billing_rates,
        "effective_rates",
        lambda: {
            "did_monthly_usd_cents": 400,
            "pstn_rate_usd_cents_per_min": 9,
            "web_agent_rate_usd_cents_per_min": 7,
            "fx_rate_inr": 95.64,
        },
    )
    monkeypatch.setattr(
        billing_rates,
        "rates_with_derived_inr",
        lambda: {
            "did_monthly_usd_cents": 400,
            "did_monthly_inr_paise": 38256,
            "pstn_rate_usd_cents_per_min": 9,
            "pstn_rate_inr_paise_per_min": 861,
            "web_agent_rate_usd_cents_per_min": 7,
            "web_agent_rate_inr_paise_per_min": 669,
            "fx_rate_inr": 95.64,
        },
    )
    return 400


async def test_number_purchase_charges_usd_when_usd_is_funded(monkeypatch):
    wallet = FakeWallet(cents=1000, paise=0, currency="usd")
    session, added = _fake_session(wallet)
    _use_session(monkeypatch, session)

    result = await bws.debit_did_purchase(
        uuid.uuid4(), user_id=uuid.uuid4(), e164="+14155552671", purchase_id=uuid.uuid4()
    )
    assert result["amountCents"] == 400
    assert result["amountInrPaise"] == 0
    assert wallet.balance_cents == 600
    assert len(added) == 1  # exactly one ledger row


async def test_number_purchase_charges_inr_when_inr_is_funded(monkeypatch):
    # The INR charge is the derived mirror of the USD price ($4.00 at the
    # configured FX), not an independently stored rupee figure — a rupee price
    # authored separately would drift from the dollar price it mirrors.
    from server.services.saas.billing_rates import rates_with_derived_inr

    want_paise = int(rates_with_derived_inr()["did_monthly_inr_paise"])
    wallet = FakeWallet(cents=0, paise=want_paise + 10000, currency="inr")
    session, added = _fake_session(wallet)
    _use_session(monkeypatch, session)

    result = await bws.debit_did_purchase(
        uuid.uuid4(), user_id=uuid.uuid4(), e164="+14155552671", purchase_id=uuid.uuid4()
    )
    assert result["amountInrPaise"] == want_paise
    assert result["amountCents"] == 0
    assert wallet.balance_inr_paise == 10000
    assert wallet.currency == "inr"


async def test_number_purchase_falls_back_to_the_other_currency(monkeypatch):
    """A workspace funded only in USD must still be able to buy."""
    wallet = FakeWallet(cents=1000, paise=0, currency="inr")
    session, _ = _fake_session(wallet)
    _use_session(monkeypatch, session)

    result = await bws.debit_did_purchase(
        uuid.uuid4(), user_id=uuid.uuid4(), e164="+14155552671", purchase_id=uuid.uuid4()
    )
    assert result["amountCents"] == 400
    assert wallet.balance_cents == 600


async def test_number_purchase_refused_when_either_leg_is_short(monkeypatch):
    wallet = FakeWallet(cents=100, paise=100, currency="usd")
    session, _ = _fake_session(wallet)
    _use_session(monkeypatch, session)

    with pytest.raises(HTTPException) as exc:
        await bws.debit_did_purchase(
            uuid.uuid4(), user_id=uuid.uuid4(), e164="+14155552671", purchase_id=uuid.uuid4()
        )
    assert exc.value.status_code == 402
    assert exc.value.detail["error"]["code"] == "insufficient_balance"
    # The message must state the price so the console can show it.
    assert "$4.00" in exc.value.detail["error"]["message"]


async def test_number_purchase_is_idempotent(monkeypatch):
    """A retried purchase must not charge twice."""
    wallet = FakeWallet(cents=1000, paise=0, currency="usd")
    session, added = _fake_session(wallet, existing_refs={"did:fixed"})
    _use_session(monkeypatch, session)

    result = await bws.debit_did_purchase(
        uuid.uuid4(), user_id=uuid.uuid4(), e164="+14155552671", purchase_id="fixed"
    )
    assert result["duplicate"] is True
    assert result["amountCents"] == 0
    assert wallet.balance_cents == 1000  # untouched
    assert added == []


# --------------------------------------------------------------------------
# Refunds must reverse exactly what was charged
# --------------------------------------------------------------------------


class _RefundSession:
    """Session holding one existing wallet and one existing debit row."""

    def __init__(self, wallet: FakeWallet, debits: dict[str, object]):
        self.wallet = wallet
        self.debits = debits
        self.added: list[object] = []

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, _model, _pk):
        return self.wallet

    async def execute(self, stmt, *args, **kwargs):
        bound = list(stmt.compile().params.values())
        ref = bound[0] if bound else None
        return self._Result(self.debits.get(ref))

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None

    async def flush(self):
        return None


def _use_refund_session(monkeypatch, session):
    class _Factory:
        def __call__(self):
            return session

    monkeypatch.setattr(bws, "get_session_factory", lambda: _Factory())


async def test_refund_returns_only_the_currency_that_was_charged(monkeypatch):
    """A failed purchase must give back exactly what it took — no more.

    A purchase debits a single currency leg. Refunding both would credit money
    that was never collected.
    """
    wallet = FakeWallet(cents=0, paise=50000, currency="inr")
    purchase_id = "p1"
    debit = type(
        "Debit",
        (),
        {
            "amount_cents": 0,
            "amount_inr_paise": -50000,
            "user_id": None,
        },
    )()
    session = _RefundSession(wallet, {f"did:{purchase_id}": debit})
    _use_refund_session(monkeypatch, session)

    result = await bws.refund_did_purchase(
        wallet.tenant_id, user_id=None, purchase_id=purchase_id
    )
    assert result["ok"] is True
    assert result["amountCents"] == 0
    assert result["amountInrPaise"] == 50000
    assert wallet.balance_inr_paise == 100000
    # The phantom-currency bug: USD must stay at zero.
    assert wallet.balance_cents == 0


async def test_refund_does_not_use_the_current_price(monkeypatch):
    """A price change between purchase and refund must not alter the refund."""
    wallet = FakeWallet(cents=600, paise=0, currency="usd")
    purchase_id = "p2"
    debit = type(
        "Debit",
        (),
        {"amount_cents": -300, "amount_inr_paise": 0, "user_id": None},
    )()
    session = _RefundSession(wallet, {f"did:{purchase_id}": debit})
    _use_refund_session(monkeypatch, session)

    result = await bws.refund_did_purchase(
        wallet.tenant_id, user_id=None, purchase_id=purchase_id
    )
    # Charged $3.00, so the refund is $3.00 even though a number now costs $4.00.
    assert result["amountCents"] == 300
    assert wallet.balance_cents == 900


async def test_refund_without_an_original_debit_credits_nothing(monkeypatch):
    """Never credit a refund when there is no matching charge."""
    wallet = FakeWallet(cents=100, paise=200, currency="usd")
    session = _RefundSession(wallet, {})
    _use_refund_session(monkeypatch, session)

    result = await bws.refund_did_purchase(
        wallet.tenant_id, user_id=None, purchase_id="missing"
    )
    assert result["ok"] is False
    assert wallet.balance_cents == 100
    assert wallet.balance_inr_paise == 200
    assert session.added == []


async def test_refund_is_idempotent(monkeypatch):
    """A retried refund must not credit twice."""
    wallet = FakeWallet(cents=0, paise=50000, currency="inr")
    purchase_id = "p3"
    debit = type(
        "Debit",
        (),
        {"amount_cents": 0, "amount_inr_paise": -50000, "user_id": None},
    )()
    existing_refund = type("Refund", (), {"amount_cents": 50000, "amount_inr_paise": 50000})()
    session = _RefundSession(
        wallet, {f"did:{purchase_id}": debit, f"did_refund:{purchase_id}": existing_refund}
    )
    _use_refund_session(monkeypatch, session)

    result = await bws.refund_did_purchase(
        wallet.tenant_id, user_id=None, purchase_id=purchase_id
    )
    assert result["duplicate"] is True
    assert wallet.balance_inr_paise == 50000  # unchanged
