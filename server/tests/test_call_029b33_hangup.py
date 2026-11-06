"""Call 029B33: the voice failed mid-reply and the call was hung up with a goodbye.

Gnani returned "technical difficulties" five seconds into a long reply; the caller
heard silence, asked the agent to hurry, and the next reply read the failed
request's stale end-of-stream from the reused socket, produced no audio, and the
empty-reply path said goodbye and hung up.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.services import pstn_voice_core as core
from server.services.user_turn_hints import asks_to_hurry, build_hurry_turn_hint


def _loop() -> core.PstnVoiceLoop:
    return core.PstnVoiceLoop(session_id="029b33", call_id=None, on_agent_wire=AsyncMock())


class _Session:
    def __init__(self, *, had_error: bool = False, chars: int = 0, seconds: float = 0.0) -> None:
        self.had_error = had_error
        self._chars_sent = chars
        self._tts_audio_seconds = seconds
        self._closed = False
        self.prepare_for_turn = AsyncMock()
        self.close = AsyncMock(side_effect=self._close)

    async def _close(self) -> None:
        self._closed = True


@pytest.mark.asyncio
async def test_a_socket_that_failed_is_never_reused_for_the_next_reply(monkeypatch):
    loop = _loop()
    broken = _Session(had_error=True)
    fresh = _Session()
    loop._call_tts_session = broken
    monkeypatch.setattr(loop, "_get_call_tts_session",
                        lambda: loop._call_tts_session if loop._call_tts_session else fresh)
    session = await loop._acquire_tts_session()
    assert session is fresh
    broken.close.assert_awaited_once()
    fresh.prepare_for_turn.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_healthy_socket_stays_warm(monkeypatch):
    loop = _loop()
    warm = _Session()
    loop._call_tts_session = warm
    monkeypatch.setattr(loop, "_get_call_tts_session", lambda: loop._call_tts_session)
    assert await loop._acquire_tts_session() is warm
    warm.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_empty_reply_is_said_again_on_a_fresh_voice_instead_of_hanging_up(monkeypatch):
    loop = _loop()
    session = _Session(had_error=True)

    async def speak(text, **_):
        loop._wire_frames_out += 25

    monkeypatch.setattr(loop, "speak", speak)
    assert await loop._speak_again_on_fresh_voice(session, "మీకు ఏ details కావాలి?", why="empty_reply") is True
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_second_silent_attempt_reports_failure_so_the_outage_path_runs(monkeypatch):
    loop = _loop()
    monkeypatch.setattr(loop, "speak", AsyncMock())
    assert await loop._speak_again_on_fresh_voice(_Session(), "hello", why="empty_reply") is False
    assert await loop._speak_again_on_fresh_voice(_Session(), "", why="empty_reply") is False


@pytest.mark.asyncio
async def test_no_retry_while_the_caller_is_talking(monkeypatch):
    loop = _loop()
    loop._awaiting_barge_final = True
    speak = AsyncMock()
    monkeypatch.setattr(loop, "speak", speak)
    assert await loop._speak_again_on_fresh_voice(_Session(), "hello", why="empty_reply") is False
    speak.assert_not_awaited()


REPLY = ("తప్పకుండా. మా దగ్గర Tellapur లోని Green Valley Residency 3 BHK apartments ఉన్నాయి. "
         "Kokapet లోని Prestige Heights luxury apartments ఉన్నాయి. Bachupally లో Sai Enclave plots ఉన్నాయి.")


def test_mid_reply_failure_resumes_from_the_sentence_that_broke():
    loop = _loop()
    loop._turn_tts_accum = REPLY
    loop._speech_chars_per_s = 12.0
    # 10 s played: the first two sentences and part of the third (Kokapet ...).
    remainder = loop._unheard_reply_remainder(_Session(had_error=True, seconds=10.0))
    assert remainder.startswith("Kokapet") and remainder.endswith("plots ఉన్నాయి.")
    # The estimate errs early: a break just after a sentence end repeats that sentence.
    assert loop._unheard_reply_remainder(_Session(seconds=7.0)).startswith("మా దగ్గర")
    # Nothing played: say all of it. Everything played: nothing to resume.
    assert loop._unheard_reply_remainder(_Session(seconds=0.0)) == REPLY
    assert loop._unheard_reply_remainder(_Session(seconds=60.0)) == ""


def test_speaking_rate_is_learned_from_replies_that_played_in_full():
    loop = _loop()
    loop._note_speech_rate(_Session(chars=150, seconds=10.0))
    assert loop._speech_chars_per_s == pytest.approx(15.0)
    loop._note_speech_rate(_Session(chars=10, seconds=0.5))  # too short to measure
    assert loop._speech_chars_per_s == pytest.approx(15.0)


@pytest.mark.parametrize("text", [
    "చేయండి నాన్న, కొంచెం లేట్ అవుతుంది. కొంచెం ఎర్లీగా చెప్పగలరా? ఫాస్ట్గా చెప్పండి కొంచెం.",
    "please hurry and answer fast", "Just get to the point", "जल्दी बताइए", "jaldi bolo",
    "சீக்கிரம் சொல்லுங்க", "ಬೇಗ ಹೇಳಿ", "വേഗം പറയൂ", "लवकर सांगा", "তাড়াতাড়ি বলুন",
    "જલ્દી કહો", "ਜਲਦੀ ਦੱਸੋ",
])
def test_a_request_to_hurry_is_recognised_in_every_language(text):
    assert asks_to_hurry(text)


@pytest.mark.parametrize("text", ["I had breakfast", "అపార్ట్మెంట్ ధర ఎంత?", "", "ok thanks"])
def test_ordinary_turns_are_not_hurry_requests(text):
    assert not asks_to_hurry(text)


def test_hurry_hint_forbids_the_unclear_audio_reply():
    hint = build_hurry_turn_hint(just_asked=True)
    assert "Do not ask them to repeat" in hint and "one or two" in hint
    assert "short" in build_hurry_turn_hint(just_asked=False)

