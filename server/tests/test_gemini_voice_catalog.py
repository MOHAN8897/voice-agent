from types import SimpleNamespace

import pytest

from server.services.saas import voice_catalog
from server.realtime.models import GEMINI_LIVE_LIBRARY_VOICES, GEMINI_LIVE_VOICES
from server.services.saas.voice_preview import resolve_preview_voice


def test_catalog_exposes_all_gemini_live_voices_when_configured(monkeypatch):
    monkeypatch.setattr(
        voice_catalog,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key="configured", enable_gemini=False),
    )

    rows = voice_catalog.phone_voice_catalog()
    gemini_rows = [row for row in rows if row.get("provider") == "gemini"]

    assert len(gemini_rows) == len(GEMINI_LIVE_VOICES) + len(GEMINI_LIVE_LIBRARY_VOICES)
    assert {
        row["geminiVoice"] for row in gemini_rows if not row.get("languageCode")
    } == set(GEMINI_LIVE_VOICES)
    assert {
        row["id"] for row in gemini_rows if row.get("languageCode")
    } == set(GEMINI_LIVE_LIBRARY_VOICES)
    assert all(row.get("accent") and row.get("sampleText") for row in gemini_rows if row.get("languageCode"))


def test_direct_gemini_voice_id_resolves_to_the_selected_live_voice(monkeypatch):
    monkeypatch.setattr(
        voice_catalog,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key="configured", enable_gemini=False),
    )

    voice, label = resolve_preview_voice("alnilam")

    assert voice == "Alnilam"
    assert label == "Alnilam"

    voice, label = resolve_preview_voice("te-in-csagent-5")
    assert voice == "te-in-csagent-5"
    assert label == "Telugu · Female"


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

    result = await app_telephony.telephony_voice_options(SimpleNamespace())

    providers = {voice["provider"] for voice in result["voices"]}
    assert expected_voice_provider in providers
    if expected_voice_provider == "gemini":
        # Keep the OpenAI catalog aliases in the response: existing saved agent
        # IDs use those rows to resolve their Gemini equivalent in the UI.
        assert {voice["id"] for voice in result["voices"] if voice["provider"] == "gemini"} == {"zephyr"}
        assert "marin" in {voice["id"] for voice in result["voices"] if voice["provider"] == "openai"}
    else:
        assert "gemini" not in providers
