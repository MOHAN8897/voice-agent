Implementation Plan: Option B — Realtime Prewarm Greeting (Deferred Playback)
Goal: On outbound realtime_voice calls, synthesize the opening line via OpenAI Realtime during ring, store it as wire PCM, stay silent at answer, then play instantly on first callee speech — without breaking listen-first or double-speaking.

Non-goals (do not implement in this pass):

Greeting on connect (before user speaks)
Inbound calls
Dummy user messages for warmup
Replacing composed (pstn_voice_core) pipeline behavior
Wiring schedule_prewarm to production Telnyx dial (separate follow-up; dev telephony already calls it)
1. Target behavior (exact sequence)
schedule_prewarm(provider, control_id, dial_meta)
create + wait_ready (during ring)
start_response(opening only)
audio_delta PCM @ 24kHz
resample → wire frames
delete greeting conversation items (MANDATORY)
discard_queued stale events
answers call
take_prewarm_for_answer
start_call(greeting_wire_frames, greeting_text)
hello
cancel_response (kill VAD auto-reply)
play buffered wire frames
note_assistant_text(greeting_text)
bundle ready: frames + text + rt_key
PHASE_LISTENING, no audio out
turn 2+ = normal Realtime VAD
Outbound dial
pstn_prewarm
Realtime session (rt_key)
PSTN bridge
PstnRealtimeVoiceLoop
Callee
2. Hard invariants (agents must not violate these)
#	Rule
I1
Never play greeting at start_call on outbound realtime_voice
I2
Never call start_response at connect on outbound
I3
Always delete Realtime conversation items created by prewarm greeting synthesis before adopt
I4
Always cancel_response when playing deferred greeting (VAD has create_response: true)
I5
note_assistant_text only after buffered greeting finishes playing to the phone
I6
Set _intro_noted = True after note_assistant_text so live response_done does not note again
I7
Outbound-only: gate on direction == "outbound" AND play_greeting=True AND greeting_wire_frames non-empty
I8
If prewarm greeting synthesis fails → empty frames, fall back to current natural-VAD first reply (no crash, no connect-time greeting)
3. Critical bug to fix first (otherwise prewarm is useless)
File: server/services/pstn_prewarm.py

PREWARM_ADOPT_WAIT_SEC = 0.15  # TOO SHORT — change to 3.0
take() often returns before _build_prewarm_bundle finishes → cold Realtime connect + no greeting frames. Bump to 3.0 (or 5.0 on slow networks) in the same PR.

4. New module (recommended)
Create: server/services/pstn_realtime_greeting_prewarm.py

Keeps orchestration in pstn_prewarm.py and playback in pstn_realtime_voice_core.py separate.

4.1 realtime_pcm24_to_wire_frames(...)
Purpose: Convert captured Realtime PCM into PSTN wire chunks (same shape as live path).

Inputs:

pcm24: bytes (accumulated from audio_delta)
sample_rate: int — from _PROVIDER_WIRE[provider]["sample_rate"] (16000 Telnyx, 8000 Exotel/Plivo)
tts_output_codec: str — "linear16" or "mulaw"
Logic (mirror PstnRealtimeVoiceLoop._emit_realtime_pcm):

StreamingPcmResampler(REALTIME_PCM_RATE, sample_rate).feed(pcm24) + flush()
If codec is mulaw → pcm16_to_mulaw
Chunk into 20ms frames:
L16 @ 16kHz → 640 bytes/frame
PCMU @ 8kHz → 160 bytes/frame
Output: list[bytes]

4.2 async def synthesize_realtime_greeting_frames(...)
Signature:

async def synthesize_realtime_greeting_frames(
    adapter,  # OpenAIRealtimeVoiceAdapter
    *,
    greeting_text: str,
    sample_rate: int,
    tts_output_codec: str,
    timeout_sec: float = 12.0,
) -> tuple[list[bytes], str]:
    """Returns (wire_frames, spoken_transcript). Empty frames on failure."""
Algorithm:

spoken = prepare_spoken_reply(greeting_text).strip() — reuse from server/services/spoken_numbers.py

If empty → return ([], "")

await adapter.start_response(instructions=PREWARM_GREETING_INSTRUCTION.format(line=spoken))

Instruction template (exact):

Speak exactly the following opening line once, then stop. Do not add anything else:
"{spoken}"
Consume adapter.events() until response_done or cancelled or timeout:

On audio_delta: append event["pcm"] to buffer
On assistant_transcript: save transcript
On error / timeout: log, await adapter.cancel_response(), return ([], "")
Convert accumulated PCM → wire frames via helper above

MANDATORY cleanup: await adapter.delete_synthetic_response_items() (new adapter method — see §5)

adapter.discard_queued() — drain stale events before live pump starts

If len(frames) == 0 → treat as failure, log prewarm.greeting.realtime.empty

Return (frames, transcript or spoken)

Do NOT call note_assistant_text during prewarm — caller has not heard it yet.

5. Adapter changes (conversation history cleanup)
File: server/realtime/providers/openai_voice.py

Problem: start_response during prewarm adds an assistant turn to OpenAI history before the user speaks. If not removed, order becomes assistant → user and the model may skip or repeat the intro.

Add (mirror text adapter pattern in openai.py):

self._current_output_item_ids: list[str] = []
In _normalize / _pump, handle:

response.output_item.added → append item.id to _current_output_item_ids
On response.created → clear _current_output_item_ids
New method:

async def delete_synthetic_response_items(self) -> None:
    """Remove assistant items from the last synthetic response (prewarm greeting)."""
    async with self._response_lock:
        for item_id in list(dict.fromkeys(self._current_output_item_ids)):
            await self._conn.send({"type": "conversation.item.delete", "item_id": item_id})
        self._current_output_item_ids = []
Also add to: server/realtime/testing.py FakeRealtimeVoiceAdapter (track deletes for tests).

6. Prewarm bundle build changes
File: server/services/pstn_prewarm.py — _build_prewarm_bundle

Current (line ~359–369):
if greeting and mode != "realtime_voice":
    frames = await _synthesize_greeting_frames(...)  # TTS path
Change to:
frames: list[bytes] = []
greeting_transcript = greeting or ""
if greeting and mode == "realtime_voice":
    adapter = realtime_voice_manager.get(rt_key)
    if adapter is not None:
        try:
            frames, greeting_transcript = await synthesize_realtime_greeting_frames(
                adapter,
                greeting_text=greeting,
                sample_rate=sample_rate,
                tts_output_codec=tts_codec,
            )
            log_pstn(
                "prewarm.greeting.realtime",
                control=external_id,
                provider=provider,
                frames=len(frames),
                chars=len(greeting_transcript or ""),
            )
        except Exception as exc:
            log_pstn("prewarm.greeting.realtime.failed", control=external_id, error=str(exc)[:200])
            frames = []
elif greeting and mode != "realtime_voice":
    frames = await _synthesize_greeting_frames(...)  # unchanged TTS path
Optional bundle field (recommended):
@dataclass
class PstnPrewarmBundle:
    ...
    greeting_source: str | None = None  # "realtime_voice" | "tts" | None
Set greeting_source="realtime_voice" when Realtime synthesis succeeds.

Log in prewarm.ready: include greeting_source, greeting_frames.

7. Live call loop changes (deferred playback)
File: server/services/pstn_realtime_voice_core.py

7.1 New instance state (in __init__)
self._deferred_greeting_frames: list[bytes] | None = None
self._deferred_greeting_text: str | None = None
self._deferred_greeting_armed = False   # waiting for first user speech
self._deferred_greeting_playing = False # suppress VAD audio_delta during playback
7.2 start_call changes
Remove:

_ = greeting_wire_frames  # Composed TTS frames are not used on this path.
Add after direction/brain resolved:

if (
    play_greeting
    and direction == "outbound"
    and greeting_wire_frames
    and greeting_text
):
    self._deferred_greeting_frames = list(greeting_wire_frames)
    self._deferred_greeting_text = greeting_text.strip()
    self._deferred_greeting_armed = True
elif play_greeting and direction == "outbound" and greeting_text and not greeting_wire_frames:
    log_pstn("greeting.deferred.miss", call_id=self.call_id, reason="no_prewarm_frames")
Keep unchanged:

No start_response at connect
_set_phase(PHASE_LISTENING) at end
Instructions still include [Canonical opening line] (model knows script; playback handles turn 1)
On adopt path: if prewarm session already open, prefer update_instructions only when instructions actually changed (optional optimization — not required for v1).

7.3 New method: _play_deferred_greeting
Port pattern from pstn_voice_core._play_buffered_greeting (lines 995–1010):

async def _play_deferred_greeting(self) -> None:
    frames = self._deferred_greeting_frames or []
    text = self._deferred_greeting_text or ""
    if not frames or not text:
        return
    self._deferred_greeting_armed = False
    self._deferred_greeting_playing = True
    self._set_phase(PHASE_INTRO)
    self._set_tts_active(True)
    self.current_turn_id = self.current_turn_id or uuid.uuid4().hex[:12]
    self.current_generation_id = uuid.uuid4().hex[:12]
    # set playback generation if playback object exists
    log_pstn("greeting.deferred.play", call_id=self.call_id, frames=len(frames), chars=len(text))
    try:
        for wire in frames:
            if self._closed or self.emission_blocked():
                break
            if self.call_id:
                self._archive.enqueue(self.call_id, "agent", wire)
            self._wire_frames_out += 1
            await self.on_agent_wire(wire)
    finally:
        self._set_tts_active(False)
        self._deferred_greeting_playing = False
    if self._closed:
        return
    # History sync AFTER phone heard it
    noter = getattr(self._adapter, "note_assistant_text", None)
    if callable(noter):
        await noter(text)
    self._intro_noted = True
    if self.call_id:
        await call_ledger.append_assistant_turn(self.call_id, text)
    log_pstn("greeting.deferred.done", call_id=self.call_id)
    self._set_phase(PHASE_LISTENING)
7.4 Trigger: first user speech (_handle_event)
Trigger on speech_stopped (earliest reliable point — same moment VAD auto-fires response.create):

if kind == "speech_stopped" and self._deferred_greeting_armed:
    asyncio.create_task(self._on_first_user_speech_deferred_greeting())
    return
New coroutine:

async def _on_first_user_speech_deferred_greeting(self) -> None:
    if not self._deferred_greeting_armed or self._closed:
        return
    self._deferred_greeting_armed = False  # idempotent guard
    if self._adapter:
        await self._adapter.cancel_response()
        clearer = getattr(self._adapter, "clear_output_audio", None)
        if callable(clearer):
            await clearer()
    await self._play_deferred_greeting()
Why not user_transcript final alone? Transcript arrives after speech_stopped; VAD response would already be generating. speech_stopped is the race-critical hook.

7.5 Suppress duplicate live audio during deferred playback
In _handle_event:

Event	When _deferred_greeting_playing	When _deferred_greeting_armed and VAD fires
response_created
ignore or cancel immediately
cancel + clear output
audio_delta
drop (do not _emit_realtime_pcm)
drop if greeting task already running
response_done
ignore assistant note if _intro_noted will be set by deferred path
same
Add at top of audio_delta handler:

if self._deferred_greeting_playing or self._deferred_greeting_armed:
    return  # until _play_deferred_greeting clears armed flag at start
Correction: After _on_first_user_speech_deferred_greeting sets _deferred_greeting_armed = False, VAD response may still emit deltas — use _deferred_greeting_playing for drop, and always cancel on response_created while _intro_noted is False and frames were configured.

Safer rule:

if self._deferred_greeting_playing:
    return  # drop live model audio
if kind == "response_created" and not self._intro_noted and self._deferred_greeting_frames:
    await self._adapter.cancel_response()
    return
7.6 Existing response_done intro note
Keep existing block (lines 541–552) but guard:

if kind == "response_done" and ... and not self._intro_noted and not self._deferred_greeting_frames:
So deferred-greeting calls never double-note from live inference on turn 1.

8. Bridge layer (minimal changes)
Files: telnyx_pstn_bridge.py, exotel_pstn_bridge.py, plivo_pstn_bridge.py

Already correct — they pass prewarm bundle into start_call:


telnyx_pstn_bridge.py
Ln 485–488
await self._voice.start_call(
    play_greeting=bool(self.call_id) and not skip_greeting,
    greeting_wire_frames=prewarm.greeting_wire_frames if prewarm else None,
    greeting_text=prewarm.greeting_text if prewarm else None,
No bridge changes required if loop + prewarm are fixed.

Call lifecycle adopt (call_lifecycle_service.py L226–227) — already adopts realtime_prewarm_key → call_id. No change.

9. Tests (required before merge)
9.1 server/tests/test_pstn_realtime_greeting_prewarm.py (new)
Test	Asserts
test_pcm24_to_wire_frames_telnyx_l16
24k → 16k L16 640-byte frames
test_pcm24_to_wire_frames_exotel_mulaw
24k → 8k mulaw 160-byte frames
test_synthesize_collects_audio_and_deletes_items
Mock adapter events → frames + delete called
test_synthesize_empty_on_timeout
No audio → [], no raise
9.2 server/tests/test_pstn_prewarm.py (extend)
Test	Asserts
test_build_prewarm_realtime_voice_synthesizes_greeting
Patch synthesize_realtime_greeting_frames, verify called when mode==realtime_voice
test_realtime_voice_does_not_use_tts_synth
TTS _synthesize_greeting_frames NOT called for realtime_voice
9.3 server/tests/test_pstn_realtime_voice.py (extend)
Test	Asserts
Update test_start_call_outbound_natural_vad_no_forced_greeting
Frames stored (_deferred_greeting_armed=True), wires empty at start
test_deferred_greeting_plays_on_speech_stopped
speech_stopped → wire emitted, note_assistant_text called, _intro_noted=True
test_deferred_greeting_cancels_vad_response
response_created before play → cancel_response called
test_no_deferred_greeting_when_frames_missing
Falls back: speech_stopped does not play buffer
9.4 server/tests/test_openai_voice_adapter.py or extend realtime tests
Test	Asserts
test_delete_synthetic_response_items
Sends conversation.item.delete for tracked IDs
10. Logging checklist (grep-friendly)
Event	When
prewarm.greeting.realtime
Synthesis success
prewarm.greeting.realtime.failed
Exception during synthesis
prewarm.greeting.realtime.empty
Zero frames after synthesis
greeting.deferred.miss
Outbound but no prewarm frames at answer
greeting.deferred.play
Starting buffered playback
greeting.deferred.done
Playback + note complete
11. Fallback matrix
Condition at answer	Behavior
Prewarm adopted + frames present
Deferred playback on first speech
Prewarm adopted + frames empty
Current behavior: VAD → live first inference
Prewarm missed (cold connect)
Current behavior
play_greeting=False
No deferred path
Inbound direction
Ignore deferred frames even if present
Stale brain (prewarm.stale_brain)
Realtime key destroyed; frames may still exist — OK to play script greeting, but session is cold
12. Implementation order (for agents)
Bump PREWARM_ADOPT_WAIT_SEC → 3.0
Add delete_synthetic_response_items + item tracking to openai_voice.py + fake adapter
Add pstn_realtime_greeting_prewarm.py (PCM → wire + synthesis loop)
Wire synthesis into _build_prewarm_bundle for realtime_voice
Implement deferred playback in pstn_realtime_voice_core.py
Tests (§9)
Manual verify: dev telephony outbound → logs show prewarm.greeting.realtime → answer → say hello → greeting.deferred.play within ~0.5–1s
13. Common mistakes to avoid
Mistake	Consequence
Playing greeting at start_call
Breaks listen-first outbound
Skipping conversation item delete after prewarm synth
Model thinks intro already happened; wrong turn order
Calling note_assistant_text during ring
History says agent spoke before user
Not canceling VAD response.create
Double voice (buffer + model)
Using TTS frames for realtime_voice
Wrong voice vs Realtime marin/etc.
Consuming adapter events in prewarm without discard_queued
Stale events hit live _event_pump
Triggering on connect instead of speech_stopped
User hears agent before speaking
14. Optional follow-ups (separate PRs)
Wire schedule_prewarm into production outbound dial path (not only dev_telephony.py)
Skip redundant update_instructions at answer when prewarm instructions unchanged
Tune VAD (silence_ms, vad_eagerness) for additional ~300ms savings
15. Files touched (summary)
File	Action
server/services/pstn_realtime_greeting_prewarm.py
CREATE
server/services/pstn_prewarm.py
MODIFY — synthesis call + adopt wait
server/services/pstn_realtime_voice_core.py
MODIFY — deferred playback
server/realtime/providers/openai_voice.py
MODIFY — item tracking + delete
server/realtime/testing.py
MODIFY — fake adapter
server/tests/test_pstn_realtime_greeting_prewarm.py
CREATE
server/tests/test_pstn_prewarm.py
MODIFY
server/tests/test_pstn_realtime_voice.py
MODIFY
No changes needed: bridges, call_lifecycle_service, compiler, prompts (unless you want explicit “opening will be played from buffer” text later).

This plan is scoped to outbound realtime_voice + prewarm present + greeting synthesis succeeded. Everything else keeps today’s natural-VAD first reply as fallback.

If you want this built next, say implement and I’ll follow this plan file-by-file.

Prewarm started during ringing ✅
Greeting generated successfully in ~3.7s ✅
235 buffered frames were stored ✅
At answer, prewarm was marked stale_brain incorrectly ❌
The warm Realtime session was closed ❌
A new cold Realtime session took ~3.5s to open ❌
Early caller audio during that period could be dropped ❌
Buffered greeting eventually played ✅
VAD was never actually disabled during greeting ❌
Unsupported output_audio_buffer.clear caused Realtime API errors ❌
The key evidence:

prewarm.greeting.realtime ... frames=235
prewarm.adopted
prewarm.stale_brain ... prewarm=session-v6 active=cb_v...
session closed call=prewarm-...
REALTIME_VOICE session started call=<live-call>  # new cold session
The stale check compares two incompatible version systems:

Session override: session-v6
Published agent brain: cb_v20260910_499822
It therefore destroys a valid prewarm session even though the live call also uses session-v6.

There was roughly a six-second answer-to-live-session delay. That explains why your first “hi” did not trigger immediate playback.

Additionally:

Invalid value: 'output_audio_buffer.clear'
The currently connected Realtime API does not support that client event. It must be removed/replaced.

Required corrections:

Validate staleness against the same Test Studio/session brain, preferably by checksum—not published-agent version.
Never destroy the valid prewarm session for session-vN versus cb_vN.
Adopt the exact prewarm adapter before starting the voice loop.
Arm deferred greeting before accepting caller audio.
Temporarily disable automatic VAD response creation during the deferred greeting phase.
On caller speech end, play the buffered greeting directly.
After playback, add the greeting to assistant history.
Re-enable normal VAD automatic responses.
Remove unsupported output_audio_buffer.clear.
Add a test proving the adapter object before and after adoption is the same object.