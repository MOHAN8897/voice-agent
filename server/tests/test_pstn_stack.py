"""PSTN stack validation — tier-only dials unchanged; custom stacks normalized."""
from server.services.pstn_stack import (
    PstnStackValidationError,
    normalize_pstn_stack_override,
    prepare_pstn_dial_stack,
)


def test_tier_only_override_unchanged():
    out, adj = prepare_pstn_dial_stack(None, language="te-IN", tier="medium")
    assert out is None
    assert adj == []


def test_sarvam_stt_upgraded_to_realtime():
    raw = {
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe"}},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
        "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    }
    out, adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out is not None
    assert out["stt"]["model"] == "saaras:v3-realtime"
    assert "llm" not in out
    assert out.get("pipeline") == "realtime_text"
    assert any("realtime" in a for a in adj)


def test_gemini_llm_override_stripped_for_pstn():
    raw = {
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
        "llm": {"provider": "gemini", "model": "gemini-2.5-flash"},
    }
    out, adj = normalize_pstn_stack_override(raw, language="en-IN")
    assert out is not None
    assert "llm" not in out
    assert out.get("pipeline") == "realtime_text"
    assert any("llm override removed" in a for a in adj)


def test_full_pstn_pipeline_wins_over_leftover_realtime_voice_flow():
    raw = {
        "pipeline": "realtime_text",
        "voice_flow": "realtime_e2e",
        "realtime_voice": {"voice": "marin"},
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
    }
    out, _adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out["pipeline"] == "realtime_text"
    assert "voice_flow" not in out
    assert "realtime_voice" not in out
    assert out["stt"]["model"] == "saaras:v3-realtime"


def test_cartesia_tts_sarvam_speaker_replaced():
    raw = {
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "tts": {"provider": "cartesia", "model": "sonic-3.5", "config": {"speaker": "priya"}},
        "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    }
    out, adj = normalize_pstn_stack_override(raw, language="te-IN")
    speaker = out["tts"]["config"]["speaker"]
    assert speaker != "priya"
    assert len(speaker) >= 32  # UUID
    assert any("Sarvam" in a or "Cartesia" in a for a in adj)


def test_cartesia_stt_ink2_telugu_upgraded():
    raw = {
        "stt": {"provider": "cartesia", "model": "ink-2"},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
    }
    out, adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out["stt"]["model"] == "ink-whisper"


def test_pstn_stt_stream_type_normalized():
    raw = {
        "stt": {
            "provider": "sarvam",
            "model": "saaras:v3-realtime",
            "config": {"stream_type": "accurate", "mode": "translate"},
        },
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
    }
    out, adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out["stt"]["config"]["stream_type"] == "fast"
    assert out["stt"]["config"]["mode"] == "transcribe"
    assert any("fast" in a for a in adj)


def test_full_pstn_keeps_place_call_noise_reduction():
    raw = {
        "pipeline": "realtime_text",
        "noise_reduction": "off",
        "realtime_voice": {"voice": "marin", "noise_reduction": "off"},
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
    }
    out, _adj = normalize_pstn_stack_override(raw, language="te-IN")
    assert out["pipeline"] == "realtime_text"
    assert "realtime_voice" not in out
    assert out["noise_reduction"] == "off"


def test_invalid_sarvam_speaker_raises():
    raw = {
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "not_a_real_voice"}},
    }
    try:
        normalize_pstn_stack_override(raw, language="te-IN")
        assert False, "expected PstnStackValidationError"
    except PstnStackValidationError as e:
        assert "not_a_real_voice" in str(e)
