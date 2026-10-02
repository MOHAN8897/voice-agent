"""Callbacks: the missed-caller re-dial must go through the real outbound path.

The point of these tests is that a callback is not a shortcut around the existing
guards — it goes through ``subscriber_outbound``, so the published-brain check,
wallet balance, caller-id resolution and concurrency cap all still apply.
"""
from __future__ import annotations

import uuid

import pytest

from server.services.saas import call_callback_service as svc
from server.services.saas.tenant_guard import SubscriberPrincipal


async def _approved(_principal, *, action: str) -> None:
    """Stand-in for a passed KYC gate, for tests that are not about the gate."""
    return None


@pytest.fixture
def principal():
    return SubscriberPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="customer_admin",
        email="owner@example.com",
    )


# --------------------------------------------------------------------------
# E.164 normalisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+919999999999", "+919999999999"),
        ("+1 415 555 2671", "+14155552671"),
        ("+1-415-555-2671", "+14155552671"),
        ("0091 99999 99999", "+919999999999"),
        ("9999999999", "+919999999999"),
        # A bare 10-digit number without a country code defaults to India, which
        # is this product's default. Use a full E.164 for other countries.
        ("(415) 555-2671", "+914155552671"),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_normalize_e164(raw, expected):
    assert svc.normalize_e164(raw) == expected


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------


async def test_callback_rejects_a_foreign_call(principal, monkeypatch):
    """A call id outside the caller's workspace must be a 404, not a dial."""
    dialled = []

    async def _never(*_a, **_k):
        dialled.append(True)
        raise AssertionError("must not dial a call from another tenant")

    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", _never)

    async def _resolve(*_a, **_k):
        raise HTTPError404()

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(principal, call_id=str(uuid.uuid4()))
    assert exc.value.status_code == 404
    assert not dialled


def HTTPError404():
    from fastapi import HTTPException

    return HTTPException(
        status_code=404, detail={"error": {"code": "not_found", "message": "Call not found"}}
    )


async def test_callback_requires_an_agent(principal, monkeypatch):
    from fastapi import HTTPException

    async def _resolve(*_a, **_k):
        return "+919999999999", None, "attempt"

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(principal, call_id=str(uuid.uuid4()))
    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "invalid_agent"


async def test_callback_rejects_an_unknown_mode(principal):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(principal, call_id=str(uuid.uuid4()), to_e164="+919999999999", mode="telepathy")
    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "invalid_mode"


# --------------------------------------------------------------------------
# It reuses the real outbound path
# --------------------------------------------------------------------------


async def test_callback_delegates_to_subscriber_outbound(principal, monkeypatch):
    seen = {}

    async def _fake_outbound(princ, *, agent_id, from_e164, to_e164, dial_request_id=None):
        seen["principal"] = princ
        seen["agent_id"] = agent_id
        seen["to"] = to_e164
        seen["from"] = from_e164
        seen["dial_request_id"] = dial_request_id
        return {"ok": True, "provider": "telnyx", "call_control_id": "cc-123"}

    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", _fake_outbound)

    async def _resolve(*_a, **_k):
        return "+919999999999", None, "attempt"

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _fake_agent)

    result = await svc.request_callback(
        principal, call_id=str(uuid.uuid4()), to_e164="+919999999999", agent_id=str(uuid.uuid4())
    )
    assert result["ok"] is True
    assert result["toE164"] == "+919999999999"
    assert result["callControlId"] == "cc-123"
    # The caller's own principal is threaded through, so every guard applies.
    assert seen["principal"].tenant_id == principal.tenant_id
    assert seen["dial_request_id"]


async def test_callback_surfaces_a_dial_failure_without_raising(principal, monkeypatch):
    async def _fake_outbound(*_a, **_k):
        return {"ok": False, "error": "Agent not published", "code": "brain_not_published"}

    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", _fake_outbound)

    async def _resolve(*_a, **_k):
        return "+919999999999", None, "attempt"

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _fake_agent)

    result = await svc.request_callback(
        principal, call_id=str(uuid.uuid4()), to_e164="+919999999999", agent_id=str(uuid.uuid4())
    )
    assert result["ok"] is False
    assert result["error"] == "Agent not published"
    assert result["code"] == "brain_not_published"


async def test_unknown_agent_is_a_clean_404_not_a_500(principal, monkeypatch):
    """A stale agent id must never leak an unhandled KeyError as a 500."""
    from fastapi import HTTPException

    async def _missing(agent_id, tenant_id=None):
        raise KeyError(agent_id)

    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _missing)

    async def _resolve(*_a, **_k):
        return "+919999999999", None, "attempt"

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", _fake_never_dial)

    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(
            principal, call_id=str(uuid.uuid4()), to_e164="+919999999999", agent_id="ghost-agent"
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["error"]["code"] == "not_found"


async def test_outbound_route_also_returns_404_for_an_unknown_agent(principal, monkeypatch):
    """The same protection applies to a plain outgoing call."""
    from fastapi import HTTPException

    from server.services.saas.telephony_orchestrator import subscriber_outbound

    async def _missing(agent_id, tenant_id=None):
        raise KeyError(agent_id)

    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _missing)
    # The KYC gate runs before the agent lookup and refuses an unverified caller
    # with 403. This test is about the 404 for an unknown agent, so the gate is
    # switched off here — otherwise the result depends on whether the developer
    # running it has Didit keys in .env, which is not what this test is asserting.
    monkeypatch.setattr(
        "server.services.saas.kyc_gate.assert_kyc_approved", _approved, raising=True
    )

    with pytest.raises(HTTPException) as exc:
        await subscriber_outbound(
            principal, agent_id="ghost-agent", from_e164=None, to_e164="+919999999999"
        )
    assert exc.value.status_code == 404


async def test_an_unverified_caller_is_stopped_before_the_agent_lookup(principal, monkeypatch):
    """With Didit configured, the compliance gate refuses before anything is dialled.

    Kept next to the 404 test on purpose: the two gates sit on the same path, and
    it is the interaction between them that is easy to break silently.
    """
    from fastapi import HTTPException

    from server.services.saas import kyc_service
    from server.services.saas.telephony_orchestrator import subscriber_outbound

    async def _not_approved(_user_id):
        return False

    async def _never_looked_up(*_a, **_kw):
        raise AssertionError("the agent must not be resolved before the gate")

    # Stub Didit's own answers, not the gate: the gate under test here is the real
    # one, and it reads both of these at call time.
    monkeypatch.setattr(kyc_service, "is_configured", lambda: True)
    monkeypatch.setattr(kyc_service, "is_approved", _not_approved)
    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _never_looked_up)

    with pytest.raises(HTTPException) as exc:
        await subscriber_outbound(
            principal, agent_id="ghost-agent", from_e164=None, to_e164="+919999999999"
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"]["code"] == "kyc_required"


async def test_callback_authorises_the_chosen_agent(principal, monkeypatch):
    """An agent the caller's workspace does not own must be rejected before dialling."""
    seen_tenant = {}

    async def _get_agent(agent_id, tenant_id=None):
        from fastapi import HTTPException

        seen_tenant["tenant_id"] = tenant_id
        # Simulate agent_service rejecting a tenant mismatch.
        raise HTTPException(
            status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}}
        )

    monkeypatch.setattr("server.brain.agent_service.agent_service.get_agent", _get_agent)

    async def _resolve(*_a, **_k):
        return "+919999999999", None, "attempt"

    monkeypatch.setattr(svc, "_resolve_target", _resolve)
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", _fake_never_dial)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(
            principal,
            call_id=str(uuid.uuid4()),
            to_e164="+919999999999",
            agent_id="11111111-1111-4111-8111-111111111111",
        )
    assert exc.value.status_code == 404
    # The lookup was scoped to the caller's own workspace tenant.
    assert seen_tenant["tenant_id"] == str(principal.tenant_id)


async def _fake_agent(agent_id, tenant_id=None):
    return {"agent_id": agent_id}


async def _fake_never_dial(*_a, **_k):
    raise AssertionError("must not dial")


async def test_invalid_call_id_is_rejected(principal):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.request_callback(principal, call_id="not-a-uuid")
    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "invalid_call_id"


# --------------------------------------------------------------------------
# Callback history
# --------------------------------------------------------------------------


def _history_session(rows, tenant_id=None, expect_or: bool = True):
    class _Result:
        def __init__(self, value):
            self._value = value

        def scalars(self):
            return self._value

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt, *args, **kwargs):
            sql = str(stmt)
            if not expect_or:
                return _Result(rows)
            # The filter must match on either original_call_id or
            # original_attempt_id, so both columns must be present and OR'd.
            assert "original_call_id" in sql, sql
            assert "original_attempt_id" in sql, sql
            assert " OR " in sql, sql
            # Actually apply the filter, so a lookup that only matched one of the
            # two columns would be caught rather than passing by accident.
            wanted = next(
                (
                    p
                    for p in stmt.compile().params.values()
                    if isinstance(p, uuid.UUID) and p != tenant_id
                ),
                None,
            )
            if wanted is None:
                return _Result(rows)
            matched = [
                r
                for r in rows
                if r.original_call_id == wanted or r.original_attempt_id == wanted
            ]
            return _Result(matched)

    class _Factory:
        def __call__(self):
            return _Session()

    return _Factory()


def _row(**kwargs):
    base = {
        "callback_id": uuid.uuid4(),
        "original_call_id": None,
        "original_attempt_id": None,
        "agent_id": "agent-1",
        "to_e164": "+919000000001",
        "from_e164": None,
        "mode": "manual",
        "status": "dialed",
        "provider": "telnyx",
        "provider_call_control_id": "cc-1",
        "error": None,
        "created_at": None,
    }
    base.update(kwargs)
    return type("Row", (), base)()


async def test_callback_history_matches_attempts_and_calls(principal, monkeypatch):
    """A callback on a missed attempt must be findable by that attempt's id."""
    attempt_id = uuid.uuid4()
    call_id = uuid.uuid4()
    rows = [
        _row(original_attempt_id=attempt_id),
        _row(original_call_id=call_id),
    ]
    monkeypatch.setattr(
        svc,
        "get_session_factory",
        lambda: _history_session(rows, tenant_id=principal.tenant_id),
    )

    import server.services.saas.call_callback_service as module

    # Both lookups must return a row, not silently drop it.
    found_attempt = await module.list_callbacks(principal, call_id=str(attempt_id))
    assert len(found_attempt) == 1
    assert found_attempt[0]["originalAttemptId"] == str(attempt_id)

    found_call = await module.list_callbacks(principal, call_id=str(call_id))
    assert len(found_call) == 1
    assert found_call[0]["originalCallId"] == str(call_id)


async def test_callback_history_without_a_filter_lists_the_tenant(principal, monkeypatch):
    monkeypatch.setattr(
        svc, "get_session_factory", lambda: _history_session([_row()], expect_or=False)
    )
    import server.services.saas.call_callback_service as module

    found = await module.list_callbacks(principal)
    assert len(found) == 1
    assert found[0]["toE164"] == "+919000000001"
