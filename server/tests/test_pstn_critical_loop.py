"""Critical PSTN voice-loop tests — greeting overlap, first audio, hangup, turn drain."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from server.call import turn_coordinator
from server.services.pstn_voice_core import PstnVoiceLoop


class FakeTtsSession:
    def __init__(self, voice, *, open_delay: float = 0.0):
        self.voice = voice
        self.open_delay = open_delay
        self.texts: list[str] = []
        self.open_started: float | None = None
        self.open_done: float | None = None
        self.first_send: float | None = None
        self.finished = False
        self.closed = False
        self.interrupted = False
        self._chars_sent = 0

    @property
    def has_sent_text(self) -> bool:
        return self._chars_sent > 0

    async def open(self, **_kwargs) -> None:
        self.open_started = time.perf_counter()
        if self.open_delay:
            await asyncio.sleep(self.open_delay)
        self.open_done = time.perf_counter()

    async def send_text(self, text: str) -> None:
        if self.first_send is None:
            self.first_send = time.perf_counter()
        self.texts.append(text)
        self._chars_sent += len(text or "")

    async def finish(self) -> None:
        self.finished = True

    async def close(self) -> None:
        self.closed = True

    async def interrupt(self) -> None:
        self.interrupted = True
        await self.close()


@pytest.mark.asyncio
async def test_start_call_overlaps_stt_and_greeting(monkeypatch):
    marks: dict[str, float | str] = {}

    async def slow_stt(self):
        marks["stt_start"] = time.perf_counter()
        await asyncio.sleep(0.12)
        marks["stt_end"] = time.perf_counter()

    async def slow_speak(self, text, **_kwargs):
        marks["speak_start"] = time.perf_counter()
        await asyncio.sleep(0.12)
        marks["speak_end"] = time.perf_counter()
        marks["greeting"] = text
        # Successful greeting now requires audio evidence before history priming.
        self._wire_frames_out += 1

    async def note(self, greeting):
        marks["noted"] = greeting

    loop = PstnVoiceLoop(session_id="s", call_id="c-overlap", on_agent_wire=AsyncMock())
    monkeypatch.setattr(PstnVoiceLoop, "open_stt", slow_stt)
    monkeypatch.setattr(PstnVoiceLoop, "speak", slow_speak)
    monkeypatch.setattr(PstnVoiceLoop, "_note_opening_spoken", note)
    monkeypatch.setattr(
        "server.services.pstn_voice_core.extract_opening_greeting",
        lambda *_a, **_k: "Namaste! Nenu Priya.",
    )

    t0 = time.perf_counter()
    await loop.start_call()
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.22, f"STT and greeting ran serially: {elapsed:.3f}s"
    assert marks["greeting"] == "Namaste! Nenu Priya."
    assert marks["noted"] == "Namaste! Nenu Priya."
    assert abs(float(marks["stt_start"]) - float(marks["speak_start"])) < 0.05


@pytest.mark.asyncio
async def test_run_turn_overlaps_tts_open_with_llm(monkeypatch):
    fake: FakeTtsSession | None = None

    def factory(voice):
        nonlocal fake
        fake = FakeTtsSession(voice, open_delay=0.08)
        return fake

    async def fake_stream(**_kwargs):
        await asyncio.sleep(0.08)
        yield {"delta": "Sure I can help you with that property today. "}
        yield {
            "done": True,
            "text": "Sure I can help you with that property today.",
            "end_call": {"should_end": False, "reason": "none", "farewell": ""},
        }

    loop = PstnVoiceLoop(session_id="s", call_id="c-first-audio", on_agent_wire=AsyncMock())
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )

    t0 = time.perf_counter()
    await loop._run_turn("Parking unda?")
    first_ms = (fake.first_send - t0) * 1000 if fake and fake.first_send else 9_999
    assert fake is not None
    assert fake.texts
    assert fake.finished
    assert fake.closed
    assert first_ms < 160, f"TTS open still serial with LLM: first audio {first_ms:.0f}ms"


@pytest.mark.asyncio
async def test_run_turn_agent_hangup_calls_lifecycle(monkeypatch):
    ended = {}
    hung_up = {}

    def factory(voice):
        return FakeTtsSession(voice)

    async def fake_stream(**_kwargs):
        yield {"delta": "Thank you. Goodbye."}
        yield {
            "done": True,
            "text": "Thank you. Goodbye.",
            "end_call": {"should_end": True, "reason": "goodbye", "farewell": "Thank you. Goodbye."},
        }

    async def fake_end(call_id, reason="user_stop"):
        ended["call_id"] = call_id
        ended["reason"] = reason

    async def on_hangup():
        hung_up["ok"] = True

    loop = PstnVoiceLoop(session_id="s", call_id="c-hangup", on_agent_wire=AsyncMock())
    loop.set_hangup_handler(on_hangup)
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    from server.call.call_lifecycle_service import call_lifecycle_service as lifecycle

    monkeypatch.setattr(lifecycle, "end", fake_end)

    await loop._run_turn("ok bye hang up")
    assert ended == {"call_id": "c-hangup", "reason": "agent_hangup"}
    assert hung_up.get("ok") is True


@pytest.mark.asyncio
async def test_run_turn_firm_refusal_hangup(monkeypatch):
    ended = {}
    hung_up = {}

    def factory(voice):
        return FakeTtsSession(voice)

    async def fake_stream(**_kwargs):
        yield {"delta": "Thank you for your time. Goodbye."}
        yield {
            "done": True,
            "text": "Thank you for your time. Goodbye.",
            "end_call": {
                "should_end": True,
                "reason": "firm_refusal",
                "farewell": "Thank you for your time. Goodbye.",
            },
        }

    async def fake_end(call_id, reason="user_stop"):
        ended.update(call_id=call_id, reason=reason)

    async def on_hangup():
        hung_up["ok"] = True

    loop = PstnVoiceLoop(session_id="s", call_id="c-refuse", on_agent_wire=AsyncMock())
    loop.set_hangup_handler(on_hangup)
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    from server.call.call_lifecycle_service import call_lifecycle_service as lifecycle

    monkeypatch.setattr(lifecycle, "end", fake_end)

    await loop._run_turn("I'm not interested")
    assert ended == {"call_id": "c-refuse", "reason": "agent_hangup"}
    assert hung_up.get("ok") is True


@pytest.mark.asyncio
async def test_run_turn_goal_complete_hangup(monkeypatch):
    ended = {}
    hung_up = {}
    spoken = []

    def factory(voice):
        session = FakeTtsSession(voice)
        spoken.append(session)
        return session

    async def fake_stream(**_kwargs):
        yield {"delta": "Noted — our team will contact you. Goodbye."}
        yield {
            "done": True,
            "text": "Noted — our team will contact you. Goodbye.",
            "end_call": {
                "should_end": True,
                "reason": "goal_complete",
                "farewell": "Noted — our team will contact you. Goodbye.",
            },
        }

    async def fake_end(call_id, reason="user_stop"):
        ended.update(call_id=call_id, reason=reason)

    async def on_hangup():
        hung_up["ok"] = True

    loop = PstnVoiceLoop(session_id="s", call_id="c-goal", on_agent_wire=AsyncMock())
    loop.set_hangup_handler(on_hangup)
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    from server.call.call_lifecycle_service import call_lifecycle_service as lifecycle

    monkeypatch.setattr(lifecycle, "end", fake_end)

    await loop._run_turn("Yes, please have the team call me back")
    assert ended == {"call_id": "c-goal", "reason": "agent_hangup"}
    assert hung_up.get("ok") is True
    assert spoken and any("team will contact" in t.lower() for t in spoken[0].texts)


@pytest.mark.asyncio
async def test_busy_turn_replays_latest_pending_transcript(monkeypatch):
    turn_coordinator.reset_for_tests()
    first_started = asyncio.Event()
    first_release = asyncio.Event()
    seen: list[str] = []

    def factory(voice):
        return FakeTtsSession(voice)

    async def fake_stream(**kwargs):
        transcript = str(kwargs.get("transcript") or "")
        seen.append(transcript)
        if transcript == "one":
            first_started.set()
            await first_release.wait()
        yield {"delta": f"reply {transcript}"}
        yield {
            "done": True,
            "text": f"reply {transcript}",
            "end_call": {"should_end": False, "reason": "none", "farewell": ""},
        }

    loop = PstnVoiceLoop(session_id="s", call_id="c-pending", on_agent_wire=AsyncMock())
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )

    first = asyncio.create_task(loop._run_turn("one"))
    await first_started.wait()
    loop._pending_transcript = "two"
    loop._pending_transcript = "three"
    first_release.set()
    await first
    await turn_coordinator.drain("c-pending")
    assert seen == ["one", "three"]
    turn_coordinator.reset_for_tests()


@pytest.mark.asyncio
async def test_interrupt_cancels_realtime_and_tts(monkeypatch):
    cancelled = {}
    fake = FakeTtsSession(None)

    async def fake_cancel(call_id):
        cancelled["call_id"] = call_id

    loop = PstnVoiceLoop(session_id="s", call_id="c-barge", on_agent_wire=AsyncMock())
    loop._active_tts_session = fake
    monkeypatch.setattr(
        "server.realtime.manager.realtime_text_manager.cancel",
        fake_cancel,
    )
    await loop.interrupt_tts()
    # Realtime cancel is fire-and-forget off the audio-stop path.
    await asyncio.sleep(0)
    assert fake.interrupted is True
    assert cancelled["call_id"] == "c-barge"


@pytest.mark.asyncio
async def test_close_interrupts_active_tts(monkeypatch):
    fake = FakeTtsSession(None)
    loop = PstnVoiceLoop(session_id="s", call_id="c-close", on_agent_wire=AsyncMock())
    loop._active_tts_session = fake
    monkeypatch.setattr(
        "server.realtime.manager.realtime_text_manager.cancel",
        AsyncMock(),
    )
    await loop.close()
    assert fake.interrupted is True
    assert loop._closed is True


@pytest.mark.asyncio
async def test_launch_turn_is_drained_on_coordinator(monkeypatch):
    turn_coordinator.reset_for_tests()
    started = asyncio.Event()
    release = asyncio.Event()

    def factory(voice):
        return FakeTtsSession(voice)

    async def fake_stream(**_kwargs):
        started.set()
        await release.wait()
        yield {"delta": "Hello there friend."}
        yield {
            "done": True,
            "text": "Hello there friend.",
            "end_call": {"should_end": False, "reason": "none", "farewell": ""},
        }

    loop = PstnVoiceLoop(session_id="s", call_id="c-drain", on_agent_wire=AsyncMock())
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", factory)
    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.pstn_turn_runtime",
        lambda *_a, **_k: {},
    )
    loop._launch_turn("hello")
    await started.wait()
    drain_task = asyncio.create_task(turn_coordinator.drain("c-drain"))
    await asyncio.sleep(0.02)
    assert not drain_task.done()
    release.set()
    await drain_task
    turn_coordinator.reset_for_tests()
