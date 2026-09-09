# PSTN flow latency audit

Date: 2026-09-07  
Scope: full PSTN path (Telnyx / Exotel / Plivo → `PstnVoiceLoop` → shared Realtime LLM → TTS → hangup)

Web and PSTN share the live LLM: `LiveTurnOrchestrator.handle_user_turn_stream()` → `RealtimeTextSession.run_turn()`. PSTN-only work is STT ingest, greeting TTS, sentence chunking, `PstnTurnTtsSession`, and carrier audio.

Barge-in stays **off** (`ENABLE_PSTN_BARGE_IN = False`) until the dedicated TEST 7 echo gate. That is intentional, not a regression from this pass.

---

## Runtime sequence

1. Carrier WebSocket `start` (Telnyx `/ws/telnyx-stream`, Exotel `/ws/exotel-stream`, Plivo `/ws/plivo-stream`).
2. `call_lifecycle_service.start(channel="pstn")` — Realtime WS boots in the background (`wait_ready=False`).
3. Bridge creates `PstnVoiceLoop` and `create_task(start_call())`.
4. **STT open, greeting TTS, and “already spoken” note run in parallel.**
5. Inbound PCM → STT. `transcript.final` launches `_run_turn` (tracked in `turn_coordinator`).
6. Turn: TTS socket opens **in parallel** with Realtime deltas → `drain_complete_sentences(allow_first_fast=True)` → TTS text → wire.
7. Explicit goodbye → `end_call` / hangup-without-model → `call_lifecycle_service.end(agent_hangup)` → provider hangup.
8. Remote `stop` → `voice.close()` (now interrupts active TTS) → `end(pstn_hangup)`.

---

## Issues found and fixed

| Issue | Why it hurt | Fix |
|---|---|---|
| `start_call()` awaited STT WebSocket **before** greeting TTS | Caller heard silence until Sarvam STT connected | STT open, greeting speak, and Realtime `note_spoken` run with `asyncio.gather` |
| `_run_turn` opened TTS, **then** started the LLM | First audio = TTS connect + first token, added | TTS `open()` starts as a task; first speakable sentence awaits it |
| Speak lock only covered TTS open, not the rest of the turn | Greeting/turn TTS sockets could overlap | `_speak_lock` held for the whole turn (open + stream + finish) |
| `_run_turn` used bare `asyncio.create_task` | `call_lifecycle_service.end()` drained coordinator tasks but **not** in-flight PSTN turns | `_launch_turn()` uses `turn_coordinator.track()` |
| Greeting was not in Realtime history | First user turn often greeted again | `note_spoken()` injects an assistant item after the opening line |
| `close()` did not stop active TTS | Hangup could leave TTS playing | `close()` calls `interrupt_tts()` |

Left unchanged on purpose:

- **PSTN barge-in remains False** until TEST 7 (echo + Telnyx `clear`).
- Single `_pending_transcript` slot (latest-wins) — documented and tested.
- No live Telnyx/Exotel/Plivo audio in this pass (no phone in the loop).

---

## Critical tests

Always-on (`server/tests/test_pstn_critical_loop.py`):

| Test | Result |
|---|---|
| STT + greeting overlap (`< 220 ms` for two 120 ms jobs) | Pass |
| TTS open overlapped with LLM (`first audio < 160 ms` for two 80 ms jobs) | Pass |
| Agent hangup → `lifecycle.end(agent_hangup)` + provider hangup | Pass |
| Busy turn replays **latest** pending transcript | Pass |
| `interrupt_tts` cancels Realtime + TTS | Pass |
| `close()` interrupts active TTS | Pass |
| In-flight `_run_turn` is drained by `turn_coordinator` | Pass |

Related unit suite: 55 passed (chunking, media flow, Telnyx frames, barge policy with flag forced on, Realtime helpers).

Live (`LIVE_TEST=1`, OpenAI Realtime text-only, `audio_tokens = 0`):

| Probe | Result |
|---|---|
| Web 5-turn critical path | Pass |
| PSTN channel 5-turn same LLM path | Pass |
| `PstnVoiceLoop._run_turn` + live Realtime + fake TTS | Pass; hangup used **`agent_hangup`** |

---

## Live latency (this pass)

Ledger `ms` is orchestrator time-to-first-delta. SSE TTFB includes HTTP overhead.

### PSTN channel (`channel=pstn`, shared orchestrator)

Call start **14 ms**.

| Turn | First token (ledger) | SSE TTFB | Chars |
|---|---:|---:|---:|
| greeting | 1682 ms | 2149 ms | 141 |
| parking | 1237 ms | 1560 ms | 116 |
| language_mix | 1030 ms | 1312 ms | 195 |
| busy (must not hang up) | 1058 ms | 1400 ms | 138 |
| hangup | 810 ms | 912 ms | 30 |

Language-mix output had no Tamil/Korean. Interrupt returned `ok`. Hangup set `should_end`.

### Full PSTN loop (Realtime + `PstnVoiceLoop._run_turn` + fake TTS)

Call start **12 ms**.

| Turn | Time to first TTS text | Notes |
|---|---:|---|
| parking | **1512 ms** | STT skipped; this is LLM → chunk → TTS send |
| hangup | **700 ms** | Lifecycle ended with `reason=agent_hangup` |

First PSTN TTS text is essentially first-token time (1512 vs ledger 1509). Overlapping TTS open is working: it is no longer additive.

### Web (same LLM, for comparison)

Call start **1167 ms** (agent/stack lookup). Follow-up first token **671–1172 ms**. Hangup **671 ms** ledger / **1066 ms** SSE.

---

## What still sits on the model / carrier

- Warm Realtime first token is about **0.7–1.7 s**. That is `gpt-realtime-2.1-mini`, not STT/TTS scheduling.
- Real Sarvam STT + TTS and Telnyx 20 ms pacing are **on top** of these numbers. They were not live-phoned here.
- PSTN barge-in is still disabled. Caller speech during agent TTS is queued as the latest final after the turn, not cut in.

---

## Files touched

- `server/services/pstn_voice_core.py` — parallel start, overlapped TTS open, turn tracking, close interrupt
- `server/realtime/text_session.py`, `manager.py`, `providers/openai.py`, `testing.py` — `note_spoken` / assistant item
- `server/call/call_lifecycle_service.py` — language on session instructions
- `server/tests/test_pstn_critical_loop.py` — new critical loop tests
- `server/tests/test_realtime_live_latency.py` — live PSTN loop probe

Re-run:

```text
python -m pytest server/tests/test_pstn_critical_loop.py server/tests/test_pstn_voice_core.py -q

LIVE_TEST=1 python -m pytest server/tests/test_realtime_live_latency.py -v -s --tb=short
```
