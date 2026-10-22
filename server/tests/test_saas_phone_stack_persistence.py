from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def _stack(provider: str, updated_at: datetime) -> dict:
    return {
        "stack_override": {
            "pipeline": "realtime_voice",
            "language": "te-IN",
            "llm": {
                "provider": provider,
                "model": "gemini-3.8-live" if provider == "gemini" else "gpt-realtime-2.1-mini",
            },
            "realtime_voice": {"voice": "te-in-csagent-5" if provider == "gemini" else "marin"},
        },
        "updated_at": updated_at.isoformat(),
    }


class _FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_hydration_uses_newer_database_stack_even_when_disk_file_exists(monkeypatch, tmp_path):
    from server.services.saas import platform_phone_stack as mod

    newer = datetime.now(timezone.utc)
    old_disk = _stack("openai", newer - timedelta(minutes=1))
    newest_db = _stack("gemini", newer)
    path = tmp_path / "saas_universal_phone_stack.json"
    path.write_text(json.dumps(old_disk), encoding="utf-8")
    monkeypatch.setattr(mod, "_stack_path", lambda: path)

    class FakeSession:
        async def execute(self, _query):
            return SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(payload=newest_db, created_at=newer)
            )

    monkeypatch.setattr(
        "server.db.connection.get_session_factory",
        lambda: lambda: _FakeSessionContext(FakeSession()),
    )

    assert await mod.hydrate_universal_phone_stack_from_db()
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["stack_override"]["llm"]["provider"] == "gemini"


@pytest.mark.asyncio
async def test_hydration_preserves_newer_disk_save_when_database_has_old_snapshot(monkeypatch, tmp_path):
    from server.services.saas import platform_phone_stack as mod

    now = datetime.now(timezone.utc)
    newer_disk = _stack("openai", now)
    old_db = _stack("gemini", now - timedelta(minutes=2))
    path = tmp_path / "saas_universal_phone_stack.json"
    path.write_text(json.dumps(newer_disk), encoding="utf-8")
    monkeypatch.setattr(mod, "_stack_path", lambda: path)

    class FakeSession:
        async def execute(self, _query):
            return SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(
                    payload=old_db,
                    created_at=now - timedelta(minutes=2),
                )
            )

    monkeypatch.setattr(
        "server.db.connection.get_session_factory",
        lambda: lambda: _FakeSessionContext(FakeSession()),
    )

    assert await mod.hydrate_universal_phone_stack_from_db()
    preserved = json.loads(path.read_text(encoding="utf-8"))
    assert preserved["stack_override"]["llm"]["provider"] == "openai"


def test_stack_file_save_is_atomic_and_round_trips(monkeypatch, tmp_path):
    from server.services.saas import platform_phone_stack as mod

    path = tmp_path / "saas_universal_phone_stack.json"
    monkeypatch.setattr(mod, "_stack_path", lambda: path)
    payload = _stack("gemini", datetime.now(timezone.utc))

    assert mod.save_universal_phone_stack_raw(payload) == payload
    assert mod.load_universal_phone_stack_raw() == payload
    assert list(tmp_path.glob("*.tmp")) == []
