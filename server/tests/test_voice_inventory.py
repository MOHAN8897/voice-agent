"""Supplier catalog compatibility, complete pagination and stable tenant aliases."""
from __future__ import annotations

import copy
import json

import httpx
import pytest

from server.providers import voice_inventory as catalog


@pytest.mark.parametrize("provider,model,voice,language", [
    ("sarvam", "bulbul:v4-flash", "shubh", "te-IN"),
    ("sarvam", "bulbul:v3", "shubh_enhi_ads", "te-IN"),
    ("sarvam", "bulbul:v4-flash", "shubh_enhi_ads", "as-IN"),
    ("gnani", "timbre-v3.0", "Nalini", "te-IN"),
    ("gnani", "timbre-v2.5", "Shivani", "te-IN"),
    ("gnani", "timbre-v2.5", "Nalini", "te-IN"),
    ("gemini", "gemini-2.0-flash", "Puck", "te-IN"),
    ("cartesia", "sonic-3.5", "97303aad-0000-0000-0000-000000000000", "te-IN"),
])
def test_incompatible_model_voice_language_is_rejected(provider, model, voice, language):
    with pytest.raises(ValueError):
        catalog.validate_voice(provider, model, voice, language)


def test_gnani_selection_is_case_insensitive_and_language_scoped():
    from server.providers.voice_inventory import default_voice
    from server.services.gnani_tts_ws import _resolve_gnani_voice

    assert _resolve_gnani_voice("lakshmi", model="timbre-v3.0", language="te-IN") == "Lakshmi"
    assert _resolve_gnani_voice("POORVI", model="timbre-v2.5", language="hi-IN") == "Poorvi"
    # A published voice that cannot speak the requested language resolves to the
    # model's catalog default instead of an invalid supplier tuple.
    assert _resolve_gnani_voice("Nalini", model="timbre-v2.5", language="te-IN") == default_voice(
        "gnani", "timbre-v2.5", "te-IN")
    # Generic and cross-model IDs never pass through to the supplier.
    for voice in ("Nalini", "Pranav", "voice-gnani-1", "unknown"):
        assert _resolve_gnani_voice(voice, model="timbre-v3.0", language="te-IN") == default_voice(
            "gnani", "timbre-v3.0", "te-IN")
    assert catalog.validate_voice("gnani", "timbre-v2.5", "Lavanya", "te-IN")


def test_v4_voice_languages_follow_published_ids_and_repair_legacy_rows():
    assert catalog.v4_voice_languages("kavitha_te_conversation") == ["te-IN"]
    assert catalog.v4_voice_languages("shubh_enhi_ads") == ["hi-IN", "en-IN"]
    assert catalog.v4_voice_languages("anushka") is None
    data = {"sarvam": {"models": {"bulbul:v4-flash": [
        {"id": "kavitha_te_conversation", "providerVoiceId": "kavitha_te_conversation",
         "languages": ["te-IN", "hi-IN", "en-IN"]},
        {"id": "shubh_enhi_ads", "providerVoiceId": "shubh_enhi_ads", "languages": ["hi-IN"]},
    ]}}}
    catalog._repair_v4_rows(data)
    rows = data["sarvam"]["models"]["bulbul:v4-flash"]
    supported = sorted(code for code in __import__("server.config.constants", fromlist=["constants"]).constants.SUPPORTED_LANGUAGES if code.endswith("-IN"))
    assert rows[0]["languages"] == supported
    assert rows[0]["preferredLanguages"] == ["te-IN"]
    assert rows[1]["languages"] == supported
    assert rows[1]["preferredLanguages"] == ["hi-IN", "en-IN"]


def test_default_voice_is_model_and_language_scoped():
    from server.config.constants import constants
    from server.providers.voice_inventory import default_voice, profile_voice_rows

    assert default_voice("sarvam", "bulbul:v4-flash", "te-IN") == "kavitha_te_conversation"
    assert default_voice("sarvam", "bulbul:v3", "te-IN") == "shubh"
    assert default_voice("cartesia", "sonic-3.5", "te-IN") == "47c38ca4-5f35-497b-b1a3-415245fb35e1"
    with pytest.raises(ValueError, match="No sarvam voice"):
        default_voice("sarvam", "bulbul:v4-flash", "fr-FR")
    indian = {code for code in constants.SUPPORTED_LANGUAGES if code.endswith("-IN")}
    cartesia = catalog.voices_for_model("cartesia", "sonic-3.5")
    assert len(cartesia) >= 100
    assert all(row["languages"] and set(row["languages"]) <= indian for row in cartesia)
    assert all("te-IN" in row["languages"] for row in profile_voice_rows("cartesia", "sonic-3.5", ["te-IN"]))


def test_stale_sarvam_2b_is_not_advertised_or_priced():
    from server.config.env import get_settings
    from server.services.saas.composed_costing import default_provider_rates

    assert "sarvam-2b" not in get_settings().allowed_sarvam_llm_models
    assert all(rate["model"] != "sarvam-2b" for rate in default_provider_rates())


def test_cartesia_uses_actual_indian_locale_mappings_not_names():
    voice = {"id": "provider-id", "name": "Indian Telugu narrator", "language": "en", "country": "US"}
    assert catalog.normalize_cartesia_voice(voice) is None
    row = catalog.normalize_cartesia_voice({**voice, "accents": [{"locale": "hi-IN"}, {"locale": "te-IN"}]})
    assert row["languages"] == ["hi-IN", "te-IN"]
    assert not row["category"]  # No invented conversational/promotional category.
    assert catalog.normalize_cartesia_voice({**voice, "language": "te", "status": "inactive"}) is None
    assert catalog.normalize_cartesia_voice({**voice, "language": "te", "access": "private"}) is None


@pytest.mark.asyncio
async def test_gemini_pagination_uses_snake_case_and_excludes_custom_voices():
    requests = []
    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            assert request.url.params["page_size"] == "100"
            return httpx.Response(200, json={"voices": [{"id": "te-first", "type": "prebuilt", "language_code": "te-IN"},
                {"id": "private-custom", "type": "prompted"}], "next_page_token": "page-two"})
        assert request.url.params["page_token"] == "page-two"
        return httpx.Response(200, json={"voices": [{"id": "te-second", "type": "prebuilt", "language_code": "te-IN"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rows = await catalog._api_voices(client, "gemini", "test-key")
    assert [row["id"] for row in rows] == ["te-first", "te-second"]


@pytest.mark.asyncio
async def test_incomplete_or_repeating_catalog_page_fails():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200,
        json={"data": [{"id": "last", "language": "te"}], "has_more": True, "next_page": "repeat"}))) as client:
        with pytest.raises(ValueError, match="repeated"):
            await catalog._api_voices(client, "cartesia", "test-key")


def test_featured_gemini_voice_retains_identity_and_multilingual_capability(monkeypatch):
    data = copy.deepcopy(catalog.inventory())
    data["gemini"]["voices"] = [{"id": "puck", "providerVoiceId": "puck", "languages": ["en-US"], "category": "Conversational"},
        {"id": "te-regional", "providerVoiceId": "te-regional", "languages": ["te-IN"]}]
    monkeypatch.setattr(catalog, "inventory", lambda: data)
    assert catalog.validate_voice("gemini", "gemini-3.8-flash-lite-tts", "Puck", "te-IN")["category"] == "Conversational"
    with pytest.raises(ValueError):
        catalog.validate_voice("gemini", "gemini-2.5-flash-preview-tts", "te-regional", "te-IN")
    assert catalog.validate_voice("gemini", "gemini-3.8-live", "te-regional", "te-IN")


def test_read_through_expansion_preserves_saved_alias_and_revision():
    from server.services.saas.voice_stack_profiles import expand_model_voices
    record = {"revision": 8, "profile": {"supportedLanguages": ["te-IN"], "engines": [{"id": "engine", "models": [{"id": "model",
        "provider": "gnani", "model": "timbre-v3.0", "voices": [{"id": "saved", "providerVoiceId": "Shivani"}]}]}]},
        "publicAliases": {"voices": {"engine::model::saved": "voc_saved"}}}
    before = copy.deepcopy(record)
    expanded = expand_model_voices("custom", record)
    assert record == before
    assert expanded["revision"] == 8
    assert expanded["publicAliases"]["voices"]["engine::model::saved"] == "voc_saved"
    assert len(expanded["profile"]["engines"][0]["models"][0]["voices"]) == 13
    assert expanded == expand_model_voices("custom", record)


@pytest.mark.asyncio
async def test_live_sarvam_inventory_reconciles_every_speaker_without_synthesizing():
    previous = catalog.voices_for_model("sarvam", "bulbul:v4-flash")
    names = list(dict.fromkeys([row["providerVoiceId"] for row in previous] + ["kangkana_as_conversational", "mouchumi_as_conversational"]))
    requests = []

    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["speaker"] == "__catalog_discovery_invalid__"
        assert body["model"] == "bulbul:v4-flash"
        assert body["language_code"] == "en-IN"
        return httpx.Response(400, json={"error": {"message":
            "Speaker is not recognized. Available speakers for bulbul:v4-flash are: " + ", ".join(reversed(names))}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        rows = await catalog._sarvam_api_voices(client, "test-key", [row for row in previous if row["languages"]])
    assert len(requests) == 1
    assert {row["providerVoiceId"] for row in rows} == set(names)
    assert [row["providerVoiceId"] for row in rows] == [row["providerVoiceId"] for row in previous]
    supported = {code for code in __import__("server.config.constants", fromlist=["constants"]).constants.SUPPORTED_LANGUAGES if code.endswith("-IN")}
    assert all(set(row["languages"]) == supported for row in rows)
    assert sum("te-IN" in row["languages"] for row in rows) == len(rows)
    kavitha = next(row for row in rows if row["providerVoiceId"] == "kavitha_te_conversation")
    assert kavitha["gender"] == "female" and kavitha["preferredLanguages"] == ["te-IN"]
    assamese = [row for row in rows if row["providerVoiceId"].startswith(("kangkana_", "mouchumi_"))]
    assert len(assamese) == 2 and all(row["preferredLanguages"] == ["as-IN"] for row in assamese)
    assert all("selectable" not in row and "unavailableReason" not in row for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"error": {"message": "Authentication error"}},
    {"error": {"message": "Available speakers for bulbul:v4-flash are: kavitha_te_conversation"}},
    {"error": "Unexpected validation response"},
])
async def test_sarvam_inventory_refuses_incomplete_or_unrecognized_error_responses(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(400, json=body))) as client:
        with pytest.raises(ValueError, match="inventory"):
            await catalog._sarvam_api_voices(client, "test-key", [])


def test_every_provider_v4_voice_reaches_the_tenant_for_a_supported_language():
    provider_rows = catalog.voices_for_model("sarvam", "bulbul:v4-flash")
    admin_rows = catalog.profile_voice_rows("sarvam", "bulbul:v4-flash", ["te-IN"], include_unavailable=True)
    tenant_rows = catalog.profile_voice_rows("sarvam", "bulbul:v4-flash", ["te-IN"])
    assert len(provider_rows) == len(admin_rows) == len(tenant_rows) == len(provider_rows)
    assert [row["providerVoiceId"] for row in tenant_rows] == [row["providerVoiceId"] for row in provider_rows]
    assert all(row["languages"] == ["te-IN"] for row in tenant_rows)
    assert {row["providerVoiceId"] for row in tenant_rows} >= {"kavitha_te_conversation", "kangkana_as_conversational"}


def test_empty_catalog_fails_readiness_before_registry_lookup():
    from server.services.saas.voice_stack_profiles import _runtime_profile_blockers
    assert _runtime_profile_blockers({"engines": []})[0]["code"] == "speech_voice_mismatch"


@pytest.mark.asyncio
async def test_failed_refresh_retains_verified_api_catalog(monkeypatch, tmp_path):
    from server.services.dev_secrets_store import dev_secrets_store
    data = copy.deepcopy(catalog.inventory())
    data["cartesia"] = {"voices": [{"id": "verified", "languages": ["te-IN"]}]}
    monkeypatch.setattr(catalog, "inventory", lambda: data)
    monkeypatch.setattr(catalog, "_cache_path", lambda: tmp_path / "inventory.json")
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda field: "test-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(catalog.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(503)), **kw))
    report = await catalog.refresh_inventory()
    assert report["errors"]
    saved = json.loads((tmp_path / "inventory.json").read_text(encoding="utf-8"))
    assert saved["cartesia"]["voices"][0]["id"] == "verified"


def test_gnani_hinglish_voice_uses_supplier_language_alias():
    assert catalog.provider_language("gnani", "timbre-v2.5", "Poorvi", "hi-IN") == "hi-en"
    with pytest.raises(ValueError):
        catalog.provider_language("gnani", "timbre-v2.5", "Poorvi", "te-IN")


def test_alias_cache_never_matches_same_voice_id_in_another_model():
    from server.services.saas import voice_stack_profiles as profiles
    record = {"profile": {"engines": [{"id": "engine", "models": [
        {"id": "one", "provider": "gnani", "model": "timbre-v3.0", "voices": [{"id": "shared-id", "providerVoiceId": "Shivani"}]},
        {"id": "two", "provider": "sarvam", "model": "bulbul:v3", "voices": [{"id": "shared-id", "providerVoiceId": "shubh"}]},
    ]}]}, "publicAliases": {"voices": {"engine::one::shared-id": "voc_g", "engine::two::shared-id": "voc_s"}}}
    profiles.cache_aliases_from_record("test", record)
    assert profiles.lookup_cached_voice_alias("voc_g")["providerVoiceId"] == "Shivani"
    assert profiles.lookup_cached_voice_alias("voc_s")["providerVoiceId"] == "shubh"


@pytest.mark.asyncio
async def test_sarvam_preview_forwards_selected_model_without_tier_override(monkeypatch):
    from server.services.saas import voice_preview
    calls = []
    async def synthesize(**kwargs):
        calls.append(kwargs)
        return {"audio_bytes": b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40}
    monkeypatch.setattr("server.services.sarvam_tts_service.synthesize", synthesize)
    await voice_preview._synthesize_sarvam("Hello", "shubh_enhi_ads", 1, language="te-IN", model="bulbul:v4-flash")
    assert calls[0]["model"] == "bulbul:v4-flash"
    assert calls[0]["speaker"] == "shubh_enhi_ads"


def test_validation_materializes_inventory_once_and_refresh_invalidates_it(monkeypatch):
    from unittest.mock import Mock
    data = copy.deepcopy(catalog.inventory())
    monkeypatch.setattr(catalog, "inventory", lambda: data)
    materialize = Mock(wraps=catalog.voices_for_model)
    monkeypatch.setattr(catalog, "voices_for_model", materialize)
    for _ in range(100):
        catalog.validate_voice("gnani", "timbre-v3.0", "Shivani", "te-IN")
    assert materialize.call_count == 1
    data["gnani"]["models"]["timbre-v3.0"] = []
    with pytest.raises(ValueError):
        catalog.validate_voice("gnani", "timbre-v3.0", "Shivani", "te-IN")


def test_fresh_import_of_voice_services_has_no_registry_cycle():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c", "import server.services.cartesia_voices; import server.services.saas.pstn_saas_stack"], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
