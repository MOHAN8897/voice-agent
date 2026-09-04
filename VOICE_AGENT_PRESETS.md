# TASK: Fix Telnyx PSTN AI Voice Audio Pipeline + Build Live Audio-Flow Debugger

You are working on a production Telugu AI voice agent using:

**PSTN → Telnyx → WebSocket → STT → LLM → TTS → WebSocket → Telnyx → PSTN**

The current problem is:

* The PSTN call connects successfully.
* Incoming caller audio reaches the backend.
* STT appears to receive and transcribe audio.
* LLM generates responses.
* TTS generates large amounts of audio.
* However, the person on the PSTN call cannot hear the AI agent's voice reliably / at all.

I have provided runtime logs showing this behavior.

Your job is to **inspect the actual code and runtime media flow, identify the root cause, fix it properly, and add a live visual media-flow debugger.**

Do NOT assume the existing logging is correct. Verify the actual bytes, codecs, sample rates, queue behavior, WebSocket messages, and Telnyx configuration.

---

# 1. FIRST: AUDIT THE ENTIRE AUDIO PIPELINE

Trace one complete call using:

* `call_id`
* Telnyx stream/control ID
* `turn_id`
* WebSocket connection ID

The exact flow must be traceable as:

```text
PSTN Caller
    ↓
Telnyx
    ↓
Telnyx WebSocket inbound media
    ↓
Audio Decoder / Normalizer
    ↓
STT
    ↓
Transcript
    ↓
LLM
    ↓
TTS
    ↓
Audio Decoder / Converter
    ↓
Outbound Audio Queue
    ↓
Telnyx WebSocket outbound media
    ↓
Telnyx
    ↓
PSTN Caller
```

For every stage, log:

```text
call_id
turn_id
timestamp
stage
direction
codec
sample_rate
channels
bytes
frames
duration_ms
queue_size
```

Do not rely only on configuration values.

Log the **actual negotiated media format from Telnyx**.

---

# 2. FIX THE TELNYX CODEC MISMATCH

The current logs show a major inconsistency:

```text
call initiation:
wire_codec = PCMU
wire_rate = 8000

actual Telnyx stream.start:
codec = PCMA
sample_rate = 8000

TTS:
codec = mulaw
sample_rate = 8000

outbound:
wire_mulaw = true
codec = PCMA
```

This is potentially the primary reason the PSTN side is silent.

PCMU / μ-law and PCMA / A-law are NOT the same encoding.

DO NOT fix this by simply changing:

```text
codec = "PCMU"
```

to:

```text
codec = "PCMA"
```

if the actual bytes remain μ-law.

Metadata changes do not convert audio.

---

# 3. CHOOSE ONE AUTHORITATIVE TELNYX MEDIA FORMAT

Inspect how the Telnyx call/stream is created.

Determine exactly which codec Telnyx actually negotiates.

Then choose ONE consistent architecture.

Preferred initial configuration:

```text
Telnyx
codec: PCMU
sample_rate: 8000
channels: 1

STT:
codec/input: matching PCMU/μ-law or correctly decoded PCM
sample_rate: 8000

TTS:
codec: μ-law
sample_rate: 8000

Outbound:
codec: PCMU
sample_rate: 8000
channels: 1
```

If Telnyx actually requires/negotiates PCMA instead, then use:

```text
TTS μ-law
      ↓
decode μ-law → PCM16
      ↓
encode PCM16 → A-law
      ↓
PCMA bytes
      ↓
Telnyx
```

Do NOT relabel μ-law bytes as A-law.

Implement an explicit conversion layer if necessary.

Create clear functions such as:

```python
decode_mulaw_to_pcm16(...)
encode_pcm16_to_mulaw(...)
decode_alaw_to_pcm16(...)
encode_pcm16_to_alaw(...)
```

The outbound function must know the **actual negotiated Telnyx codec**.

Add a hard assertion:

```python
assert outbound_codec == negotiated_telnyx_codec
assert outbound_sample_rate == negotiated_telnyx_sample_rate
assert outbound_channels == negotiated_telnyx_channels
```

If there is a mismatch, fail loudly and log it instead of sending potentially invalid audio.

---

# 4. VERIFY THE ACTUAL AUDIO BYTES

Do not trust variables such as:

```text
wire_mulaw=true
codec=PCMA
```

Inspect the actual outbound byte buffer.

For every outbound audio chunk calculate:

```text
byte_length
sample_count
duration_ms
codec
sample_rate
channels
```

For G.711 8 kHz mono:

```text
20 ms = 160 samples
PCMU/PCMA = 160 bytes
```

Therefore a 160-byte G.711 chunk should represent approximately:

```text
20 ms
```

Verify this mathematically.

Also verify that the implementation is not accidentally sending:

* WAV headers
* MP3 bytes
* PCM16 bytes
* μ-law bytes as A-law
* A-law bytes as μ-law
* base64 text instead of decoded bytes
* double-base64 encoded data
* RTP headers when only payload is expected
* RTP payload when RTP packets are expected

Inspect the exact Telnyx WebSocket outbound media contract currently being used by the application and make the implementation match it.

---

# 5. VERIFY BASE64 HANDLING

Trace the outbound path carefully.

The pipeline should clearly identify:

```text
TTS audio bytes
    ↓
codec conversion
    ↓
raw media bytes
    ↓
base64 encoding
    ↓
JSON WebSocket message
    ↓
Telnyx
```

Make sure the code does not accidentally:

```text
bytes → base64 → base64 again
```

or:

```text
base64 string → send as if it were audio bytes
```

or:

```text
raw bytes → JSON string incorrectly
```

Log:

```text
raw_bytes
base64_length
JSON_payload_length
```

but NEVER log the complete audio payload.

---

# 6. FIX THE OUTBOUND AUDIO QUEUE

The logs show another serious problem.

The queue reaches values such as:

```text
queue_qsize = 458
queue_qsize = 1284
```

while audio is being generated.

At 20 ms per G.711 frame:

```text
458 × 20 ms ≈ 9.16 seconds
1284 × 20 ms ≈ 25.68 seconds
```

This means the TTS producer is generating audio substantially faster than the Telnyx consumer is transmitting it.

That is not acceptable for a real-time voice agent.

Fix the architecture.

Use a bounded queue:

```python
MAX_AUDIO_QUEUE_FRAMES = ...
```

The TTS producer must not be allowed to endlessly fill memory.

The outbound sender must consume audio at approximately real-time speed.

For G.711 8 kHz mono:

```text
20 ms frame = 160 bytes
```

Send frames at approximately:

```text
1 frame every 20 ms
```

or according to the exact chunking/pacing requirements of the Telnyx streaming interface being used.

Do NOT send an entire TTS response as fast as possible.

---

# 7. IMPLEMENT BARGE-IN / INTERRUPT HANDLING

If the caller starts speaking while TTS is playing:

```text
caller speech detected
        ↓
stop/cancel current TTS generation
        ↓
clear outbound audio queue
        ↓
stop pending audio playback
        ↓
start processing new caller turn
```

Do not allow old TTS audio to continue playing after the caller has interrupted.

Every audio queue item should belong to:

```text
call_id
turn_id
generation_id
```

If a new turn supersedes an old turn, old audio must be discarded.

---

# 8. DO NOT WAIT FOR COMPLETE TTS

Use streaming TTS correctly.

Desired flow:

```text
LLM token stream
       ↓
TTS streaming
       ↓
first audio chunk
       ↓
codec conversion
       ↓
audio queue
       ↓
Telnyx
```

The system should begin playing audio as soon as enough valid audio exists.

Do not wait for:

```text
LLM complete
+
TTS complete
+
entire audio response buffered
```

before starting playback.

Track:

```text
LLM first token latency
TTS first audio latency
Telnyx first outbound audio latency
```

---

# 9. ADD AUDIO VALIDATION

Before transmitting every TTS response, calculate:

```text
audio_duration_ms
audio_bytes
codec
sample_rate
channels
```

For example:

```text
TTS generated:
67855 bytes

codec:
mulaw

sample_rate:
8000

channels:
1
```

Calculate expected duration.

For 8-bit G.711:

```text
duration_seconds = bytes / 8000
```

If the calculated duration is unreasonable, log an error.

Example:

```text
AUDIO_VALIDATION_FAILED
expected_codec=PCMU
actual_codec=PCMA
```

---

# 10. CREATE A LIVE CALL MEDIA-FLOW DEBUGGER

This is extremely important.

When a call is active, the dashboard must show a live diagram of the actual audio flow.

Create a UI similar to:

```text
┌──────────────────┐
│   PSTN CALLER    │
│   🎙 Speaking    │
└────────┬─────────┘
         │
         │ INBOUND AUDIO
         │ PCMU/PCMA
         │ 8 kHz
         ▼
┌──────────────────┐
│      TELNYX      │
│   Media Stream   │
│   🟢 CONNECTED   │
└────────┬─────────┘
         │
         ▼
┌────────────────────────┐
│   INBOUND AUDIO        │
│   8 kHz / 1 channel    │
│   Frames: 523          │
│   Bytes: 83,680        │
│   Level: -23 dBFS      │
│   🟢 RECEIVING         │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│       STT              │
│   Sarvam Telugu        │
│   🟢 STREAMING         │
│                        │
│ "మీకు కారు కావాలా?"    │
└────────┬───────────────┘
         │
         │ TRANSCRIPT
         ▼
┌────────────────────────┐
│        LLM             │
│   🧠 PROCESSING        │
│                        │
│ Turn: 3                 │
│ First token: 820 ms    │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│        TTS             │
│   🔊 Sarvam/Cartesia   │
│   🟢 GENERATING        │
│                        │
│ Codec: MULAW           │
│ Rate: 8000             │
│ First audio: 180 ms    │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   AUDIO CONVERTER      │
│                        │
│ MULAW → PCMU           │
│ or                     │
│ MULAW → PCM → PCMA     │
│                        │
│ 🟢 VALID               │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   OUTBOUND QUEUE       │
│                        │
│ Frames: 4              │
│ ~80 ms                 │
│ 🟢 HEALTHY             │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│      TELNYX            │
│  OUTBOUND MEDIA        │
│                        │
│ Codec: PCMU            │
│ Rate: 8000             │
│ Frames sent: 512       │
│ 🟢 TRANSMITTING        │
└────────┬───────────────┘
         │
         ▼
┌──────────────────┐
│   PSTN CALLER    │
│   🔊 AI VOICE    │
└──────────────────┘
```

The diagram must be **live**, not a static architecture diagram.

---

# 11. SHOW TWO SEPARATE AUDIO DIRECTIONS

This is critical.

The dashboard must visually distinguish:

### INBOUND AUDIO

```text
PSTN
 ↓
Telnyx
 ↓
Backend
 ↓
STT
```

and:

### OUTBOUND AUDIO

```text
LLM
 ↓
TTS
 ↓
Audio Converter
 ↓
Queue
 ↓
Telnyx
 ↓
PSTN
```

Use different visual flow directions.

For example:

```text
                 LIVE CALL

        INBOUND AUDIO
PSTN ────────────────► STT
        Telnyx
        8k PCMA
        320-byte chunks


        OUTBOUND AUDIO
PSTN ◄──────────────── TTS
        Telnyx
        8k PCMU
        160-byte frames
```

This must make it immediately obvious whether:

```text
caller → agent
```

is working and whether:

```text
agent → caller
```

is working.

---

# 12. SHOW AUDIO FLOW STATUS

Each pipeline stage should have a state:

```text
GRAY   = not started
BLUE   = processing
GREEN  = healthy / receiving
YELLOW = delayed / queue growing
RED    = failed / stopped
```

For example:

```text
PSTN
 🟢
   ↓
Telnyx inbound
 🟢  320 bytes/chunk
   ↓
STT
 🟢  8 kHz
   ↓
LLM
 🟢
   ↓
TTS
 🟢  160 bytes/chunk
   ↓
Converter
 🔴 CODEC MISMATCH
   ↓
Telnyx outbound
 🔴
   ↓
PSTN
 🔴 NO AUDIO
```

This should allow me to immediately identify where the voice stops.

---

# 13. ADD REAL-TIME METRICS

For each active call display:

```text
Call ID
Call duration

Inbound:
  packets/sec
  bytes/sec
  codec
  sample rate
  channels
  audio level
  frames received

STT:
  status
  partial transcript
  final transcript
  latency

LLM:
  status
  first token latency
  generation time

TTS:
  provider
  codec
  sample rate
  first audio latency
  total bytes
  duration

Outbound:
  codec
  sample rate
  frames generated
  frames sent
  packets/sec
  queue size
  queue duration
  dropped frames
  interrupted frames
```

---

# 14. ADD AUDIO LEVEL / SILENCE DETECTION

For inbound and outbound audio, calculate an approximate audio level.

Show:

```text
INBOUND LEVEL
████████░░  -18 dBFS

OUTBOUND LEVEL
██████░░░░  -24 dBFS
```

This helps distinguish:

```text
audio is not arriving
```

from:

```text
audio is arriving but is silence
```

from:

```text
audio is generated but not transmitted
```

Do not store raw call audio unnecessarily.

Only store short diagnostic samples if the existing privacy/security design permits it.

---

# 15. ADD "LAST AUDIO EVENT"

For every stage show:

```text
Last packet:
250 ms ago

Last audio:
18 ms ago

Last transcript:
1.2 sec ago

Last TTS chunk:
80 ms ago

Last Telnyx outbound:
20 ms ago
```

If any stage stops updating, make it visually obvious.

---

# 16. ADD AUDIO FLOW EVENT LOG

Create a structured event timeline:

```text
15:21:02.001
TELNYX_STREAM_CONNECTED

15:21:02.120
INBOUND_AUDIO
codec=PCMA
rate=8000
bytes=320

15:21:02.145
STT_AUDIO_RECEIVED

15:21:03.842
STT_FINAL
text="..."

15:21:03.900
LLM_STARTED

15:21:04.620
LLM_FIRST_TOKEN

15:21:04.810
TTS_FIRST_AUDIO
codec=MULAW
rate=8000
bytes=160

15:21:04.812
CODEC_CONVERSION
MULAW → PCMA

15:21:04.815
OUTBOUND_AUDIO_QUEUED
bytes=160

15:21:04.835
TELNYX_OUTBOUND_SENT
bytes=160

15:21:04.855
TELNYX_OUTBOUND_SENT
bytes=160
```

Make the event timeline filterable by:

```text
Inbound
STT
LLM
TTS
Conversion
Queue
Outbound
Errors
```

---

# 17. ADD HARD FAILURE DETECTION

The dashboard must explicitly detect:

### Codec mismatch

```text
NEGOTIATED = PCMA
ACTUAL OUTBOUND = MULAW

🔴 CODEC MISMATCH
```

### Sample-rate mismatch

```text
NEGOTIATED = 8000
ACTUAL = 24000

🔴 SAMPLE RATE MISMATCH
```

### Queue overload

```text
QUEUE = 1284 frames
≈ 25.7 seconds

🔴 AUDIO BACKLOG
```

### No outbound audio

```text
TTS AUDIO EXISTS
OUTBOUND AUDIO = 0

🔴 AUDIO TRANSMISSION FAILURE
```

### STT receives nothing

```text
TELNYX INBOUND = 0
STT = 0

🔴 INBOUND MEDIA FAILURE
```

### TTS receives no text

```text
LLM = SUCCESS
TTS = 0

🔴 TTS INPUT FAILURE
```

### TTS generates audio but Telnyx does not receive it

```text
TTS = SUCCESS
QUEUE = SUCCESS
TELNYX OUTBOUND = 0

🔴 OUTBOUND TRANSMISSION FAILURE
```

---

# 18. CREATE AN END-TO-END HEALTH SCORE

For each active call display:

```text
VOICE PIPELINE HEALTH
████████░░ 82%
```

Calculate this from actual runtime conditions.

Example:

```text
Telnyx inbound       ✓
STT                   ✓
LLM                   ✓
TTS                   ✓
Codec conversion      ✗
Outbound queue        ⚠
Telnyx outbound       ✗
```

Do not make the health score claim that the human actually heard the audio.

It should only say:

```text
"Outbound media successfully transmitted"
```

The system cannot know that the human's physical handset speaker actually produced audible sound unless endpoint-level instrumentation exists.

---

# 19. ADD A ONE-CLICK DIAGNOSTIC TEST

Add:

```text
[ TEST AGENT AUDIO ]
```

The test should generate a short known test phrase/audio signal and run it through:

```text
TTS
 ↓
conversion
 ↓
queue
 ↓
Telnyx outbound
```

Show exactly where it succeeds/fails.

Also create a:

```text
[ TEST CODEC ]
```

button that validates:

```text
PCMU
PCMA
PCM16
```

conversion paths.

---

# 20. DO NOT MASK ERRORS

Do not silently fallback between:

```text
PCMU
PCMA
PCM
MP3
WAV
```

If an unsupported format is detected:

```text
raise/log explicit error
```

Do not silently send it to Telnyx.

Likewise, remove confusing layered configuration where generic TTS defaults to:

```text
MP3 / 24 kHz
```

and later another layer changes it to:

```text
μ-law / 8 kHz
```

Create ONE authoritative call media configuration.

For example:

```python
CallMediaConfig(
    codec="PCMU",
    sample_rate=8000,
    channels=1,
)
```

Everything downstream must use this configuration.

---

# 21. VERIFY TELNYX STREAM CONFIGURATION

Inspect the actual API request that starts the Telnyx media stream.

Verify:

```text
codec
sample rate
bidirectional mode
target legs
stream URL
```

Do not assume the values in application configuration are the same as the values Telnyx negotiated.

The `stream.start` event received from Telnyx is authoritative for the actual stream.

If the configured codec and actual negotiated codec differ:

```text
show RED WARNING
```

and either:

1. fix the Telnyx configuration so the expected codec is negotiated, OR
2. dynamically convert audio to the actual negotiated codec.

---

# 22. WRITE AUTOMATED TESTS

Add unit/integration tests for:

```text
μ-law encode/decode
A-law encode/decode
PCM16 → μ-law
PCM16 → A-law
codec mismatch detection
sample-rate mismatch detection
channel mismatch detection
base64 encoding/decoding
queue backpressure
queue clearing
barge-in
20 ms frame duration
Telnyx outbound message construction
```

Especially test:

```text
PCM → μ-law → PCM
PCM → A-law → PCM
```

and verify that the resulting waveform is valid.

---

# 23. FINAL REQUIRED RESULT

After implementing the fixes, provide me with:

### A. Root cause

Explain exactly why the PSTN caller could not hear the AI.

### B. Files changed

List every file changed.

### C. Codec flow

Show the final actual codec flow:

```text
PSTN
 ↓
Telnyx: ______
 ↓
STT: ______
 ↓
LLM
 ↓
TTS: ______
 ↓
Converter: ______
 ↓
Telnyx outbound: ______
 ↓
PSTN
```

### D. Queue behavior

Show before/after:

```text
Before:
queue = 1284 frames

After:
queue = approximately ___ frames
```

### E. Runtime proof

Provide a sample successful call trace:

```text
INBOUND AUDIO ✓
STT ✓
LLM ✓
TTS ✓
CONVERSION ✓
QUEUE ✓
TELNYX OUTBOUND ✓
```

### F. Dashboard

The dashboard must clearly show two independent audio directions:

```text
CALLER → TELNYX → STT
```

and:

```text
LLM → TTS → CONVERTER → TELNYX → CALLER
```

The purpose is that during a live call I can look at the diagram and immediately know:

**"Is caller audio reaching my agent?"**

and separately:

**"Is agent audio actually being transmitted back to the caller?"**

Do not stop at identifying the problem. Implement the fixes, run the available tests, inspect the resulting logs, and verify the complete runtime path.
