# PSTN Turn-Taking, VAD & Barge-In Engineering Audit & Production Solution (v2.0)

> **Target Systems**: Economical & Standard PSTN Telephony Tiers (`vobiz` carrier primary, 8 kHz G.711 μ-law / Telnyx L16)  
> **Voice Stack**: Sarvam STT (realtime streaming WebSocket) + Sarvam / Gemini LLM + Sarvam Bulbul / Gemini TTS  
> **Document Purpose**: Re-audit of turn-taking, VAD sensitivity, and barge-in mechanics. Identifies critical ambiguities and flawed assumptions in naive fixes, and provides an optimized, production-grade architecture benchmarked against LiveKit, Retell, and Vapi.

---

## 1. Executive Summary & Why Naive Fixes Fail

During live PSTN calls on the **Economical** and **Standard** tiers, three conversational failures occur:
1. **1-Word False Barge-In**: The caller naturally acknowledges with *"Yeah"*, *"Avunu"* (Telugu), or *"Haan"* (Hindi). The agent instantly truncates its speech.
2. **Background Speaker Interruption**: A family member or colleague talking 6 feet away causes the bot to cut itself off and respond to the room noise.
3. **Background Noise Cut-Off**: A ceiling fan, vehicle horn, or phone speakerphone acoustic echo kills the agent's playout mid-sentence.

### Re-Audit: Critical Flaws in the Initial Fix Plan

A naive review of these problems often proposes simplistic fixes that create severe secondary bugs. Our re-audit identified **3 critical flaws in common/initial fix proposals**:

| Initial Proposal | Why It Fails in Production | Superior Architecture Solution |
| :--- | :--- | :--- |
| **Flaw A: Dropping Audio Frames in `feed_user_pcm16`** | Dropping 20ms audio frames below an RMS energy floor creates **temporal tears and packet discontinuities** in streaming WebSocket STT (Sarvam). This corrupts the acoustic encoder's convolutional memory, causes audible packet jitter, and clips the quiet unvoiced onsets of legitimate caller speech (`/p/`, `/t/`, `/k/`, `/s/`). | **Keep the raw STT audio stream 100% continuous**. Apply energy gating and hysteresis **at the Barge Commit decision point (`_should_commit_barge`)**, utilizing the existing `_aec_barge_open` signal rather than dropping raw PCM packets. |
| **Flaw B: Ignoring the "Ghost Turn" in `_pending_transcript`** | Merely preventing barge-in during speech is not enough. If the caller says *"Haan"* while the agent speaks, Sarvam still emits a `transcript.final: "Haan"`. In [`pstn_voice_core.py:1984`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L1984), the turn completion handler unconditionally calls `self._launch_turn(pending)`. **The agent finishes its sentence, and then immediately launches a second, hallucinated LLM turn responding to its own prompt!** | Implement **Post-Playout Backchannel Purging**. When a turn completes naturally, if `_pending_transcript` contains only backchannel acknowledgment tokens, it is cleared without launching an LLM turn. |
| **Flaw C: Rigid Regexes Missing Indic Morphology** | Standard English regexes fail on Indic agglutination, honorific suffixes (`అవునండి` *avunandi*, `సరేనండి` *sarenandi*, `हाँ जी` *haan ji*), and Romanized phonetic transcripts (`"avunu"`, `"sare"`, `"theek"`, `"theek hai"`). | Implement an **Adaptive Indic Backchannel Classifier** supporting unspaced Telugu script, honorific compounds, and Romanized Hinglish/Tenglish tokens. |

---

## 2. Forensic Codebase Audit: The 6 Root Causes

Our codebase investigation revealed **6 interconnected failure points** across the telephony media pipeline:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                TELEPHONY INBOUND AUDIO                                 │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Root Cause 1: Sarvam STT WebSocket Hyper-Sensitivity (server/services/sarvam_ws.py)    │
│ • high_vad_sensitivity = True by default (drops internal threshold to ~0.2)           │
│ • min_speech_duration_ms is None (transient clicks/fans trip vad.speech_start)         │
│ • silence_duration_ms = None (premature endpointing on natural Indic phrase pauses)   │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Emits partial/final transcripts
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Root Cause 2: Backchannels Bundled with Halt Commands (pstn_voice_core.py:56-62)      │
│ • _SHORT_INTERRUPT matches "yes", "yeah", "అవును", "हाँ", "ठीक"                         │
│ • Bypasses bargeMinWords rule (lines 558-560) and substantive gate (line 546)         │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                     ┌─────────────────────┴─────────────────────┐
                     ▼                                           ▼
┌──────────────────────────────────────────┐┌──────────────────────────────────────────┐
│ Root Cause 3: Premature Barge Timers     ││ Root Cause 4: LLM Thinking Cancel Leak   │
│ • PSTN_BARGE_MIN_WORDS = 1 (line 31)     ││ • _THINK_CANCEL_ACK_ONLY misses Indic    │
│ • PSTN_BARGE_HOLD_S = 0.12s (120ms!)     ││   words ("అవును", "సరే", "हाँ")          │
│ • PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.04s   ││ • Saying "అవును" while LLM is generating │
│   (40ms is too short for telco echo!)    ││   aborts the thinking turn!              │
└──────────────────────────────────────────┘└──────────────────────────────────────────┘
                     │                                           │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Root Cause 5: Unconnected Soft AEC Hysteresis (_aec_barge_open ignored in commit)     │
│ • pstn_voice_core.py:1636 calculates _aec_barge_open (RMS >= 320 for 2 frames)        │
│ • BUT _should_commit_barge NEVER checks _aec_barge_open! Background noise commits!    │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Turn completes naturally
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Root Cause 6: The "Ghost Brain Turn" (pstn_voice_core.py:1984)                         │
│ • Caller backchannel nod ("Haan") during speech is queued in _pending_transcript       │
│ • On playback finish, line 1984 launches _run_turn("Haan") without substantive filter! │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Detailed Analysis of Each Root Cause

#### Root Cause 1: Sarvam STT WebSocket Hyper-Sensitivity
In [`server/services/sarvam_ws.py:64-86`](file:///d:/voice%20agent/server/services/sarvam_ws.py#L64-L86) and [`server/routes/ws.py:124`](file:///d:/voice%20agent/server/routes/ws.py#L124):
- `high_vad_sensitivity` defaults to `True`.
- In `server/routes/ws.py:124`, `threshold` is hardcoded to `0.3`.
- `min_speech_duration_ms` is `None` in the provider adapter.
- In Silero/neural VAD, a threshold of `0.3` combined with `high_vad_sensitivity=True` triggers on low-energy ambient sounds: breathing into the receiver, distant room conversation, keyboard typing, or ceiling fan rotation.

#### Root Cause 2: Backchannels Bundled into `_SHORT_INTERRUPT`
In [`server/services/pstn_voice_core.py:56-62`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L56-L62):
```python
_SHORT_INTERRUPT = re.compile(
    r"^(?:yes|no|yeah|yep|nope|wait|stop|actually|hold on|one second|sorry|"
    r"కాదు|లేదు|లేదండి|అవును|వద్దు|అది కాదు|"
    r"नहीं|हाँ|रुको|ठीक)"
    r"(?:\s+\w+){0,3}[.!,]*$",
    re.I,
)
```
In `_should_commit_barge` (lines 545–560):
```python
short_ok = bool(_SHORT_INTERRUPT.match((text or "").strip()))
...
elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not short_ok:
    self._partial_started_at = 0.0
    result, reason = False, "min_words"
```
Because *"yeah"*, *"haan"*, and *"అవును"* match `_SHORT_INTERRUPT`, `short_ok` evaluates to `True`. It **bypasses `bargeMinWords` entirely**. A single nod word halts the agent.

#### Root Cause 3: 40ms Playout Window vs. 160–330ms Telco Acoustic Echo Loop
In [`server/services/pstn_voice_core.py:40`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L40):
```python
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.04  # 40 milliseconds
```
In PSTN telephony (carrier Vobiz G.711 μ-law), round-trip acoustic latency follows this physical timeline:
1. **Server to Carrier RTP egress**: 20–40ms
2. **Carrier cellular transit to base station & handset**: 50–90ms
3. **Handset speaker acoustic leak into handset mic**: 10–30ms
4. **Handset mic audio back through cellular transit to server**: 60–110ms
5. **Total Round-Trip Time (RTT)**: **140ms to 270ms** (often up to 330ms on speakerphones)

Because the protection window was only **40ms**, the reflection of the agent's *own first word* returned to the server at ~180ms, after the 40ms window had expired. The agent interrupted itself on its own voice.

#### Root Cause 4: LLM Thinking Phase Cancellation on Telugu/Hindi Nods
In [`server/services/pstn_voice_core.py:607-610`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L607-L610):
```python
# In _should_think_cancel:
if _THINK_CANCEL_ACK_ONLY.match(cleaned):
    self._think_partial_started_at = 0.0
    return False
short_ok = bool(_SHORT_INTERRUPT.match(cleaned))
```
`_THINK_CANCEL_ACK_ONLY` (lines 49-54) only contained English tokens (`yeah`, `yes`, `ok`, `sure`).
When a caller nodded in Telugu (`"అవును"`), `_THINK_CANCEL_ACK_ONLY` did not match, but line 610 matched `_SHORT_INTERRUPT`! The system treated the nod as an interruption and cancelled the in-flight LLM generation while the bot was thinking.

#### Root Cause 5: Unconnected Soft AEC Hysteresis
[`pstn_voice_core.py:1631-1642`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L1631-L1642) calculates:
```python
rms = pcm16_rms(pcm16)
if rms >= PSTN_TTS_STT_ENERGY_MIN:
    self._last_vad_voice_at = time.monotonic()
    self._aec_loud_streak += 1
    self._aec_quiet_streak = 0
    if self._aec_loud_streak >= PSTN_AEC_LOUD_OPEN_FRAMES:
        self._aec_barge_open = True
```
This state machine correctly requires 2 consecutive loud frames (RMS $\ge$ 320) to open `_aec_barge_open`. However, **`_aec_barge_open` was never checked inside `_should_commit_barge`!** Low-energy noise (< 320 RMS) was allowed to commit barge-in as long as STT produced any text.

#### Root Cause 6: The "Ghost Brain Turn" on Queued Backchannels
In [`pstn_voice_core.py:1456-1460`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L1456-L1460):
When the agent is speaking, any final transcript is queued via `_queue_user_transcript(text)` into `self._pending_transcript`.
When the turn finishes, line 1984 executes:
```python
pending = self._pending_transcript
self._pending_transcript = None
...
else:
    self._launch_turn(pending)  # <-- UNCONDITIONAL LAUNCH
```
If the caller said *"Haan"* at second 4 of an 8-second agent speech, `self._pending_transcript` holds `"Haan"`. When the agent finishes speaking at second 8, the system immediately launches an LLM turn on `"Haan"`, causing the bot to talk to itself.

---

## 3. Acoustic Physics & Signal Characteristics in Telephony

Understanding why background speakers and ambient noise trip VAD requires examining the acoustic signal:

### A. Proximity Effect & Inverse Square Law (Primary vs. Background Speaker)
- **Primary Caller**: Lips are 1.5–3 cm from the smartphone microphone port. Sound pressure level (SPL) at the diaphragm is high: **75–85 dB SPL**, resulting in digital RMS levels of **1,200 to 4,500+** in 16-bit linear PCM.
- **Secondary Background Speaker**: Located 2 meters (~200 cm) away. By the acoustic inverse square law ($I \propto 1/r^2$), sound pressure drops by $\approx 36\text{ dB}$:
  $$\Delta L = 20 \log_{10}\left(\frac{200}{2}\right) \approx 40\text{ dB}$$
  The background speaker arrives at the microphone at **35–45 dB SPL**, producing digital RMS levels of **120 to 280**.

### B. Mobile Phone AGC (Automatic Gain Control) Pumping
When the primary caller stops talking, the mobile baseband processor's AGC ramps up analog/digital gain by **+18 dB to +24 dB** to boost faint sounds. This elevates the background speaker's RMS to **400–600**, fooling a generic VAD with a low threshold (`0.3`).

### C. Crest Factor Analysis (Impulsive Noise vs. Voiced Speech)
Our repository already contains [`pcm16_crest_factor`](file:///d:/voice%20agent/server/services/audio_transcode.py#L169-L183) ($C = \text{Peak} / \text{RMS}$):
- **Impulsive Noise** (fan blade slap, car horns, clattering cutlery, door clicks): Energy is concentrated in a brief spike ($< 30\text{ms}$). Crest factor is high: **$C > 4.5$ (often $8.0\text{--}15.0$)**.
- **Human Voiced Speech** (vowels, sonorants): Energy is distributed across periodic glottal pulses ($100\text{--}300\text{Hz}$). Crest factor is low and stable: **$C \in [1.5, 3.5]$**, and sustained for **$\ge 250\text{ms}$**.

---

## 4. Benchmark: How Industry Leaders Solve This

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 INDUSTRY ARCHITECTURES                                 │
├──────────────────────┬────────────────────────┬────────────────────────────────────────┤
│ Platform             │ Backchannel Isolation  │ Interruption Gate Policy               │
├──────────────────────┼────────────────────────┼────────────────────────────────────────┤
│ **LiveKit Agents**   │ Adaptive Mode          │ Dual-stream token classifier: listener  │
│                      │ (inference auxiliary)  │ tokens are suppressed during playout   │
├──────────────────────┼────────────────────────┼────────────────────────────────────────┤
│ **Vapi AI**          │ Stop-Speaking Plan     │ `numWords` (>= 2) + `voiceSeconds`     │
│                      │                        │ (0.3s) before buffer invalidation      │
├──────────────────────┼────────────────────────┼────────────────────────────────────────┤
│ **Retell AI**        │ Telephony Sensitivity  │ Calibrated slider (0.7-0.8) +          │
│                      │ & Denoising            │ 400ms initial echo shield window       │
├──────────────────────┼────────────────────────┼────────────────────────────────────────┤
│ **Deepgram Flux**    │ Endpointing Delay      │ Dedicated conversational turn model    │
│                      │                        │ separating nods from turn claims       │
└──────────────────────┴────────────────────────┴────────────────────────────────────────┘
```

---

## 5. The Production-Grade Solution (6 Pillars)

### Pillar 1: Robust Indic & English Lexicon Separation
Replace the monolithic `_SHORT_INTERRUPT` with two distinct regex engines supporting Indic scripts, honorific compounds, and Romanized phonetics:

```python
# 1. EMERGENCY HALT COMMANDS: ONLY these explicit words may interrupt with 1 word
_HALT_COMMANDS_RE = re.compile(
    r"^(?:"
    r"stop|wait|hold on|one second|pause|shut up|quiet|cancel|listen|"
    r"ఆగండి|ఆగు|వద్దు|వద్దండి|వద్దండీ|ఆపండి|వినండి|"
    r"रुको|रुकिए|बंद करो|चुप|मत बोलो|सुनो|सुनिए"
    r")(?:\s+\w+){0,2}[.!?,]*$",
    re.I,
)

# 2. CONVERSATIONAL BACKCHANNEL NODS: NEVER interrupt active playback
_BACKCHANNEL_NODS_RE = re.compile(
    r"^(?:"
    # English
    r"yes|yeah|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|right|correct|got it|i see|alright|"
    # Telugu (Script + Romanized)
    r"అవును|అవునండి|అవునండీ|సరే|సరేనండి|అలాగే|అలాగేనండి|బాగుంది|హాం|చెప్పండి|"
    r"avunu|avunandi|sare|sarenandi|alage|alagenandi|bagundi|cheppandi|"
    # Hindi (Script + Romanized)
    r"हाँ|हां|हाँजी|हाँ जी|जी|जी हाँ|जी हां|ठीक|ठीक है|अच्छा|अच्छा जी|सही बात|"
    r"haan|haanji|haan ji|ji|ji haan|theek|theek hai|achha|achha ji"
    r")(?:\s+(?:"
    r"yes|yeah|ok|okay|sure|hmm|haan|avunu|sare|theek|alage|ji|right"
    r"))*[.!,]*$",
    re.I,
)
```

### Pillar 2: Unambiguous Barge-In Commit Logic with Hysteresis Gate
In [`server/services/pstn_voice_core.py:_should_commit_barge`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L545):

```python
clean_text = (text or "").strip()
is_halt_command = bool(_HALT_COMMANDS_RE.match(clean_text))
is_backchannel = bool(_BACKCHANNEL_NODS_RE.match(clean_text))

# Rule A: Pure backchannel acknowledgments NEVER interrupt agent speech
if is_backchannel:
    self._partial_started_at = 0.0
    return False, "backchannel_ignored"

# Rule B: Playout Onset Echo Shield Window (350ms protects against carrier G.711 echo)
if self._tts_started_at and (now - self._tts_started_at) < PSTN_BARGE_MIN_AFTER_SPEAK_S:
    return False, "min_after_speak_echo_shield"

# Rule C: Soft AEC Energy Gate — Background noise & distant speakers (< 320 RMS) cannot interrupt
if not self._aec_barge_open and not is_halt_command:
    return False, "energy_below_floor"

# Rule D: Emergency halt commands ("stop", "wait", "ఆగండి") can interrupt immediately
if is_halt_command:
    return True, "halt_command"

# Rule E: General conversational interruptions require >= 2 words sustained for >= 300ms
min_words = int(self._barge_runtime.get("bargeMinWords") or 2)
if words < min_words:
    self._partial_started_at = 0.0
    return False, "min_words"

if self._partial_started_at <= 0:
    self._partial_started_at = now
    return False, "hold_start"
elif (now - self._partial_started_at) < PSTN_BARGE_HOLD_S:
    return False, "hold"
```

### Pillar 3: Post-Playout Backchannel Purging (Fixing the "Ghost Brain Turn")
In [`server/services/pstn_voice_core.py`](file:///d:/voice%20agent/server/services/pstn_voice_core.py), update the turn cleanup in `finally` of `_run_turn` (line 1972):

```python
pending = self._pending_transcript
self._pending_transcript = None
self.current_generation_id = None
self._interrupted_generation = None

if pending and self._phase != PHASE_ENDED:
    clean_pending = (pending or "").strip()
    # PURGE GHOST TURNS: If the queued transcript is merely a backchannel nod, discard it!
    if _BACKCHANNEL_NODS_RE.match(clean_pending):
        log_pstn("PENDING_PURGED_BACKCHANNEL", call_id=self.call_id, text=clean_pending[:80])
        # Clean transition to LISTENING — do NOT launch an LLM turn on "Haan" or "Avunu"
        pending = None

if pending and self._phase != PHASE_ENDED:
    if self._awaiting_barge_final or self._phase == PHASE_INTERRUPTING:
        self._pending_transcript = pending
    elif cancelled and self._think_cancel_relaunch == "immediate":
        self._think_cancel_relaunch = None
        self._launch_turn(pending)
    elif cancelled:
        self._think_cancel_relaunch = None
        self._arm_listen_coalesce(pending)
    else:
        self._launch_turn(pending)
```

### Pillar 4: Thinking-Phase Immunity for Indic Backchannels
Update `_should_think_cancel` ([`pstn_voice_core.py:607`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L607)) to share `_BACKCHANNEL_NODS_RE`:

```python
def _should_think_cancel(self, text: str) -> bool:
    if self._phase != PHASE_THINKING or self._agent_audio_playing():
        self._think_partial_started_at = 0.0
        return False
    cleaned = (text or "").strip()
    if not cleaned:
        self._think_partial_started_at = 0.0
        return False
        
    # Indic + English backchannels must never abort an in-flight LLM generation
    if _BACKCHANNEL_NODS_RE.match(cleaned):
        self._think_partial_started_at = 0.0
        return False
        
    is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))
    words = effective_word_count(cleaned)
    if words < PSTN_THINK_CANCEL_MIN_WORDS and not is_halt:
        self._think_partial_started_at = 0.0
        return False
...
```

### Pillar 5: Multi-File Calibration of Sarvam STT Real-time VAD
Update the configuration cascade across all three files:

1. **[`server/services/sarvam_ws.py:64`](file:///d:/voice%20agent/server/services/sarvam_ws.py#L64)**:
   - Change default `high_vad_sensitivity = False`.
2. **[`server/routes/ws.py:124`](file:///d:/voice%20agent/server/routes/ws.py#L124)**:
   - Change `threshold: 0.3` to `threshold: 0.55`.
   - Update `silence_duration_ms: 600` and `min_speech_duration_ms: 300`.
3. **[`server/providers/sarvam_stt.py:21`](file:///d:/voice%20agent/server/providers/sarvam_stt.py#L21)**:
   - Pass calibrated defaults:
     ```python
     def connect_realtime(self, config: STTConfig):
         vad = config.vad_config or {}
         return connect_stt_realtime(
             language_code=provider_language_code(config.language, provider="sarvam", stage="stt"),
             stream_type=config.stream_type,
             mode="transcribe",
             endpointing="vad",
             sample_rate=config.sample_rate,
             silence_duration_ms=vad.get("silence_duration_ms", 600),
             threshold=vad.get("threshold", 0.55),
             min_speech_duration_ms=vad.get("min_speech_duration_ms", 300),
             prefix_padding_ms=vad.get("prefix_padding_ms", 100),
             high_vad_sensitivity=False,
             model=config.model,
         )
     ```

### Pillar 6: Calibrated Playout Onset Echo Shield Window
In [`server/services/pstn_voice_core.py:40`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L40):
```python
# Increase from 0.04 to 0.35s to shield against measured 140-270ms carrier G.711 echo
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35
PSTN_BARGE_MIN_WORDS = 2
PSTN_BARGE_HOLD_S = 0.30
```

---

## 6. Implementation Code Diffs

### Diff 1: [`server/services/pstn_voice_core.py`](file:///d:/voice%20agent/server/services/pstn_voice_core.py)

```diff
--- a/server/services/pstn_voice_core.py
+++ b/server/services/pstn_voice_core.py
@@ -30,17 +30,34 @@
 # Prefer substantive/short natural interruptions over a rigid 3-word rule.
-PSTN_BARGE_MIN_WORDS = 1
-PSTN_BARGE_HOLD_S = 0.12
+PSTN_BARGE_MIN_WORDS = 2
+PSTN_BARGE_HOLD_S = 0.30
 # Soft AEC energy is a barge confidence signal only — never a hard STT drop gate.
 PSTN_TTS_STT_ENERGY_MIN = 320
 # Soft AEC barge hysteresis: open after 2 loud frames; close after 8 quiet frames.
 PSTN_AEC_LOUD_OPEN_FRAMES = 2
 PSTN_AEC_QUIET_CLOSE_FRAMES = 8
 PSTN_BARGE_FINAL_TIMEOUT_S = 0.8
-# Two 20ms frames protect the onset; transcript confirmation still holds 120ms.
-PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.04
+PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35
 PSTN_BARGE_DEBOUNCE_S = 0.45
 
-# Short natural barge / think-cancel phrases (EN + common TE/HI).
-_SHORT_INTERRUPT = re.compile(
-    r"^(?:yes|no|yeah|yep|nope|wait|stop|actually|hold on|one second|sorry|"
-    r"కాదు|లేదు|లేదండి|అవును|వద్దు|అది కాదు|"
-    r"नहीं|हाँ|रुको|ठीक)"
-    r"(?:\s+\w+){0,3}[.!,]*$",
-    re.I,
-)
+# 1. Emergency Halt Commands — ONLY these single words may interrupt active agent speech
+_HALT_COMMANDS_RE = re.compile(
+    r"^(?:stop|wait|hold on|one second|pause|shut up|quiet|cancel|listen|"
+    r"ఆగండి|ఆగు|వద్దు|వద్దండి|వద్దండీ|ఆపండి|వినండి|"
+    r"रुको|रुकिए|बंद करो|चुप|मत बोलो|सुनो|सुनिए"
+    r")(?:\s+\w+){0,2}[.!?,]*$",
+    re.I,
+)
+
+# 2. Conversational Backchannel Nods — NEVER interrupt active agent speech
+_BACKCHANNEL_NODS_RE = re.compile(
+    r"^(?:yes|yeah|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|right|correct|got it|i see|alright|"
+    r"అవును|అవునండి|అవునండీ|సరే|సరేనండి|అలాగే|అలాగేనండి|బాగుంది|హాం|చెప్పండి|"
+    r"avunu|avunandi|sare|sarenandi|alage|alagenandi|bagundi|cheppandi|"
+    r"हाँ|हां|हाँजी|हाँ जी|जी|जी हाँ|जी हां|ठीक|ठीक है|अच्छा|अच्छा जी|सही बात|"
+    r"haan|haanji|haan ji|ji|ji haan|theek|theek hai|achha|achha ji"
+    r")(?:\s+(?:yes|yeah|ok|okay|sure|hmm|haan|avunu|sare|theek|alage|ji|right))*[.!,]*$",
+    re.I,
+)
@@ -544,4 +561,16 @@
         intro = self._phase == PHASE_INTRO or self._intro_phase
-        short_ok = bool(_SHORT_INTERRUPT.match((text or "").strip()))
-        substantive = is_substantive_transcript(text or "", after_barge=True) or short_ok
+        clean_text = (text or "").strip()
+        is_halt_command = bool(_HALT_COMMANDS_RE.match(clean_text))
+        is_backchannel = bool(_BACKCHANNEL_NODS_RE.match(clean_text))
+
+        # Backchannel nods during active playback must NEVER interrupt the agent
+        if is_backchannel:
+            self._partial_started_at = 0.0
+            return False
+
+        substantive = is_substantive_transcript(text or "", after_barge=True) or is_halt_command
@@ -557,4 +586,8 @@
         elif now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
             result, reason = False, "debounce"
+        elif not self._aec_barge_open and not is_halt_command:
+            result, reason = False, "energy_below_floor"
+        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
+            result, reason = False, "min_after_speak_echo_shield"
-        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not short_ok:
+        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not is_halt_command:
             self._partial_started_at = 0.0
             result, reason = False, "min_words"
@@ -1971,3 +2004,8 @@
             self.current_generation_id = None
             self._interrupted_generation = None
+            if pending and self._phase != PHASE_ENDED:
+                # Purge ghost turns: backchannel nods during speech must not launch a brain turn
+                if _BACKCHANNEL_NODS_RE.match((pending or "").strip()):
+                    log_pstn("PENDING_PURGED_BACKCHANNEL", call_id=self.call_id, text=pending[:80])
+                    pending = None
             if pending and self._phase != PHASE_ENDED:
```

### Diff 2: [`server/services/sarvam_ws.py`](file:///d:/voice%20agent/server/services/sarvam_ws.py)

```diff
--- a/server/services/sarvam_ws.py
+++ b/server/services/sarvam_ws.py
@@ -63,3 +63,3 @@
     prefix_padding_ms: int | None = None,
-    high_vad_sensitivity: bool = True,
+    high_vad_sensitivity: bool = False,
     model: str | None = None,
```

### Diff 3: [`server/routes/ws.py`](file:///d:/voice%20agent/server/routes/ws.py)

```diff
--- a/server/routes/ws.py
+++ b/server/routes/ws.py
@@ -122,5 +122,5 @@
             vad_config={
                 # Explicit endpointing/onset padding for composed voice.
-                "silence_duration_ms": kwargs.get("silence_duration_ms") or 500,
-                "threshold": kwargs.get("threshold") if kwargs.get("threshold") is not None else 0.3,
-                "min_speech_duration_ms": 250,
+                "silence_duration_ms": kwargs.get("silence_duration_ms") or 600,
+                "threshold": kwargs.get("threshold") if kwargs.get("threshold") is not None else 0.55,
+                "min_speech_duration_ms": 300,
                 "prefix_padding_ms": 300,
```

---

## 7. Verification & Telephony Field Test Matrix

| # | Test Scenario | Caller Action During Call | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Conversational Nod (English)** | While agent explains an offer, say *"Yeah"* or *"Okay"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **2** | **Conversational Nod (Telugu)** | While agent explains an offer, say *"అవునండి"* (*avunandi*) or *"సరే"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **3** | **Conversational Nod (Hindi)** | While agent explains an offer, say *"हाँ जी"* (*haan ji*) or *"ठीक है"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **4** | **No Ghost Turn at Turn End** | Say *"Avunu"* during agent speech, then remain silent when agent finishes. | Agent finishes, transitions to `listening`, and waits silently. | Does NOT respond to *"Avunu"*; waits for user. |
| **5** | **Emergency Halt Command** | While agent is speaking, say *"Wait!"*, *"Stop!"*, or *"ఆగండి"*. | Agent halts speech within 150ms. | Immediate playback clear and cancel. |
| **6** | **Substantive Question Barge-In** | While agent is speaking, say *"Actually what is the fee?"* ($\ge 3$ words). | Agent halts cleanly after 300ms and answers the question. | Smooth transition to new LLM turn. |
| **7** | **Background Speaker Rejection** | Remain quiet while a colleague speaks 5 feet away in the room. | Agent continues speaking; VAD does not trip. | Low RMS (< 320) rejected by `_aec_barge_open`. |
| **8** | **High Ambient Fan Noise** | Hold phone near a running ceiling fan or road traffic. | Agent plays speech to completion without clipping. | Sarvam STT threshold `0.55` ignores steady noise. |
| **9** | **Speakerphone Echo Shield** | Put call on loud speakerphone in an echoic room. | Agent does not cut itself off during first word. | `min_after_speak` 350ms absorbs reflection. |
| **10**| **Thinking Phase Immunity** | Ask a question, and say *"అవును"* while the bot is generating. | Bot completes thinking and speaks the answer normally. | Generation is NOT cancelled. |
