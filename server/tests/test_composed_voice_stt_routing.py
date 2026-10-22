from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.routes.ws import _connect_stt_upstream
from server.services.pstn_voice_flow import create_pstn_voice_loop


@pytest.mark.asyncio
async def test_composed_stt_cost_uses_only_successfully_forwarded_audio(monkeypatch):
    from server.services.pstn_voice_core import PstnVoiceLoop
    from server.services.saas import composed_costing

    recorded = Mock()
    monkeypatch.setattr(composed_costing, "record_composed_stage_usage", recorded)
    loop = PstnVoiceLoop(
        session_id="stage-usage-test", call_id=None, on_agent_wire=AsyncMock(),
        sample_rate=16000, tts_output_codec="linear16",
        stack_override={"pipeline": "composed_voice"},
    )
    loop._stt = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    await loop.feed_user_pcm16(b"\x00\x00" * 320)
    loop._stt.send.side_effect = RuntimeError("connection closed")
    await loop.feed_user_pcm16(b"\x00\x00" * 320)
    loop.call_id = "stage-usage-test"
    await loop.close()
    recorded.assert_called_once_with("stage-usage-test", "stt", {"audio_seconds": 0.02}, accumulate=False)


@pytest.mark.asyncio
async def test_classic_voice_loop_does_not_record_composed_costs(monkeypatch):
    from server.services.pstn_voice_core import PstnVoiceLoop
    from server.services.saas import composed_costing

    recorded = Mock()
    monkeypatch.setattr(composed_costing, "record_composed_stage_usage", recorded)
    loop = PstnVoiceLoop(session_id="legacy-cost-test", call_id=None, on_agent_wire=AsyncMock())
    await loop.close()
    recorded.assert_not_called()


def _stack(*, provider: str = "sarvam", model: str = "saaras:v3-realtime"):
    return SimpleNamespace(
        language="te-IN",
        stt=SimpleNamespace(
            provider=provider,
            model=model,
            config={"mode": "realtime", "stream_type": "fast"},
        ),
    )


def test_composed_stt_uses_the_admitted_provider_model_and_mode(monkeypatch):
    from server.call import call_context
    from server.routes import ws

    context = SimpleNamespace(pipeline="composed_voice", resolved_stack=_stack())
    connect = Mock(return_value="stream")
    adapter = SimpleNamespace(connect_realtime=connect)
    registry = SimpleNamespace(
        is_provider_enabled=Mock(return_value=True),
        is_model_allowed=Mock(return_value=True),
        get_stt=Mock(return_value=adapter),
    )
    monkeypatch.setattr(call_context, "get", lambda _call_id: context)
    monkeypatch.setattr(ws, "get_settings", lambda: SimpleNamespace(use_provider_registry=True))
    monkeypatch.setattr(ws, "get_provider_registry", lambda: registry)

    result = _connect_stt_upstream(
        session_id="pstn-session",
        call_id="composed-call",
        expected_pipeline="composed_voice",
        pinned_stack={"pipeline": "composed_voice", "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"}},
        language_code="te-IN",
        sample_rate=8000,
    )

    assert result == "stream"
    registry.get_stt.assert_called_once_with("sarvam")
    config = connect.call_args.args[0]
    assert config.provider == "sarvam"
    assert config.model == "saaras:v3-realtime"
    assert config.mode == "realtime"
    assert config.sample_rate == 8000
    assert config.vad_config == {
        "silence_duration_ms": 300, "threshold": 0.55,
        "min_speech_duration_ms": 200, "prefix_padding_ms": 300,
    }


@pytest.mark.parametrize(
    ("context", "registry_enabled", "message"),
    [
        (None, True, "no matching pinned call context"),
        (SimpleNamespace(pipeline="realtime_text", resolved_stack=_stack()), True, "no matching pinned call context"),
        (SimpleNamespace(pipeline="composed_voice", resolved_stack=_stack()), False, "requires the provider registry"),
    ],
)
def test_composed_stt_fails_closed_without_a_matching_registry_context(
    monkeypatch, context, registry_enabled, message
):
    from server.call import call_context
    from server.routes import ws
    from server.services import sarvam_ws

    legacy = Mock(side_effect=AssertionError("composed STT must not use the session fallback"))
    resolver = Mock(side_effect=AssertionError("composed STT must not re-resolve a session stack"))
    monkeypatch.setattr(call_context, "get", lambda _call_id: context)
    monkeypatch.setattr(ws, "get_settings", lambda: SimpleNamespace(use_provider_registry=registry_enabled))
    monkeypatch.setattr(sarvam_ws, "connect_stt_realtime", legacy)
    monkeypatch.setattr(ws, "resolve_stack_for_session", resolver)

    with pytest.raises(RuntimeError, match=message):
        _connect_stt_upstream(
            session_id="pstn-session",
            call_id="composed-call",
            expected_pipeline="composed_voice",
            language_code="te-IN",
        )

    legacy.assert_not_called()
    resolver.assert_not_called()


def test_composed_factory_preserves_intent_for_initial_connect_and_reconnect():
    override = {
        "pipeline": "composed_voice",
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
    }
    loop = create_pstn_voice_loop(
        stack_override=override,
        session_id="pstn-session",
        call_id="composed-call",
        on_agent_wire=lambda _chunk: None,
    )

    assert loop.stack_override == override
    assert loop._stt_pipeline_options() == ("composed_voice", override)
