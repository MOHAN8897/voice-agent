from __future__ import annotations

import base64
import io
import json
import wave
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call.call_ledger import call_ledger
from server.services.pstn_media_flow import pstn_media_flow
from server.services.pstn_turn_tts import PstnTurnTtsSession


def _wav_bytes(*, sample_rate: int, samples: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * samples)
    return out.getvalue()


def _voice() -> SimpleNamespace:
    return SimpleNamespace(
        call_id="call-test",
        current_turn_id="turn-1",
        current_generation_id="generation-1",
        _interrupted_generation=None,
        _closed=False,
        _wire_frames_out=0,
        current_output_codec="L16",
        sample_rate=16000,
        tts_output_codec="linear16",
        emission_blocked=lambda: False,
    )


def _patch_meta(monkeypatch, meta: dict) -> None:
    monkeypatch.setattr(call_ledger, "read_meta", lambda _call_id: deepcopy(meta))
    monkeypatch.setattr(call_ledger, "write_meta", lambda _call_id, value: meta.update(deepcopy(value)))
    monkeypatch.setattr(pstn_media_flow, "emit", lambda *_args, **_kwargs: None)


@pytest.mark.asyncio
async def test_gemini_tts_usage_records_actual_wav_rate_and_keeps_it_internal(monkeypatch):
    meta = {"usage": {"cost_usd": 0.12}}
    _patch_meta(monkeypatch, meta)
    session = PstnTurnTtsSession(_voice())
    session._composed = True
    session._opened = True
    session._merged = {"speech_sample_rate": "24000"}
    session._unary_config = object()
    session._unary_adapter = SimpleNamespace(
        synthesize_with_metadata=AsyncMock(
            return_value=SimpleNamespace(
                audio_bytes=_wav_bytes(sample_rate=22050, samples=551),
                usage={"input_tokens": 4, "output_tokens": 7, "output_audio_tokens": 7},
            )
        )
    )
    session._emit_audio_chunk = AsyncMock()
    session._flush_audio_tail = AsyncMock()

    await session.send_text("hello")
    await session.finish()

    assert session._merged["speech_sample_rate"] == "22050"
    assert meta["usage"] == {"cost_usd": 0.12}
    assert "stage_usage" not in call_ledger.review_fields("call-test")
    assert meta["stage_usage"]["tts"] == {
        "input_characters": 5,
        "output_audio_seconds": round(551 / 22050, 6),
        "output_audio_samples": 551,
        "native_usage": {"input_tokens": 4, "output_tokens": 7, "output_audio_tokens": 7},
    }


@pytest.mark.asyncio
async def test_multiple_unary_tts_chunks_accumulate_native_usage(monkeypatch):
    meta = {"usage": {"cost_usd": 0.12}}
    _patch_meta(monkeypatch, meta)

    class Unary:
        async def synthesize_with_metadata(self, _text, _config):
            return SimpleNamespace(
                audio_bytes=_wav_bytes(sample_rate=22050, samples=220),
                usage={"input_tokens": 3, "output_tokens": 5, "output_audio_tokens": 5},
            )

    session = PstnTurnTtsSession(_voice())
    session._composed = True
    session._opened = True
    session._unary_config = object()
    session._unary_adapter = Unary()
    session._emit_audio_chunk = AsyncMock()
    session._flush_audio_tail = AsyncMock()

    await session.send_text("first sentence.")
    await session.send_text("final tail.")
    await session.finish()

    assert meta["stage_usage"]["tts"]["native_usage"] == {
        "input_tokens": 6,
        "output_tokens": 10,
        "output_audio_tokens": 10,
    }
    assert meta["stage_usage"]["tts"]["input_characters"] == 26


@pytest.mark.asyncio
async def test_prepared_composed_tts_usage_is_attached_to_real_call_internally(monkeypatch):
    from server.services.pstn_prewarm import PstnPrewarmBundle, record_bundle_greeting_usage

    meta = {"call_id": "call-test", "usage": {"cost_usd": 0.12}}
    _patch_meta(monkeypatch, meta)
    bundle = PstnPrewarmBundle(
        provider="vobiz",
        external_id="prepared-id",
        realtime_key="prepared-id",
        greeting_text="Hello there.",
        greeting_tts_usage={
            "input_characters": 12,
            "output_audio_seconds": 0.5,
            "output_audio_samples": 11025,
            "native_usage": {"output_audio_tokens": 7},
        },
    )

    await record_bundle_greeting_usage("call-test", bundle)

    assert meta["usage"] == {"cost_usd": 0.12}
    assert meta["stage_usage"]["tts"]["prewarm_input_characters"] == 12
    assert meta["stage_usage"]["tts"]["prewarm_output_audio_seconds"] == 0.5
    assert meta["stage_usage"]["tts"]["prewarm_native_usage"] == {"output_audio_tokens": 7}
    assert "stage_usage" not in call_ledger.review_fields("call-test")


@pytest.mark.asyncio
async def test_streamed_tts_counts_split_pcm16_samples_once(monkeypatch):
    meta = {"stage_usage": {"tts": {"input_characters": 2, "output_audio_samples": 10}}}
    _patch_meta(monkeypatch, meta)
    pcm = b"\x00" * 96
    encoded_parts = (base64.b64encode(pcm[:95]).decode(), base64.b64encode(pcm[95:]).decode())

    class Socket:
        def __aiter__(self):
            async def messages():
                for part in encoded_parts:
                    yield json.dumps({"type": "chunk", "data": part})
                yield json.dumps({"type": "done", "data": {}})

            return messages()

    session = PstnTurnTtsSession(_voice())
    session._composed = True
    session._tts_rate = 16000
    session._chars_sent = 3
    session._tts = Socket()
    session._emit_audio_chunk = AsyncMock()
    session._flush_audio_tail = AsyncMock()

    await session._reader_loop()
    session._record_composed_usage()
    session._record_composed_usage()

    assert meta["stage_usage"]["tts"] == {
        "input_characters": 5,
        "output_audio_samples": 58,
        "output_audio_seconds": 0.003,
        "native_usage": {},
    }
