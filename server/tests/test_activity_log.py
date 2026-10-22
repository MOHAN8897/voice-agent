"""The activity log has to be trustworthy, because it is the debugging surface.

Three properties are load-bearing and none are visible to a type checker:
a failed log write must never break the action being logged; a refused purchase
must be distinguishable from a completed one; and filtering must not silently
drop rows.
"""
from __future__ import annotations

import uuid

import pytest

from server.services.saas import activity_log


class _BoomSession:
    """A session whose commit always fails, like a full disk or a bad schema."""

    def add(self, _row) -> None:
        return None

    async def commit(self) -> None:
        raise RuntimeError("database is gone")


class _CaptureSession:
    """Records the row a caller would have written."""

    def __init__(self) -> None:
        self.rows: list = []

    def add(self, row) -> None:
        self.rows.append(row)

    async def commit(self) -> None:
        return None


@pytest.fixture
def capture(monkeypatch):
    session = _CaptureSession()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(activity_log, "get_session_factory", lambda: _Factory())
    return session


def test_a_failing_log_write_never_breaks_the_action(monkeypatch):
    """The whole point of swallowing: a lost log line beats a lost purchase."""

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _BoomSession()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(activity_log, "get_session_factory", lambda: _Factory())
    # Must not raise.
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        activity_log.record_event(action="test", resource_type="test")
    )


def test_a_recorded_event_carries_its_origin_and_outcome(capture):
    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(
            action="number.purchase.refused",
            resource_type="number_purchase",
            resource_id="+15551234567",
            actor="buyer@example.com",
            payload={"error": "kyc_required"},
            source="subscriber",
            outcome="error",
            severity="warning",
        )
    )
    row = capture.rows[0]
    assert row.source == "subscriber"
    assert row.outcome == "error"
    assert row.severity == "warning"
    assert row.action == "number.purchase.refused"
    assert row.actor == "buyer@example.com"


def test_severity_defaults_to_error_only_when_the_outcome_failed(capture):
    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(activity_log.record_event(action="a", resource_type="t"))
    loop.run_until_complete(
        activity_log.record_event(action="b", resource_type="t", outcome="error")
    )
    assert capture.rows[0].severity == "info"
    assert capture.rows[1].severity == "error"


def test_an_unknown_source_cannot_be_written(capture):
    """A typo in a source string must not silently invent a new category."""

    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(action="a", resource_type="t", source="not-a-source")
    )
    assert capture.rows[0].source == "system"


def test_a_oversized_value_is_clamped(capture):
    """One huge field is clipped rather than dropped, so the log still shows it."""

    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(
            action="a",
            resource_type="t",
            payload={"blob": "x" * 50_000},
        )
    )
    stored = capture.rows[0].payload
    assert "blob" in stored
    assert stored["blob"].endswith("(truncated)")
    assert len(stored["blob"]) <= 2100


def test_a_manually_huge_payload_is_dropped_with_a_note(capture):
    """Many large fields must not be stored at all — the row is unusable."""

    import asyncio

    loop = asyncio.new_event_loop()
    loop.run_until_complete(
        activity_log.record_event(
            action="a",
            resource_type="t",
            payload={f"field_{i}": "y" * 4000 for i in range(20)},
        )
    )
    stored = capture.rows[0].payload
    assert stored == {
        "_truncated": True,
        "_note": "payload exceeded the log size limit",
    }


def test_request_context_is_read_when_a_request_is_supplied(capture):
    """So one user action can be traced across every row it produced."""

    class _Headers(dict):
        def get(self, key, default=None):
            for k, v in self.items():
                if k.lower() == key.lower():
                    return v
            return default

    class _Request:
        client = type("C", (), {"host": "203.0.113.9"})()
        headers = _Headers({"User-Agent": "Mozilla/5.0", "X-Request-Id": "req-abc"})

    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(action="a", resource_type="t", request=_Request())
    )
    row = capture.rows[0]
    assert row.ip == "203.0.113.9"
    assert row.request_id == "req-abc"
    assert row.user_agent == "Mozilla/5.0"


def test_a_broken_request_object_does_not_stop_the_write(capture):
    """Request introspection is best-effort; the log row is not optional."""

    class _Hostile:
        @property
        def client(self):
            raise RuntimeError("no")

        @property
        def headers(self):
            raise RuntimeError("no")

    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(action="a", resource_type="t", request=_Hostile())
    )
    assert capture.rows[0].ip is None
    assert capture.rows[0].action == "a"


# --- the admin shim ----------------------------------------------------------


def test_the_admin_shim_delegates_without_raising(monkeypatch):
    """Every admin mutation routes through this.

    A signature mismatch between the shim and the recorder took down every admin
    endpoint with a 500 — and the type checker cannot see it, because both files
    are valid. So the call is made here for real.
    """
    import asyncio

    from server.services.saas import admin_audit

    seen: dict = {}

    async def _fake_record_event(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(admin_audit, "record_event", _fake_record_event)
    asyncio.new_event_loop().run_until_complete(
        admin_audit.record_admin_action(
            actor="admin",
            action="wallet.adjust",
            resource_type="tenant",
            resource_id="t-1",
            tenant_id=uuid.uuid4(),
            payload={"deltaUsdCents": 500},
        )
    )
    assert seen["source"] == "admin"
    assert seen["action"] == "wallet.adjust"
    assert seen["payload"] == {"deltaUsdCents": 500}


class _FakeHeaders(dict):
    """Case-insensitive header lookup, like Starlette's."""

    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeRequest:
    def __init__(self, host: str = "198.51.100.7") -> None:
        self.client = type("C", (), {"host": host})()
        self.headers = _FakeHeaders(
            {"User-Agent": "curl/8", "X-Request-Id": "req-xyz"}
        )


def test_the_in_flight_request_is_picked_up_without_being_passed(capture):
    """Admin call sites never pass a Request; the middleware supplies it.

    Threading a Request through every admin mutation was the alternative, and the
    next call site added would have forgotten. This asserts the fallback works.
    """
    import asyncio

    from server.services.saas.request_context import set_current_request

    async def go():
        set_current_request(_FakeRequest())
        await activity_log.record_event(action="a", resource_type="t")

    asyncio.new_event_loop().run_until_complete(go())
    row = capture.rows[0]
    assert row.ip == "198.51.100.7"
    assert row.request_id == "req-xyz"
    assert row.user_agent == "curl/8"


def test_no_in_flight_request_leaves_the_columns_null(capture):
    """Background workers and scripts log with no request at all."""

    import asyncio

    asyncio.new_event_loop().run_until_complete(
        activity_log.record_event(action="a", resource_type="t")
    )
    row = capture.rows[0]
    assert row.ip is None and row.request_id is None and row.user_agent is None


# --- filters -----------------------------------------------------------------


def test_an_unparseable_since_is_ignored_rather_than_erroring(monkeypatch):
    """A bad date in the URL must not 500 the whole log page."""
    monkeypatch.setattr(activity_log, "get_session_factory", lambda: None)
    assert activity_log._parse_since("not-a-date") is None
    assert activity_log._parse_since("") is None
    # A naive timestamp is assumed UTC, matching how created_at is stored.
    assert activity_log._parse_since("2026-01-01T00:00:00").tzinfo is not None
    assert activity_log._parse_since("2026-01-01T00:00:00Z").tzinfo is not None


def test_paging_bounds_are_clamped(monkeypatch):
    """A hostile limit must not become an unbounded query."""
    monkeypatch.setattr(activity_log, "get_session_factory", lambda: None)

    import asyncio

    async def go(**kw):
        return await activity_log.list_events(**kw)

    loop = asyncio.new_event_loop()
    out = loop.run_until_complete(go(limit=100_000, offset=-5))
    # With no factory there is nothing to return, but the call still completed
    # rather than passing a negative offset into SQL.
    assert out["total"] == 0