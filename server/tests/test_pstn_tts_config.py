"""PSTN telephony TTS/STT configuration."""
from server.services.tts_config import merge_pstn_tts_config


def test_merge_pstn_tts_config_sarvam_l16_16k(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()

    cfg = merge_pstn_tts_config("test-studio", call_id=None, ws_model="bulbul:v3", wire_mode="rtp_l16")
    assert cfg["output_audio_codec"] == "linear16"
    assert cfg["speech_sample_rate"] == "16000"
    assert "output_audio_bitrate" not in cfg
    assert "sample_rate" not in cfg
    assert cfg.get("provider") == "sarvam"

    mulaw_cfg = merge_pstn_tts_config("test-studio", call_id=None, ws_model="bulbul:v3", wire_mode="rtp_mulaw")
    assert mulaw_cfg["output_audio_codec"] == "linear16"
    assert mulaw_cfg["speech_sample_rate"] == "8000"
