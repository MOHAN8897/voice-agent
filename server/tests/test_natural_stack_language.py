"""Locale/register and model capabilities must reach the actual call speech paths."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.brain.compiled_brain_artifact import assemble_unified_brain, refresh_platform_sections
from server.prompts.agent_voice_rules import LANGUAGE_LOCK, spoken_pack_for
from server.prompts.spoken_locale_style import SPOKEN_LOCALES
from server.prompts.tts_delivery_rules import (
    GNANI_V3_TAGS,
    sanitize_tts_tags,
    supports_inline_audio_tags,
)
from server.providers.base import StageSelection, TTSConfig
from server.services.composed_voice_session import composed_system_prompt
from server.services.spoken_numbers import prepare_spoken_reply

MODELS = [
    ("sarvam", "bulbul:v3"), ("sarvam", "bulbul:v4-flash"),
    ("gemini", "gemini-3.8-flash-tts"), ("gemini", "gemini-3.8-flash-lite-tts"),
    ("gnani", "timbre-v3.0"), ("gnani", "timbre-v2.5"), ("gnani", "timbre-future"),
    ("cartesia", "sonic-3.5"),
]


def context(locale, provider, model, tier="medium"):
    return SimpleNamespace(pipeline="composed_voice", tier=tier,
        compiled_brain_text=assemble_unified_brain(language=locale,
            script="--- AGENT IDENTITY ---\nYou are Sam from Acme.\n--- COMPANY & OFFER ---\nHours are 09:00 to 18:00.\n<pauses> Approved details only."),
        compiled_brain_version="same-approved-script",
        resolved_stack=SimpleNamespace(language=locale, tier=tier, combination_id=f"{tier}-selection",
            llm=StageSelection("sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"}),
            tts=StageSelection(provider, model, {"api_mode": "websocket", "speaker": "selected-voice"})))


@pytest.mark.parametrize("locale", tuple(SPOKEN_LOCALES))
@pytest.mark.parametrize("provider,model", MODELS)
def test_selected_locale_and_tts_model_are_compiled_together(locale, provider, model):
    ctx = context(locale, provider, model, tier="custom_standard")
    original = ctx.compiled_brain_text
    prompt = composed_system_prompt(ctx)
    style = SPOKEN_LOCALES[locale]
    assert prompt.count(f"--- SPOKEN LANGUAGE ({locale}) ---") == 1
    assert prompt.count(LANGUAGE_LOCK[locale]) == 1
    assert style.clarification in prompt and style.unknown in prompt
    assert "Hours are 09:00 to 18:00" in prompt
    assert ctx.compiled_brain_text == original
    if supports_inline_audio_tags(provider, model):
        assert "[Gnani Audio Tags Expressive Guidelines]" in prompt
        assert "<pauses>" in prompt and "at most one tag" in prompt
        assert "no closing tag" in prompt
    else:
        assert "[Gnani Audio Tags Expressive Guidelines]" not in prompt
        assert "<pauses>" not in prompt and "<excited>" not in prompt
        assert "No inline audio tags" in prompt
    if provider == "sarvam":
        assert ("v4 Flash" if "v4" in model else "v3") in prompt


@pytest.mark.parametrize("locale", tuple(SPOKEN_LOCALES))
def test_compact_packs_keep_local_examples_and_never_translate_to_another_language(locale):
    core = spoken_pack_for(locale, include_brevity=False, core_only=True)
    assert SPOKEN_LOCALES[locale].clarification in core
    assert SPOKEN_LOCALES[locale].unknown in core
    assert "CONVERSATIONAL REGISTER" in core
    assert "VOICE EXAMPLES" not in core
    if not locale.startswith("en-"):
        assert f"native {SPOKEN_LOCALES[locale].script} script" in core
        assert "Latin script for English" in core
    if locale == "te-IN":
        assert "Telugu-English" in core and "Tanglish" not in core


def test_prompt_cache_follows_tier_model_and_language_without_pinning_an_old_provider():
    ctx = context("te-IN", "gnani", "timbre-v3.0", "low")
    first = composed_system_prompt(ctx)
    assert composed_system_prompt(ctx) is first
    ctx.resolved_stack.tts = StageSelection("gnani", "timbre-v2.5", {})
    assert "<pauses>" not in composed_system_prompt(ctx)
    snapshot = ctx.composed_prompt_snapshot
    ctx.resolved_stack.tier = "custom_low"
    composed_system_prompt(ctx)
    assert ctx.composed_prompt_snapshot is not snapshot
    ctx.resolved_stack.language = "hi-IN"
    assert "CONVERSATIONAL REGISTER (hi-IN)" in composed_system_prompt(ctx)
    assert "CONVERSATIONAL REGISTER (te-IN)" not in composed_system_prompt(ctx)


@pytest.mark.parametrize("locale", tuple(SPOKEN_LOCALES))
@pytest.mark.parametrize("model", ["gemini-3.8-live", "gpt-realtime-2.1-mini"])
@pytest.mark.parametrize("legacy", [False, True])
def test_native_audio_ignores_separate_tts_slots_and_uses_natural_tag_free_speech(locale, model, legacy):
    from server.realtime.voice_instructions import build_realtime_voice_instructions

    ctx = context(locale, "gnani", "timbre-v3.0", "premium")
    brain = "--- AGENT IDENTITY ---\nYou are Sam from Acme." if legacy else ctx.compiled_brain_text
    prompt = build_realtime_voice_instructions(brain, language=locale, model=model, direction="inbound")
    assert "[Native audio delivery]" in prompt
    assert "<pauses>" not in prompt and "Gnani Audio Tags" not in prompt
    assert SPOKEN_LOCALES[locale].clarification in prompt
    assert "Acme" in prompt


@pytest.mark.parametrize("provider,model", MODELS)
def test_final_spoken_reply_allows_only_matching_model_tags(provider, model):
    text = "సరే అండి.<pauses> ఏ details కావాలి? <unknown> [laughs]"
    prepared = prepare_spoken_reply(text, provider=provider, model=model)
    assert "ఏ details కావాలి?" in prepared
    assert "<unknown>" not in prepared and "[laughs]" not in prepared
    assert (" <pauses> " in prepared) == supports_inline_audio_tags(provider, model)
    assert sanitize_tts_tags("<pauses><slow>", provider=provider, model=model) == ""


@pytest.mark.parametrize("tag", sorted(GNANI_V3_TAGS))
def test_only_exact_documented_tag_spelling_survives(tag):
    assert f"<{tag}>" in sanitize_tts_tags(f"First. <{tag}> Next sentence.", provider="gnani", model="timbre-v3.0")
    assert "<" not in sanitize_tts_tags(f"First. <{tag.upper()}> Next sentence.", provider="gnani", model="timbre-v3.0")
    assert "<" not in sanitize_tts_tags(f"First. <{tag}> Next sentence.", provider="gnani")


def test_completed_turn_finalizer_keeps_v3_tags_and_strips_them_after_switch():
    from server.call.live_turn_orchestrator import finalize_live_spoken_text

    ctx = context("te-IN", "gnani", "timbre-v3.0")
    text = "ఆ విషయం నాకు తెలియదు అండి. <pauses> ఏ details కావాలి?"
    assert "<pauses>" in finalize_live_spoken_text("more details", text, ctx=ctx)
    ctx.resolved_stack.tts = StageSelection("sarvam", "bulbul:v3", {})
    assert "<" not in finalize_live_spoken_text("more details", text, ctx=ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model", MODELS[:6])
async def test_actual_turn_tts_socket_receives_only_selected_model_markup(provider, model):
    from server.services.pstn_turn_tts import PstnTurnTtsSession

    voice = SimpleNamespace(call_id=None, current_generation_id="g", _interrupted_generation=None,
        _closed=False, sample_rate=16000, current_turn_id="t", emission_blocked=lambda: False)
    session = PstnTurnTtsSession(voice)
    session._bound_generation = "g"
    session._opened = True
    session._merged = {"provider": provider, "model": model}
    session._tts = SimpleNamespace(send=AsyncMock())
    await session.send_text("సరే అండి. <slow> ఏ details కావాలి?")
    request = json.loads(session._tts.send.await_args.args[0])
    sent = request["data"]["text"]
    assert ("<slow>" in sent) == supports_inline_audio_tags(provider, model)
    assert session._chars_sent == len(sent)


def test_gemini_delivery_metadata_is_warm_and_transcript_is_tag_free():
    from server.providers.gemini_tts import _speech_part

    part = _speech_part("Hello. <pauses> Which details would you like?", TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", pace=1.0), "gemini-3.8-flash-tts")
    assert part["text"] == "Hello. Which details would you like?"
    assert "Warm" in part["speech_metadata"]["style"]
    assert "Brisk" not in part["speech_metadata"]["style"]


def test_short_acknowledgements_and_multiword_tags_are_not_lost_or_split():
    from server.services.pstn_text_chunker import drain_complete_sentences

    ready, pending = drain_complete_sentences("సరే. మీకు ఏ details కావాలి?")
    assert " ".join([*ready, pending]).strip() == "సరే. మీకు ఏ details కావాలి?"
    assert drain_complete_sentences("సరే.") == ([], "సరే.")
    text = "word " * 54 + "<clears throat> ఇంకేమైనా details కావాలా"
    ready, pending = drain_complete_sentences(text)
    assert "<clears throat>" in pending
    assert "<clears" not in " ".join(ready)


@pytest.mark.asyncio
async def test_unchecked_natural_style_toggle_never_compiles_a_hidden_formal_directive():
    from server.brain.agent_script_compiler import compile_agent_from_brief

    _, result, *_ = await compile_agent_from_brief(brief="Agent name is Sam. Answer service questions for Acme.",
        language="te-IN", interpret_brief=False, generation_config={"naturalSpokenStyle": False})
    assert "formal register" not in result.agent_script
    assert "clear conversational wording" in result.agent_script


def test_legacy_platform_pack_refresh_keeps_business_source_and_new_register():
    source = "--- SPOKEN LANGUAGE (te-IN) ---\nSTALE. Telugu only.\n--- COMPANY & OFFER ---\nAcme has approved hours."
    refreshed = refresh_platform_sections(source, "kn-IN")
    assert "STALE" not in refreshed and "Acme has approved hours." in refreshed
    assert "CONVERSATIONAL REGISTER (kn-IN)" in refreshed


def test_gnani_voice_selection_respects_model_specific_catalog():
    from server.services.gnani_tts_ws import _resolve_gnani_voice

    assert _resolve_gnani_voice("voice-gnani-1", model="timbre-v2.5", language="te-IN") == "Lavanya"
    assert _resolve_gnani_voice("voice-gnani-1", model="timbre-v3.0", language="te-IN") == "Avinash"
    assert _resolve_gnani_voice("Prakash", model="timbre-v3.0", language="te-IN") == "Prakash"


@pytest.mark.asyncio
@pytest.mark.parametrize("model,voice", [("timbre-v2.5", "Lavanya"), ("timbre-v3.0", "Avinash")])
async def test_gnani_rest_and_websocket_send_matching_model_tags_and_voice(monkeypatch, model, voice):
    import httpx

    from server.providers.gnani_tts import GnaniTTSAdapter
    from server.services import gnani_tts_ws

    transcript = "సరే అండి. <slow> ఏ details కావాలి? <unknown>"
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=b"RIFF\x00\x00\x00\x00WAVE")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("server.providers.gnani_tts.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(GnaniTTSAdapter, "_api_key", lambda self: "test-placeholder")
    await GnaniTTSAdapter().synthesize_rest(transcript,
        TTSConfig(provider="gnani", model=model, speaker="voice-gnani-1", language="te-IN"))

    incoming = asyncio.Queue()
    ws = SimpleNamespace(send=AsyncMock(), recv=incoming.get, close=AsyncMock())
    monkeypatch.setattr(gnani_tts_ws.websockets, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(gnani_tts_ws, "_gnani_api_key", lambda: "test-placeholder")
    async with gnani_tts_ws.connect_gnani_tts_ws(model=model) as proxy:
        await proxy.send(json.dumps({"type": "config", "data": {"speaker": "voice-gnani-1", "language_code": "te-IN"}}))
        await proxy.send(json.dumps({"type": "text", "data": {"text": transcript}}))
        requests.append(json.loads(ws.send.await_args.args[0]))
        before = ws.send.await_count
        await proxy.send(json.dumps({"type": "text", "data": {"text": "<pauses>"}}))
        assert ws.send.await_count == before
    for payload in requests:
        assert payload["model"] == model and payload["voice"] == voice
        assert "<unknown>" not in payload["text"]
        assert ("<slow>" in payload["text"]) == (model == "timbre-v3.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model", MODELS[:6])
@pytest.mark.parametrize("as_dict", [False, True])
async def test_prewarm_keeps_only_selected_model_tags_and_counts_sent_text(monkeypatch, provider, model, as_dict):
    from server.services import pstn_turn_tts
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    captured = []

    class GreetingTTS:
        had_error = False

        def __init__(self, stub):
            self.stub = stub

        async def open(self, **kwargs):
            assert kwargs["resolved_stack"] is stack

        async def send_text(self, text):
            captured.append(text)
            self._chars_sent = len(text)
            await self.stub._emit_agent_wire(b"test-audio")

        async def finish(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(pstn_turn_tts, "PstnTurnTtsSession", GreetingTTS)
    stack = {"tts": {"provider": provider, "model": model}} if as_dict else context("te-IN", provider, model).resolved_stack
    frames, usage = await _synthesize_greeting_frames(greeting="హలో అండి. <slow> ఒక్క నిమిషం మాట్లాడొచ్చా?",
        session_id="test", pseudo_call_id="test", sample_rate=16000,
        tts_output_codec="linear16", language="te-IN", resolved_stack=stack, pipeline="composed_voice")
    assert frames == [b"test-audio"]
    assert ("<slow>" in captured[0]) == supports_inline_audio_tags(provider, model)
    assert usage["input_characters"] == len(captured[0])
