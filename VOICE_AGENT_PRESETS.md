# Voice Agent Presets & Implementation Specs

Operational specs and industry-standard patterns for PSTN voice quality, TTS pipeline behavior, and web agent prosody.

---

# Fix PSTN Audio Queue Backpressure Without Dropping Speech

## Objective

Fix the PSTN outbound audio pipeline so that TTS audio is delivered continuously to Telnyx without queue saturation, burst playback, stutter, crackle, or loss of speech.

### CRITICAL RULE

**DO NOT DROP AUDIO FRAMES DURING NORMAL SPEECH.**

If the outbound audio queue becomes full or reaches its high-water mark, the system must **apply backpressure and slow/wait the audio producer**.

Backpressure means:

> TTS/audio production waits until the playback queue has enough capacity.

It does **NOT** mean:

> Queue is full → discard audio frames.

---

## 1. Audit the Existing Pipeline First

Before modifying code, trace the complete PSTN audio path:

```text
LLM
 ↓
text chunking
 ↓
TTS streaming
 ↓
TTS audio receiver/reader
 ↓
PCM/μ-law conversion
 ↓
20ms audio frames
 ↓
outbound asyncio queue
 ↓
20ms RTP/WebSocket pacing
 ↓
Telnyx
 ↓
caller
```

Identify:

- Where TTS audio is received.
- Where TTS audio is converted into frames.
- Where frames enter the outbound queue.
- Where the queue has its maximum size.
- Where frames are currently dropped.
- Where `queue.put()` / `put_nowait()` / timeout logic is used.
- Where the 20ms playback loop consumes frames.
- What happens during barge-in.
- What happens during call termination.
- Whether TTS continues generating audio while the local queue is blocked.
- Whether the specific TTS provider supports any real streaming flow-control mechanism.

Do not change unrelated components before understanding this path.

### Repo map (current code)

| Stage | File | Function / symbol |
|-------|------|-------------------|
| Text chunking | `server/services/pstn_text_chunker.py` | `drain_complete_sentences()` |
| TTS session | `server/services/pstn_turn_tts.py` | `PstnTurnTtsSession._reader_loop()`, `_emit_audio_chunk()` |
| Frame enqueue | `server/services/telnyx_pstn_bridge.py` | `_send_agent_wire()` |
| Outbound queue | `server/services/telnyx_pstn_bridge.py` | `MAX_AUDIO_QUEUE_FRAMES`, `_out_queue` |
| RTP pacer | `server/services/telnyx_pstn_bridge.py` | `_out_worker()` |
| Drop on stale gen | `server/services/telnyx_pstn_bridge.py` | `_out_worker()`, `_send_agent_wire()` — counted as `barge_in_discarded_frames` |
| Playout governor | `server/services/telnyx_pstn_bridge.py` | `_wait_for_playout_capacity()`, `QUEUE_HIGH_WATERMARK` |

---

## 2. Required Queue Behavior

Use a bounded queue.

Start with these values unless existing measurements demonstrate better values:

```text
HIGH_WATERMARK = 10–15 frames
LOW_WATERMARK  = 3–5 frames
MAX_QUEUE      = 15–20 frames
```

Do NOT blindly use 50 frames as the normal operating buffer.

The queue should behave approximately like this:

```text
queue < HIGH_WATERMARK
    ↓
producer can continue

queue >= HIGH_WATERMARK
    ↓
producer waits / applies backpressure

RTP playback consumes frames
    ↓
queue falls below LOW_WATERMARK
    ↓
producer resumes
```

The exact implementation can use an `asyncio.Condition`, semaphore, credits, or another appropriate mechanism.

Choose the implementation that fits the existing architecture.

---

## 3. ABSOLUTE NO-DROP RULE

During ordinary agent speech:

```text
queue full
→ WAIT
→ DO NOT DROP
→ DO NOT DISCARD NEWEST FRAME
→ DO NOT DISCARD OLDEST FRAME
→ DO NOT overwrite existing audio
→ DO NOT silently truncate audio
```

Remove or redesign logic such as:

```python
queue.put_nowait(...)
```

followed by:

```python
except asyncio.QueueFull:
    drop_frame()
```

or:

```python
if queue.full():
    frames_dropped += 1
```

if that logic is being used for normal speech.

Likewise, do not solve the problem by simply increasing:

```text
MAX_AUDIO_QUEUE_FRAMES
```

to a huge value.

That only hides the producer/consumer mismatch and increases latency.

---

## 4. Producer Backpressure

The TTS audio producer must not be allowed to continuously push audio into the playback queue faster than the RTP consumer can play it.

Conceptually:

```python
async def enqueue_audio(frame):
    while queue_is_above_high_watermark():
        await wait_for_playback_capacity()

    await outbound_queue.put(frame)
```

The actual implementation should be adapted to the existing code.

Important:

**The producer must be cancellable.**

If the user interrupts the agent:

```text
BARGE-IN
   ↓
cancel current TTS generation
   ↓
wake/unblock any producer waiting on queue capacity
   ↓
clear obsolete queued audio
   ↓
start new response
```

A producer waiting for queue capacity must never remain blocked after barge-in or hangup.

---

## 5. Do NOT Confuse Backpressure With Dropping

The implementation must explicitly distinguish these two cases.

### Case A — Normal speech

```text
TTS produces faster than playback
        ↓
queue reaches high watermark
        ↓
producer waits
        ↓
RTP continues consuming at 20ms/frame
        ↓
queue decreases
        ↓
producer resumes
```

Expected:

```text
dropped_frames = 0
```

### Case B — User interrupts agent

```text
Agent is speaking
        ↓
User speaks
        ↓
BARGE-IN detected
        ↓
Cancel old TTS generation
        ↓
Clear obsolete queued audio
        ↓
Generate response to user's new utterance
```

Discarding the **old pending response** here is intentional.

These are not considered audio-quality frame drops because that audio is obsolete and should no longer be played.

Track these separately, for example:

```text
dropped_frames_reason = "barge_in_cancel"
```

rather than incorrectly counting them as normal queue overflow.

---

## 6. Hangup / Call Termination

When the call ends:

```text
cancel TTS
cancel producer
cancel playback
clear queue
release resources
```

Do not allow blocked `queue.put()` or backpressure waits to keep tasks alive after call termination.

---

## 7. RTP / Telnyx Playback Must Remain Clock-Driven

The consumer/playback side should continue sending audio at the correct real-time cadence.

For 20ms frames:

```text
1 frame every 20ms
≈ 50 frames/second
```

Do NOT make the RTP sender consume the queue as quickly as frames arrive.

Do NOT burst 10 frames immediately just because 10 frames are available.

The playback side should remain paced by the media clock.

Conceptually:

```text
queue
 ↓
20ms pacer
 ↓
20ms frame
 ↓
Telnyx
 ↓
20ms
 ↓
next frame
```

---

## 8. Important TTS Streaming Caveat

Do not assume that:

```text
"stop reading TTS WebSocket"
```

automatically means:

```text
"stop TTS provider from generating audio"
```

Investigate the actual TTS provider streaming behavior.

If the provider supports true flow control/backpressure, use it where appropriate.

If it does not, implement bounded local buffering and appropriate request/chunk pacing so that remote TTS generation cannot create an uncontrolled local backlog.

Do not claim that WebSocket read-pausing provides provider-side backpressure unless the provider's protocol actually guarantees that behavior.

---

## 9. Prevent Normal-Speech Queue Timeouts From Becoming Audio Loss

If the existing code has logic similar to:

```python
await asyncio.wait_for(queue.put(frame), timeout=2.0)
```

and then drops the frame when the timeout expires, do NOT keep this behavior for ordinary speech.

Instead:

- Make the producer wait for capacity.
- Allow cancellation to interrupt the wait.
- Handle barge-in immediately.
- Handle hangup immediately.
- Never silently lose speech because the queue temporarily reached its watermark.

If a timeout is retained for defensive programming, it must NOT silently discard normal speech frames. Surface the failure clearly and investigate the underlying producer/consumer problem.

---

## 10. Add Observability

Add or preserve metrics/logging for:

```text
queue_depth
queue_depth_p50
queue_depth_p95
queue_depth_p99
queue_high_watermark_events
producer_backpressure_wait_ms
producer_backpressure_wait_count
playout_underrun_count
normal_speech_dropped_frames
barge_in_discarded_frames
hangup_discarded_frames
tts_generation_lag_ms
```

Most importantly:

```text
normal_speech_dropped_frames
```

must remain:

```text
0
```

under healthy operation.

Do not combine intentional barge-in cancellation with normal queue overflow.

### UI verification (Test Studio)

During a live Telnyx call, use **Live call media flow** (`web/components/dev/test-studio/LiveMediaFlowDebugger.tsx`):

- **Queue · N** on the outbound pipeline — target N &lt; 15 during speech.
- Filter event log by **Queue** — watch `outbound_queued` and `q` size.
- Health failures — `AUDIO_BACKLOG` should not appear during normal replies.

---

## 11. Detect the Real Failure Mode

After implementation, test with:

### Test 1 — Short response

Ask the agent a question requiring a short answer.

Verify:

```text
smooth speech
queue stays controlled
normal_speech_dropped_frames = 0
```

### Test 2 — Long response

Force a long response.

Verify:

```text
queue does not permanently saturate
producer waits when necessary
audio remains continuous
no missing words
no crackle caused by frame loss
```

### Test 3 — Rapid TTS generation

Use a response where TTS generates audio much faster than real-time.

Verify:

```text
producer backpressure activates
queue remains bounded
no normal-speech frame drops
```

### Test 4 — Barge-in

Interrupt the agent while it is speaking.

Verify:

```text
old TTS is cancelled
old queued audio is discarded
producer wait is cancelled
new response starts
no stale old speech continues
```

### Test 5 — Hangup

Hang up while TTS is actively producing audio.

Verify:

```text
all producer waits terminate
TTS is cancelled
queue is cleared
no task remains blocked
```

---

## 12. Acceptance Criteria

The implementation is NOT complete unless all of these are true:

### Normal speech

```text
normal_speech_dropped_frames = 0
```

### Queue

Target starting point:

```text
p95 queue depth < 10 frames
p99 queue depth < 15 frames
MAX_QUEUE ≈ 15–20 frames
```

Tune these based on real measurements rather than treating them as immutable constants.

### Playback

```text
~50 frames/sec
20ms/frame
continuous pacing
no burst playback
```

### Barge-in

```text
old TTS cancelled
old queued audio cleared
new response generated
```

### Audio quality

```text
no missing words
no artificial gaps caused by queue overflow
no cracking caused by dropped frames
no growing playback latency
```

---

## 13. Do Not Make These Incorrect Fixes

DO NOT:

1. Fix the problem by increasing the queue to 100/500/1000 frames.
2. Drop newest frames when the queue is full.
3. Drop oldest frames during normal speech.
4. Randomly discard PCM chunks.
5. Speed up the RTP sender to drain the queue.
6. Burst-send accumulated frames.
7. Treat barge-in cancellation as a normal queue overflow.
8. Assume stopping local TTS reads automatically stops remote TTS generation.
9. Add arbitrary sleeps instead of real producer/consumer flow control.
10. Hide queue saturation by suppressing logs/metrics.

---

## 14. Preserve Existing Architecture Where Possible

Do not rewrite the entire PSTN pipeline unnecessarily.

First identify the existing:

```text
TTS reader
→ audio frame producer
→ outbound queue
→ RTP/WebSocket sender
```

Then implement proper flow control around those components.

Avoid changing:

- Telnyx signaling
- STT
- LLM behavior
- codec configuration
- barge-in detection

unless the investigation proves they are directly involved.

---

## Final Requirement (PSTN Queue)

The fundamental invariant of this implementation must be:

> **During normal agent speech, if TTS produces audio faster than PSTN playback can consume it, the producer must wait rather than dropping audio.**

The queue is a **bounded buffer**, not a lossy buffer.

The only expected intentional audio discard should occur when the current response becomes obsolete due to:

```text
BARGE-IN
or
CALL HANGUP
```

Implement this carefully, run the relevant tests, inspect the resulting logs/metrics, and report:

1. Which files/functions were changed.
2. How backpressure works in the actual implementation.
3. How normal speech is guaranteed not to drop frames.
4. How barge-in cancels and clears obsolete audio.
5. Queue depth before vs after.
6. Number of normal-speech dropped frames before vs after.
7. Any remaining risk caused by the specific TTS provider's streaming behavior.
8. Any tests that could not be performed.

---

# Related Industry-Standard Fixes (Full Voice Stack)

These patterns apply to the broader PSTN + web voice issues beyond queue backpressure. Use alongside the queue spec above.

## Problem 1 — TTS provider / voice config mismatch (PSTN)

**Current behavior:** `merge_pstn_tts_config()` picks Sarvam, but `_connect_tts_upstream()` re-resolves and may open Cartesia with a Sarvam voice name.

**Industry standard — immutable call media contract:**

At dial/answer, resolve once and freeze:

```text
CallMediaProfile {
  tts_provider, tts_model, voice_id, sample_rate, codec, language
}
```

Every downstream step uses only that object: prewarm, greeting, turn TTS, fallback (explicit re-resolve only).

**Rules:**

- Stack lock at call start — runtime UI overrides cannot change provider mid-call.
- Connect from resolved profile — never “config from A, socket from B.”
- Voice ID is provider-scoped — Sarvam names vs Cartesia UUIDs; validate at dial time.
- Fail fast at validation — block outbound dial if stack + voice are incompatible.

**Fix shape:** `PstnTurnTtsSession.open()` should connect using `self._merged` provider directly, not `_connect_tts_upstream()` which re-runs `resolve_tts_config()`.

---

## Problem 3 — Multiple TTS text chunks per reply (burst synthesis)

**Current behavior:** `drain_complete_sentences()` splits at 14/40/72 chars and on commas → multiple `send_text()` per turn → TTS bursts → queue fills.

**Industry standard — semantic chunking:**

| Approach | When used |
|----------|-----------|
| One TTS request per sentence | Most common for quality PSTN |
| One TTS request per full turn | Best quality; slightly higher TTFA |
| Sub-sentence chunking | Only if TTFA &lt; 300ms is mandatory |

**Do not flush on:** token boundaries, commas/semicolons mid-thought, arbitrary char counts (40, 72).

**Do flush on:** `. ? ! ।` (real sentence ends), end of LLM stream (tail only).

**Optional:** Hold text 50–150ms after last token before first TTS send (coalesce micro-deltas).

---

## Problem 5 — Prewarm uses same broken connect path

**Industry standard — warm path = hot path:**

- Prewarm uses the same `CallMediaProfile`, TTS session factory, and codec chain as live speech.
- Warm during ring (outbound norm).
- Adopt-or-regenerate: play cached frames only if `generation_id` matches; else synthesize live.
- Health gate: don't play greeting until `prewarm.status == ready` or fallback is armed.

---

## Problem 6 — Web adds `.` to every chunk (false sentence ends)

**Current behavior:** PSTN uses `ensure_terminal=False` on stream chunks; web `prepareSpokenReply()` always adds terminal punctuation.

**Industry standard — prosody-safe streaming text:**

| Chunk type | Punctuation rule |
|------------|------------------|
| Intermediate streaming | Preserve LLM punctuation; no forced `.` |
| Final chunk / flush | Optional single terminal if missing |
| Full-turn synthesis | One `prepare_spoken_reply()` pass at end |

**Fix shape:** Web `TurnTtsPipeline` should use `ensureTerminal: false` for intermediate chunks; terminal pass only on `finishLlm()`.

---

## Problem 7 — Clause splitting at 40 characters

**Industry standard — latency budget allocation:**

| Tier | First audio target | Chunking |
|------|-------------------|----------|
| Low-latency | &lt; 400ms | First word group (8–12 words), then sentences |
| Balanced (PSTN default) | &lt; 700ms | First full sentence only |
| Quality | &lt; 1200ms | Full turn one shot |

Do not split on commas for conversational TTS. Shorten LLM first sentence via prompt instead.

---

## Problem 8 — Multiple `text` messages before one `flush`

**Industry default for telephony:** single utterance per turn for replies under ~300 chars:

```text
config → text(full_reply) → flush
```

Multi-utterance (`text(sent1) → text(sent2) → flush`) only for long monologues with complete sentence boundaries.

---

## Cross-cutting architecture

```text
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐     ┌────────┐
│ LLM stream  │────▶│ Sentence buffer  │────▶│ TTS session │────▶│ Playout│
│             │     │ (semantic only)  │     │ (locked cfg)│     │ governor│
└─────────────┘     └──────────────────┘     └─────────────┘     └───┬────┘
                                                                      │
                                                              ┌───────▼───────┐
                                                              │ RTP pacer 20ms│
                                                              │ jitter buf 3-5│
                                                              └───────┬───────┘
                                                                      │
                                                              ┌───────▼───────┐
                                                              │ Telnyx / PSTN │
                                                              └───────────────┘
```

**Principles:**

1. Immutable media profile per call
2. Semantic text chunking only
3. Backpressure from playout to TTS
4. Small jitter buffer on PSTN
5. Prewarm = production path
6. No fake punctuation on stream chunks

---

## Priority implementation order

| Order | Fix | Impact |
|-------|-----|--------|
| 1 | Immutable TTS connect from `merge_pstn_tts_config` | Stops wrong voice / prewarm failures |
| 2 | Playout governor + 10–15 frame cap + backpressure | Stops PSTN crackle |
| 3 | Sentence-only chunking; remove comma/40-char flush | Smoother speech both channels |
| 4 | Web `ensure_terminal=false` on stream chunks | Stops false web pauses |
| 5 | Single-utterance-per-turn for short replies | Best PSTN quality |
| 6 | Observability: queue depth, chunk count, provider badge | Faster tuning |

---

## Global acceptance criteria

| Metric | Target |
|--------|--------|
| Queue depth during speech | p95 &lt; 10 frames |
| `text_queued` per turn | ≤ 2 for replies &lt; 200 chars |
| Provider mismatch in logs | 0 |
| `normal_speech_dropped_frames` | 0 |
| Subjective listen test | No mid-sentence chops without barge-in |
| TTFA (first agent audio) | &lt; 800ms PSTN, &lt; 500ms web |
