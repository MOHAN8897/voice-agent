"""The quick-call helper must not contact a carrier without two explicit gates."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from scripts import run_test_call_quick as quick_call


@pytest.mark.asyncio
async def test_default_invocation_is_no_network_mock_only(monkeypatch, capsys) -> None:
    def forbidden_client(*_args, **_kwargs):
        pytest.fail("default invocation must not construct an HTTP client")

    monkeypatch.setattr(quick_call.httpx, "AsyncClient", forbidden_client)

    assert await quick_call.main([]) == 0
    assert "no network request was sent" in capsys.readouterr().out


class _Response:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _install_mock_client(monkeypatch, flows):
    requests = []

    class FakeClient:
        cookies = {"dev_csrf": "mock-csrf"}

        def __init__(self, **_kwargs):
            self._flows = iter(flows)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, path, **kwargs):
            requests.append(("POST", path, kwargs))
            if path == "/api/dev/login":
                return _Response({"ok": True})
            return _Response({"ok": True, "call_id": "mock-call-id"})

        async def get(self, path, **kwargs):
            requests.append(("GET", path, kwargs))
            return _Response({"ok": True, "flow": next(self._flows)})

    monkeypatch.setattr(quick_call.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(quick_call.asyncio, "sleep", AsyncMock())
    return requests


def _mock_live_config():
    return quick_call.resolve_live_config(
        live_requested=True,
        talk_seconds=10,
        environ={
            "VOXLY_ALLOW_REAL_TEST_CALLS": "1",
            "VOXLY_TEST_CALL_TO_E164": "+12025550123",
            "VOXLY_TEST_CALL_AGENT_ID": "00000000-0000-4000-8000-000000000001",
            "VOXLY_DEV_USERNAME": "operator",
            "VOXLY_DEV_PASSWORD": "test-only-password",
        },
    )


@pytest.mark.asyncio
async def test_explicit_live_path_observes_hangup_completion_with_mock_api(monkeypatch, capsys) -> None:
    requests = _install_mock_client(
        monkeypatch,
        [
            {"active": True, "stages": {}, "events": []},
            {"active": False, "stages": {"hangup_complete": True}, "events": []},
        ],
    )

    assert await quick_call._run_live_call(_mock_live_config()) == 0
    assert any(
        method == "GET" and path.endswith("?call_id=mock-call-id")
        for method, path, _kwargs in requests
    )
    output = capsys.readouterr().out
    assert "hangup completion observed" in output
    assert "test-only-password" not in output
    assert "+12025550123" not in output


@pytest.mark.asyncio
async def test_explicit_live_path_fails_when_hangup_completion_is_missing(monkeypatch, capsys) -> None:
    _install_mock_client(
        monkeypatch,
        [
            {"active": True, "stages": {}, "events": []},
            {"active": False, "stages": {}, "events": []},
        ],
    )

    assert await quick_call._run_live_call(_mock_live_config()) == 1
    assert "without a hangup-completion event" in capsys.readouterr().out


def test_live_configuration_requires_operator_opt_in() -> None:
    with pytest.raises(ValueError, match="Live calling is disabled"):
        quick_call.resolve_live_config(live_requested=False, talk_seconds=120, environ={})
    with pytest.raises(ValueError, match="VOXLY_ALLOW_REAL_TEST_CALLS"):
        quick_call.resolve_live_config(live_requested=True, talk_seconds=120, environ={})


def test_live_configuration_rejects_non_loopback_api_origins() -> None:
    env = {
        "VOXLY_ALLOW_REAL_TEST_CALLS": "1",
        "VOXLY_TEST_API_BASE_URL": "https://example.invalid",
        "VOXLY_TEST_CALL_TO_E164": "+12025550123",
        "VOXLY_TEST_CALL_AGENT_ID": "00000000-0000-4000-8000-000000000001",
        "VOXLY_DEV_USERNAME": "operator",
        "VOXLY_DEV_PASSWORD": "test-only-password",
    }
    with pytest.raises(ValueError, match="loopback origin"):
        quick_call.resolve_live_config(live_requested=True, talk_seconds=120, environ=env)


def test_live_configuration_validates_destination_and_agent_before_network() -> None:
    env = {
        "VOXLY_ALLOW_REAL_TEST_CALLS": "1",
        "VOXLY_TEST_CALL_TO_E164": "not-a-number",
        "VOXLY_TEST_CALL_AGENT_ID": "00000000-0000-4000-8000-000000000001",
        "VOXLY_DEV_USERNAME": "operator",
        "VOXLY_DEV_PASSWORD": "test-only-password",
    }
    with pytest.raises(ValueError, match="E.164"):
        quick_call.resolve_live_config(live_requested=True, talk_seconds=120, environ=env)

    env["VOXLY_TEST_CALL_TO_E164"] = "+12025550123"
    config = quick_call.resolve_live_config(live_requested=True, talk_seconds=120, environ=env)
    assert config.agent_id == env["VOXLY_TEST_CALL_AGENT_ID"]
    assert "test-only-password" not in repr(config)
    assert env["VOXLY_TEST_CALL_TO_E164"] not in repr(config)
