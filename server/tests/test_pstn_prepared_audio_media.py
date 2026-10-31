import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.audio_transcode import transcode_audio_frames


def test_prepared_linear16_audio_is_resampled_and_encoded_for_8khz_mulaw():
    source = b"\x00\x20" * 320  # 20 ms of 16 kHz PCM16.

    frames = transcode_audio_frames(
        [source],
        source_codec="linear16",
        source_rate=16000,
        target_codec="mulaw",
        target_rate=8000,
    )

    assert len(frames) == 1
    assert len(frames[0]) == 160
    assert frames[0] != source[:160]


def test_prepared_linear16_audio_resamples_to_non_16khz_linear_media():
    source = b"\x00\x20" * 480  # 20 ms of 24 kHz PCM16.

    frames = transcode_audio_frames(
        [source],
        source_codec="linear16",
        source_rate=24000,
        target_codec="linear16",
        target_rate=12000,
    )

    assert len(frames) == 1
    assert len(frames[0]) == 480


def test_prepared_audio_can_be_encoded_as_alaw():
    source = b"\x00\x20" * 320

    frames = transcode_audio_frames(
        [source],
        source_codec="linear16",
        source_rate=16000,
        target_codec="alaw",
        target_rate=8000,
    )

    assert len(frames) == 1
    assert len(frames[0]) == 160
    assert frames[0] != b"\xff" * 160


@pytest.mark.asyncio
async def test_vobiz_emits_negotiated_alaw_content_type_and_encoded_payload():
    from server.services.vobiz_pstn_bridge import VobizPstnBridge

    ws = SimpleNamespace(send_text=AsyncMock())
    bridge = VobizPstnBridge(ws)
    bridge._wire_codec = "alaw"
    bridge._wire_sample_rate = 8000
    bridge._voice = SimpleNamespace(current_generation_id="generation-1", current_turn_id="turn-1")
    pcmu = b"\x00" * 160

    await bridge._send_agent_wire(pcmu)

    message = json.loads(ws.send_text.await_args.args[0])
    payload = base64.b64decode(message["media"]["payload"])
    assert message["media"]["contentType"] == "audio/x-alaw;rate=8000"
    assert message["media"]["sampleRate"] == 8000
    assert len(payload) == 160
    assert payload != pcmu
