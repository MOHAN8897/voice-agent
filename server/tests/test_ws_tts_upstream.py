"""Browser /ws/tts upstream config — sample rate must reach Cartesia/Sarvam."""
from server.routes.ws import _upstream_tts_config_payload


def test_upstream_cartesia_forwards_both_sample_rates():
    merged = {
        "provider": "cartesia",
        "speaker": "voice-id",
        "language_code": "te-IN",
        "pace": 1.0,
        "min_buffer_size": 30,
        "max_chunk_length": 80,
        "output_audio_codec": "linear16",
        "output_audio_bitrate": "128k",
        "model": "sonic-3.5",
        "sample_rate": 24000,
    }
    out = _upstream_tts_config_payload(merged)
    assert out["sample_rate"] == 24000
    assert out["speech_sample_rate"] == "24000"


def test_upstream_sarvam_forwards_speech_sample_rate_only():
    merged = {
        "provider": "sarvam",
        "speaker": "shubh",
        "language_code": "te-IN",
        "pace": 1.0,
        "min_buffer_size": 30,
        "max_chunk_length": 80,
        "output_audio_codec": "linear16",
        "output_audio_bitrate": "128k",
        "model": "bulbul:v3",
        "sample_rate": 24000,
    }
    out = _upstream_tts_config_payload(merged)
    assert out["speech_sample_rate"] == "24000"
    assert "sample_rate" not in out
