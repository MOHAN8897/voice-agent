I checked the current Sarvam documentation and OpenAI documentation against your logs. The biggest issue is your live voice path is not actually using streaming TTS even though your architecture has a TTS WebSocket.

🔴 What your logs reveal

Your actual flow is currently:

User speaks
   ↓
STT WebSocket
   ↓
Brain streaming
   ↓
TTS WebSocket CONNECTS
   ↓
❌ TTS WebSocket closes
   ↓
Brain completes
   ↓
POST /api/tts
   ↓
WAIT ~2–3 seconds
   ↓
FULL AUDIO

Look at this:

22:41:16 [BRAIN] Stream started
22:41:18 [WS] tts error: received 1000 (OK)
22:41:19 [BRAIN] Stream completed
22:41:19 [TTS] Synthesis started
22:41:22 [TTS] Audio received

That's the smoking gun.

You're opening the streaming TTS WebSocket...
22:41:12 WebSocket /ws/tts accepted
22:41:12 TTS upstream connected

...but then it closes:

tts error: received 1000 (OK)

and your application falls back to:

POST /api/tts

So you're paying the latency penalty of creating the WebSocket, failing to use it, and then doing a full HTTP TTS synthesis.

🔥 Issue #1 — Your TTS WebSocket is not actually being used

This is the biggest problem.

Sarvam's current documentation explicitly recommends the WebSocket streaming TTS path for conversational agents because audio chunks arrive progressively instead of waiting for complete synthesis.

Your logs show:

WS /ws/tts
      ↓
connected
      ↓
1000 OK
      ↓
closed
      ↓
POST /api/tts
      ↓
wait
      ↓
full audio

That's exactly what you don't want.

Fix

Your code should do:

Brain delta
    ↓
Sentence ready
    ↓
WS /ws/tts
    ↓
send text
    ↓
Sarvam audio chunk #1
    ↓
Browser
    ↓
PLAY

Not:

Brain complete
    ↓
POST /api/tts
    ↓
wait for entire WAV/MP3
    ↓
play
🔴 Issue #2 — Your TTS is starting AFTER Brain completes

Your logs:

22:41:16 Brain started
22:41:19 Brain completed
22:41:19 TTS synthesis started

That's roughly 3 seconds before TTS even starts.

This defeats the entire purpose of streaming.

You want:

22:41:16 Brain starts
22:41:16.5 first delta
22:41:17 sentence ready
22:41:17 TTS starts
22:41:17.3 first audio
22:41:17.3 SPEAKER

The Brain should not need to finish the entire answer before TTS begins.

Sarvam specifically describes WebSocket TTS as suitable for conversational agents because audio can flow before the sentence finishes synthesizing.

🔴 Issue #3 — You have TWO TTS architectures competing

Your logs show:

WebSocket TTS
/ws/tts

and:

HTTP TTS
POST /api/tts

This is dangerous.

You should have:

LIVE VOICE MODE
       ↓
WS TTS

and optionally:

TEST / REPLAY
       ↓
HTTP TTS

Currently it appears to be:

LIVE
 ↓
WS
 ↓
fails/closes
 ↓
HTTP fallback

That fallback is destroying your latency.

My recommendation

For live mode:

Disable HTTP fallback entirely during normal operation.

If WS fails, log an explicit error instead of silently switching to slow REST synthesis.

That will make the problem visible and force you to fix the actual streaming path.

🔴 Issue #4 — You're opening a new TTS WebSocket every turn

Look at:

22:41:12 WebSocket /ws/tts

Then again:

22:41:34 WebSocket /ws/tts

Then again:

22:41:44 WebSocket /ws/tts

So every turn appears to establish a new connection.

That's unnecessary overhead.

Your architecture earlier said:

"WS /ws/tts (warm per turn)"

But your implementation appears to be creating a new connection for every turn.

Better

Maintain:

Voice session
      │
      ├── STT WebSocket ───────────── persistent
      │
      └── TTS WebSocket ───────────── persistent

Then:

Turn 1 → text → same TTS WS
Turn 2 → text → same TTS WS
Turn 3 → text → same TTS WS

Sarvam's WebSocket API supports streaming configuration and text chunks over the same connection.

This can eliminate repeated WebSocket handshake latency.

🔴 Issue #5 — Your TTS config has temperature=-

This is suspicious:

temperature=-

Your runtime config is logging:

model=bulbul:v3
speaker=shubh
pace=1.08
temperature=-

But your earlier UI had a temperature setting.

So your runtime configuration appears to have no actual TTS temperature value.

That's something I'd fix immediately.

For Bulbul v3, Sarvam documents temperature as supported from 0.01–1.0, with 0.6 default.

For your business voice agent I'd test:

temperature = 0.4

or:

0.45

Sarvam's own contact-center examples use Bulbul v3 with pace=1.1 and temperature=0.4, which is actually very close to your use case.

🟠 Issue #6 — You're using pace=1.08

This isn't a problem.

Actually, it's reasonable.

Sarvam's contact-center guidance uses:

pace=1.1
temperature=0.4

for a brisk professional delivery.

So I'd keep:

pace = 1.05–1.10

Your:

1.08

is perfectly reasonable.

Don't waste time optimizing this before fixing streaming.

🟠 Issue #7 — Your audio codec changes between paths

Look:

WebSocket:

codec=linear16

HTTP:

codec=mp3

This means your two paths aren't even producing the same audio format.

Your WebSocket path:

linear16 / 24kHz

Your HTTP fallback:

MP3 / 24kHz

That's another reason your playback architecture can behave differently between automatic and manual playback.

Sarvam's WebSocket API supports streaming audio chunks and Bulbul v3 uses 24 kHz by default.

For browser voice agent

I'd pick one format and use it consistently.

If your current browser playback is already built around MediaSource + MPEG:

MP3

can be convenient.

But if your WebSocket implementation is receiving linear16, then your browser needs a proper PCM playback pipeline — you cannot simply treat raw PCM as MP3.

So don't change this blindly.

Your coding agent should audit:

Sarvam output
 ↓
codec
 ↓
base64 decode
 ↓
browser buffer
 ↓
AudioContext / MediaSource
🔴 Issue #8 — The biggest architecture mistake: TTS starts too late

You currently have:

Brain starts
       ↓
Brain completes
       ↓
TTS starts

You want:

Brain starts
       ↓
first delta
       ↓
sentence accumulator
       ↓
sentence complete
       ↓
TTS immediately

For example Brain generates:

"అవునా సార్…"

then:

"అవునా సార్… 50 లక్షల వరకు చూస్తున్నారా?"

As soon as the sentence is complete:

→ TTS

Don't wait for:

"అవునా సార్… 50 లక్షల వరకు చూస్తున్నారా? మీకు plot కావాలా, flat కావాలా? మా దగ్గర..."
🟠 Issue #9 — Your STT architecture is also not using the newest realtime path

Your log:

stt saaras:v3

and:

/ws/stt-realtime?language_code=te-IN&stream_type=fast&mode=transcribe

Your current Sarvam documentation says the older saaras:v3 streaming endpoint is the generally available legacy WebSocket, while saaras:v3-realtime is the newer realtime streaming path intended for new voice-agent/live transcription work, with interim transcripts and finer VAD tuning.

So I'd have your developer test:

saaras:v3
vs
saaras:v3-realtime

Don't blindly switch production yet.

Measure:

speech end
→ transcript.final

If realtime gives you lower endpointing latency and stable Telugu recognition, migrate.

🟠 Issue #10 — Brain is taking ~1–3 seconds

Your first example:

22:41:16 Brain started
22:41:19 Brain completed

That's ~3 seconds.

But we don't know the first delta latency, because your logs aren't recording it.

That's a major observability gap.

You need:

BRAIN_STARTED
BRAIN_FIRST_DELTA
BRAIN_FIRST_SENTENCE
BRAIN_COMPLETED

For example:

16.000 Brain started
16.420 First delta
16.850 Sentence ready
18.900 Brain completed

If first delta is 400ms but completion is 3s, that's fine because TTS can start at 850ms.

If first delta itself is 2.5s, then Brain configuration is the bottleneck.

🟢 GPT-5.6 Luna is actually a good choice here

Your log:

model=gpt-5.6-luna

That's a sensible model for your workload.

OpenAI currently positions GPT-5.6 Luna for cost-sensitive, high-volume workloads, while the flagship is aimed at more complex reasoning.

For a real-time voice agent, don't use heavy reasoning for every turn.

Routine:

"50 lakhs budget."

doesn't require deep reasoning.

Use the lowest practical reasoning configuration.

🔴 Issue #11 — Your current log doesn't show Brain reasoning configuration

You log:

model=gpt-5.6-luna
historyLen=4

but not:

reasoning_effort
temperature
max_output_tokens

You need to log:

[BRAIN_CONFIG]
model=gpt-5.6-luna
reasoning_effort=none
max_output_tokens=140

That lets you prove what is actually being sent.

🟠 Issue #12 — History is growing

You have:

historyLen=0
historyLen=2
historyLen=4

This is okay for now.

But eventually:

historyLen=12

etc. increases input processing.

For voice conversations, don't send huge conversation histories.

I'd use:

6–10 recent turns

plus a compact customer summary if needed.