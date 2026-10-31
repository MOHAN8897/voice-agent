import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.db.models.entities import Base, ConfigVersion, TierAssignment
from server.services.saas import voice_profile_verification as verification
from server.services.saas import voice_stack_profiles as profiles
from server.services.saas.voice_stack_defaults import recommended_composed_profile


@pytest.fixture
async def store(monkeypatch):
    for model in (TierAssignment, ConfigVersion):
        for column in model.__table__.columns:
            if isinstance(column.type, JSONB):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync,
            tables=[TierAssignment.__table__, ConfigVersion.__table__]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(profiles, "get_session_factory", lambda: factory)
    monkeypatch.setattr(verification, "get_session_factory", lambda: factory)
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _: [])
    monkeypatch.setattr(profiles, "expand_model_voices", lambda tier, record: copy.deepcopy(record))
    rates = {"pstn_low_rate_usd_micros_per_min": 10_000, "pstn_low_rate_inr_paise_per_min": 100, "fx_rate_inr": 100, "version": 1}
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", AsyncMock(return_value=rates))
    monkeypatch.setattr(profiles, "_rates_for_session", AsyncMock(return_value=rates))
    payload = recommended_composed_profile("low")
    async with factory() as db:
        db.add(TierAssignment(environment="test", tier="low", combination_id="original", stack_payload={
            "unrelated": "preserve", "composed_voice_profile": {"revision": 1, "profile": payload,
                "publicAliases": profiles._choice_keys(payload)}}))
        await db.commit()
    yield factory
    await engine.dispose()


def passed_checks():
    return {key: {"passed": True, "detail": "Synthetic test passed."} for key in profiles._EVIDENCE_KEYS}


@pytest.mark.asyncio
async def test_first_save_cannot_self_attest_provider_readiness(store):
    draft = recommended_composed_profile("low")
    draft["enabled"] = False
    draft["evidence"] = {key: True for key in profiles._EVIDENCE_KEYS}
    saved = await profiles.save_composed_profile(environment="test", tier="new_profile",
        expected_revision=0, payload=draft, actor="test")
    assert not any(saved["composedProfile"]["evidence"].values())
    assert not saved["readiness"]["ready"]


@pytest.mark.asyncio
async def test_successful_recheck_keeps_saved_voice_revision(store, monkeypatch):
    monkeypatch.setattr(verification, "probe_profile", AsyncMock(return_value=passed_checks()))
    first = await verification.verify_saved_profile(environment="test", tier="low", expected_revision=1, actor="test")
    second = await verification.verify_saved_profile(environment="test", tier="low", expected_revision=2, actor="test")
    assert first["profile"]["profileRevision"] == second["profile"]["profileRevision"] == 2
    assert second["profile"]["readiness"]["ready"]
    async with store() as db:
        audits = (await db.execute(select(ConfigVersion))).scalars().all()
        assert len(audits) == 2


@pytest.mark.asyncio
async def test_activation_never_fabricates_missing_evidence(store):
    with pytest.raises(profiles.VoiceProfileError) as error:
        await profiles.set_profile_enabled(environment="test", tier="low", expected_revision=1,
            enabled=True, actor="test")
    assert error.value.code == "profile_not_ready"
    row = (await profiles.load_profile_records("test", ["low"]))["low"]
    assert not any(row["profile"]["evidence"].values()) and not row["profile"]["enabled"]


@pytest.mark.asyncio
async def test_web_price_persists_without_changing_phone_price_or_verified_stack(store, monkeypatch):
    monkeypatch.setattr(verification, "probe_profile", AsyncMock(return_value=passed_checks()))
    verified = await verification.verify_saved_profile(environment="test", tier="low", expected_revision=1, actor="test")
    draft = verified["profile"]["composedProfile"]
    phone_price = draft.get("retailRateInr")
    draft["webRetailRateInr"] = 3.4567
    saved = await profiles.save_composed_profile(environment="test", tier="low", expected_revision=2, payload=draft, actor="test")
    restored = (await profiles.load_profile_records("test", ["low"]))["low"]
    assert restored["profile"]["webRetailRateInr"] == 3.4567
    assert restored["profile"].get("retailRateInr") == phone_price
    assert saved["webRetailRate"]["inrPaisePerMin"] == 346
    assert all(saved["composedProfile"]["evidence"].values())
    assert "verification" in restored


@pytest.mark.asyncio
async def test_verified_evidence_survives_stale_editor_but_not_model_change(store, monkeypatch):
    monkeypatch.setattr(verification, "probe_profile", AsyncMock(return_value=passed_checks()))
    result = await verification.verify_saved_profile(environment="test", tier="low", expected_revision=1, actor="test")
    assert result["profile"]["readiness"]["ready"] and not result["profile"]["readiness"]["enabled"]
    draft = result["profile"]["composedProfile"]
    draft["evidence"] = {key: False for key in profiles._EVIDENCE_KEYS}
    draft["label"] = "New display label"
    saved = await profiles.save_composed_profile(environment="test", tier="low", expected_revision=2, payload=draft, actor="test")
    assert all(saved["composedProfile"]["evidence"].values())
    assert "verification" in (await profiles.load_profile_records("test", ["low"]))["low"]
    draft["llm"]["modelId"] = "sarvam-105b"
    changed = await profiles.save_composed_profile(environment="test", tier="low", expected_revision=3, payload=draft, actor="test")
    assert not any(changed["composedProfile"]["evidence"].values())
    assert "verification" not in (await profiles.load_profile_records("test", ["low"]))["low"]
    async with store() as db:
        row = (await db.execute(select(TierAssignment))).scalar_one()
        assert row.stack_payload["unrelated"] == "preserve"


@pytest.mark.asyncio
async def test_failed_check_remains_a_blocker(store, monkeypatch):
    checks = passed_checks()
    checks["sttVerified"] = {"passed": False, "detail": "Synthetic STT failure."}
    monkeypatch.setattr(verification, "probe_profile", AsyncMock(return_value=checks))
    result = await verification.verify_saved_profile(environment="test", tier="low", expected_revision=1, actor="test")
    assert not result["profile"]["readiness"]["ready"]
    assert "stt_unverified" in {row["code"] for row in result["profile"]["readiness"]["blockers"]}


@pytest.mark.asyncio
async def test_concurrent_edit_cannot_receive_old_verification(store, monkeypatch):
    async def edit_during_probe(_profile):
        async with store() as db:
            row = (await db.execute(select(TierAssignment))).scalar_one()
            payload = copy.deepcopy(row.stack_payload)
            payload["composed_voice_profile"]["revision"] = 2
            row.stack_payload = payload
            await db.commit()
        return passed_checks()
    monkeypatch.setattr(verification, "probe_profile", edit_during_probe)
    with pytest.raises(profiles.VoiceProfileError) as error:
        await verification.verify_saved_profile(environment="test", tier="low", expected_revision=1, actor="test")
    assert error.value.code == "revision_conflict"
    assert not any((await profiles.load_profile_records("test", ["low"]))["low"]["profile"]["evidence"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("stt_error", [False, True])
async def test_probe_uses_bounded_vad_frames_and_never_executes_business_tool(monkeypatch, stt_error):
    sent = []

    class Text:
        async def stream_live_turn(self, **kwargs):
            event = {"done": True, "text": "READY"}
            if kwargs.get("tools"):
                event["tool_calls"] = [{"function": {"name": "readiness_probe", "arguments": '{"status":"READY"}'}}]
            yield event

    class Socket:
        async def send(self, message):
            sent.append(json.loads(message))

        async def recv(self):
            return json.dumps({"event": "error"} if stt_error else {"event": "transcript.final", "text": "Test speech"})

    @asynccontextmanager
    async def connect(_config):
        yield Socket()

    registry = SimpleNamespace(get_llm=lambda _: Text(), get_stt=lambda _: SimpleNamespace(connect_realtime=connect))
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _: [])
    monkeypatch.setattr("server.services.pstn_prewarm._synthesize_greeting_frames", AsyncMock(return_value=([b"\1\0" * 8000], {})))
    checks = await verification.probe_profile(recommended_composed_profile("low"))
    assert checks["sttVerified"]["passed"] is not stt_error
    assert checks["toolsVerified"]["passed"]
    assert all(row["event"] == "audio_input" for row in sent)
    import base64
    assert max(len(base64.b64decode(row["audio"])) for row in sent) <= 6400


@pytest.mark.asyncio
@pytest.mark.parametrize("role,status", [(None, 401), ("customer_viewer", 403), ("developer", 200)])
async def test_verification_route_requires_privileged_session(monkeypatch, role, status):
    import httpx
    from fastapi import FastAPI

    from server.auth.dependencies import require_dev_session
    from server.routes.dev_stack import router

    app = FastAPI()
    app.include_router(router)
    if role:
        app.dependency_overrides[require_dev_session] = lambda: SimpleNamespace(role=role, subject="test", kind="dev")
    probe = AsyncMock(return_value={"checks": {}})
    monkeypatch.setattr(verification, "verify_saved_profile", probe)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/dev/stack/voice-profiles/low/verify", json={"expectedRevision": 1})
    assert response.status_code == status
    assert probe.await_count == (1 if status == 200 else 0)
