Here are concrete fixes mapped to each root cause, in the order I'd implement them. These are design recommendations — switch to Agent mode if you want them applied in code.

Priority 1 — Stop mid-word cuts (playout layer)
File: server/services/telnyx_pstn_bridge.py

Fix A: Soft underrun — don’t reset the clock mid-utterance
Problem: When the queue empties briefly, this path fires:


telnyx_pstn_bridge.py
Ln 794–801
elif in_playout:
    self._note_queue_metric("playout_underrun_count", 1)
    next_send_at = None
    self._playout_primed = False
That forces a full re-prime (~240ms + 80ms headroom) and sounds like a word got chopped.

Solution:

If _tts_still_generating() or queue was non-empty in the last ~500ms, do not reset next_send_at / _playout_primed.
Keep sending concealment frames and keep the 20ms clock running.
Only reset on true end-of-speech (TTS session closed, queue empty, _agent_audio_playing() false).
Effect: Removes the biggest audible “cut” without dropping frames.

Fix B: Track “waiting for next TTS chunk” explicitly
Problem: _expect_more_playout_audio() uses _tts_still_generating(), but between Cartesia WebSocket messages the session is “open” while audio hasn’t arrived yet. If the queue drains during that gap, you hit underrun or heavy PLC.

Solution:

In PstnTurnTtsSession._reader_loop, set a flag like _awaiting_audio = True before await ws.recv() and False after _emit_audio_chunk.
Bridge reads voice._active_tts_session._awaiting_audio.
While true, extend grace to 400–600ms instead of PLAYOUT_BURST_GAP_GRACE_S = 0.28.
Effect: Covers Cartesia burst gaps without freezing vowels or resetting the pacer.

Fix C: Raise burst-gap tolerance (quick win)
Current constants:


telnyx_pstn_bridge.py
Ln 45–50
PLAYOUT_PRIME_FRAMES = 12
PLAYOUT_UNDERRUN_GRACE_S = 0.30
PLAYOUT_BURST_GAP_GRACE_S = 0.28
Suggested starting values for L16 @ 16kHz:

Constant	Current	Try
PLAYOUT_BURST_GAP_GRACE_S
0.28s
0.45–0.55s
PLAYOUT_UNDERRUN_GRACE_S
0.30s
0.40s
PLAYOUT_PRIME_FRAMES
12 (~240ms)
14–16 (~280–320ms)
Tradeoff: Slightly more latency before first audio; smoother mid-sentence.

Fix D: Better concealment (less “robotic freeze”)
Problem: _concealment_frame() repeats the exact last 20ms sample — sounds like a stuck vowel.

**Solution options (pick one):

Short crossfade — blend last frame with silence over 2–3 frames.
Attenuated repeat — multiply samples by 0.85 each concealment frame (natural decay).
Cap PLC — max 8–12 concealment frames (~160–240ms), then hold clock without reset.
Effect: Gaps are less obvious when TTS is slow between chunks.

Priority 2 — Fix burst vs pacer mismatch (producer side)
Problem: TTS dumps many frames at once → queue hits 18 → producer blocks → queue drains → gap. Logs showed queue pinned at 18 for whole utterances.

Fix E: Real-time rate limiter on enqueue
Where: _send_agent_wire() loop (lines 1080–1105) or _emit_audio_chunk() in pstn_turn_tts.py.

Solution: Token-bucket / leaky-bucket:

Target steady queue depth ~10–14 frames.
Enqueue at most 1 frame per 20ms (or 2 frames per 40ms during catch-up).
Never burst 20+ frames synchronously in one await chain.
Pseudologic:

# After each put_nowait:
await asyncio.sleep(0.02)  # only when queue > target_depth
Effect: Smoother playout, far fewer backpressure oscillations. Your probe’s 51 backpressure waits should drop sharply.

Fix F: Retune watermarks (alternative/complement)
Current:


telnyx_pstn_bridge.py
Ln 40–42
MAX_AUDIO_QUEUE_FRAMES = 28
QUEUE_HIGH_WATERMARK = 18
QUEUE_LOW_WATERMARK = 8
Option 1 — deeper buffer:

MAX = 40, HIGH = 28, LOW = 14 (~560ms buffer)
Option 2 — keep size, change behavior:

Producer blocks at HIGH but pacer never lets queue drop below LOW during active TTS (stronger _hold_for_min_playout_depth).
Recommendation: Fix E (rate limit) + slightly deeper buffer is better than only raising watermarks.

Priority 3 — Prewarm greeting burst
Problem: _play_buffered_greeting() pushes all frames as fast as possible:


pstn_voice_core.py
Ln 906–909
for wire in frames:
    ...
    await self._emit_agent_wire(wire)
128 frames ≈ 2.56s dumped instantly → immediate backpressure at call answer.

Solution: Pace greeting the same as Fix E:

for wire in frames:
    await self._emit_agent_wire(wire)
    await asyncio.sleep(0.02)  # or use shared rate limiter
Or enqueue greeting through the same paced path as live TTS.

Effect: Cleaner call start; less buffer shock before the first real turn.

Priority 4 — Fewer TTS text chunks per turn
Problem: Streaming LLM → drain_complete_sentences() → multiple text_queued per generation (91 + 127 + 33 chars). Each send_text can cause a micro-gap in Cartesia synthesis.

Files: pstn_voice_core.py (_run_turn), pstn_text_chunker.py

**Solutions (pick based on latency tolerance):

Approach	Latency	Smoothness
A. PSTN-only larger chunks — raise MIN_CHUNK_CHARS / FORCE_FLUSH_AT for PSTN
Slightly slower first audio
Better
B. One TTS flush per turn — accumulate full LLM reply, single send_text
Slowest first token
Smoothest
C. Hybrid (recommended) — stream first sentence fast, batch rest until done
Balanced
Good
Hybrid example:

First sentence: send when complete (low time-to-first-audio).
After that: buffer until LLM done, then one send_text for the rest.
Priority 5 — TTS cold start (~1.4s silence before speech)
Problem: New PstnTurnTtsSession.open() per turn → new WebSocket + config each time.

Solutions:

Call-level TTS pool — one warm WebSocket for the whole call; send_text / flush per turn, close on hangup.
Prewarm TTS on ring — extend pstn_prewarm.py to open TTS WS during ring (like greeting prewarm).
Overlap connect — you already tts_open = asyncio.create_task(tts_session.open()) during LLM stream; ensure LLM work always starts before await tts_open on short replies.
Effect: Removes pre-speech pause; does not fix mid-word cuts but improves perceived quality.

Priority 6 — Observability (verify fixes)
Add per-turn summary log at end of each TTS session:

playout_underrun_count
playout_concealment_frames
producer_backpressure_wait_count
producer_backpressure_wait_ms
queue_peak
Where: pstn_turn_tts.close() or pstn_voice_core after tts_session.finish().

Verify with:

python -m scripts.pstn_audio_pipeline_probe --preset medium --chunking production
Listen to *__pacer_out.wav vs *__tts_wire.wav
Target: playout_underrun_count = 0, backpressure waits low
Live call: Dev UI media-flow → watch underrun/concealment during speech.

Recommended implementation order
Step	Fix	Effort	Impact
1
A Soft underrun (no clock reset)
Small
High
2
B awaiting-audio flag + longer grace
Medium
High
3
E Real-time enqueue rate limit
Medium
High
4
C Tune grace/prime constants
Tiny
Medium
5
Greeting pace
Small
Medium
6
Hybrid chunking for PSTN
Medium
Medium
7
TTS WS reuse
Larger
Medium (latency)
8
D Better PLC
Medium
Polish
What you should not do
Don’t drop frames to “fix” jitter — you already avoid that; dropping would make cuts worse.
Don’t blame Telnyx — audio is reaching them; the issue is pre-wire pacing.
Don’t only increase buffer size without pacing — bursts will still oscillate at the watermark.
Expected outcome after fixes 1–5
playout_underrun_count → 0 on probe and live calls
playout_concealment_frames → low and brief
outbound.queue.backpressure → occasional, not sustained for whole utterances
Word-level chopping should largely disappear; any remaining issues likely from Cartesia chunk boundaries (fix with chunking / TTS reuse)
If you want this implemented, switch to Agent mode and I can apply fixes A, B, E, and greeting pacing first — that’s the highest-impact bundle for mid-word cutting.