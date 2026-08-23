# CRITICAL VOICE AGENT DEBUGGING TASK
# Fix TWO production issues in the Telugu voice-agent TTS pipeline

You are working on a real-time Telugu voice agent.

I have TWO separate but related bugs that must be investigated and fixed at code level.

DO NOT simply modify the UI.

DO NOT assume the problem is solved because the settings page displays the selected value.

Trace the actual runtime path from configuration → backend → Sarvam → audio playback.

============================================================
ISSUE 1 — SELECTING A DIFFERENT TTS SPEAKER DOES NOT CHANGE
THE ACTUAL VOICE
============================================================

The Fine-tune Console currently shows:

TTS model:
Bulbul v3

Speaker:
ritu

Pace:
1.00

Temperature:
0.50

However, when I actually use the voice agent, I STILL hear the same male voice that I heard when the speaker was:

shubh

This means the UI says "ritu", but the actual TTS audio is still being generated with the old/default male speaker.

This MUST be investigated end-to-end.

IMPORTANT:

Do NOT assume the UI value is the real runtime value.

Trace the exact speaker value through the entire system.

The expected flow is:

Fine-tune Console
      ↓
runtime settings
      ↓
frontend configuration
      ↓
voice session
      ↓
TTS configuration
      ↓
/api/tts OR /ws/tts
      ↓
Sarvam Bulbul v3
      ↓
selected speaker
      ↓
audio
      ↓
speaker output

============================================================
ISSUE 1A — AUDIT EVERY POSSIBLE SPEAKER OVERRIDE
============================================================

Search the entire codebase for:

"shubh"

"ritu"

"speaker"

"voice"

"bulbul"

"Bulbul"

"speaker_id"

"speakerId"

"tts_speaker"

"ttsSpeaker"

"voice_name"

"voiceName"

"model"

Find EVERY place where a TTS speaker is:

- declared
- defaulted
- saved
- loaded
- cached
- transformed
- passed to the backend
- passed to Sarvam
- used in REST TTS
- used in TTS WebSocket
- used in voice session initialization
- used in replay
- used in automatic playback

I specifically want you to find hardcoded defaults such as:

speaker = "shubh"

or:

speaker || "shubh"

or:

speaker ?? "shubh"

or:

const DEFAULT_SPEAKER = "shubh"

or any equivalent fallback.

Do NOT remove a fallback blindly.

Determine whether that fallback is overriding the user's selected runtime speaker.

============================================================
ISSUE 1B — TRACE THE ACTUAL SARVAM REQUEST
============================================================

Inspect the actual request sent to Sarvam.

For every TTS request, safely log:

[VOICE][TTS_CONFIG]
model=...
speaker=...
pace=...
temperature=...
codec=...
sample_rate=...

DO NOT log API keys or secrets.

The most important diagnostic is:

What speaker value is actually being sent to Sarvam?

For example:

Expected:

[VOICE][TTS_CONFIG]
model=bulbul:v3
speaker=ritu

But if the actual log says:

[VOICE][TTS_CONFIG]
model=bulbul:v3
speaker=shubh

then the bug is BEFORE the Sarvam API call.

Fix the configuration propagation.

If the request says:

speaker=ritu

but the audio still sounds like Shubh, then inspect:

- Sarvam request schema
- model/speaker compatibility
- WebSocket initialization
- speaker field naming
- fallback handling
- response metadata
- whether the selected speaker is actually accepted by Sarvam

Do not silently fall back to Shubh.

If Ritu is invalid or unsupported, return an explicit error:

[VOICE][TTS] SPEAKER_INVALID speaker=ritu

instead of silently using Shubh.

============================================================
ISSUE 1C — REST TTS AND WEBSOCKET TTS MUST USE THE SAME
RUNTIME CONFIGURATION
============================================================

The architecture supports:

/api/tts

and:

/ws/tts

Audit both.

It is unacceptable for:

REST TTS → ritu

while:

WebSocket TTS → shubh

or vice versa.

Both must use the same resolved runtime TTS configuration.

Create one canonical configuration object:

ttsConfig = {
    model,
    speaker,
    pace,
    temperature,
    codec,
    sampleRate
}

Resolve it once from the current runtime settings.

Then pass the SAME resolved configuration into:

- REST TTS
- TTS WebSocket
- voice turn
- automatic TTS
- replay TTS
- test TTS

Do not duplicate speaker defaults across services.

============================================================
ISSUE 1D — RUNTIME SETTINGS MUST ACTUALLY PROPAGATE
============================================================

When I change:

shubh → ritu

the following must happen:

UI
 ↓
save settings
 ↓
backend/runtime settings
 ↓
current/new voice session
 ↓
TTS configuration
 ↓
Sarvam

Verify that the save operation actually succeeds.

Verify that the backend returns:

speaker=ritu

after saving.

Verify that a new voice turn uses ritu.

If settings are cached, invalidate or refresh the relevant cache.

If the current WebSocket session captures the old speaker configuration when it starts, determine whether the session must be recreated after settings change.

Do not require a browser refresh unless absolutely necessary.

If a refresh is necessary, document why.

============================================================
ISSUE 1E — TEST MULTIPLE SPEAKERS
============================================================

After fixing the bug, test at least:

shubh
ritu

If additional valid Bulbul v3 Telugu speakers exist in the application's speaker list, test at least one more.

The actual audio must change when the speaker changes.

Do NOT mark the issue fixed just because the dropdown changes.

Acceptance criterion:

Selecting Ritu → actual audio sounds like Ritu.

Selecting Shubh → actual audio sounds like Shubh.

The runtime log must confirm the corresponding speaker value.

============================================================
ISSUE 2 — AUTOMATIC TTS DOES NOT SPEAK
============================================================

The second screenshot shows:

PLAYBACK — SARVAM BULBUL:V3 (TE-IN) AUTO

The UI says:

"Hands-free mode: replies play automatically through your speakers."

However, the actual behavior is:

User speaks
    ↓
STT correctly transcribes
    ↓
Brain correctly generates text
    ↓
AI response text appears on screen
    ↓
NO AUDIO PLAYS
    ↓
User must manually click:

"Speak current text"

    ↓
Then the agent speaks successfully.

This proves that at least one TTS/playback path is functioning.

The problem is specifically the automatic:

Brain → TTS → Speaker

path.

============================================================
ISSUE 2A — TRACE THE COMPLETE AUTOMATIC PATH
============================================================

Trace this exact sequence:

transcript.final
    ↓
runTurn()
    ↓
brain request
    ↓
brain stream
    ↓
output_text.delta
    ↓
SentenceAccumulator
    ↓
TTS text
    ↓
/ws/tts
    ↓
TTS audio chunks
    ↓
AudioPlaybackManager
    ↓
MediaSource / Audio element
    ↓
audio.play()
    ↓
speaker

Identify EXACTLY where the automatic path stops.

Do not simply add another click handler.

The desired architecture is:

USER SPEAKS
    ↓
STT FINAL
    ↓
BRAIN STREAM
    ↓
FIRST USABLE SENTENCE
    ↓
TTS IMMEDIATELY
    ↓
FIRST AUDIO CHUNK
    ↓
AUTOMATIC PLAYBACK
    ↓
SPEAKER

No additional user interaction.

============================================================
ISSUE 2B — COMPARE "SPEAK CURRENT TEXT" WITH AUTOMATIC TTS
============================================================

This is extremely important.

Find the exact code executed when the user clicks:

"Speak current text"

Then compare it with the automatic response path.

Determine:

Does the manual button:

- create an Audio object?
- call audio.play()?
- unlock AudioContext?
- initialize MediaSource?
- create a TTS request?
- use a different TTS endpoint?
- use a different speaker configuration?
- bypass AudioPlaybackManager?
- use a different audio element?
- use a different codec?
- use a different state?
- call a missing function that automatic playback never calls?

If manual playback works, reuse the SAME working playback mechanism for automatic playback.

Do NOT maintain two separate playback implementations.

Required architecture:

AudioPlaybackManager
    ↓
single canonical playAudio() path

Automatic response
    → AudioPlaybackManager

Manual replay
    → AudioPlaybackManager

"Speak current text"
    → AudioPlaybackManager

The only difference should be WHAT text/audio is being played.

============================================================
ISSUE 2C — CHECK AUTOPLAY POLICY
============================================================

The user already clicks the microphone button to start the voice session.

Use that initial user gesture to unlock audio playback.

At microphone/session start:

1. Initialize audio playback.
2. Create/attach the persistent audio element.
3. Unlock AudioContext if used.
4. Prepare MediaSource if used.
5. Mark audioUnlocked=true only after successful initialization.

Do NOT wait until several seconds later when TTS audio arrives.

Do NOT require the user to click "Speak current text" after every response.

If browser autoplay is actually blocking playback, capture the exact error.

For example:

audio.play()

must have proper Promise handling.

Log:

[VOICE][AUDIO] PLAY_REQUEST
[VOICE][AUDIO] PLAY_SUCCESS
[VOICE][AUDIO] PLAY_BLOCKED
[VOICE][AUDIO] PLAY_ERROR

If the error is:

NotAllowedError

determine whether the initial microphone gesture is being correctly used to unlock playback.

Do not silently swallow the error.

============================================================
ISSUE 2D — PERSISTENT AUDIO PLAYER
============================================================

Use one persistent audio playback instance for the voice session.

Do NOT create a completely new audio element for every Brain response.

Expected:

voice session starts
    ↓
persistent audio element
    ↓
TTS chunks arrive
    ↓
automatic playback

The same playback manager must remain available throughout the session.

============================================================
ISSUE 2E — DO NOT WAIT FOR THE ENTIRE BRAIN RESPONSE
============================================================

The voice agent must be low latency.

Do NOT do:

Brain complete
    ↓
wait
    ↓
full response
    ↓
TTS
    ↓
audio
    ↓
play

Instead:

Brain delta
Brain delta
Brain delta
    ↓
first complete natural sentence
    ↓
TTS immediately
    ↓
first audio chunk
    ↓
play immediately

While the first sentence is being spoken, the Brain can continue generating the rest.

============================================================
ISSUE 2F — SENTENCE ACCUMULATOR
============================================================

Audit SentenceAccumulator.

It should flush TTS text when a natural sentence boundary is reached.

Recognize:

.
?
!
।

and appropriate Telugu conversational boundaries.

Do not wait unnecessarily for the entire response.

For example:

Brain produces:

"అవునా సార్… 50 లక్షల వరకు చూస్తున్నారా? మీకు plot కావాలా, flat కావాలా?"

As soon as the first natural sentence is ready, TTS should begin.

Do not wait for the entire response if streaming allows earlier playback.

============================================================
ISSUE 2G — AUDIO CHUNK QUEUE
============================================================

If TTS is streaming MP3 chunks:

TTS chunk
    ↓
AudioPlaybackManager
    ↓
MediaSource
    ↓
SourceBuffer

Handle SourceBuffer backpressure correctly.

If:

sourceBuffer.updating === true

queue the chunk.

When:

updateend

append the next chunk.

Do not drop chunks.

Do not append simultaneously.

Do not call endOfStream() before the TTS stream finishes.

============================================================
ISSUE 2H — AUTOMATIC PLAYBACK STATE
============================================================

Audit these states carefully:

IDLE
LISTENING
PROCESSING_STT
THINKING
GENERATING_TTS
SPEAKING
INTERRUPTED
ERROR

The current bug may be caused by the UI reaching:

THINKING → text displayed → IDLE

without entering:

GENERATING_TTS → SPEAKING

Verify the actual state transitions.

Add safe logs:

[VOICE][STATE] IDLE -> LISTENING
[VOICE][STATE] LISTENING -> THINKING
[VOICE][STATE] THINKING -> GENERATING_TTS
[VOICE][STATE] GENERATING_TTS -> SPEAKING
[VOICE][STATE] SPEAKING -> LISTENING

If TTS is generated but state remains THINKING/IDLE, fix that.

============================================================
ISSUE 2I — AUTO MODE MUST ACTUALLY BE ENABLED
============================================================

The UI currently displays:

AUTO

Verify that this is a real runtime boolean, not just a visual label.

Trace:

handsFree
voiceLoop
autoPlayback
autoSpeak
autoTts
liveMode

or whatever equivalent flags exist.

Determine whether automatic playback is actually enabled in the runtime session.

Do not trust the UI.

Log:

[VOICE][AUTO]
enabled=true/false

When Brain produces a response:

if autoPlayback === true:

automatically invoke the canonical TTS/playback path.

Do NOT wait for:

"Speak current text"

button click.

============================================================
ISSUE 2J — BARGE-IN MUST CONTINUE TO WORK
============================================================

Do not fix automatic playback by breaking microphone listening.

The final behavior must remain:

User speaks
    ↓
Agent listens
    ↓
Agent responds automatically
    ↓
Agent speaks
    ↓
User interrupts
    ↓
Current audio stops quickly
    ↓
Current TTS/Brain generation is cancelled
    ↓
Agent listens to new speech
    ↓
New response automatically speaks

No overlapping voices.

No stale audio.

============================================================
OBSERVABILITY
============================================================

Add safe diagnostic logs around the entire critical path.

Required logs:

[VOICE][CONFIG]
model=...
speaker=...
pace=...
temperature=...

[VOICE][STT]
FINAL

[VOICE][BRAIN]
START

[VOICE][BRAIN]
FIRST_DELTA

[VOICE][BRAIN]
SENTENCE_READY

[VOICE][TTS]
START

[VOICE][TTS]
FIRST_AUDIO

[VOICE][AUDIO]
CHUNK_RECEIVED

[VOICE][AUDIO]
CHUNK_APPENDED

[VOICE][AUDIO]
PLAY_REQUEST

[VOICE][AUDIO]
PLAY_STARTED

[VOICE][AUDIO]
PLAY_BLOCKED

[VOICE][AUDIO]
PLAY_ERROR

[VOICE][AUDIO]
PLAY_ENDED

[VOICE][STATE]
state transitions

Never log:

- API keys
- access tokens
- secrets
- private credentials

============================================================
PERFORMANCE MEASUREMENTS
============================================================

Measure:

t0 = transcript.final
t1 = first Brain delta
t2 = first sentence ready
t3 = TTS request start
t4 = first TTS audio chunk
t5 = audio.play() request
t6 = actual audio playback start

Log:

[VOICE][PERF]
brain_first_delta_ms=...
sentence_ready_ms=...
tts_first_audio_ms=...
audio_play_start_ms=...
total_time_to_first_audio_ms=...

The goal is the lowest practical time-to-first-audio.

============================================================
IMPORTANT — DO NOT MAKE SUPERFICIAL FIXES
============================================================

Do NOT:

- hardcode Ritu
- hardcode Shubh
- remove the speaker dropdown
- fake the selected speaker in the UI
- automatically click the "Speak current text" button programmatically
- add an artificial button click
- hide autoplay errors
- simply call TTS again without finding the root cause
- create duplicate audio players
- wait for the complete Brain response
- remove hands-free mode
- disable barge-in
- rewrite the entire voice architecture unnecessarily

The fix must be architectural and use the existing voice pipeline correctly.

============================================================
ACCEPTANCE TEST 1 — SPEAKER SELECTION
============================================================

Set:

speaker = shubh

Speak the same Telugu sentence.

Record actual voice.

Then set:

speaker = ritu

Speak the EXACT same Telugu sentence.

Record actual voice.

Expected:

The voices are genuinely different.

Runtime logs must show:

speaker=shubh

and then:

speaker=ritu

respectively.

The backend must not silently override either value.

============================================================
ACCEPTANCE TEST 2 — AUTOMATIC SPEECH
============================================================

Click microphone ONCE.

Say:

"నాకు 50 లక్షల budgetలో ఒక మంచి property కావాలి."

Expected:

STT
→ Brain
→ TTS
→ SPEAKER

automatically.

The user must NOT click:

"Speak current text"

The user must hear the response automatically.

============================================================
ACCEPTANCE TEST 3 — MULTIPLE TURNS
============================================================

Perform at least 10 consecutive voice turns.

Expected:

- every response automatically speaks
- no manual button
- no silent responses
- no duplicate responses
- no overlapping audio
- no stale audio
- no memory leak
- selected speaker remains consistent

============================================================
ACCEPTANCE TEST 4 — SPEAKER CHANGE
============================================================

Change:

shubh → ritu

without changing anything else.

Start a new voice turn.

Expected:

new voice is Ritu.

Then change:

ritu → shubh

Start another new voice turn.

Expected:

new voice is Shubh.

============================================================
ACCEPTANCE TEST 5 — REPLAY
============================================================

After automatic playback works:

Click "Replay last".

Expected:

The last response plays again.

Replay must use the same canonical playback manager.

============================================================
FINAL REPORT
============================================================

After implementation, report:

1. Root cause of the speaker-selection bug.
2. Exact file(s) causing the speaker override.
3. Actual speaker value sent to Sarvam before the fix.
4. Why selecting Ritu in the UI did not change the actual voice.
5. Root cause of automatic playback failure.
6. Why "Speak current text" worked while automatic playback did not.
7. Whether browser autoplay policy was involved.
8. Whether audio.play() was failing.
9. Whether MediaSource/SourceBuffer was involved.
10. Whether autoPlayback/handsFree state was incorrectly handled.
11. Files changed.
12. Exact configuration path after the fix.
13. First-audio latency before/after.
14. Confirmation that Ritu and Shubh produce different voices.
15. Confirmation that responses now speak automatically without clicking any button.
16. Confirmation that barge-in still works.

DO NOT declare the task complete until both issues are demonstrated working end-to-end.

The real acceptance criteria are:

1. Changing the speaker changes the ACTUAL generated voice.
2. After the initial microphone interaction, every Brain response automatically reaches the user's speaker without clicking "Speak current text".