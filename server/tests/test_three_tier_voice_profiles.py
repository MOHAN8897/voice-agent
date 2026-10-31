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
            "modelId": "sarvam-105b-conversations",
            "apiMode": "chat_completions_v1",
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
    assert public["engines"][0]["models"][0]["audioStreaming"] is False
    assert public["engines"][0]["models"][0]["voices"][0]["id"] == "voice-a"
    for internal in (
        "internal-engine-id",
        "internal-model-id",
        "internal-voice-id",
        "sarvam-105b-conversations",
        "gemini-3.1-flash-tts-preview",
        "Zephyr",
        "sarvam",
        "gemini",
    ):
        assert internal not in serialized


@pytest.mark.parametrize("tier", ["low", "medium"])
def test_profile_accepts_documented_streaming_transport_and_reports_it(monkeypatch, tier):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    payload = _profile()
    payload["engines"][0]["models"][0]["apiMode"] = "streaming_rest"
    validated = profiles.validate_composed_profile(payload, tier=tier)
    assert validated["engines"][0]["models"][0]["apiMode"] == "streaming_rest"
    record = _record()
    record["profile"] = {**validated, "enabled": True}
    public = profiles.public_catalog_profile(tier, record, _rates(tier))
    assert public["engines"][0]["models"][0]["audioStreaming"] is True


def test_profile_refuses_streaming_transport_for_unary_only_model():
    payload = _profile()
    payload["engines"][0]["models"][0].update(
        model="gemini-2.5-flash-preview-tts", apiMode="streaming_rest"
    )
    with pytest.raises(profiles.VoiceProfileError, match="does not support streaming"):
        profiles.validate_composed_profile(payload, tier="low")


def test_public_catalog_scrubs_internal_labels_and_does_not_invent_voice_samples(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    record = _record()
    engine = record["profile"]["engines"][0]
    engine["label"] = "Sarvam voice engine"
    engine["models"][0]["label"] = "Gemini TTS"
    engine["models"][0]["voices"][0]["label"] = "https://internal.example/voice"
    public = profiles.public_catalog_profile("low", record, _rates())
    serialized = json.dumps(public).lower()
    assert "sarvam" not in serialized
    assert "gemini" not in serialized
    assert "https://" not in serialized
    voice = public["engines"][0]["models"][0]["voices"][0]
    assert voice["label"] == "Voice 1"
    assert voice["previewUrl"] is None
    # Operator labels never reach tenants, even harmless-looking ones.
    assert public["engines"][0]["label"] == "Voice engine 1"
    assert public["engines"][0]["models"][0]["label"] == "Speech model 1"


def test_public_catalog_scrubs_operator_tier_label(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    record = _record()
    record["profile"]["label"] = "Sarvam Bulbul v4 Flash Stack"
    public = profiles.public_catalog_profile("low", record, _rates())
    assert public["label"] == "Economical"


@pytest.mark.asyncio
async def test_catalog_route_attaches_opaque_stored_sample_urls(monkeypatch):
    from fastapi import BackgroundTasks
    from server.routes import voice_stacks

    record = _record()
    record["publicAliases"]["voices"] = {
        "internal-engine-id\u0000internal-model-id\u0000internal-voice-id": "voc_voice_a",
    }
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])

    async def load_records(_environment, _tiers):
        return {"low": record}

    async def load_rates():
        return _rates()

    monkeypatch.setattr(voice_stacks, "load_profile_records", load_records)
    monkeypatch.setattr(voice_stacks, "_load_rates_without_fallback", load_rates)
    monkeypatch.setattr("server.services.dev_runtime.effective_app_environment", lambda: "test")

    background = BackgroundTasks()
    result = await voice_stacks.voice_stack_catalog(language="te-IN", background=background)

    voice = result["profiles"][0]["engines"][0]["models"][0]["voices"][0]
    assert voice["previewUrl"] == "/api/telephony/voice-preview/catalog?voiceId=voc_voice_a&language=te-IN"
    assert [task.func.__name__ for task in background.tasks] == ["schedule_preview_warm"]
    serialized = json.dumps(result).lower()
    for internal in ("gemini", "sarvam", "zephyr", "internal-voice-id"):
        assert internal not in serialized


def test_public_catalog_expands_every_v4_voice_for_a_supported_language(monkeypatch):
    from server.providers import voice_inventory

    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    record = _record()
    model = record["profile"]["engines"][0]["models"][0]
    model.update({"provider": "sarvam", "model": "bulbul:v4-flash", "apiMode": "websocket", "voices": []})
    expanded = profiles.expand_model_voices("low", record)
    voices = expanded["profile"]["engines"][0]["models"][0]["voices"]
    expected = voice_inventory.voices_for_model("sarvam", "bulbul:v4-flash")
    assert len(voices) == len(expected) > 200
    public = profiles.public_catalog_profile("low", expanded, _rates())
    public_voices = public["engines"][0]["models"][0]["voices"]
    assert len(public_voices) == len(expected)
    assert len({voice["id"] for voice in public_voices}) == len(expected)
    assert all("te-IN" in voice["languages"] for voice in public_voices)
    assert all(voice["id"].startswith("voc_") for voice in public_voices)


@pytest.mark.asyncio
async def test_tenant_catalog_reports_complete_inventory_without_truncating_language_matches(monkeypatch):
    from server.routes import voice_stacks

    record = _record()
    record["profile"]["supportedLanguages"] = ["te-IN", "hi-IN"]
    model = record["profile"]["engines"][0]["models"][0]
    model["voices"] = [
        {"id": f"internal-{index}", "providerVoiceId": f"private-{index}", "label": "Internal label",
         "languages": ["te-IN"] if index < 60 else ["hi-IN"]}
        for index in range(70)
    ]
    record["publicAliases"] = profiles._choice_keys(record["profile"])
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    monkeypatch.setattr(voice_stacks, "load_profile_records", _async_return({"low": record}))
    monkeypatch.setattr(voice_stacks, "_load_rates_without_fallback", _async_return(_rates()))
    monkeypatch.setattr("server.services.dev_runtime.effective_app_environment", lambda: "test")
    result = await voice_stacks.voice_stack_catalog(language="te-IN")
    profile = result["profiles"][0]
    assert profile["voiceInventory"] == {"totalVoices": 70, "voicesByLanguage": {"te-IN": 60, "hi-IN": 10}}
    public_voices = profile["engines"][0]["models"][0]["voices"]
    assert len(public_voices) == 60
    assert len({voice["id"] for voice in public_voices}) == 60
    assert all(voice["languages"] == ["te-IN"] for voice in public_voices)
    assert "private-" not in json.dumps(result) and "internal-" not in json.dumps(result)


@pytest.mark.parametrize(
    ("raw_gender", "expected"),
    [("Female", "female"), ("feminine", "female"), ("MALE", "male"),
     ("masculine", "male"), ("Neutral", "neutral"), ("gender_neutral", "neutral"), ("", ""), ("unknown", "")],
)
def test_public_catalog_normalizes_gender_without_guessing(monkeypatch, raw_gender, expected):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    record = _record()
    record["profile"]["engines"][0]["models"][0]["voices"][0]["gender"] = raw_gender
    public = profiles.public_catalog_profile("low", record, _rates())
    assert public["engines"][0]["models"][0]["voices"][0]["gender"] == expected


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
    assert stack["llm"]["model"] == "sarvam-105b-conversations"
    assert stack["tts"]["provider"] == "gemini"
    assert stack["tts"]["model"] == "gemini-3.1-flash-tts-preview"
    assert stack["tts"]["config"]["speaker"] == "Zephyr"
    assert snapshot["profileRevision"] == 4
    assert snapshot["retailRate"]["version"] == 7

    # An older revision whose aliases still resolve stays callable (admin knob
    # and price edits bump the revision without changing the agent's choice).
    stale = copy.deepcopy(selection)
    stale["profileRevision"] = 3
    _stack, stale_snapshot = await profiles.resolve_agent_selection(
        environment="test", tier="low", voice_settings=stale, language="te-IN"
    )
    assert stale_snapshot["profileRevision"] == 4

    # A removed choice on an older revision is still a revision conflict.
    removed = {**stale, "voiceId": "voice-removed"}
    with pytest.raises(profiles.VoiceProfileError) as conflict:
        await profiles.resolve_agent_selection(
            environment="test", tier="low", voice_settings=removed, language="te-IN"
        )
    assert conflict.value.code == "profile_revision_conflict"


def test_choice_keys_uses_colons_without_nul_bytes():
    profile = _profile()
    aliases = profiles._choice_keys(profile)
    for model_key in aliases["models"]:
        assert "\u0000" not in model_key
        assert "::" in model_key
    for voice_key in aliases["voices"]:
        assert "\u0000" not in voice_key
        assert "::" in voice_key


def test_public_catalog_supports_both_colon_and_legacy_nul_delimiters(monkeypatch):
    monkeypatch.setattr(profiles, "_runtime_profile_blockers", lambda _profile: [])
    # Colon delimited
    record_colon = {
        "revision": 1,
        "profile": _profile(enabled=True),
        "publicAliases": {
            "engines": {"internal-engine-id": "engine-colon"},
            "models": {"internal-engine-id::internal-model-id": "model-colon"},
            "voices": {"internal-engine-id::internal-model-id::internal-voice-id": "voice-colon"},
        },
    }
    public_colon = profiles.public_catalog_profile("low", record_colon, _rates())
    assert public_colon["ready"] is True
    assert public_colon["engines"][0]["id"] == "engine-colon"
    assert public_colon["engines"][0]["models"][0]["id"] == "model-colon"
    assert public_colon["engines"][0]["models"][0]["voices"][0]["id"] == "voice-colon"

    # Legacy NUL delimited fallback
    record_nul = {
        "revision": 2,
        "profile": _profile(enabled=True),
        "publicAliases": {
            "engines": {"internal-engine-id": "engine-nul"},
            "models": {"internal-engine-id\u0000internal-model-id": "model-nul"},
            "voices": {"internal-engine-id\u0000internal-model-id\u0000internal-voice-id": "voice-nul"},
        },
    }
    public_nul = profiles.public_catalog_profile("low", record_nul, _rates())
    assert public_nul["ready"] is True
    assert public_nul["engines"][0]["id"] == "engine-nul"
    assert public_nul["engines"][0]["models"][0]["id"] == "model-nul"
    assert public_nul["engines"][0]["models"][0]["voices"][0]["id"] == "voice-nul"


def _async_return(value):
    async def _return(*_args, **_kwargs):
        return value

    return _return

