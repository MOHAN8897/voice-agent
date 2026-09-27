"""Post-call Gemini 3.5 Transcribe pipeline (Telnyx recording → transcript.jsonl)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server.call.call_ledger import call_ledger
from server.call.post_call_transcription import (
    call_uses_gemini_post_call_transcript,
    enqueue,
    run_transcription,
)
from server.config.env import get_settings
from server.services.gemini_post_call_transcribe import words_to_transcript_lines


def test_gemini_live_connect_config_omits_native_transcription():
    import inspect

    from server.realtime.providers import gemini_voice as mod

    source = inspect.getsource(mod.GeminiLiveVoiceAdapter.connect)
    assert "input_audio_transcription" not in source
    assert "output_audio_transcription" not in source


def test_no_transcribe_live_adapter_in_repo():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "server"
    hits = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "gemini-3.5-transcribe-live" in text:
            hits.append(str(path))
    assert hits == []


def test_words_to_lines_maps_outbound_speakers():
    words = [
        {"word": "Hello", "speaker": "spk_1", "start_sec": 0.1},
        {"word": "there", "speaker": "spk_1", "start_sec": 0.3},
        {"word": "Hi", "speaker": "spk_2", "start_sec": 1.0},
        {"word": "Priya", "speaker": "spk_2", "start_sec": 1.2},
    ]
    lines = words_to_transcript_lines(
        words,
        call_started_at="2026-09-27T10:00:00+00:00",
        direction="outbound",
    )
    assert len(lines) == 2
    assert lines[0]["role"] == "user"
    assert "Hello" in lines[0]["text"]
    assert lines[1]["role"] == "assistant"
    assert "Priya" in lines[1]["text"]


def test_words_to_lines_preserves_telugu():
    words = [
        {"word": "నాకు", "speaker": "spk_1", "start_sec": 0.0},
        {"word": "అవసరం", "speaker": "spk_1", "start_sec": 0.2},
        {"word": "లేదు", "speaker": "spk_1", "start_sec": 0.4},
    ]
    lines = words_to_transcript_lines(words, call_started_at="2026-09-27T10:00:00Z", direction="outbound")
    assert lines[0]["role"] == "user"
    assert "నాకు" in lines[0]["text"]


def test_call_uses_gemini_post_call_transcript_gate():
    meta = {
        "pipeline": "realtime_voice",
        "resolved_stack": {"llm": {"model": "gemini-3.8-live"}},
    }
    assert call_uses_gemini_post_call_transcript(meta) is True
    meta["pipeline"] = "classic"
    assert call_uses_gemini_post_call_transcript(meta) is False


@pytest.mark.asyncio
async def test_transcription_pipeline_stores_transcript(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_ENABLED", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()

    call_id = "post-call-tx-1"
    await call_ledger.init(
        call_id,
        {
            "call_id": call_id,
            "pipeline": "realtime_voice",
            "direction": "outbound",
            "language": "te-IN",
            "started_at": "2026-09-27T10:00:00Z",
            "resolved_stack": {"llm": {"model": "gemini-3.8-live"}},
            "usage": {"llm_model": "gemini-3.8-live", "duration_sec": 60},
        },
    )
    await call_ledger.seal(call_id)
    rec_dir = tmp_path / "calls" / call_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "telnyx.wav").write_bytes(b"RIFF" + b"\x00" * 128)

    words = [
        {"word": "Hello", "speaker": "spk_1", "start_sec": 0.0},
        {"word": "Bye", "speaker": "spk_2", "start_sec": 1.0},
    ]

    def fake_transcribe(*_a, **_k):
        return (words, "", {"model": "gemini-3.5-transcribe"})

    with patch(
        "server.call.post_call_transcription.transcribe_recording_file",
        side_effect=fake_transcribe,
    ):
        with patch(
            "server.call.post_call_transcription.recording_path",
            return_value=rec_dir / "telnyx.wav",
        ):
            with patch("server.call.post_call_pipeline.enqueue", new_callable=AsyncMock) as outcome:
                result = await run_transcription(call_id)
    assert result["status"] == "complete"
    lines = call_ledger.read_lines(call_id)
    assert any(row.get("role") == "user" for row in lines)
    assert any(row.get("role") == "assistant" for row in lines)
    usage = call_ledger.read_meta(call_id).get("usage") or {}
    assert usage.get("transcription_billing") == "post_call_gemini_transcribe"
    assert float(usage.get("post_call_transcript_usd") or 0) > 0
    assert float(usage.get("post_call_transcript_inr") or 0) > 0
    meta = call_ledger.read_meta(call_id)
    assert meta.get("transcript_source") == "telnyx+gemini-3.5-transcribe"
    outcome.assert_awaited()


@pytest.mark.asyncio
async def test_recording_delay_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_ENABLED", "true")
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_MAX_RETRIES", "3")
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_RETRY_BASE_SEC", "0.01")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()

    call_id = "retry-rec"
    await call_ledger.init(
        call_id,
        {
            "call_id": call_id,
            "pipeline": "realtime_voice",
            "direction": "outbound",
            "started_at": "2026-09-27T10:00:00Z",
            "resolved_stack": {"llm": {"model": "gemini-3.8-live"}},
            "usage": {"duration_sec": 30},
        },
    )
    rec_dir = tmp_path / "calls" / call_id
    rec_dir.mkdir(parents=True, exist_ok=True)

    words = [
        {"word": "Hi", "speaker": "spk_1", "start_sec": 0.0},
        {"word": "Bye", "speaker": "spk_2", "start_sec": 1.0},
    ]
    attempts = {"n": 0}

    def fake_path(_cid: str):
        attempts["n"] += 1
        if attempts["n"] < 2:
            return None
        return rec_dir / "telnyx.wav"

    with patch("server.call.post_call_transcription.recording_path", side_effect=fake_path):
        with patch(
            "server.call.post_call_transcription.transcribe_recording_file",
            return_value=(words, "", {}),
        ):
            with patch("server.call.post_call_pipeline.enqueue", new_callable=AsyncMock):
                (rec_dir / "telnyx.wav").write_bytes(b"RIFF" + b"\x00" * 64)
                result = await run_transcription(call_id)
    assert result["status"] == "complete"
    assert attempts["n"] >= 2


@pytest.mark.asyncio
async def test_duplicate_enqueue_one_job(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_ENABLED", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    call_id = "dedupe-tx"
    await call_ledger.init(
        call_id,
        {
            "call_id": call_id,
            "pipeline": "realtime_voice",
            "resolved_stack": {"llm": {"model": "gemini-3.8-live"}},
        },
    )
    call_ledger.write_meta(
        call_id,
        {
            **call_ledger.read_meta(call_id),
            "post_call_transcript": {"status": "complete"},
        },
    )
    with patch("server.call.post_call_transcription._QUEUE.put", new_callable=AsyncMock) as put:
        await enqueue(call_id)
        put.assert_not_awaited()
    claimed = call_ledger.read_meta(call_id).get("post_call_transcript", {})
    assert claimed.get("status") == "complete"
    await enqueue(call_id)
    put.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcription_failure_does_not_touch_end_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_ENABLED", "true")
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    call_id = "fail-tx"
    await call_ledger.init(
        call_id,
        {
            "call_id": call_id,
            "pipeline": "realtime_voice",
            "end_reason": "pstn_hangup",
            "resolved_stack": {"llm": {"model": "gemini-3.8-live"}},
            "usage": {"duration_sec": 10},
        },
    )
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_MAX_RETRIES", "1")
    monkeypatch.setenv("POST_CALL_TRANSCRIPT_RETRY_BASE_SEC", "0.01")
    get_settings.cache_clear()
    with patch("server.call.post_call_transcription.recording_path", return_value=None):
        result = await run_transcription(call_id)
    assert result["status"] == "failed"
    meta = call_ledger.read_meta(call_id)
    assert meta.get("end_reason") == "pstn_hangup"
    assert meta.get("post_call_transcript", {}).get("status") == "failed"
