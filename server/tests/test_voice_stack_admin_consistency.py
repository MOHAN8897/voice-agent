"""Admin tier configuration applies consistently to calls, prices, previews and caches."""
from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.services.saas import voice_stack_profiles as profiles
from server.services.saas.voice_stack_defaults import recommended_composed_profile


def _medium_profile(**extra):
    profile = recommended_composed_profile("medium")
    profile.update(enabled=True, retailRateInr=9)
    profile["evidence"] = {key: True for key in profiles._EVIDENCE_KEYS}
    profile.update(extra)
    return profile


def _record(profile, revision=5):
    return {"revision": revision, "profile": profile, "publicAliases": profiles._choice_keys(profile)}


def _choice(record):
    aliases = record["publicAliases"]
    return {"profileRevision": record["revision"], "engineId": next(iter(aliases["engines"].values())),
            "modelId": next(iter(aliases["models"].values())), "voiceId": next(iter(aliases["voices"].values()))}


@pytest.fixture
async def stack_db(monkeypatch):
    from server.db import tier_store
    from server.db.models.entities import Base, ConfigVersion, TierAssignment
    from server.db.models.saas_models import BillingRateVersion

    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB

    for model in (TierAssignment, ConfigVersion, BillingRateVersion):
        for column in model.__table__.columns:
            if isinstance(column.type, (JSONB, ARRAY)):
                monkeypatch.setattr(column, "type", JSON())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
            TierAssignment.__table__, ConfigVersion.__table__, BillingRateVersion.__table__]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(profiles, "get_session_factory", lambda: factory)
    monkeypatch.setattr(tier_store, "get_session_factory", lambda: factory)
    monkeypatch.setattr(tier_store, "_cache_put", lambda *_: None)
    monkeypatch.setattr(profiles, "profile_view", AsyncMock(return_value={}))
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    yield factory
    await engine.dispose()


async def _seed(factory, profile, revision=5):
    from server.db.models.entities import TierAssignment

    async with factory() as session:
        session.add(TierAssignment(environment="development", tier="medium", combination_id="seed",
                                   stack_payload={"composed_voice_profile": _record(profile, revision)}))
        await session.commit()


async def _stored(factory):
    from server.db.models.entities import TierAssignment

    async with factory() as session:
        row = (await session.execute(select(TierAssignment))).scalar_one()
        return row.stack_payload


# Finding 1: an admin save must not break agents whose choice still exists.
@pytest.mark.asyncio
async def test_older_revision_with_resolving_aliases_is_callable(monkeypatch):
    record = _record(_medium_profile(), revision=9)
    monkeypatch.setattr(profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", AsyncMock(return_value={"fx_rate_inr": 100}))
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    selection = {**_choice(record), "profileRevision": 2}
    stack, snapshot = await profiles.resolve_agent_selection(
        environment="development", tier="medium", voice_settings=selection, language="te-IN")
    assert stack["pipeline"] == "composed_voice"
    assert snapshot["profileRevision"] == 9


# Finding 10: knobs are applied per selected model at call time.
@pytest.mark.asyncio
async def test_call_applies_only_knobs_the_selected_model_supports(monkeypatch):
    profile = _medium_profile(voiceDynamics={"speed": 2.6, "pace": 2.6, "pitch": 0.5, "temperature": 0.4})
    record = _record(profile)
    monkeypatch.setattr(profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", AsyncMock(return_value={"fx_rate_inr": 100}))
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    stack, _ = await profiles.resolve_agent_selection(
        environment="development", tier="medium", voice_settings=_choice(record), language="te-IN")
    config = stack["tts"]["config"]
    assert stack["tts"]["model"] == "bulbul:v3"
    assert config["speed"] == 2.0 and config["pace"] == 2.0  # bulbul v3 pace band is 0.5-2.0
    assert config["temperature"] == 0.4
    assert "pitch" not in config  # bulbul v3 ignores pitch
    effective = profiles.effective_voice_dynamics(profile)[0]
    assert "pitch" in effective["ignored"] and effective["applied"]["speed"] == 2.0


# Finding 2: a runtime change cannot leave an enabled tier enabled-but-broken.
@pytest.mark.asyncio
async def test_runtime_change_on_enabled_tier_needs_confirmation_then_goes_offline(stack_db):
    profile = _medium_profile()
    await _seed(stack_db, profile)
    changed = copy.deepcopy(profile)
    changed["stt"]["model"] = "saaras:v3"
    with pytest.raises(profiles.VoiceProfileError) as exc:
        await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=5,
                                             payload=changed, actor="admin")
    assert exc.value.code == "change_takes_tier_offline" and exc.value.status_code == 409
    assert (await _stored(stack_db))["composed_voice_profile"]["revision"] == 5

    await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=5,
                                         payload=changed, actor="admin", confirm_take_offline=True)
    saved = (await _stored(stack_db))["composed_voice_profile"]
    assert saved["revision"] == 6
    assert saved["profile"]["enabled"] is False
    assert saved["profile"]["disabledReason"]["code"] == "runtime_changed"
    assert saved["profile"]["evidence"]["sttVerified"] is False


@pytest.mark.asyncio
async def test_knob_only_change_keeps_enabled_tier_live_and_mirrors_dynamics(stack_db):
    from server.db.models.saas_models import BillingRateVersion

    async with stack_db() as session:
        session.add(BillingRateVersion(version=1, pstn_rate_usd_cents_per_min=10, web_agent_rate_usd_cents_per_min=5,
            did_monthly_usd_cents=100, fx_rate_inr=90, created_by="test", reason="Approved rates"))
        await session.commit()
    profile = _medium_profile()
    await _seed(stack_db, profile)
    tweaked = copy.deepcopy(profile)
    tweaked["voiceDynamics"] = {"speed": 1.2, "temperature": 0.5}
    await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=5,
                                         payload=tweaked, actor="admin")
    payload = await _stored(stack_db)
    assert payload["composed_voice_profile"]["profile"]["enabled"] is True
    # Finding 8: the legacy stage mirror carries the tier knobs.
    assert payload["tts"]["config"]["speed"] == 1.2 and payload["tts"]["config"]["temperature"] == 0.5


@pytest.mark.asyncio
async def test_save_never_self_enables_a_disabled_tier(stack_db):
    profile = _medium_profile(enabled=False)
    await _seed(stack_db, profile)
    await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=5,
                                         payload={**profile, "enabled": True}, actor="admin")
    assert (await _stored(stack_db))["composed_voice_profile"]["profile"]["enabled"] is False


# Finding 5: prices are validated and published as a new rate version.
@pytest.mark.parametrize("field,value", [
    ("retailRateInr", -1), ("retailRateInr", 0), ("retailRateInr", "abc"), ("retailRateInr", "Infinity"),
    ("webRetailRateInr", -2), ("supplierCostInr", -0.5),
])
def test_invalid_prices_are_rejected_with_the_field_name(field, value):
    profile = _medium_profile()
    profile[field] = value
    with pytest.raises(profiles.VoiceProfileError) as exc:
        profiles.validate_composed_profile(profile, tier="medium")
    assert exc.value.code == "invalid_price" and exc.value.status_code == 422
    assert exc.value.details["field"] == field


@pytest.mark.asyncio
async def test_price_change_publishes_new_rate_version_without_mutating_active_row(stack_db, monkeypatch):
    from server.db.models.saas_models import BillingRateVersion

    async with stack_db() as session:
        session.add(BillingRateVersion(version=3, pstn_rate_usd_cents_per_min=10, web_agent_rate_usd_cents_per_min=5,
            did_monthly_usd_cents=100, fx_rate_inr=90, created_by="test", reason="Approved rates",
            pstn_medium_rate_inr_paise_per_min=900, pstn_medium_rate_usd_micros_per_min=100000))
        await session.commit()
    published = AsyncMock()
    monkeypatch.setattr(profiles, "_publish_core_tier_price", published)
    profile = _medium_profile()
    await _seed(stack_db, profile)
    await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=5,
                                         payload={**profile, "retailRateInr": 11.5}, actor="admin")
    published.assert_awaited_once_with("medium", 11.5, actor="admin")
    async with stack_db() as session:
        rate = (await session.execute(select(BillingRateVersion))).scalar_one()
        assert rate.pstn_medium_rate_inr_paise_per_min == 900


# Finding 7: one loader, including web-call defaults.
def test_tier_rate_loader_includes_web_defaults():
    from server.services.saas.billing_rates import tier_rates_from_row

    row = SimpleNamespace(
        version=4, pstn_rate_usd_cents_per_min=10, web_agent_rate_usd_cents_per_min=5, did_monthly_usd_cents=100,
        pstn_rate_usd_micros_per_min=None, web_agent_rate_usd_micros_per_min=None, did_monthly_usd_micros=None,
        pstn_rate_inr_paise_per_min=None, web_agent_rate_inr_paise_per_min=None, did_monthly_inr_paise=None,
        pstn_low_rate_usd_micros_per_min=None, pstn_low_rate_inr_paise_per_min=None,
        pstn_medium_rate_usd_micros_per_min=50000, pstn_medium_rate_inr_paise_per_min=450,
        pstn_premium_rate_usd_micros_per_min=None, pstn_premium_rate_inr_paise_per_min=None,
        fx_rate_inr=90.0, effective_from=None, created_by="t", reason="r")
    rates = tier_rates_from_row(row)
    assert rates["medium_rate_version"] == 4 and rates["low_rate_version"] is None
    web = profiles._web_tier_retail_rate(rates, "medium", {"profile": {}})
    assert web is not None and web["inrPaisePerMin"] == 450 and web["source"] == "global_web_default"


# Finding 3: native audio profiles have a valid path to readiness.
def test_native_profile_is_ready_without_composed_stage_evidence(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    profile = recommended_composed_profile("premium", allow_premium=True)
    profile.update(enabled=True, retailRateInr=12)
    assert profiles.is_native_profile(profile)
    status = profiles.readiness_for_profile("premium", _record(profile), {"fx_rate_inr": 100})
    assert status["ready"] is True and status["verificationPath"] == "test_studio"


# Finding 6: the default agent speed inherits the tier knob.
@pytest.mark.parametrize("value,expected", [(None, None), (1.0, None), ("1", None), (1.15, 1.15), ("bad", None)])
def test_default_agent_speed_inherits_tier_speed(value, expected):
    from server.services.saas.pstn_saas_stack import _agent_speed_override

    assert _agent_speed_override(value) == expected


# Finding 11: recognition language support is validated where known.
def test_stt_model_language_mismatch_is_rejected():
    profile = _medium_profile()
    profile["stt"] = {"provider": "cartesia", "model": "ink-2"}
    with pytest.raises(profiles.VoiceProfileError) as exc:
        profiles.validate_composed_profile(profile, tier="medium")
    assert exc.value.details["field"] == "stt.model"


# Finding 4: stage-only writers keep the composed profile; promotions roll back.
@pytest.mark.asyncio
async def test_stage_upsert_preserves_composed_profile_and_promotion_rolls_back(stack_db):
    from server.db import tier_store

    profile = _medium_profile()
    await _seed(stack_db, profile)
    await tier_store.upsert_tier_assignment("development", "medium", "env-combo", {
        "stt": {"provider": "x", "model": "y", "config": {}}, "llm": {}, "tts": {}})
    stored = await _stored(stack_db)
    assert stored["composed_voice_profile"]["revision"] == 5
    assert stored["stt"]["provider"] == profile["stt"]["provider"]

    snapshot: list = []
    copied = await tier_store.promote_tier_assignments("development", "staging", snapshot=snapshot)
    assert copied == 1 and snapshot == [{"tier": "medium", "combination_id": None, "stack_payload": None}]
    restored = await tier_store.restore_tier_assignments("staging", snapshot)
    assert restored == 1
    from server.db.models.entities import TierAssignment

    async with stack_db() as session:
        rows = (await session.execute(select(TierAssignment).where(TierAssignment.environment == "staging"))).scalars().all()
        assert rows == []


# Catalog: 60s cache, invalidated on admin change; warm-up only on a miss.
@pytest.mark.asyncio
async def test_tenant_catalog_is_cached_and_invalidated(monkeypatch):
    from server.routes import voice_stacks

    monkeypatch.setenv("VOICE_CATALOG_CACHE_IN_TESTS", "1")
    profiles.invalidate_profile_caches(None)
    loader = AsyncMock(return_value={})
    monkeypatch.setattr(voice_stacks, "load_profile_records", loader)
    monkeypatch.setattr(voice_stacks, "_load_rates_without_fallback", AsyncMock(return_value=None))
    first = await voice_stacks.voice_stack_catalog(language="te-IN", principal=None, background=None)
    second = await voice_stacks.voice_stack_catalog(language="te-IN", principal=None, background=None)
    assert first == second and loader.await_count == 1
    profiles.invalidate_profile_caches("medium")
    await voice_stacks.voice_stack_catalog(language="te-IN", principal=None, background=None)
    assert loader.await_count == 2
    profiles.invalidate_profile_caches(None)


# Finding 12: Flagship is never padded with unapproved default voices.
@pytest.mark.asyncio
async def test_premium_without_voices_is_not_published_with_defaults(monkeypatch):
    from server.routes import voice_stacks

    record = {"revision": 1, "profile": {"enabled": True, "engines": []}, "publicAliases": {}}
    monkeypatch.setattr(voice_stacks, "load_profile_records", AsyncMock(return_value={"premium": record}))
    monkeypatch.setattr(voice_stacks, "_load_rates_without_fallback", AsyncMock(return_value={"fx_rate_inr": 100}))
    result = await voice_stacks.voice_stack_catalog(language="te-IN", principal=None, background=None)
    assert result["profiles"] == []
