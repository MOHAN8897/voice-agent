# Realtime live latency audit

Date: 2026-09-07  
Scope: shared web-agent and PSTN live path after `REALTIME_TEXT_LLM_CRITICAL_AUDIT.md`  
Stack: selected STT final → persistent OpenAI Realtime (`gpt-realtime-2.1-mini`, text in/out) → selected TTS

Web and PSTN use the same LLM path: `LiveTurnOrchestrator.handle_user_turn_stream()` → `RealtimeTextSession.run_turn()`. Greeting is still compiled-brain `extract_opening_greeting()`, not Realtime. The first caller utterance is the first Realtime generation.

---

## What was slow

| Issue | Effect |
|---|---|
| `call_lifecycle_service.start()` **awaited** the Realtime WebSocket handshake | `/api/call/start` and PSTN greeting waited on OpenAI connect + `session.updated` |
| Web `StreamingTextChunker` held **all** text until 140 characters or `done` | Short Realtime replies (typical 1–2 sentences) did not start TTS until the model finished |
| First-audio threshold was **28 characters** on PSTN and web | First clause sat in the buffer instead of going to TTS |
| `session.created` / `session.updated` were **queued** as turn events | First turn could spend time draining handshake events before the first text delta |
| Cancel drain waited **2.0s** | Barge-in felt stuck |
| Language filter `.strip()` on every delta, and contaminant-only chunks **fell back to the original text** | Token glue; Tamil/Korean could reappear |
| Default Realtime VAD was left on; no output cap on the socket | Extra audio-turn machinery on a text-only session; replies could run long |
| Dead socket was not detected | After a closed event loop / dropped WS, turn 2 returned empty text (`Event loop is closed`) |
| Live latency tests posted `/api/brain/stream` **without `callId`** | They measured HTTP Luna, not Realtime |

---

## Fixes and optimizations

### 1. Non-blocking session boot (start + greeting)

- Register the Realtime session immediately.
- Boot the WebSocket in a background task (`wait_ready=False` from call start).
- First `run_turn` still `wait_ready()` if the handshake is not done yet.
- PSTN greeting can play while the socket comes up.

**Measured call start**

- Browser: **844 ms** (agent/stack lookup, not WS)
- PSTN: **12 ms**

### 2. Faster first audio (web + PSTN)

- Web: removed the 140-character hold during streaming. First sentence / first word-boundary now flushes to TTS.
- Shared first-chunk threshold: **28 → 18** characters (`voice_pipeline_limits.py` and `web/lib/voice/types.ts`).
- Tiny complete replies still emit as one chunk on flush (prosody).

### 3. Socket and turn hygiene

- Do **not** queue `session.created` / `session.updated`.
- Start the recv pump **before** `session.update`.
- Disable audio VAD: `audio.input.turn_detection = null`.
- Cap live replies: `max_output_tokens = 280` on session and on `response.create`.
- Cancel drain timeout **2.0s → 0.4s**, then `discard_queued()`.
- Ignore leftover deltas from a cancelled `response_id`.
- If the pump dies, **reconnect on the next turn** instead of yielding an empty reply.

### 4. Language guard (streaming-safe)

- ASCII fast path (no scan, no strip).
- Streaming deltas keep token spaces.
- Contaminant-only chunks return `""`, never the original Tamil/Korean/CJK text.

### 5. Tests

- Unit coverage for background boot, reconnect, language guard, stale-delta drop, PSTN first-audio from Realtime deltas.
- Live probes: `LIVE_TEST=1 python -m pytest server/tests/test_realtime_live_latency.py -v -s`

Audio is still never sent to OpenAI. Post-call JSON still uses HTTP `gpt-5.6-luna`.

---

## Live measurements (OpenAI Realtime, text-only)

Probes used a long-lived ASGI client so the persistent socket survived across turns (Starlette `TestClient` closes the loop per request and killed the WS).

`LEDGER_ASSISTANT ms` is orchestrator time-to-first-delta (the number that matters for “when can TTS start”). SSE `TTFB` includes HTTP overhead on the test transport.

### Browser / web agent (`channel=browser`)

Call start **844 ms**. Pipeline `realtime_text`. All turns streamed. `audio_tokens` stayed `0`. Hangup set `should_end`. Language-mix output had no Tamil/Korean.

| Turn | Transcript intent | First token (ledger) | SSE TTFB | Total | Chars |
|---|---|---:|---:|---:|---:|
| greeting | Telugu who-are-you | 1218 ms | 1473 ms | 1473 ms | 180 |
| parking | Parking + price | 1558 ms | 1788 ms | 1789 ms | 182 |
| language_mix | Mixed scripts in user text | 1140 ms | 1510 ms | 1510 ms | 193 |
| busy | “maybe later” (must not hang up) | 813 ms | 1064 ms | 1065 ms | 142 |
| hangup | Explicit goodbye | 527 ms | 822 ms | 823 ms | 48 |

Follow-up median first-token ≈ **0.8–1.1 s**, hangup **527 ms**.

### PSTN channel (`channel=pstn`, same orchestrator)

Call start **12 ms**. Same pipeline. Same pass/fail checks.

| Turn | First token (ledger) | SSE TTFB | Total | Chars |
|---|---:|---:|---:|---:|
| greeting | 1408 ms | 1757 ms | 1757 ms | 173 |
| parking | 934 ms | 1302 ms | 1302 ms | 211 |
| language_mix | 908 ms | 1229 ms | 1229 ms | 164 |
| busy | 580 ms | 679 ms | 680 ms | 92 |
| hangup | 875 ms | 1046 ms | 1046 ms | 80 |

Follow-up first-token **580–934 ms**. PSTN start no longer waits on Realtime, so the opening greeting can play immediately while the socket boots.

### How this feels on a real call

1. Call starts without a multi-second WS stall.
2. PSTN/web greeting can speak during connect.
3. After the first user turn warms the session, later turns land around **0.5–1.1 s** to first text.
4. First TTS chunk can start at the first sentence (or ~18 characters), not after 140 characters or full completion.
5. Barge-in cancel returns in **≤ 0.4 s** plus provider `response.cancel`.
6. Explicit hangup still ends the call without waiting for a successful model tool call.

SSE TTFB ≈ total in these probes because replies are short (one burst after the first token). That is expected for 1–2 sentence voice replies, not a sign that streaming is off (`streamed=True` on every turn).

---

## Critical path coverage

| Path | Result |
|---|---|
| Web `POST /api/call/start` + `/api/brain/stream` with `callId` | Pass (5 turns) |
| PSTN channel start + same brain stream | Pass (5 turns) |
| Language mix / Tamil+Korean leak | Pass (stripped on output) |
| Busy / maybe-later does not force hangup | Pass (conversation continued) |
| Explicit hangup | Pass (`should_end`) |
| `/api/session/interrupt` | Pass (`ok: true`) |
| Zero audio tokens on Realtime usage | Pass when usage present |
| Unit: background boot &lt; 400 ms | Pass |
| Unit: reconnect after dead adapter | Pass |
| Unit: PSTN `drain_complete_sentences` from Realtime deltas | Pass |
| Classic eight-turn / catalog / lifecycle | Pass (no regression) |

---

## Remaining limits (not bugs in this pass)

- **Model floor:** `gpt-realtime-2.1-mini` first token is still ~0.5–1.6 s after a warm socket. We cannot make the provider faster from this repo.
- **First user turn** may include leftover handshake if the caller speaks before `session.updated` (~1.2–1.8 s). PSTN greeting covers most of that wall-clock.
- **Reply length:** 140–210 characters is still a bit talky for voice. The cap is 280 tokens (existing `openaiMaxTokens` default). Tightening further is a product/prompt choice, not a transport bug.
- **ASGI test transport** adds ~250–400 ms versus in-process ledger first-token. Browser/PSTN media path will add STT + TTS on top of these LLM numbers.
- **No live Telnyx/Exotel audio** in this pass. PSTN was exercised through the shared lifecycle + orchestrator path, which is the LLM/TTS sequencing used by `PstnVoiceLoop._run_turn()`.

---

## Files touched

- `server/call/call_lifecycle_service.py` — background Realtime boot
- `server/realtime/manager.py` — register first, optional `wait_ready`
- `server/realtime/text_session.py` — reconnect, 0.4 s cancel drain
- `server/realtime/providers/openai.py` — VAD off, token cap, generation isolation
- `server/realtime/language_guard.py` — streaming-safe filter
- `server/services/voice_pipeline_limits.py`, `web/lib/voice/types.ts`, `web/lib/voice/text-chunker.ts` — first audio
- `server/tests/test_realtime_text.py`, `test_realtime_live_latency.py`, `conftest.py`

Re-run live probes:

```text
LIVE_TEST=1 python -m pytest server/tests/test_realtime_live_latency.py -v -s --tb=short
```
