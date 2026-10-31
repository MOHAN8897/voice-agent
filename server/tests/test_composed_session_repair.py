"""Regressions from the Oct 22 browser sessions: 400s, English openings, stale tier saves."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.providers.base import StageSelection
from server.services import composed_voice_session as session


def _context():
    return SimpleNamespace(
        compiled_brain_text="Business facts: opening hours are 9 to 5.",
        compiled_brain_version="v1",
        resolved_stack=SimpleNamespace(
            language="te-IN", llm=StageSelection("sarvam", "sarvam-105b-conversations", {
                "api_mode": "chat_completions_v1",
            }),
        ),
    )


def test_sarvam_request_converts_locked_developer_brain_to_system_without_losing_history():
    from server.agent.instruction_builder import build_live_input
    from server.providers.sarvam_llm import _chat_messages

    messages = build_live_input(
        compiled_brain_text="Only speak Telugu. Preserve business facts.",
        history=[{"role": "assistant", "content": "నమస్కారం."}], transcript="ఎప్పుడు తెరుస్తారు?",
    )
    converted = _chat_messages(messages, None)
    assert converted == [
        {"role": "system", "content": "Only speak Telugu. Preserve business facts."},
        {"role": "assistant", "content": "నమస్కారం."},
        {"role": "user", "content": messages[-1]["content"][0]["text"]},
    ]
    assert messages[0]["role"] == "developer"  # Adapter must not mutate shared input.


def test_composed_prompt_cache_is_call_owned_and_invalidates_on_selected_language_or_script():
    ctx = _context()
    first = session.composed_system_prompt(ctx)
    snapshot = ctx.composed_prompt_snapshot
    assert session.composed_system_prompt(ctx) is first
    assert ctx.composed_prompt_snapshot is snapshot
    assert "Telugu" in first
    assert "9 to 5" in first
    other = _context()
    session.composed_system_prompt(other)
    assert other.composed_prompt_snapshot is not snapshot
    ctx.resolved_stack.language = "hi-IN"
    assert "Hindi" in session.composed_system_prompt(ctx)
    assert ctx.composed_prompt_snapshot is not snapshot
    ctx.compiled_brain_text = "Updated hours: 10 to 6."
    assert "10 to 6" in session.composed_system_prompt(ctx)
    assert "9 to 5" not in session.composed_system_prompt(ctx)


def test_composed_prompt_requires_published_script():
    ctx = _context()
    ctx.compiled_brain_text = ""
    with pytest.raises(RuntimeError, match="published instructions"):
        session.composed_system_prompt(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("language,opening", [
    ("te-IN", "నమస్కారం. నేను ఆశ. మీకు ఎలా సహాయపడగలను?"),
    ("hi-IN", "नमस्ते। मैं आशा हूँ। आपकी क्या मदद कर सकती हूँ?"),
])
async def test_english_opening_is_localized_using_pinned_model_before_tts(monkeypatch, language, opening):
    import server.providers

    requests = []

    class Adapter:
        async def stream_live_turn(self, **kwargs):
            requests.append(kwargs)
            yield {"delta": opening}
            yield {"done": True, "text": opening, "usage": {"input_tokens": 50, "output_tokens": 20}}

    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: SimpleNamespace(
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
        get_llm=lambda _: Adapter(),
    ))
    llm = _context().resolved_stack.llm
    localized, usage = await session.localize_composed_opening("Hello, I am Asha. How can I help?", language=language, llm=llm)
    assert localized == opening
    assert usage["input_tokens"] == 50
    assert requests[0]["model"] == llm.model
    assert requests[0]["api_mode"] == "chat_completions_v1"
    assert requests[0]["reasoning_effort"] is None
    assert json.loads(requests[0]["input_messages"][-1]["content"])["opening"].startswith("Hello")
    # A prepared greeting crosses into the answered call without another LLM request.
    assert await session.localize_composed_opening(localized, language=language, llm=llm) == (localized, {})
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_opening_localization_rejects_wrong_language_or_provider_failure(monkeypatch):
    import server.providers

    class Adapter:
        async def stream_live_turn(self, **_kwargs):
            yield {"done": True, "text": "Hello again."}

    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: SimpleNamespace(
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
        get_llm=lambda _: Adapter(),
    ))
    with pytest.raises(RuntimeError, match="selected language"):
        await session.localize_composed_opening("Hello.", language="te-IN", llm=_context().resolved_stack.llm)


@pytest.mark.asyncio
async def test_composed_start_speaks_and_remembers_localized_opening_once(monkeypatch):
    from server.call import call_context
    from server.services.pstn_voice_core import PstnVoiceLoop

    ctx = _context()
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    localized = "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?"
    from server.call.call_ledger import call_ledger
    from server.providers.sarvam_llm import _usage_from_payload

    # Use the real adapter telemetry shape and real strict costing recorder.
    # The old test's empty usage hid startup's rejection of diagnostic counters.
    usage = _usage_from_payload({"usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}})
    meta = {"pipeline": "composed_voice"}
    monkeypatch.setattr(call_ledger, "read_meta", lambda _: dict(meta))
    monkeypatch.setattr(call_ledger, "write_meta", lambda _, updated: meta.update(updated))
    translate = AsyncMock(return_value=(localized, usage))
    monkeypatch.setattr(session, "localize_composed_opening", translate)
    loop = PstnVoiceLoop(session_id="opening-test", call_id="opening-test", on_agent_wire=AsyncMock(),
                         stack_override={"pipeline": "composed_voice"})
    monkeypatch.setattr(loop, "open_stt", AsyncMock())
    monkeypatch.setattr(loop, "_warm_tts_connection", AsyncMock())
    monkeypatch.setattr(loop, "_wait_for_intro_playback", AsyncMock())
    noted = AsyncMock()
    monkeypatch.setattr(loop, "_note_opening_spoken", noted)

    async def speak(text):
        assert text == localized
        loop._wire_frames_out += 1

    monkeypatch.setattr(loop, "speak", speak)
    await loop.start_call(greeting_text="Hello. How can I help?")
    await loop.start_call(greeting_text="Hello. How can I help?")
    translate.assert_awaited_once()
    noted.assert_awaited_once_with(localized)
    assert meta["stage_usage"]["llm"] == {"input_tokens": 50, "output_tokens": 20, "cached_tokens": 0}
    await loop.close()


@pytest.mark.asyncio
async def test_composed_model_failure_with_silent_voice_plays_outage_clip(monkeypatch):
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    from server.services.pstn_voice_core import PHASE_ENDED, PstnVoiceLoop

    async def failed(**_kwargs):
        raise RuntimeError("Synthetic provider 400")
        yield

    monkeypatch.setattr(live_turn_orchestrator, "handle_user_turn_stream", failed)
    loop = PstnVoiceLoop(session_id="failed-turn", call_id="failed-turn", on_agent_wire=AsyncMock(),
                         stack_override={"pipeline": "composed_voice"})
    tts = SimpleNamespace(prepare_for_turn=AsyncMock(), has_sent_text=False)
    monkeypatch.setattr(loop, "_get_call_tts_session", lambda: tts)
    monkeypatch.setattr(loop, "_release_tts_turn", AsyncMock())
    speak = AsyncMock()
    monkeypatch.setattr(loop, "speak", speak)
    error, hangup = AsyncMock(), AsyncMock()
    loop.set_error_handler(error)
    loop.set_hangup_handler(hangup)
    await loop._run_turn("నాకు వివరాలు చెప్పండి")
    speak.assert_awaited_once()
    error.assert_awaited_once()
    hangup.assert_awaited_once()
    # The recovery line produced no audio after the model failed: the
    # pre-rendered outage clip closes the call instead of dead air.
    assert loop._technical_fallback_played is True
    assert loop.on_agent_wire.await_count > 0
    assert loop._phase == PHASE_ENDED
    await loop.close()


@pytest.mark.asyncio
async def test_composed_model_failure_with_provider_outage_plays_recorded_apology(monkeypatch):
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    from server.services.pstn_voice_core import PHASE_ENDED, PstnVoiceLoop

    async def failed(**_kwargs):
        raise RuntimeError("Synthetic provider 400")
        yield

    monkeypatch.setattr(live_turn_orchestrator, "handle_user_turn_stream", failed)
    loop = PstnVoiceLoop(session_id="failed-turn", call_id="failed-turn", on_agent_wire=AsyncMock(),
                         stack_override={"pipeline": "composed_voice"})
    tts = SimpleNamespace(
        prepare_for_turn=AsyncMock(),
        has_sent_text=False,
        had_error=True,
        failure_evidence={
            "kind": "provider_rejection", "provider": "sarvam", "status": 503, "retained": True,
        },
    )
    monkeypatch.setattr(loop, "_get_call_tts_session", lambda: tts)
    monkeypatch.setattr(loop, "_release_tts_turn", AsyncMock())
    speak = AsyncMock()
    monkeypatch.setattr(loop, "speak", speak)
    error, hangup = AsyncMock(), AsyncMock()
    loop.set_error_handler(error)
    loop.set_hangup_handler(hangup)
    await loop._run_turn("నాకు వివరాలు చెప్పండి")
    speak.assert_not_awaited()
    error.assert_awaited_once()
    hangup.assert_awaited_once()
    # Retained provider rejection is proof enough to use the shipped clip.
    assert loop._technical_fallback_played is True
    assert loop.on_agent_wire.await_count > 0
    assert loop._phase == PHASE_ENDED
    await loop.close()


def test_composed_stt_sends_documented_vad_and_onset_padding(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from server.providers.base import STTConfig
    from server.providers.sarvam_stt import SarvamSTTAdapter
    from server.services import sarvam_ws

    connect = Mock()
    monkeypatch.setattr(sarvam_ws, "_connect", connect)
    SarvamSTTAdapter().connect_realtime(STTConfig(
        provider="sarvam", model="saaras:v3-realtime", language="te-IN", sample_rate=8000,
        vad_config={"silence_duration_ms": 500, "threshold": 0.3, "min_speech_duration_ms": 250, "prefix_padding_ms": 300},
    ))
    params = parse_qs(urlsplit(connect.call_args.args[0]).query)
    assert params["sample_rate"] == ["8000"]
    assert params["silence_duration_ms"] == ["500"]
    assert params["min_speech_duration_ms"] == ["250"]
    assert params["prefix_padding_ms"] == ["300"]
    assert "high_vad_sensitivity" not in params
