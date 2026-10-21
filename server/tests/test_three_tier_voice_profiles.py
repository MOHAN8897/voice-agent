from __future__ import annotations

import copy
import json

import pytest

from server.services.saas import voice_stack_profiles as profiles


def _profile(*, enabled: bool = True) -> dict:
    return {
        "schemaVersion": 1,
        "enabled": enabled,
        "supportedLanguages": ["te-IN"],
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "llm": {
            "provider": "sarvam",
            "modelId": "internal-text-model",
            "apiMode": "chat_completions_v2",
        },
        "engines": [
            {
                "id": "internal-engine-id",
                "label": "Regional Expressive Engine",
                "models": [
                    {
                        "id": "internal-model-id",
                        "label": "Regional Speech Model",
                        "provider": "gemini",
                        "model": "gemini-3.1-flash-tts-preview",
                        "apiMode": "unary_rest",
                        "voices": [
                            {
                                "id": "internal-voice-id",
                                "label": "Telugu Assistant",
                                "providerVoiceId": "Zephyr",
                                "languages": ["te-IN"],
                            }
                        ],
                    }
                ],
            }
        ],
        "evidence": {key: True for key in profiles._EVIDENCE_KEYS},
    }


def _rates(tier: str = "low") -> dict:
    return {
        f"pstn_{tier}_rate_usd_micros_per_min": 12_000,
        f"pstn_{tier}_rate_inr_paise_per_min": 1_100,
        f"{tier}_rate_version": 7,
        "fx_rate_inr": 92.5,
    }


def _record(*, enabled: bool = True) -> dict:
    return {
        "revision": 4,
        "profile": _profile(enabled=enabled),
        "publicAliases": {
            "engines": {"internal-engine-id": "engine-a"},
            "models": {"internal-engine-id\u0000internal-model-id": "model-a"},
            "voices": {"internal-engine-id\u0000internal-model-id\u0000internal-voice-id": "voice-a"},
        },
    }


def test_profile_validation_keeps_drafts_disabled_and_rejects_secrets():
    valid = profiles.validate_composed_profile(_profile(enabled=True), tier="low")
    assert valid["enabled"] is False
    assert valid["evidence"] == {key: True for key in profiles._EVIDENCE_KEYS}

    secret = _profile()
    secret["llm"]["api_key"] = "test-only-placeholder"
    with pytest.raises(profiles.VoiceProfileError):
        profiles.validate_composed_profile(secret, tier="low")

    with pytest.raises(profiles.VoiceProfileError) as premium:
        profiles.validate_composed_profile(_profile(), tier="premium")
    assert premium.value.code == "read_only_tier"


def test_native_rate_and_runtime_readiness_gate_tenant_catalog(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    record = _record(enabled=True)

    readiness = profiles.readiness_for_profile("low", record, {"pstn_rate_usd_micros_per_min": 90_000})
    public = profiles.public_catalog_profile("low", record, {"pstn_rate_usd_micros_per_min": 90_000})

    assert readiness["ready"] is False
    assert "tier_native_rate_missing" in {item["code"] for item in readiness["blockers"]}
    assert public["ready"] is False
    assert public["engines"] == []

    monkeypatch.setattr(
        profiles,
        "_runtime_profile_blockers",
        lambda _profile: [{"code": "provider_not_ready", "message": "stage unavailable"}],
    )
    readiness = profiles.readiness_for_profile("low", record, _rates())
    public = profiles.public_catalog_profile("low", record, _rates())
    assert readiness["ready"] is False
    assert "provider_not_ready" in {item["code"] for item in readiness["blockers"]}
    assert public["ready"] is False
    assert public["engines"] == []


def test_public_catalog_uses_opaque_ids_and_safe_labels(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    public = profiles.public_catalog_profile("low", _record(), _rates())
    serialized = json.dumps(public)

    assert public["ready"] is True
    assert public["engines"][0]["id"] == "engine-a"
    assert public["engines"][0]["models"][0]["id"] == "model-a"
    assert public["engines"][0]["models"][0]["voices"][0]["id"] == "voice-a"
    for internal in (
        "internal-engine-id",
        "internal-model-id",
        "internal-voice-id",
        "internal-text-model",
        "gemini-3.1-flash-tts-preview",
        "Zephyr",
        "sarvam",
        "gemini",
    ):
        assert internal not in serialized


@pytest.mark.asyncio
async def test_resolved_selection_pins_exact_stages_revision_and_native_rate(monkeypatch):
    record = _record()
    rates = _rates()
    monkeypatch.setattr(profiles, "load_profile_records", _async_return({"low": record}))
    monkeypatch.setattr(profiles, "_load_rates_without_fallback", _async_return(rates))
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    selection = {
        "profileRevision": 4,
        "engineId": "engine-a",
        "modelId": "model-a",
        "voiceId": "voice-a",
    }

    stack, snapshot = await profiles.resolve_agent_selection(
        environment="test",
        tier="low",
        voice_settings=selection,
        language="te-IN",
    )

    assert stack["pipeline"] == "composed_voice"
    assert stack["stt"] == {
        "provider": "sarvam",
        "model": "saaras:v3-realtime",
        "config": {"mode": "realtime"},
    }
    assert stack["llm"]["model"] == "internal-text-model"
    assert stack["tts"]["provider"] == "gemini"
    assert stack["tts"]["model"] == "gemini-3.1-flash-tts-preview"
    assert stack["tts"]["config"]["speaker"] == "Zephyr"
    assert snapshot["profileRevision"] == 4
    assert snapshot["retailRate"]["version"] == 7

    stale = copy.deepcopy(selection)
    stale["profileRevision"] = 3
    with pytest.raises(profiles.VoiceProfileError) as conflict:
        await profiles.resolve_agent_selection(
            environment="test", tier="low", voice_settings=stale, language="te-IN"
        )
    assert conflict.value.code == "profile_revision_conflict"


def _async_return(value):
    async def _return(*_args, **_kwargs):
        return value

    return _return
