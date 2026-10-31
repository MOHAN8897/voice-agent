"""Realtime STT moves to the backup Sarvam key when the primary's stream is
accepted and then closed for credits (close code 1003 right after the upgrade).

Fake sockets only; no network.
"""
from __future__ import annotations

import asyncio

import pytest

from server.services import sarvam_ws
from server.services.sarvam_keys import sarvam_key_pool


class _FakeWs:
    def __init__(self, *, close_after: float | None, code: int | None = None, reason: str = ""):
        self._closed = asyncio.Event()
        self.close_code = None
        self.close_reason = ""
        self._close_after, self._code, self._reason = close_after, code, reason
        self.closed_by_us = False

    async def start(self):
        if self._close_after is not None:
            await asyncio.sleep(self._close_after)
            self.close_code, self.close_reason = self._code, self._reason
            self._closed.set()

    async def wait_closed(self):
        await self._closed.wait()

    async def close(self):
        self.closed_by_us = True
        self._closed.set()


@pytest.fixture
def two_keys(monkeypatch):
    monkeypatch.setattr(sarvam_key_pool, "plan", lambda **_: [("primary", "k-primary"), ("backup_1", "k-backup")])
    monkeypatch.setattr(sarvam_ws, "EARLY_CLOSE_WINDOW_S", 0.15)
    failures, successes = [], []
    monkeypatch.setattr(sarvam_key_pool, "report_failure",
                        lambda slot, category, **kw: failures.append((slot, category)))
    monkeypatch.setattr(sarvam_key_pool, "report_success", lambda slot, **kw: successes.append(slot))
    monkeypatch.setattr(sarvam_key_pool, "mark_attempt", lambda slot: None)
    return failures, successes


def _fake_connect(sockets: dict[str, _FakeWs], used: list[str]):
    def connect(url, headers, **kw):
        key = headers["api-subscription-key"]
        used.append(key)
        ws = sockets[key]

        async def opened():
            asyncio.ensure_future(ws.start())
            return ws

        return opened()

    return connect


async def test_stt_stream_closed_for_credits_moves_to_backup_key(two_keys, monkeypatch):
    failures, successes = two_keys
    sockets = {
        "k-primary": _FakeWs(close_after=0.02, code=1003, reason="Insufficient credits"),
        "k-backup": _FakeWs(close_after=None),
    }
    used: list[str] = []
    monkeypatch.setattr(sarvam_ws, "_connect", _fake_connect(sockets, used))

    ws = await sarvam_ws.connect_stt_realtime(language_code="te-IN")

    assert ws is sockets["k-backup"]
    assert used == ["k-primary", "k-backup"]
    assert failures and failures[0][0] == "primary"
    assert successes == ["backup_1"]


async def test_stream_that_stays_open_is_used_without_trying_other_keys(two_keys, monkeypatch):
    failures, successes = two_keys
    sockets = {"k-primary": _FakeWs(close_after=None), "k-backup": _FakeWs(close_after=None)}
    used: list[str] = []
    monkeypatch.setattr(sarvam_ws, "_connect", _fake_connect(sockets, used))

    ws = await sarvam_ws.connect_stt_realtime(language_code="hi-IN")

    assert ws is sockets["k-primary"] and used == ["k-primary"]
    assert not failures and successes == ["primary"]


async def test_every_key_closed_for_credits_raises_a_provider_failure(two_keys, monkeypatch):
    from server.services.provider_health import ProviderFailure

    sockets = {
        "k-primary": _FakeWs(close_after=0.01, code=1003, reason="Insufficient credits"),
        "k-backup": _FakeWs(close_after=0.01, code=1003, reason="Insufficient credits"),
    }
    monkeypatch.setattr(sarvam_ws, "_connect", _fake_connect(sockets, []))
    with pytest.raises(ProviderFailure):
        await sarvam_ws.connect_stt_realtime(language_code="te-IN")


async def test_early_close_classification():
    ws = _FakeWs(close_after=0, code=1003, reason="")
    await ws.start()
    assert (await sarvam_ws._early_close_status(ws))[0] == 402
    ws = _FakeWs(close_after=0, code=1008, reason="Invalid API key")
    await ws.start()
    assert (await sarvam_ws._early_close_status(ws))[0] == 401
    ws = _FakeWs(close_after=0, code=1000, reason="")
    await ws.start()
    assert await sarvam_ws._early_close_status(ws) is None
