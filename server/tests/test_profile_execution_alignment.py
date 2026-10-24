"""Profile selection, native pipeline mapping, custom snapshots and boot preservation."""
from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.services.saas import voice_stack_profiles as profiles
from server.services.saas.voice_stack_defaults import recommended_composed_profile


def record_for(profile):
    return {"revision": 7, "profile": profile, "publicAliases": profiles._choice_keys(profile)}


def choice_for(record):
    aliases = record["publicAliases"]
    return {"profileRevision": record["revision"], "engineId": next(iter(aliases["engines"].values())),
        "modelId": next(iter(aliases["models"].values())), "voiceId": next(iter(aliases["voices"].values()))}


@pytest.mark.parametrize("speaker,ready", [
    ("shubh", False),
    ("shubh_enhi_ads", False),
    ("kavitha_te_conversation", True),
])
def test_persisted_v4_profile_readiness_validates_voice_before_advertising(approved_registry, speaker, ready):
    profile = recommended_composed_profile("medium")
    profile.update(enabled=True, retailRateInr=9, supportedLanguages=["te-IN"])
    profile["evidence"] = {key: True for key in profiles._EVIDENCE_KEYS}
    model = profile["engines"][0]["models"][0]
    model["model"] = "bulbul:v4-flash"
    model["voices"] = [{"id": "shubh", "providerVoiceId": speaker, "label": "Voice one", "languages": ["te-IN"]}]
    record = record_for(profile)
    status = profiles.readiness_for_profile("medium", record, {"fx_rate_inr": 100})
    assert status["ready"] is ready
    catalog = profiles.public_catalog_profile("medium", record, {"fx_rate_inr": 100})
    assert catalog["ready"] is ready
    assert bool(catalog["engines"]) is ready
    if ready:
        public_voice = catalog["engines"][0]["models"][0]["voices"][0]
        assert public_voice["label"] == "Voice 1" and public_voice["name"] == "Voice 1"
        assert "providerVoiceId" not in public_voice and public_voice["id"].startswith("voc_")
    else:
        assert status["blockers"][0]["code"] == "speech_voice_mismatch"


def test_nonprofile_pstn_normalization_accepts_v4_persona_without_replacing_it():
    from server.services.pstn_stack import normalize_pstn_stack_override

    override = {"pipeline": "classic", "tts": {"provider": "sarvam", "model": "bulbul:v4-flash",
        "config": {"speaker": "kavitha_te_conversation"}}}
    normalized, _ = normalize_pstn_stack_override(override, language="te-IN")
    assert normalized["tts"]["model"] == "bulbul:v4-flash"
    assert normalized["tts"]["config"]["speaker"] == "kavitha_te_conversation"


def test_phone_setup_failure_is_actionable_without_forwarding_vendor_details():
    from server.services.saas.call_admission import safe_response, NO_DIAL_CODES
    from server.services.saas.voice_setup_errors import voice_setup_error

    error = voice_setup_error(profiles.VoiceProfileError("profile_revision_conflict", "private vendor response"))
    response = safe_response({"ok": False, "code": error["code"], "error": "private vendor response"})
    assert error["code"] in NO_DIAL_CODES
    assert "refresh" in response["error"]
    assert "private vendor" not in str(response)


@pytest.fixture
def approved_registry(monkeypatch):
    import server.providers

    registry = SimpleNamespace(get_catalog=lambda: {"providers": [
        {"id": provider, "enabled": True, "configured": True} for provider in ("gemini", "sarvam")]},
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True)
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    return registry


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["premium", "premium_copy", "custom_voice"])
async def test_native_profile_uses_selected_live_model_without_inactive_adapters(monkeypatch, approved_registry, tier):
    profile = recommended_composed_profile("premium", allow_premium=True)
    profile["enabled"] = True
    profile["evidence"] = {key: True for key in profiles._EVIDENCE_KEYS}
    profile["retailRateInr"] = 12.5
    record = record_for(profile)
    monkeypatch.setattr(profiles, "load_profile_records", AsyncMock(return_value={tier: record}))
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", AsyncMock(return_value={"fx_rate_inr": 100}))
    # Native audio must not require separate Gemini STT/TTS adapters to exist.
    approved_registry.is_provider_enabled = lambda _provider, stage: stage == "llm"
    approved_registry.is_model_allowed = lambda _provider, stage, _model: stage == "llm"
    stack, snapshot = await profiles.resolve_agent_selection(environment="development", tier=tier,
        voice_settings=choice_for(record), language="te-IN")
    assert stack["pipeline"] == "realtime_voice" and stack["voice_flow"] == "realtime_e2e"
    assert stack["llm"] == {"provider": "gemini", "model": profile["llm"]["modelId"]}
    assert "stt" not in stack and "tts" not in stack
    assert stack["realtime_voice"]["voice"] == profile["engines"][0]["models"][0]["voices"][0]["providerVoiceId"]
    assert snapshot["tier"] == tier and snapshot["retailRate"]["inrPaisePerMin"] == 1250
    assert snapshot["retailRate"]["usdMicrosPerMin"] == 125000


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["voice", "revision"])
async def test_obsolete_fallback_flag_never_replaces_invalid_saved_selection(monkeypatch, approved_registry, change):
    profile = recommended_composed_profile("medium")
    profile.update(enabled=True, retailRateInr=9)
    profile["evidence"] = {key: True for key in profiles._EVIDENCE_KEYS}
    record = record_for(profile)
    selection = choice_for(record)
    selection["voiceId" if change == "voice" else "profileRevision"] = "missing" if change == "voice" else 1
    monkeypatch.setattr(profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", AsyncMock(return_value={"fx_rate_inr": 100}))
    with pytest.raises(profiles.VoiceProfileError) as exc:
        await profiles.resolve_agent_selection(environment="development", tier="medium", voice_settings=selection,
            language="te-IN", allow_fallback=True)
    assert exc.value.code == ("voice_selection_invalid" if change == "voice" else "profile_revision_conflict")


def test_profile_validation_accepts_native_transport_and_rejects_cross_model_tuple():
    profile = recommended_composed_profile("premium", allow_premium=True)
    assert profiles.validate_composed_profile(profile, tier="premium", allow_premium=True)["llm"]["apiMode"] == "websocket"
    profile["engines"][0]["models"][0]["model"] = "gemini-3.8-flash-tts"
    with pytest.raises(profiles.VoiceProfileError, match="same live model"):
        profiles.validate_composed_profile(profile, tier="premium", allow_premium=True)


@pytest.mark.asyncio
async def test_boot_only_reads_configuration_and_never_marks_evidence_or_rates_approved(monkeypatch):
    from server.db import tier_store
    from server.services.saas import billing_rates, composed_costing

    record = record_for(recommended_composed_profile("medium"))
    original = copy.deepcopy(record)
    factory = Mock()
    monkeypatch.setattr(profiles, "get_session_factory", lambda: factory)
    monkeypatch.setattr(tier_store, "load_tier_cache", AsyncMock(return_value=1))
    monkeypatch.setattr(profiles, "load_profile_records", AsyncMock(return_value={"medium": record}))
    monkeypatch.setattr(profiles, "cache_aliases_from_record", Mock())
    seed = AsyncMock()
    reprice = AsyncMock()
    save = AsyncMock()
    monkeypatch.setattr(composed_costing, "seed_default_provider_costs", seed)
    monkeypatch.setattr(billing_rates, "update_rates_versioned", reprice)
    monkeypatch.setattr(profiles, "save_composed_profile", save)
    await profiles.hydrate_composed_voice_stacks_and_rates()
    assert record == original
    seed.assert_not_awaited()
    reprice.assert_not_awaited()
    save.assert_not_awaited()
    factory.assert_not_called()
