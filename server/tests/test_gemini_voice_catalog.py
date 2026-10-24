from types import SimpleNamespace

import pytest

from server.services.saas import voice_catalog
from server.realtime.models import GEMINI_LIVE_LIBRARY_VOICES, GEMINI_LIVE_VOICES
from server.services.saas.voice_preview import resolve_preview_voice


def test_catalog_exposes_all_published_featured_voices_without_invented_categories():
    from server.providers.voice_inventory import voices_for_model
    rows = [row for row in voice_catalog.phone_voice_catalog() if row.get("provider") == "gemini"]
    featured = voices_for_model("gemini", "gemini-3.1-flash-tts-preview")
    assert {row["providerVoiceId"] for row in featured} <= {row["providerVoiceId"] for row in rows}
    assert len(featured) == 30
    assert all(row.get("tone") for row in featured)


def test_featured_gemini_voices_get_documented_genders_without_overriding_api_values():
    from server.providers.voice_inventory import _gemini_gender, voices_for_model

    rows = {row["id"]: row for row in voices_for_model("gemini", "gemini-3.1-flash-tts-preview")}
    assert rows["Zephyr"]["gender"] == "female"
    assert rows["Kore"]["gender"] == "female"
    assert rows["Puck"]["gender"] == "male"
    assert rows["Charon"]["gender"] == "male"
    assert all(row["gender"] for row in rows.values())
    # The API remains authoritative when it publishes a gender.
    assert _gemini_gender({"id": "Zephyr", "gender": "male"}) == "male"


def test_direct_gemini_voice_id_resolves_to_the_selected_voice():
    voice, label = resolve_preview_voice("zephyr", provider="gemini")

    assert voice == "Zephyr"
    assert label == "Zephyr"

    voice, label = resolve_preview_voice("kore", provider="gemini")
    assert voice == "Kore"
    assert label == "Kore"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model", "expected_voice_provider"),
    [
        ("openai", "gpt-realtime-2.1-mini", "openai"),
        ("gemini", "gemini-3.8-live", "gemini"),
    ],
)
async def test_voice_options_expose_direct_gemini_voices_and_hide_them_for_openai(
    monkeypatch, provider, model, expected_voice_provider
):
    from server.routes import app_telephony
    from server.services.saas import platform_languages, platform_phone_stack

    rows = [
        {"id": "marin", "provider": "openai"},
        {"id": "zephyr", "provider": "gemini"},
    ]
    monkeypatch.setattr(platform_languages, "language_options", lambda: [{"code": "te-IN", "label": "Telugu"}])

    async def resolve_stack(_language):
        return {"llm": {"provider": provider, "model": model}}

    monkeypatch.setattr(platform_phone_stack, "resolve_platform_phone_stack", resolve_stack)
    monkeypatch.setattr(app_telephony, "phone_voice_catalog", lambda: rows)

    response = SimpleNamespace(headers={})
    result = await app_telephony.telephony_voice_options(response, principal=SimpleNamespace())

    providers = {voice["provider"] for voice in result["voices"]}
    assert result["activeVoiceProvider"] == expected_voice_provider
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert expected_voice_provider in providers
    if expected_voice_provider == "gemini":
        # Keep the OpenAI catalog aliases in the response: existing saved agent
        # IDs use those rows to resolve their Gemini equivalent in the UI.
        assert {voice["id"] for voice in result["voices"] if voice["provider"] == "gemini"} == {"zephyr"}
        assert "marin" in {voice["id"] for voice in result["voices"] if voice["provider"] == "openai"}
        gemini_voice = next(voice for voice in result["voices"] if voice["id"] == "zephyr")
        assert gemini_voice["previewUrl"] == "/api/telephony/voice-preview/live?voiceId=zephyr&language=te-IN"
        assert all("previewUrl" not in voice for voice in result["voices"] if voice["provider"] != "gemini")
    else:
        assert "gemini" not in providers
        assert all(voice.get("previewUrl") == "/api/telephony/voice-preview/live?voiceId=marin&language=te-IN"
                   for voice in result["voices"])
