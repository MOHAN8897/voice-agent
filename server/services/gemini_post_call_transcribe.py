"""Post-call Telnyx recording → Gemini 3.5 Transcribe (batch generateContent, not Live)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from server.utils.logger import logger

_OFFSET_RE = re.compile(r"^(\d+(?:\.\d+)?)s?$")


def _parse_offset_seconds(raw: str | None) -> float:
    text = str(raw or "").strip().lower()
    if not text:
        return 0.0
    m = _OFFSET_RE.match(text)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except ValueError:
        return 0.0


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".mp3":
        return "audio/mp3"
    if ext == ".wav":
        return "audio/wav"
    return "audio/wav"


def _user_speaker_label(first_speaker: str, speakers: set[str], direction: str) -> str:
    if not first_speaker or not speakers:
        return ""
    direction = str(direction or "outbound").strip().lower()
    others = [s for s in speakers if s and s != first_speaker]
    if direction == "inbound":
        return others[0] if others else first_speaker
    return first_speaker


def _role_for_speaker(speaker: str, user_label: str) -> str:
    if not speaker:
        return "user"
    if user_label and speaker == user_label:
        return "user"
    return "assistant"


def extract_word_entries(response: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            transcription = getattr(part, "audio_transcription", None)
            if not transcription:
                continue
            speaker = str(getattr(transcription, "speaker_label", "") or "").strip()
            for word_info in getattr(transcription, "words", []) or []:
                word = str(getattr(word_info, "word", "") or "").strip()
                if not word:
                    continue
                words.append(
                    {
                        "word": word,
                        "speaker": speaker,
                        "start_sec": _parse_offset_seconds(getattr(word_info, "start_offset", "")),
                    }
                )
    words.sort(key=lambda row: row["start_sec"])
    return words


def words_to_transcript_lines(
    words: list[dict[str, Any]],
    *,
    call_started_at: str | None,
    direction: str,
    fallback_text: str = "",
) -> list[dict[str, Any]]:
    if not words:
        text = (fallback_text or "").strip()
        if not text:
            return []
        return [{"seq": 1, "role": "user", "text": text, "ts": call_started_at or _utcnow()}]

    speakers = {str(w.get("speaker") or "") for w in words if w.get("speaker")}
    first_speaker = str(words[0].get("speaker") or "")
    user_label = _user_speaker_label(first_speaker, speakers, direction)

    base = _parse_call_started(call_started_at)
    lines: list[dict[str, Any]] = []
    current_role = ""
    current_words: list[str] = []
    current_start = 0.0
    seq = 0

    def flush() -> None:
        nonlocal seq, current_role, current_words, current_start
        text = " ".join(current_words).strip()
        if not text:
            current_words = []
            return
        seq += 1
        ts = (base + timedelta(seconds=current_start)).isoformat().replace("+00:00", "Z")
        lines.append({"seq": seq, "role": current_role or "user", "text": text, "ts": ts})
        current_words = []

    for row in words:
        role = _role_for_speaker(str(row.get("speaker") or ""), user_label)
        if role != current_role and current_words:
            flush()
        if not current_words:
            current_role = role
            current_start = float(row.get("start_sec") or 0.0)
        current_words.append(str(row.get("word") or ""))
    flush()
    return lines


def _parse_call_started(raw: str | None) -> datetime:
    if raw:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def transcribe_recording_file(
    path: Path,
    *,
    model: str,
    language_code: str | None = None,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Sync API call — run inside asyncio.to_thread."""
    from google import genai
    from google.genai import types

    from server.config.env import get_settings

    settings = get_settings()
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing for post-call transcription")

    client = genai.Client(api_key=key)
    mime = _mime_for_path(path)
    audio_bytes = path.read_bytes()
    if not audio_bytes:
        raise RuntimeError("recording file is empty")

    lang_codes: list[str] = []
    if language_code:
        lang_codes = [language_code]

    config = types.GenerateContentConfig(
        audio_transcription_config=types.AudioTranscriptionConfig(
            diarization=True,
            word_timestamp=True,
            language_codes=lang_codes,
        )
    )
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
        ],
        config=config,
    )
    fallback = str(getattr(response, "text", "") or "").strip()
    words = extract_word_entries(response)
    usage_meta: dict[str, Any] = {"model": model, "bytes": len(audio_bytes)}
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        usage_meta["input_tokens"] = getattr(usage, "prompt_token_count", None)
        usage_meta["output_tokens"] = getattr(usage, "candidates_token_count", None)
    return words, fallback, usage_meta
