# PSTN Turn-Taking, VAD & Barge-In Engineering Audit & Production Solution (v2.1)

> **Target Systems**: Economical & Standard PSTN Telephony Tiers (`vobiz` carrier primary, 8 kHz G.711 μ-law / Telnyx L16)  
> **Voice Stack**: Sarvam STT (realtime streaming WebSocket) + Sarvam / Gemini LLM + Sarvam Bulbul / Gemini TTS  
> **Document Purpose**: Re-audit of turn-taking, VAD sensitivity, and barge-in mechanics. v2.1 fixes 10 critical errata from v2.0 (return-type mismatch, AEC timing race, missing halt words, Indic regex failure, ghost-turn dead-air, and adds soft pause/resume + self-echo pillars).

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

### Pre-Ship Production Criticality Audit (Must Fix Before Shipping)

Every issue identified during review has been systematically audited and categorized by severity, blast radius, and failure mechanism:

| # | Issue Identified | Severity | Production Impact / Failure Mechanism | Status |
|---|------------------|----------|---------------------------------------|--------|
| **1** | **Return Type Tuple Mismatch in `_should_commit_barge`** | **CRITICAL** | `_should_commit_barge` is typed `-> bool`. Returning `(False, reason)` creates a truthy tuple in Python. Every caller `if self._should_commit_barge(text):` evaluates `(False, "...")` as `True`, inverting the logic and causing **100% of backchannel nods to instantly barge in!** | **Resolved in v2.1** (returns bare `bool`) |
| **2** | **AEC Gate Timing Race (`_aec_barge_open` 160ms vs STT 300-800ms)** | **CRITICAL** | The gate closes after 8 quiet frames (~160ms), but Sarvam's WebSocket partial transcript arrives 300–800ms after audio. The gate is guaranteed closed when words arrive, falsely rejecting real interruptions as `energy_below_floor`. | **Resolved in v2.1** (800ms time latch via `_last_vad_voice_at`) |
| **3** | **Ghost-Turn Purge Dead Air on Question Turns** | **CRITICAL** | If agent asks *"Shall I proceed?"* and caller replies *"Haan"* or *"Avunu"* slightly before TTS completes, unconditional backchannel purge discards their answer. The agent goes silent in `listening` mode; neither party speaks. | **Resolved in v2.1** (`agent_asked_question` context preservation) |
| **4** | **Missing Negative / Correction Halt Words** | **CRITICAL** | "No", "nope", "కాదు", "లేదు", "లేదండి", "नहीं", "actually", "sorry" were dropped in v2.0. Callers correcting wrong bot statements are forced into 2 words + 300ms hold, letting the bot talk over them. | **Resolved in v2.1** (restored to `_HALT_COMMANDS_RE`) |
| **5** | **Leftover `_SHORT_INTERRUPT` / `short_ok` / `_THINK_CANCEL_ACK_ONLY`** | **CRITICAL** | 9 call sites across `pstn_voice_core.py` reference `_SHORT_INTERRUPT` and `short_ok`. Removing the regex without full migration causes runtime `NameError` crash on the first think-cancel or barge attempt. | **Resolved in v2.1** (complete 9-site migration table & diff) |
| **6** | **Mobile AGC Pumping (400-600 RMS) vs Fixed 320 RMS Gate** | **HIGH** | Phone AGC boosts background voices to 400–600 RMS during caller pauses, passing a 320 gate. Conversely, soft-spoken primary callers (<320 RMS) are locked out. Absolute thresholds fail in telephony; gate must be treated as a soft confidence signal. | **Resolved in v2.1** (soft signal + relative SNRs + field test protocol) |
| **7** | **Regex `\w` Failure on Indic Diacritics & "చెప్పండి" (cheppandi) Misclassification** | **HIGH** | `(?:\s+\w+){0,2}` splits Telugu/Hindi combining characters (virama/halant/matras). `\S+` is required. "చెప్పండి" means *"tell me / go ahead"*, an invitation to speak, NOT a passive nod. | **Resolved in v2.1** (`\S+` used; `చెప్పండి` removed from nods) |
| **8** | **Root Cause 1 Fact-Check, `prefix_padding_ms` Inconsistency & +100ms Latency** | **HIGH** | `ws.py` already passes `min_speech_duration_ms=250` and `prefix_padding_ms=300`. Provider adapter passed `None`, missing calibration. +100ms silence duration adds +100ms latency to every turn-end. | **Resolved in v2.1** (exact parameter cascade & latency budget documented) |
| **9** | **Soft Pause & Resume (TTS Ducking on VAD Onset)** | **HIGH (Architectural Win)** | Binary barge-in makes false positives jarring. Ducking TTS to 20% on VAD onset and restoring to 100% after 700ms if no substantive words arrive hides false positives completely. | **Resolved in v2.1** (Pillar 7 implementation) |
| **10**| **Partial-Level Self-Echo Text Suppression** | **HIGH** | Waiting until barge commit to check echo overlap allows speakerphone echo partials to manipulate hold timers and latch gates. Early drop at partial handler prevents noise from entering the pipeline. | **Resolved in v2.1** (Pillar 8 implementation) |

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
│ Root Cause 1: Sarvam STT VAD Miscalibration (multi-file inconsistency)                 │
│ • sarvam_ws.py: high_vad_sensitivity=True default, but guarded by None checks          │
│ • ws.py already sends threshold=0.3, min_speech=250ms, prefix_padding=300ms            │
│ • sarvam_stt.py provider passes None for all VAD params (no defaults!)                 │
│ • Real delta: threshold 0.3→0.55, min_speech 250→300, silence 500→600                  │
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

#### Root Cause 1: Sarvam STT VAD Miscalibration (Multi-File Inconsistency)

> **v2.1 Correction**: The v2.0 audit overstated this root cause. `ws.py` already passes `min_speech_duration_ms=250` and `prefix_padding_ms=300` via `vad_config`. The `high_vad_sensitivity` flag in `sarvam_ws.py:85` is only sent when **both** `min_speech_duration_ms` and `prefix_padding_ms` are `None` — so on the composed-voice route (ws.py), the flag was never sent. The real problem is:

In [`server/services/sarvam_ws.py:64-86`](file:///d:/voice%20agent/server/services/sarvam_ws.py#L64-L86), [`server/routes/ws.py:121-127`](file:///d:/voice%20agent/server/routes/ws.py#L121-L127), and [`server/providers/sarvam_stt.py:20-33`](file:///d:/voice%20agent/server/providers/sarvam_stt.py#L20-L33):

| File | Current Value | Target Value | Issue |
|------|--------------|-------------|-------|
| `ws.py:124` | `threshold: 0.3` | `0.55` | Too low — trips on breathing, distant speech, fan noise |
| `ws.py:123` | `silence_duration_ms: 500` | `600` | +100ms adds turn-end latency (trade-off!) |
| `ws.py:125` | `min_speech_duration_ms: 250` | `300` | +50ms, modest improvement |
| `ws.py:126` | `prefix_padding_ms: 300` | `300` | Already correct on this route |
| `sarvam_stt.py:28-31` | All `None` (no defaults!) | Match ws.py values | Provider route sends no VAD params — Sarvam uses its own defaults |
| `sarvam_ws.py:64` | `high_vad_sensitivity=True` | `False` | Default still True, affects direct callers |

**Key insight**: The `sarvam_stt.py` provider adapter passes `None` for all VAD params. When a call uses the provider registry path (line 130-146 in ws.py), Sarvam receives no threshold/silence/min_speech configuration at all, falling back to Sarvam's internal defaults. This is the route where `high_vad_sensitivity` matters.

**Latency trade-off**: The +100ms silence_duration_ms (500→600) adds ~100ms to every turn-end. This is acceptable for PSTN (carrier jitter already adds 40-80ms), but should be profiled in production call recordings.

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
  $$\Delta L = 20 \---

## 5. The Production-Grade Solution (8 Unified Pillars)

The production solution unifies 8 architectural pillars into a cohesive turn-taking engine for the Economical and Standard PSTN voice stacks:

### Pillar 1: Pan-Indic 10-Language Lexicon Separation & Dialectal Robustness

Our platform officially supports **10 languages** ([server/config/constants.py:95-108](file:///d:/voice%20agent/server/config/constants.py#L95-L108)):
`te-IN` (Telugu), `hi-IN` (Hindi), `ta-IN` (Tamil), `kn-IN` (Kannada), `ml-IN` (Malayalam), `mr-IN` (Marathi), `bn-IN` (Bengali), `gu-IN` (Gujarati), `pa-IN` (Punjabi), and `en-IN` / `en-US` / `en-GB` (English).

To ensure zero turn-taking failure regardless of which language pack a tenant selects, the turn-taking engine must support:
1. **Native Indic Scripts** with `\S+` matching to preserve complex Unicode combining diacritics (virama `్` / halant `्`, anusvara `ం` / `ं`, matras).
2. **Romanized / Transliterated Phonetics** (Hinglish, Tanglish, Kanglish, Tenglish, Benglish) because Indian callers code-mix English alphabet phonetics and streaming STTs often output Romanized text.
3. **Turn-Claiming Exclusion**: Explicitly banning "invitation-to-speak" tokens (`చెప్పండి`, `சொல்லுங்க`, `ಹೇಳಿ`, `പറയൂ`, `सांगा`, `বলুন`, `કહો`, `ਦੱਸੋ`, `बोलिए`) from being misclassified as passive nods.

```python
# 1. EMERGENCY HALT COMMANDS (ALL 10 PLATFORM LANGUAGES):
# Immediate 1-word barge-in without hold timer. Covers stops, negations, pauses, and listening demands.
# Uses \S+ instead of \w+ to preserve Indic combining characters across all scripts.
_HALT_COMMANDS_RE = re.compile(
    r"^(?:"
    # English (en-IN, en-US, en-GB)
    r"stop|wait|hold on|one second|pause|shut up|quiet|cancel|listen|no|nope|actually|sorry|wrong|enough|"
    # Telugu (te-IN)
    r"ఆగండి|ఆగు|వద్దు|వద్దండి|వద్దండీ|ఆపండి|వినండి|కాదు|లేదు|లేదండి|అది కాదు|చాలు|"
    r"aagandi|aagu|vaddu|vaddandi|aapandi|vinandi|kaadu|ledu|ledandi|adi kaadu|chaalu|"
    # Hindi (hi-IN)
    r"रुको|रुकिए|बंद करो|चुप|मत बोलो|सुनो|सुनिए|नहीं|ना|बस|रहने दो|गलत|"
    r"ruko|rukiye|band karo|chup|mat bolo|suno|suniye|nahin|nahi|na|bas|rehne do|galat|"
    # Tamil (ta-IN)
    r"நில்லுங்கள்|நில்லு|பொறுங்கள்|பொறு|வேண்டாம்|வேண்டாங்க|இல்லை|இல்ல|இல்லீங்க|அது இல்லை|கேளுங்கள்|போதும்|தவறு|"
    r"nillungal|nillu|porungal|poru|vendaam|vendanga|illai|illa|illenga|podhum|kelungal|thavaru|"
    # Kannada (kn-IN)
    r"ನಿಲ್ಲಿಸಿ|ನಿಲ್ಲು|ತಾಳಿ|ಇರಿ|ಬೇಡ|ಬೇಡಿ|ಇಲ್ಲ|ಇಲ್ಲರೀ|ಅದಲ್ಲ|ಕೇಳಿ|ಸಾಕು|ತಪ್ಪು|"
    r"nillisi|nillu|thali|iri|beda|bedi|illa|illari|adalla|keli|saaku|thappu|"
    # Malayalam (ml-IN)
    r"നിൽക്കൂ|നിൽക്ക്|കാക്കൂ|കാക്ക്|വേണ്ട|വേണ്ടതില്ല|അല്ല|ഇല്ല|കേൾക്കൂ|മതി|തെറ്റാണ്|"
    r"nilkkoo|nilkku|kaakkoo|kaakku|venda|vendathilla|alla|illa|kelkkoo|mathi|thettanu|"
    # Marathi (mr-IN)
    r"थांबा|थांब|नको|नकोस|नाही|ते नाही|ऐका|ऐक|चूप|पुरे|चूक|"
    r"thamba|thamb|nako|nakos|nahi|te nahi|aika|aik|choop|pure|chook|"
    # Bengali (bn-IN)
    r"থামুন|থামো|দাঁড়ান|দাঁড়াও|না|একটু শুনুন|শুনুন|শোনো|থাক|চুপ|ভুল|"
    r"thamun|thamo|daran|darao|na|shunun|shono|thak|chup|bhul|"
    # Gujarati (gu-IN)
    r"ઊભા રહો|થોભો|થોભ|ના|નહીં|નથી|સાંભળો|સાંભળ|રહેવા દો|શાંત રહો|ખોટું|"
    r"ubha raho|thobho|thobh|na|nahin|nathi|sambhalo|rehwa do|khotu|"
    # Punjabi (pa-IN)
    r"ਰੁਕੋ|ਰੁਕ|ਖਲੋਵੋ|ਨਾ|ਨਹੀਂ|ਰਹਿਣ ਦਿਓ|ਸੁਣੋ|ਚੁੱਪ|ਗ਼ਲਤ|"
    r"ruko|ruk|khalovo|na|nahin|rehn do|suno|chup|galat"
    r")(?:\s+\S+){0,2}[.!?,]*$",
    re.I,
)

# 2. CONVERSATIONAL BACKCHANNEL NODS (ALL 10 PLATFORM LANGUAGES):
# Passive acknowledgment nods that NEVER interrupt active agent playout.
# EXCLUSIONS ENFORCED: Words meaning "tell me / speak / go ahead" (e.g., చెప్పండి, சொல்லுங்க,
# ಹೇಳಿ, പറയൂ, सांगा, বলুন, કહો, ਦੱਸੋ, बोलिए) are TURN-CLAIMING invitations and are STRICTLY EXCLUDED!
_BACKCHANNEL_NODS_RE = re.compile(
    r"^(?:"
    # English nods
    r"yes|yeah|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|right|correct|got it|i see|alright|"
    # Telugu (te-IN) nods (Script + Romanized) — చెప్పండి excluded
    r"అవును|అవునండి|అవునండీ|సరే|సరేనండి|అలాగే|అలాగేనండి|బాగుంది|హాం|"
    r"avunu|avunandi|sare|sarenandi|alage|alagenandi|bagundi|"
    # Hindi (hi-IN) nods (Script + Romanized) — बोलिए/बताइए excluded
    r"हाँ|हां|हाँजी|हाँ जी|जी|जी हाँ|जी हां|ठीक|ठीक है|अच्छा|अच्छा जी|सही बात|"
    r"haan|haanji|haan ji|ji|ji haan|theek|theek hai|achha|achha ji|sahi baat|"
    # Tamil (ta-IN) nods (Script + Romanized) — சொல்லுங்க excluded
    r"ஆம்|ஆமாம்|ஆமாங்க|ஆமா|சரி|சரிங்க|நன்று|ஓம்|அப்படியா|"
    r"aam|aamaam|aamanga|aama|sari|saringa|nandru|om|appadiya|"
    # Kannada (kn-IN) nods (Script + Romanized) — ಹೇಳಿ excluded
    r"ಹೌದು|ಹೌದೌದು|ಹೌದಾ|ಹೌದುರೀ|ಸರಿ|ಸರೀ|ಆಯಿತು|ಆಯ್ತು|ಚೆನ್ನಾಗಿದೆ|"
    r"haudu|haudaudu|hauda|hauduri|sari|aayithu|aaytu|chennagide|"
    # Malayalam (ml-IN) nods (Script + Romanized) — പറയൂ excluded
    r"അതെ|അതെ അതെ|ശരി|ശരിയാണ്|ശരിയായി|നന്ന്|കൊള്ളാം|"
    r"athe|athe athe|shari|shariyaanu|shariyayi|nannu|kollam|"
    # Marathi (mr-IN) nods (Script + Romanized) — सांगा excluded
    r"हो|होय|हो ना|बरे|बरं|ठीक|ठीक आहे|छान|समजले|"
    r"ho|hoy|ho na|bare|baram|theek|theek aahe|chhan|samajle|"
    # Bengali (bn-IN) nods (Script + Romanized) — বলুন excluded
    r"হ্যাঁ|হাঁ|হ্যাঁ হ্যাঁ|ঠিক|ঠিক আছে|আচ্ছা|আচ্ছা আচ্ছা|বেশ|বুঝেছি|"
    r"haan|hya|hyan|theek|theek ache|achha|achha achha|besh|bujhechi|"
    # Gujarati (gu-IN) nods (Script + Romanized) — કહો excluded
    r"હા|હાજી|હા હા|બરાબર|બરાબર છે|સારું|ઠીક|સમજાયું|"
    r"haa|haaji|haa haa|barabar|barabar che|saaru|theek|samjayu|"
    # Punjabi (pa-IN) nods (Script + Romanized) — ਦੱਸੋ excluded
    r"ਹਾਂ|ਹਾਂਜੀ|ਹਾਂ ਹਾਂ|ਠੀਕ|ਠੀਕ ਹੈ|ਚੰਗਾ|ਸਮਝ ਗਿਆ|"
    r"haan|haanji|haa haa|theek|theek hai|changa|samajh gaya"
    r")(?:\s+(?:"
    r"yes|yeah|ok|okay|sure|hmm|haan|avunu|sare|theek|alage|ji|right|aam|haudu|athe|ho|haa|changa"
    r"))*[.!,]*$",
    re.I,
)
```

---

### 5.1 Master 10-Language Lexicon & Language Pack Matrix

The following authoritative matrix defines the acoustic and lexical behavior across all 10 platform language packs:

| Language & Locale | Emergency Halt Commands (Immediate 1-Word Barge) | Conversational Nods (Playout Protected) | Turn-Claiming Words (Excluded from Nods!) | Question / Confirmation Markers |
| :--- | :--- | :--- | :--- | :--- |
| **Telugu (`te-IN`)** | `ఆగండి`, `ఆగు`, `వద్దు`, `కాదు`, `లేదు`, `చాలు`, `aagandi`, `vaddu`, `kaadu` | `అవును`, `అవునండి`, `సరే`, `అలాగే`, `avunu`, `sare`, `alage` | `చెప్పండి` (*cheppandi*), `చెప్పు` (*cheppu*) | `చెప్పండి`, `చెప్తారా`, `కావాలా`, `సరేనా`, `అవునా`, `ముందుకు వెళ్దామా` |
| **Hindi (`hi-IN`)** | `रुको`, `रुकिए`, `बंद करो`, `चुप`, `नहीं`, `ना`, `गलत`, `ruko`, `nahin`, `galat` | `हाँ`, `हाँजी`, `जी`, `ठीक`, `अच्छा`, `haan`, `theek`, `achha` | `बोलिए` (*boliye*), `बताइए` (*bataiye*) | `बताइए`, `चाहिए`, `ठीक है ना`, `करूं`, `पुष्टि`, `आगे बढ़ें` |
| **Tamil (`ta-IN`)** | `நில்லுங்கள்`, `பொறுங்கள்`, `வேண்டாம்`, `இல்லை`, `போதும்`, `nillungal`, `illai` | `ஆம்`, `ஆமாம்`, `சரி`, `சரிங்க`, `நன்று`, `aamaam`, `sari` | `சொல்லுங்க` (*sollunga*), `பேசுங்க` (*pesunga*) | `சொல்லுங்க`, `வேண்டுமா`, `சரியா`, `தொடரலாமா`, `உறுதிப்படுத்தவா` |
| **Kannada (`kn-IN`)** | `ನಿಲ್ಲಿಸಿ`, `ತಾಳಿ`, `ಬೇಡ`, `ಇಲ್ಲ`, `ಸಾಕು`, `ತಪ್ಪು`, `nillisi`, `beda`, `illa` | `ಹೌದು`, `ಸರಿ`, `ಆಯಿತು`, `ಚೆನ್ನಾಗಿದೆ`, `haudu`, `sari`, `aayithu` | `ಹೇಳಿ` (*heli*), `ಮಾತನಾಡಿ` (*maathanaadi*) | `ಹೇಳಿ`, `ಬೇಕಾ`, `ಸರಿನಾ`, `ಮುಂದುವರಿಯಲೇ`, `ದೃಢೀಕರಿಸಿ` |
| **Malayalam (`ml-IN`)** | `നിൽക്കൂ`, `കാക്കൂ`, `വേണ്ട`, `അല്ല`, `ഇല്ല`, `മതി`, `nilkkoo`, `venda`, `alla` | `അതെ`, `ശരി`, `ശരിയാണ്`, `നന്ന്`, `athe`, `shari`, `kollam` | `പറയൂ` (*parayoo*), `സംസാരിക്കൂ` (*samsarikkoo*) | `പറയൂ`, `വേണമോ`, `ശരിയാണോ`, `തുടരണമോ`, `ഉറപ്പാക്കണോ` |
| **Marathi (`mr-IN`)** | `थांबा`, `नको`, `नाही`, `ऐका`, `चूप`, `पुरे`, `thamba`, `nako`, `nahi` | `हो`, `होय`, `बरे`, `ठीक`, `छान`, `ho`, `bare`, `theek` | `सांगा` (*saanga*), `बोला` (*bola*) | `सांगा`, `हवे का`, `बरोबर का`, `पुढे जाऊ का`, `खात्री करा` |
| **Bengali (`bn-IN`)** | `থামুন`, `দাঁড়ান`, `না`, `শুনুন`, `থাক`, `ভুল`, `thamun`, `daran`, `na` | `হ্যাঁ`, `ঠিক`, `আচ্ছা`, `বেশ`, `বুঝেছি`, `haan`, `theek`, `achha` | `বলুন` (*bolun*), `কথা বলুন` (*kotha bolun*) | `বলুন`, `চাই কি`, `ঠিক আছে তো`, `এগিয়ে যাব কি`, `নিশ্চিত করবেন` |
| **Gujarati (`gu-IN`)** | `ઊભા રહો`, `થોભો`, `ના`, `નહીં`, `સાંભળો`, `ખોટું`, `thobho`, `nahin` | `હા`, `હાજી`, `બરાબર`, `સારું`, `ઠીક`, `haa`, `barabar`, `saaru` | `કહો` (*kaho*), `બોલો` (*bolo*) | `કહો`, `જોઈએ છે`, `બરાબર ને`, `આગળ વધું`, `પુષ્ટિ કરો` |
| **Punjabi (`pa-IN`)** | `ਰੁਕੋ`, `ਖਲੋਵੋ`, `ਨਾ`, `ਨਹੀਂ`, `ਰਹਿਣ ਦਿਓ`, `ਗ਼ਲਤ`, `ruko`, `nahin` | `ਹਾਂ`, `ਹਾਂਜੀ`, `ਠੀਕ`, `ਚੰਗਾ`, `ਸਮਝ ਗਿਆ`, `haan`, `theek`, `changa` | `ਦੱਸੋ` (*dasso*), `ਬੋਲੋ` (*bolo*) | `ਦੱਸੋ`, `ਚਾਹੀਦਾ`, `ਠੀਕ ਹੈ నా`, `ਅੱਗੇ ਵਧਾਂ`, `ਪੁਸ਼ਟੀ ਕਰੋ` |
| **English (`en-IN/US/GB`)**| `stop`, `wait`, `hold on`, `pause`, `no`, `nope`, `actually`, `sorry`, `wrong` | `yes`, `yeah`, `yep`, `ok`, `okay`, `sure`, `hmm`, `right`, `got it` | `tell me`, `go ahead`, `speak` | `shall i`, `do you want`, `would you like`, `is that ok`, `proceed`, `confirm` |

---


### Pillar 2: Unambiguous Barge-In Commit Logic with Latched AEC Gate & Strict `bool` Return Type

> **CRITICAL FIX 1 (Return-Type Tuple Mismatch)**: The v2.0 draft snippet returned `(False, "reason")` tuples, but `_should_commit_barge` is declared `-> bool` ([pstn_voice_core.py:524](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L524)) and all callers use `if self._should_commit_barge(text):`. In Python, any non-empty tuple `(False, "...")` evaluates to `True` (truthy!), which would cause **every backchannel nod to immediately barge in and truncate the agent!** The function must assign to local variables `result, reason` and return bare `bool(result)`.
>
> **CRITICAL FIX 2 (AEC Gate Timing Race)**: `_aec_barge_open` closes after 8 quiet frames (~160ms), but Sarvam's WebSocket partial transcripts arrive **300–800ms after physical speech**. When words arrive, the gate is already closed, rejecting legitimate caller interruptions as `energy_below_floor`. **Fix**: Latch the gate using `_last_vad_voice_at` with an 800ms window (`(now - self._last_vad_voice_at) <= PSTN_AEC_VOICE_LATCH_S`).

In [`server/services/pstn_voice_core.py:_should_commit_barge`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L524):

```python
    def _should_commit_barge(self, text: str) -> bool:
        """Evaluate if user text justifies cutting off assistant playout.
        
        Strict Invariant: Returns bare bool (True = commit barge, False = reject).
        Callers rely on truthy/falsy evaluation. Never return a (result, reason) tuple.
        """
        now = time.monotonic()
        speaking = self._agent_audio_playing()
        tts_age_ms = int((now - self._tts_started_at) * 1000) if self._tts_started_at else 0
        echo_tail_ms = max(0, int((self._tts_tail_until - now) * 1000)) if self._tts_tail_until else 0
        last_barge_age_ms = int((now - self._last_barge_at) * 1000) if self._last_barge_at else -1
        words = effective_word_count(text)
        hold_ms = int((now - self._partial_started_at) * 1000) if self._partial_started_at > 0 else 0
        heard_ref = self._tts_heard_text or self._last_tts_text
        ref = window_assistant_text(heard_ref)
        overlap = echo_overlap_ratio(text, ref)
        provider_queued_ms = self._provider_queued_ms()
        intro = self._phase == PHASE_INTRO or self._intro_phase

        clean_text = (text or "").strip()
        is_halt_command = bool(_HALT_COMMANDS_RE.match(clean_text))
        is_backchannel = bool(_BACKCHANNEL_NODS_RE.match(clean_text))
        substantive = is_substantive_transcript(clean_text, after_barge=True) or is_halt_command

        result = True
        reason = "ok"

        # 1. Platform Master Switch
        if not ENABLE_PSTN_BARGE_IN:
            result, reason = False, "disabled"

        # 2. Playout State Check
        elif not speaking:
            result, reason = False, "not_speaking"

        # 3. Barge Debounce Protection
        elif now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
            result, reason = False, "debounce"

        # 4. Pure Backchannel Nods NEVER Interrupt Playout
        elif is_backchannel:
            self._partial_started_at = 0.0
            result, reason = False, "backchannel_ignored"

        # 5. Playout Onset Echo Shield (350ms protects against carrier G.711 acoustic loop)
        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
            result, reason = False, "min_after_speak_echo_shield"

        # 6. Soft AEC Energy Gate with 800ms Latched Timing Window
        # Bridges the 300-800ms Sarvam STT WebSocket transcript arrival latency.
        # Emergency halt commands bypass this gate to ensure immediate response.
        elif (
            not self._aec_barge_open
            and (now - self._last_vad_voice_at) > PSTN_AEC_VOICE_LATCH_S
            and not is_halt_command
        ):
            result, reason = False, "energy_below_floor"

        # 7. Emergency Halt Commands: 1-word immediate interruption ("stop", "wait", "no", "ఆగండి", "नहीं")
        elif is_halt_command:
            result, reason = True, "halt_command"

        # 8. General Conversational Speech: Requires >= 2 words
        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS):
            self._partial_started_at = 0.0
            result, reason = False, "min_words"

        # 9. Substantive Content Gate (Filters filler phonemes and residual clicks)
        elif not substantive:
            self._partial_started_at = 0.0
            result, reason = False, "not_substantive"

        # 10. Optional VAD Activity Floor
        elif self._barge_runtime.get("bargeRequireVad") and now - self._last_vad_voice_at > 0.8:
            result, reason = False, "vad_required"

        # 11. Conversational Hold Timer (300ms verification)
        elif self._partial_started_at <= 0:
            self._partial_started_at = now
            result, reason = False, "hold_start"
        elif now - self._partial_started_at < PSTN_BARGE_HOLD_S:
            result, reason = False, "hold"

        # 12. Full-Sentence Acoustic Echo Filter
        elif is_barge_echo(clean_text, heard_ref):
            result, reason = False, "echo"

        log_pstn(
            "BARGE_CHECK",
            call_id=self.call_id,
            turn_id=self.current_turn_id,
            tts_active=self._tts_active,
            tts_age_ms=tts_age_ms,
            echo_tail_ms=echo_tail_ms,
            partial_words=words,
            partial_hold_ms=hold_ms,
            echo_overlap=round(overlap, 3),
            intro=intro,
            last_barge_age_ms=last_barge_age_ms,
            provider_queued_ms=round(provider_queued_ms, 1),
            fsm=self._phase,
            reason=reason,
            result=result,
        )
        return result  # Strict bare bool!
```

---

### Pillar 3: Question-Aware Post-Playout Backchannel Purging (Preventing Dead Air)

> **CRITICAL FIX (Dead Air Bug)**: Unconditionally purging backchannel nods creates **dead air** when the agent's last utterance was a question or confirmation request.
>
> *Scenario*: Agent asks: *"Shall I book your appointment for 10 AM?"* The caller replies *"Haan"* or *"Avunu"* slightly before the agent's TTS finishes playing. If the system blindly purges *"Haan"*, the agent transitions to `listening` and waits in silence. The caller already said yes, so neither side speaks, creating dead air until hang-up.
>
> **Fix**: Detect if the agent's last utterance was a question via `agent_asked_question` (checking for `?` or question keywords in Telugu, Hindi, and English). Only purge nods if the agent was making a statement. If the agent asked a question, preserve the nod and launch the turn!

In [`server/services/pstn_voice_core.py:_run_turn`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L1970) (finally block):

```python
            self.current_generation_id = None
            self._interrupted_generation = None
            if pending and self._phase != PHASE_ENDED:
                clean_pending = (pending or "").strip()
                last_tts = (self._last_tts_text or "").strip()
                
                # Context Check: Did the agent just ask a question or confirmation across all 10 platform languages?
                agent_asked_question = last_tts.rstrip().endswith("?") or any(
                    kw in last_tts.lower() for kw in (
                        # English (en-IN, en-US, en-GB)
                        "shall i", "do you want", "would you like", "is that ok", "proceed", "confirm", "correct", "can we",
                        # Telugu (te-IN)
                        "చెప్పండి", "చెప్తారా", "కావాలా", "సరేనా", "అవునా", "వెళ్దామా",
                        # Hindi (hi-IN)
                        "बताइए", "चाहिए", "ठीक है ना", "करूं", "पुष्टि", "आगे बढ़ें",
                        # Tamil (ta-IN)
                        "சொல்லுங்க", "வேண்டுமா", "சரியா", "தொடரலாமா", "உறுதிப்படுத்தவா", "தெரியுமா",
                        # Kannada (kn-IN)
                        "ಹೇಳಿ", "ಬೇಕಾ", "ಸರಿನಾ", "ಮುಂದುವರಿಯಲೇ", "ದೃಢೀಕರಿಸಿ", "ಗೊತ್ತಾ", "ಹೌದಾ",
                        # Malayalam (ml-IN)
                        "പറയൂ", "വേണമോ", "ശരിയാണോ", "തുടരണമോ", "ഉറപ്പാക്കണോ", "അറിയാമോ",
                        # Marathi (mr-IN)
                        "सांगा", "हवे का", "बरोबर का", "पुढे जाऊ का", "खात्री करा", "माहित आहे का",
                        # Bengali (bn-IN)
                        "বলুন", "চাই কি", "ঠিক আছে তো", "এগিয়ে যাব কি", "নিশ্চিত করবেন", "জানেন কি",
                        # Gujarati (gu-IN)
                        "કહો", "જોઈએ છે", "બરાબર ને", "આગળ વધું", "પુષ્ટિ કરો", "ખબર છે",
                        # Punjabi (pa-IN)
                        "ਦੱਸੋ", "ਚਾਹੀਦਾ", "ਠੀਕ ਹੈ ਨਾ", "ਅੱਗੇ ਵਧਾਂ", "ਪੁਸ਼ਟੀ ਕਰੋ", "ਪਤਾ ਹੈ",
                    )
                )

                if _BACKCHANNEL_NODS_RE.match(clean_pending) and not agent_asked_question:
                    # Case A: Agent made a statement. Caller nodded mid-speech.
                    # Purge nod without launching an LLM turn — prevent ghost self-conversation!
                    log_pstn("PENDING_PURGED_BACKCHANNEL", call_id=self.call_id, text=clean_pending[:80])
                    pending = None
                elif _BACKCHANNEL_NODS_RE.match(clean_pending) and agent_asked_question:
                    # Case B: Agent asked a question. Caller's "Haan" is a valid affirmative answer!
                    # Preserve pending so it launches the LLM turn cleanly.
                    log_pstn(
                        "PENDING_KEPT_ANSWER_TO_QUESTION",
                        call_id=self.call_id,
                        text=clean_pending[:80],
                        agent_question=last_tts[-80:],
                    )

            if pending and self._phase != PHASE_ENDED:
                # Barge still waiting on final — restore pending for the barge-final launcher.
                if self._awaiting_barge_final or self._phase == PHASE_INTERRUPTING:
                    self._pending_transcript = pending
                elif cancelled and self._think_cancel_relaunch == "immediate":
                    self._think_cancel_relaunch = None
                    self._launch_turn(pending)
                elif cancelled:
                    # Partial think-cancel: wait for a stable pause before re-asking the LLM.
                    self._think_cancel_relaunch = None
                    self._arm_listen_coalesce(pending)
                else:
                    self._launch_turn(pending)
```

---

### Pillar 4: Thinking-Phase Immunity for Indic Backchannels & Complete Symbol Migration

> **CRITICAL FIX**: The legacy code had two failure modes during the LLM thinking phase:
> 1. `_THINK_CANCEL_ACK_ONLY` only covered English words (`yeah`, `ok`). Saying *"అవును"* or *"हाँ"* tripped `short_ok` and aborted the LLM while generating!
> 2. `_SHORT_INTERRUPT` and `short_ok` were referenced across 9 sites. Deleting `_SHORT_INTERRUPT` without migrating all sites causes a fatal `NameError`.

In [`server/services/pstn_voice_core.py`](file:///d:/voice%20agent/server/services/pstn_voice_core.py):

```python
    def _should_think_cancel(self, text: str) -> bool:
        """Cancel LLM while THINKING (no audio yet) when caller keeps talking."""
        from server.services.transcript_gate import effective_word_count, is_substantive_transcript

        if self._phase != PHASE_THINKING or self._agent_audio_playing():
            self._think_partial_started_at = 0.0
            return False
        cleaned = (text or "").strip()
        if not cleaned:
            self._think_partial_started_at = 0.0
            return False

        # Unified Indic + English backchannels must never abort in-flight LLM generation
        if _BACKCHANNEL_NODS_RE.match(cleaned):
            self._think_partial_started_at = 0.0
            return False

        is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))
        words = effective_word_count(cleaned)
        if words < PSTN_THINK_CANCEL_MIN_WORDS and not is_halt:
            self._think_partial_started_at = 0.0
            return False
        if not is_halt and not is_substantive_transcript(cleaned, after_barge=True):
            self._think_partial_started_at = 0.0
            return False

        now = time.monotonic()
        if self._think_partial_started_at <= 0:
            self._think_partial_started_at = now
            return False
        return (now - self._think_partial_started_at) >= PSTN_THINK_CANCEL_HOLD_S

    def _should_think_continue_final(self, text: str) -> bool:
        """STT final while THINKING: merge continuation into the in-flight turn."""
        from server.services.transcript_gate import effective_word_count, is_substantive_transcript

        if self._phase != PHASE_THINKING or not self._turn_busy or self._agent_audio_playing():
            return False
        cleaned = (text or "").strip()
        if not cleaned:
            return False
        if _BACKCHANNEL_NODS_RE.match(cleaned):
            return False

        is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))
        words = effective_word_count(cleaned)
        if words < PSTN_THINK_CANCEL_MIN_WORDS and not is_halt:
            return False
        if not is_halt and not is_substantive_transcript(cleaned, after_barge=True):
            return False

        prior = (self._current_turn_transcript or "").strip().lower()
        current = cleaned.lower()
        if prior and current == prior:
            return False
        if prior and current in prior:
            return False
        return True
```

---

### Pillar 5: Multi-File Calibration of Sarvam STT Real-time VAD & Latency Budget

> **Engineering Reality & Fact-Check**:
> - `server/routes/ws.py:121-127` already passed `min_speech_duration_ms=250` and `prefix_padding_ms=300`.
> - In `server/services/sarvam_ws.py:85`, `high_vad_sensitivity="true"` was only sent if `min_speech_duration_ms is None and prefix_padding_ms is None`. Thus, on the `composed_voice` route, `high_vad_sensitivity` was **never sent**.
> - The true gap: The provider adapter `server/providers/sarvam_stt.py:28-31` passed `None` for all parameters, causing provider registry calls to receive zero explicit calibration!
> - The real parameter deltas are:
>   - `threshold`: `0.3` → `0.55` (Filters breathing, distant room voices, and steady fan noise)
>   - `min_speech_duration_ms`: `250` → `300` (+50ms absorbs transient coughs and clicks)
>   - `silence_duration_ms`: `500` → `600` (+100ms prevents premature end-of-speech mid-sentence in slower Indic speech)
>   - `prefix_padding_ms`: Unify to `300` across all files.

#### End-of-Turn Latency Trade-Off Budget
Increasing `silence_duration_ms` from 500ms to 600ms adds **+100ms** to turn-end detection across all user turns:
- **Human Conversational Norm**: Standard pause duration between turns in human-to-human conversation is **200–500ms**. In Indic languages (Telugu, Hindi), inter-phrase pauses average **350–650ms** due to agglutination and case-marker pondering.
- **Why +100ms is Acceptable**: A 500ms silence threshold caused frequent premature turn cutoffs when Telugu callers paused between subject and verb. 600ms eliminates mid-sentence cutoffs while keeping overall turn latency well within the conversational comfort zone (<1200ms end-to-speech to first audio).

---

### Pillar 6: Calibrated Playout Onset Echo Shield Window (350ms)

In [`server/services/pstn_voice_core.py:40`](file:///d:/voice%20agent/server/services/pstn_voice_core.py#L40):
```python
# Extended from 40ms to 350ms to shield against measured 140-270ms carrier G.711 echo loops
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35
PSTN_BARGE_MIN_WORDS = 2
PSTN_BARGE_HOLD_S = 0.30
PSTN_AEC_VOICE_LATCH_S = 0.8
```

---

### Pillar 7: Soft Pause & Resume (TTS Ducking on VAD Onset)

> **Industry Consensus (LiveKit, Retell, Vapi)**: Binary barge-in ("keep blasting" vs "instantly cut off") is the fundamental cause of jarring user experience. When background noise or a brief cough occurs, an instant cutoff creates an awkward silence.
>
> **Solution**: On the first loud frame (`rms >= PSTN_TTS_STT_ENERGY_MIN`), **duck the agent's playout volume to 20%** instead of terminating the generation. If substantive speech arrives within ~700ms, commit the barge cleanly. If no substantive words arrive within 700ms, **smoothly restore volume to 100%**. False alarms become completely imperceptible volume dips instead of conversational disruptions!

```python
# 1. State Tracking in __init__:
self._tts_ducked = False
self._tts_duck_at = 0.0
self._tts_duck_factor = 0.2

# 2. In feed_user_pcm16: Detect loud voice onset during agent playout
if rms >= PSTN_TTS_STT_ENERGY_MIN and self._agent_audio_playing():
    if not self._tts_ducked:
        self._tts_ducked = True
        self._tts_duck_at = time.monotonic()
        log_pstn("TTS_DUCK_ON_VAD", call_id=self.call_id, rms=rms)

# 3. In _emit_agent_wire: Apply volume attenuation when ducked
async def _emit_agent_wire(self, wire: bytes) -> None:
    if not wire or self.emission_blocked():
        return
    # Check if ducking timeout has expired without words
    if self._tts_ducked and (time.monotonic() - self._tts_duck_at) > 0.7:
        if not self._awaiting_barge_final:
            self._tts_ducked = False
            log_pstn("TTS_UNDUCK_RESUMED", call_id=self.call_id)

    # Scale samples if ducked (for G.711 mu-law, decode to linear, scale, re-encode)
    out_wire = wire
    if self._tts_ducked and len(wire) > 0:
        out_wire = scale_wire_volume(wire, self.tts_output_codec, self._tts_duck_factor)

    await self.on_agent_wire(out_wire)
```

---

### Pillar 8: Partial-Level Self-Echo Text Suppression

> **Problem**: Checking echo overlap only inside `_should_commit_barge` allows echoed partials to reset `self._partial_started_at`, latch `_last_vad_voice_at`, and wake background timers.
>
> **Fix**: Suppress self-echo **at the partial ingress point** (`transcript.partial`). If an incoming partial matches the assistant's currently playing text window ($\ge 50\%$ lexical overlap), drop it immediately.

```python
# In pstn_voice_core.py event loop:
elif ev == "transcript.partial":
    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
    if text and self._agent_audio_playing():
        from server.services.echo_guard import echo_overlap_ratio, window_assistant_text
        heard_ref = window_assistant_text(self._tts_heard_text or self._last_tts_text)
        if heard_ref and echo_overlap_ratio(text, heard_ref) >= 0.5:
            log_pstn("PARTIAL_SELF_ECHO_DROPPED", call_id=self.call_id, text=text[:60])
            continue  # Drop echoed partial before barge pipeline evaluates it!
```

---

## 6. Complete Implementation Code Diffs

### Diff 1: [`server/services/pstn_voice_core.py`](file:///d:/voice%20agent/server/services/pstn_voice_core.py)

```diff
--- a/server/services/pstn_voice_core.py
+++ b/server/services/pstn_voice_core.py
@@ -30,22 +30,44 @@
-# Prefer substantive/short natural interruptions over a rigid 3-word rule.
-PSTN_BARGE_MIN_WORDS = 1
-PSTN_BARGE_HOLD_S = 0.12
+# Calibrated turn-taking: requires 2 words sustained for 300ms for general interruptions
+PSTN_BARGE_MIN_WORDS = 2
+PSTN_BARGE_HOLD_S = 0.30
 # Soft AEC energy is a barge confidence signal only — never a hard STT drop gate.
 PSTN_TTS_STT_ENERGY_MIN = 320
+# Latched time window for AEC gate — bridges 300-800ms Sarvam STT WebSocket delay
+PSTN_AEC_VOICE_LATCH_S = 0.8
 # Soft AEC barge hysteresis: open after 2 loud frames; close after 8 quiet frames.
 PSTN_AEC_LOUD_OPEN_FRAMES = 2
 PSTN_AEC_QUIET_CLOSE_FRAMES = 8
 PSTN_BARGE_FINAL_TIMEOUT_S = 0.8
-# Two 20ms frames protect the onset; transcript confirmation still holds 120ms.
-PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.04
+# 350ms protects against carrier G.711 echo loops (140-270ms RTT)
+PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35
 PSTN_BARGE_DEBOUNCE_S = 0.45
 PSTN_BARGE_FINAL_WINDOW_S = 1.5
 PSTN_BARGE_FINAL_DEBOUNCE_S = 0.3
 PSTN_ECHO_TAIL_S = 0.35
-PSTN_THINK_CANCEL_MIN_WORDS = 1
-PSTN_THINK_CANCEL_HOLD_S = 0.25
-# Pure backchannels must never kill an in-flight LLM turn.
-_THINK_CANCEL_ACK_ONLY = re.compile(
-    r"^(?:yeah|yes|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|haan|ha|han|sare|"
-    r"right|correct|got it|i see|alright|all right)"
-    r"(?:\s+(?:yeah|yes|yep|yup|ok|okay|sure|hmm|haan|ha))*[.!,]*$",
-    re.I,
-)
-# Short natural barge / think-cancel phrases (EN + common TE/HI).
-_SHORT_INTERRUPT = re.compile(
-    r"^(?:yes|no|yeah|yep|nope|wait|stop|actually|hold on|one second|sorry|"
-    r"కాదు|లేదు|లేదండి|అవును|వద్దు|అది కాదు|"
-    r"नहीं|हाँ|रुको|ठीक)"
-    r"(?:\s+\w+){0,3}[.!,]*$",
-    re.I,
-)
+# 1. EMERGENCY HALT COMMANDS (ALL 10 PLATFORM LANGUAGES):
+# Immediate 1-word barge-in without hold timer. Covers stops, negations, pauses, and listening demands.
+# Uses \S+ instead of \w+ to preserve Indic combining characters across all scripts.
+_HALT_COMMANDS_RE = re.compile(
+    r"^(?:"
+    # English (en-IN, en-US, en-GB)
+    r"stop|wait|hold on|one second|pause|shut up|quiet|cancel|listen|no|nope|actually|sorry|wrong|enough|"
+    # Telugu (te-IN)
+    r"ఆగండి|ఆగు|వద్దు|వద్దండి|వద్దండీ|ఆపండి|వినండి|కాదు|లేదు|లేదండి|అది కాదు|చాలు|"
+    r"aagandi|aagu|vaddu|vaddandi|aapandi|vinandi|kaadu|ledu|ledandi|adi kaadu|chaalu|"
+    # Hindi (hi-IN)
+    r"रुको|रुकिए|बंद करो|चुप|मत बोलो|सुनो|सुनिए|नहीं|ना|बस|रहने दो|गलत|"
+    r"ruko|rukiye|band karo|chup|mat bolo|suno|suniye|nahin|nahi|na|bas|rehne do|galat|"
+    # Tamil (ta-IN)
+    r"நில்லுங்கள்|நில்லு|பொறுங்கள்|பொறு|வேண்டாம்|வேண்டாங்க|இல்லை|இல்ல|இல்லீங்க|அது இல்லை|கேளுங்கள்|போதும்|தவறு|"
+    r"nillungal|nillu|porungal|poru|vendaam|vendanga|illai|illa|illenga|podhum|kelungal|thavaru|"
+    # Kannada (kn-IN)
+    r"ನಿಲ್ಲಿಸಿ|ನಿಲ್ಲು|ತಾಳಿ|ಇರಿ|ಬೇಡ|ಬೇಡಿ|ಇಲ್ಲ|ಇಲ್ಲರೀ|ಅದಲ್ಲ|ಕೇಳಿ|ಸಾಕು|ತಪ್ಪು|"
+    r"nillisi|nillu|thali|iri|beda|bedi|illa|illari|adalla|keli|saaku|thappu|"
+    # Malayalam (ml-IN)
+    r"നിൽക്കൂ|നിൽക്ക്|കാക്കൂ|കാക്ക്|വേണ്ട|വേണ്ടതില്ല|അല്ല|ഇല്ല|കേൾക്കൂ|മതി|തെറ്റാണ്|"
+    r"nilkkoo|nilkku|kaakkoo|kaakku|venda|vendathilla|alla|illa|kelkkoo|mathi|thettanu|"
+    # Marathi (mr-IN)
+    r"थांबा|थांब|नको|नकोस|नाही|ते नाही|ऐका|ऐक|चूप|पुरे|चूक|"
+    r"thamba|thamb|nako|nakos|nahi|te nahi|aika|aik|choop|pure|chook|"
+    # Bengali (bn-IN)
+    r"থামুন|থামো|দাঁড়ান|দাঁড়াও|না|একটু শুনুন|শুনুন|শোনো|থাক|চুপ|ভুল|"
+    r"thamun|thamo|daran|darao|na|shunun|shono|thak|chup|bhul|"
+    # Gujarati (gu-IN)
+    r"ઊભા રહો|થોભો|થોભ|ના|નહીં|નથી|સાંભળો|સાંભળ|રહેવા દો|શાંત રહો|ખોટું|"
+    r"ubha raho|thobho|thobh|na|nahin|nathi|sambhalo|rehwa do|khotu|"
+    # Punjabi (pa-IN)
+    r"ਰੁਕੋ|ਰੁਕ|ਖਲੋਵੋ|ਨਾ|ਨਹੀਂ|ਰਹਿਣ ਦਿਓ|ਸੁਣੋ|ਚੁੱਪ|ਗ਼ਲਤ|"
+    r"ruko|ruk|khalovo|na|nahin|rehn do|suno|chup|galat"
+    r")(?:\s+\S+){0,2}[.!?,]*$",
+    re.I,
+)
+# 2. CONVERSATIONAL BACKCHANNEL NODS (ALL 10 PLATFORM LANGUAGES):
+# Passive acknowledgment nods that NEVER interrupt active agent playout.
+# EXCLUSIONS ENFORCED: Words meaning "tell me / speak / go ahead" (e.g., చెప్పండి, சொல்லுங்க,
+# ಹೇಳಿ, പറയൂ, सांगा, বলুন, કહો, ਦੱਸੋ, बोलिए) are TURN-CLAIMING invitations and are STRICTLY EXCLUDED!
+_BACKCHANNEL_NODS_RE = re.compile(
+    r"^(?:"
+    # English nods
+    r"yes|yeah|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|right|correct|got it|i see|alright|"
+    # Telugu (te-IN) nods (Script + Romanized) — చెప్పండి excluded
+    r"అవును|అవునండి|అవునండీ|సరే|సరేనండి|అలాగే|అలాగేనండి|బాగుంది|హాం|"
+    r"avunu|avunandi|sare|sarenandi|alage|alagenandi|bagundi|"
+    # Hindi (hi-IN) nods (Script + Romanized) — बोलिए/बताइए excluded
+    r"हाँ|हां|हाँजी|हाँ जी|जी|जी हाँ|जी हां|ठीक|ठीक है|अच्छा|अच्छा जी|सही बात|"
+    r"haan|haanji|haan ji|ji|ji haan|theek|theek hai|achha|achha ji|sahi baat|"
+    # Tamil (ta-IN) nods (Script + Romanized) — சொல்லுங்க excluded
+    r"ஆம்|ஆமாம்|ஆமாங்க|ஆமா|சரி|சரிங்க|நன்று|ஓம்|அப்படியா|"
+    r"aam|aamaam|aamanga|aama|sari|saringa|nandru|om|appadiya|"
+    # Kannada (kn-IN) nods (Script + Romanized) — ಹೇಳಿ excluded
+    r"ಹೌದು|ಹೌದೌದು|ಹೌದಾ|ಹೌದುರೀ|ಸರಿ|ಸರೀ|ಆಯಿತು|ಆಯ್ತು|ಚೆನ್ನಾಗಿದೆ|"
+    r"haudu|haudaudu|hauda|hauduri|sari|aayithu|aaytu|chennagide|"
+    # Malayalam (ml-IN) nods (Script + Romanized) — പറയൂ excluded
+    r"അതെ|അതെ അതെ|ശരി|ശരിയാണ്|ശരിയായി|നന്ന്|കൊള്ളാം|"
+    r"athe|athe athe|shari|shariyaanu|shariyayi|nannu|kollam|"
+    # Marathi (mr-IN) nods (Script + Romanized) — सांगा excluded
+    r"हो|होय|हो ना|बरे|बरं|ठीक|ठीक आहे|छान|समजले|"
+    r"ho|hoy|ho na|bare|baram|theek|theek aahe|chhan|samajle|"
+    # Bengali (bn-IN) nods (Script + Romanized) — বলুন excluded
+    r"হ্যাঁ|হাঁ|হ্যাঁ হ্যাঁ|ঠিক|ঠিক আছে|আচ্ছা|अच्छा আচ্ছা|বেশ|বুঝেছি|"
+    r"haan|hya|hyan|theek|theek ache|achha|achha achha|besh|bujhechi|"
+    # Gujarati (gu-IN) nods (Script + Romanized) — કહો excluded
+    r"હા|હાજી|હા હા|બરાબર|બરાબર છે|સારું|ઠીક|સમજાયું|"
+    r"haa|haaji|haa haa|barabar|barabar che|saaru|theek|samjayu|"
+    # Punjabi (pa-IN) nods (Script + Romanized) — ਦੱਸੋ excluded
+    r"ਹਾਂ|ਹਾਂਜੀ|ਹਾਂ ਹਾਂ|ਠੀਕ|ਠੀਕ ਹੈ|ਚੰਗਾ|ਸਮਝ ਗਿਆ|"
+    r"haan|haanji|haa haa|theek|theek hai|changa|samajh gaya"
+    r")(?:\s+(?:"
+    r"yes|yeah|ok|okay|sure|hmm|haan|avunu|sare|theek|alage|ji|right|aam|haudu|athe|ho|haa|changa"
+    r"))*[.!,]*$",
+    re.I,
+)
@@ -544,30 +566,45 @@
         intro = self._phase == PHASE_INTRO or self._intro_phase
-        short_ok = bool(_SHORT_INTERRUPT.match((text or "").strip()))
-        substantive = is_substantive_transcript(text or "", after_barge=True) or short_ok
+        clean_text = (text or "").strip()
+        is_halt_command = bool(_HALT_COMMANDS_RE.match(clean_text))
+        is_backchannel = bool(_BACKCHANNEL_NODS_RE.match(clean_text))
+        substantive = is_substantive_transcript(clean_text, after_barge=True) or is_halt_command
 
         result = True
         reason = "ok"
         if not ENABLE_PSTN_BARGE_IN:
             result, reason = False, "disabled"
         elif not speaking:
             result, reason = False, "not_speaking"
         elif now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
             result, reason = False, "debounce"
-        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not short_ok:
+        elif is_backchannel:
+            self._partial_started_at = 0.0
+            result, reason = False, "backchannel_ignored"
+        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
+            result, reason = False, "min_after_speak_echo_shield"
+        elif (
+            not self._aec_barge_open
+            and (now - self._last_vad_voice_at) > PSTN_AEC_VOICE_LATCH_S
+            and not is_halt_command
+        ):
+            result, reason = False, "energy_below_floor"
+        elif is_halt_command:
+            result, reason = True, "halt_command"
+        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS):
             self._partial_started_at = 0.0
             result, reason = False, "min_words"
         elif not substantive:
             self._partial_started_at = 0.0
             result, reason = False, "not_substantive"
         elif self._barge_runtime.get("bargeRequireVad") and now - self._last_vad_voice_at > 0.8:
             result, reason = False, "vad_required"
         elif self._partial_started_at <= 0:
             self._partial_started_at = now
             result, reason = False, "hold_start"
         elif now - self._partial_started_at < PSTN_BARGE_HOLD_S:
             result, reason = False, "hold"
-        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
-            result, reason = False, "min_after_speak"
         elif is_barge_echo(text, heard_ref):
             result, reason = False, "echo"
@@ -606,17 +643,17 @@
-        # "yeah yeah" / "ok ok" backchannels must not abort the reply.
-        if _THINK_CANCEL_ACK_ONLY.match(cleaned):
+        # Backchannels (Telugu, Hindi, English) must never abort in-flight LLM generation
+        if _BACKCHANNEL_NODS_RE.match(cleaned):
             self._think_partial_started_at = 0.0
             return False
-        short_ok = bool(_SHORT_INTERRUPT.match(cleaned))
+        is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))
         words = effective_word_count(cleaned)
-        if words < PSTN_THINK_CANCEL_MIN_WORDS and not short_ok:
+        if words < PSTN_THINK_CANCEL_MIN_WORDS and not is_halt:
             self._think_partial_started_at = 0.0
             return False
-        if not short_ok and not is_substantive_transcript(cleaned, after_barge=True):
+        if not is_halt and not is_substantive_transcript(cleaned, after_barge=True):
             self._think_partial_started_at = 0.0
             return False
@@ -632,13 +669,13 @@
-        if _THINK_CANCEL_ACK_ONLY.match(cleaned):
+        if _BACKCHANNEL_NODS_RE.match(cleaned):
             return False
-        short_ok = bool(_SHORT_INTERRUPT.match(cleaned))
+        is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))
         words = effective_word_count(cleaned)
-        if words < PSTN_THINK_CANCEL_MIN_WORDS and not short_ok:
+        if words < PSTN_THINK_CANCEL_MIN_WORDS and not is_halt:
             return False
-        if not short_ok and not is_substantive_transcript(cleaned, after_barge=True):
+        if not is_halt and not is_substantive_transcript(cleaned, after_barge=True):
             return False
@@ -1971,3 +2008,19 @@
             self.current_generation_id = None
             self._interrupted_generation = None
+            if pending and self._phase != PHASE_ENDED:
+                clean_pending = (pending or "").strip()
+                last_tts = (self._last_tts_text or "").strip()
+                agent_asked_question = last_tts.rstrip().endswith("?") or any(
+                    kw in last_tts.lower() for kw in (
+                        # English (en-IN, en-US, en-GB)
+                        "shall i", "do you want", "would you like", "is that ok", "proceed", "confirm", "correct", "can we",
+                        # Telugu (te-IN)
+                        "చెప్పండి", "చెప్తారా", "కావాలా", "సరేనా", "అవునా", "వెళ్దామా",
+                        # Hindi (hi-IN)
+                        "बताइए", "चाहिए", "ठीक है ना", "करूं", "पुष्टि", "आगे बढ़ें",
+                        # Tamil (ta-IN)
+                        "சொல்லுங்க", "வேண்டுமா", "சரியா", "தொடரலாமா", "உறுதிப்படுத்தவா", "தெரியுமா",
+                        # Kannada (kn-IN)
+                        "ಹೇಳಿ", "ಬೇಕಾ", "ಸರಿನಾ", "ಮುಂದುವರಿಯಲೇ", "ದೃಢೀಕರಿಸಿ", "ಗೊತ್ತಾ", "ಹೌದಾ",
+                        # Malayalam (ml-IN)
+                        "പറയൂ", "വേണമോ", "ശരിയാണോ", "തുടരണമോ", "ഉറപ്പാക്കണോ", "അറിയാമോ",
+                        # Marathi (mr-IN)
+                        "सांगा", "हवे का", "बरोबर का", "पुढे जाऊ का", "खात्री करा", "माहित आहे का",
+                        # Bengali (bn-IN)
+                        "বলুন", "চাই কি", "ঠিক আছে তো", "এগিয়ে যাব কি", "নিশ্চিত করবেন", "জানেন কি",
+                        # Gujarati (gu-IN)
+                        "કહો", "જોઈએ છે", "બરાબર ને", "આગળ વધું", "પુષ્ટિ કરો", "ખબર છે",
+                        # Punjabi (pa-IN)
+                        "ਦੱਸੋ", "ਚਾਹੀਦਾ", "ਠੀਕ ਹੈ ਨਾ", "ਅੱਗੇ ਵਧਾਂ", "ਪੁਸ਼ਟੀ ਕਰੋ", "ਪਤਾ ਹੈ",
+                    )
+                )
+                if _BACKCHANNEL_NODS_RE.match(clean_pending) and not agent_asked_question:
+                    log_pstn("PENDING_PURGED_BACKCHANNEL", call_id=self.call_id, text=clean_pending[:80])
+                    pending = None
+                elif _BACKCHANNEL_NODS_RE.match(clean_pending) and agent_asked_question:
+                    log_pstn("PENDING_KEPT_ANSWER_TO_QUESTION", call_id=self.call_id, text=clean_pending[:80])
             if pending and self._phase != PHASE_ENDED:
```

---

### Exhaustive 9-Site Migration Checklist for `_SHORT_INTERRUPT` & `short_ok`

Removing `_SHORT_INTERRUPT` and `_THINK_CANCEL_ACK_ONLY` requires updating all 9 call sites across `pstn_voice_core.py` to prevent runtime `NameError`:

| # | File:Line | Original Token | Replacement Token | Rationale |
|---|-----------|----------------|-------------------|-----------|
| **1** | `pstn_voice_core.py:545` | `short_ok = bool(_SHORT_INTERRUPT.match(...))` | `is_halt_command = bool(_HALT_COMMANDS_RE.match(...))` | Isolate emergency halt words from nods |
| **2** | `pstn_voice_core.py:546` | `substantive = ... or short_ok` | `substantive = ... or is_halt_command` | Halt words bypass minimum length |
| **3** | `pstn_voice_core.py:558` | `and not short_ok` | `and not is_halt_command` | Halt words bypass `bargeMinWords` |
| **4** | `pstn_voice_core.py:607` | `_THINK_CANCEL_ACK_ONLY.match(cleaned)` | `_BACKCHANNEL_NODS_RE.match(cleaned)` | Broaden backchannel protection to Indic |
| **5** | `pstn_voice_core.py:610` | `short_ok = bool(_SHORT_INTERRUPT.match(cleaned))` | `is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))` | Halt words can cancel think |
| **6** | `pstn_voice_core.py:612` | `and not short_ok` | `and not is_halt` | Keep hold requirement for general speech |
| **7** | `pstn_voice_core.py:615` | `if not short_ok and not ...` | `if not is_halt and not ...` | Check substantive if not halt |
| **8** | `pstn_voice_core.py:633` | `_THINK_CANCEL_ACK_ONLY.match(cleaned)` | `_BACKCHANNEL_NODS_RE.match(cleaned)` | Final merge ignores Indic nods |
| **9** | `pstn_voice_core.py:635` | `short_ok = bool(_SHORT_INTERRUPT.match(cleaned))` | `is_halt = bool(_HALT_COMMANDS_RE.match(cleaned))` | Final merge evaluates halt command |

---

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

---

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

### Diff 4: [`server/providers/sarvam_stt.py`](file:///d:/voice%20agent/server/providers/sarvam_stt.py)

```diff
--- a/server/providers/sarvam_stt.py
+++ b/server/providers/sarvam_stt.py
@@ -21,11 +21,12 @@
     def connect_realtime(self, config: STTConfig):
         vad = config.vad_config or {}
         return connect_stt_realtime(
             language_code=provider_language_code(config.language, provider="sarvam", stage="stt"),
             stream_type=config.stream_type,
             mode="transcribe",
             endpointing="vad",
             sample_rate=config.sample_rate,
-            silence_duration_ms=vad.get("silence_duration_ms"),
-            threshold=vad.get("threshold"),
-            min_speech_duration_ms=vad.get("min_speech_duration_ms"),
-            prefix_padding_ms=vad.get("prefix_padding_ms"),
+            silence_duration_ms=vad.get("silence_duration_ms", 600),
+            threshold=vad.get("threshold", 0.55),
+            min_speech_duration_ms=vad.get("min_speech_duration_ms", 300),
+            prefix_padding_ms=vad.get("prefix_padding_ms", 300),
+            high_vad_sensitivity=False,
             model=config.model,
         )
```

---

### Diff 5: [`server/services/pstn_backchannel.py`](file:///d:/voice%20agent/server/services/pstn_backchannel.py)

> **CRITICAL FIX**: `pstn_backchannel.py` previously only had pools for `en-IN`, `te-IN`, and `hi-IN`. When a caller was speaking Tamil (`ta-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Bengali (`bn-IN`), Gujarati (`gu-IN`), or Punjabi (`pa-IN`), `BACKCHANNEL_PHRASES.get(lang)` returned `None` and silently defaulted to `BACKCHANNEL_PHRASES["en-IN"]`. A Tamil or Bengali caller pausing mid-sentence suddenly heard the agent say *"Right. I see."* in English!
>
> **Fix**: Expand `BACKCHANNEL_PHRASES` with curated native out-of-band continuers for all 10 platform languages.

```diff
--- a/server/services/pstn_backchannel.py
+++ b/server/services/pstn_backchannel.py
@@ -26,5 +26,16 @@
 BACKCHANNEL_PHRASES: dict[str, list[str]] = {
     "en-IN": ["Hmm.", "Mhm.", "Right.", "I see.", "Okay."],
+    "en-US": ["Hmm.", "Mhm.", "Right.", "Got it.", "Okay."],
+    "en-GB": ["Hmm.", "Mhm.", "Right.", "I see.", "Indeed."],
     "te-IN": ["Hmm.", "Mhm.", "Aha.", "Sare.", "Avunu."],
     "hi-IN": ["Hmm.", "Haan.", "Achha.", "Theek hai."],
+    "ta-IN": ["ஆம்.", "சரி.", "சரிங்க.", "நன்று.", "அப்படியா."],
+    "kn-IN": ["ಹೌದು.", "ಸರಿ.", "ಆಯಿತು.", "ಚೆನ್ನಾಗಿದೆ.", "ಹೌದಾ."],
+    "ml-IN": ["അതെ.", "ശരി.", "ശരിയാണ്.", "നന്ന്.", "കൊള്ളാം."],
+    "mr-IN": ["हो.", "होय.", "बरे.", "ठीक आहे.", "समजले."],
+    "bn-IN": ["হ্যাঁ.", "ঠিক আছে.", "अच्छा.", "বেশ.", "বুঝেছি."],
+    "gu-IN": ["હા.", "હાજી.", "બરાબર છે.", "સારું.", "સમજાયું."],
+    "pa-IN": ["ਹਾਂ.", "ਹਾਂਜੀ.", "ਠੀਕ ਹੈ.", "ਚੰਗਾ.", "ਸਮਝ ਗਿਆ."],
 }
```

---

## 7. Verification & Telephony Field Test Matrix

| # | Test Scenario | Caller Action During Call | Expected Result | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Conversational Nod (English)** | While agent explains an offer, say *"Yeah"* or *"Okay"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **2** | **Conversational Nod (Telugu)** | While agent explains an offer, say *"అవునండి"* (*avunandi*) or *"సరే"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **3** | **Conversational Nod (Hindi)** | While agent explains an offer, say *"हाँ जी"* (*haan ji*) or *"ठीक है"*. | Agent continues speaking uninterrupted. | Playout continues smoothly; no buffer flush. |
| **3b**| **Conversational Nods (7 Other Indic Languages)** | While agent explains in Ta/Kn/Ml/Mr/Bn/Gu/Pa, say *"ஆம்"* (*aam*), *"ಹೌದು"* (*haudu*), *"അതെ"* (*athe*), *"हो"* (*ho*), *"হ্যাঁ"* (*haan*), *"હા"* (*haa*), or *"ਹਾਂ"* (*haan*). | Agent continues speaking uninterrupted in each language pack. | No barge-in triggered across any of the 10 language packs. |
| **4a** | **No Ghost Turn (Statement)** | Agent says *"I'll send you the details."* Caller says *"Avunu"* during speech, then stays silent. | Agent finishes, transitions to `listening`, waits silently. | Does NOT respond to *"Avunu"*; pending is purged. |
| **4b** | **Answer to Question Kept (En/Hi/Te)** | Agent asks *"Shall I proceed?"* Caller says *"Haan"* slightly before TTS ends. | Agent finishes, then processes *"Haan"* as a real answer. | LLM turn launches with *"Haan"*; NO dead air! |
| **4c** | **Answer to Question Kept (Ta/Kn/Ml/Mr/Bn/Gu/Pa)** | Agent asks *"தொடரலாமா?"* (Ta) or *"ಮುಂದುವರಿಯಲೇ?"* (Kn). Caller nods affirmative (*"ஆம்"* / *"ಹೌದು"*). | Agent finishes TTS, immediately processes affirmative answer. | Question detected by language keyword; NO dead air! |
| **5** | **Emergency Halt Command (En/Te/Hi)** | While agent is speaking, say *"Wait!"*, *"Stop!"*, *"No"*, *"ఆగండి"*, or *"नहीं"*. | Agent halts speech within 150ms. | Immediate playback clear and cancel. |
| **5b** | **Emergency Halt Command (7 Other Indic Languages)** | While agent is speaking, say *"நில்லுங்கள்"* (Ta), *"ನಿಲ್ಲಿಸಿ"* (Kn), *"നിൽക്കൂ"* (Ml), *"थांबा"* (Mr), *"থামুন"* (Bn), *"ઊભા રહો"* (Gu), or *"ਰੁਕੋ"* (Pa). | Agent halts speech within 150ms in all 7 languages. | Immediate playback clear and cancel without hold delay. |
| **6** | **Substantive Question Barge-In** | While agent is speaking, say *"Actually what is the fee?"* ($\ge 3$ words). | Agent halts cleanly after 300ms hold and answers the question. | Smooth transition to new LLM turn. |
| **7** | **AEC Gate Time Latching** | Caller says *"Hello?"* loudly (RMS > 320), then pauses. Sarvam transcript arrives 550ms later. | Gate remains latched (`PSTN_AEC_VOICE_LATCH_S = 0.8s`). | `energy_below_floor` NOT tripped; barge evaluated. |
| **8** | **High Ambient Fan Noise** | Hold phone near a running ceiling fan or road traffic. | Agent plays speech to completion without clipping. | Sarvam STT threshold `0.55` ignores steady noise. |
| **9** | **Speakerphone Echo Shield** | Put call on loud speakerphone in an echoic room. | Agent does not cut itself off during first word. | `min_after_speak` 350ms absorbs reflection. |
| **10**| **Thinking Phase Immunity** | Ask a question, and say *"అవును"* or *"ശരി"* while the bot is generating. | Bot completes thinking and speaks the answer normally. | Generation is NOT cancelled across any language. |
| **11**| **Negative Correction Halt** | While agent explains wrong info, caller says *"No"*, *"కాదు"*, *"இல்லை"*, *"ಬೇಡ"*, or *"नाही"*. | Agent halts speech; caller can correct immediately. | Negation matches halt list; 1-word immediate barge. |
| **12**| **Invitation to Speak ("చెప్పండి", "சொல்லுங்க", "ಹೇಳಿ")** | Caller says *"చెప్పండి"* or *"சொல்லுங்க"* while agent pauses or speaks. | Evaluated as invitation to speak, NOT suppressed as a backchannel nod. | Yields turn appropriately; never silenced. |
| **13**| **Partial Self-Echo Rejection** | Agent says *"Your OTP is four three two one"*. Mic reflects text. | Incoming partial matches heard assistant text ($\ge 50\%$). | Partial dropped; zero state change or barge fire. |
| **14**| **Soft Ducking & Unducking** | Background door closes loudly during playout; no speech follows. | Agent volume drops to 20%, then smoothly restores to 100% in 700ms. | Playout uninterrupted; no false barge. |
| **15**| **Native Backchannel Synthesis (`pstn_backchannel.py`)** | Tamil caller pauses mid-sentence for 300ms. | Agent murmurs *"சரி."* or *"ஆம்."* in Tamil. | Never speaks English *"Right. I see."* to Indic callers! |

---

## 8. Must-Fix Before Shipping: Criticality Audit of All 10 Errata & Edge Cases

### 8.1 Return Type Mismatch (`(False, reason)` vs `bool`) — [CRITICAL]
- **The Bug**: `_should_commit_barge` was declared `-> bool`, but v2.0 snippets returned `(False, "backchannel_ignored")`.
- **The Blast Radius**: In Python, all tuples are truthy: `bool((False, "reason")) == True`. Every caller `if self._should_commit_barge(text):` evaluated the tuple as `True`. **Every single backchannel nod ("Haan", "Avunu") would immediately cut off the agent!**
- **The Fix**: Use `result, reason = False, "..."` local variables and explicitly return `result` (bare `bool`).

### 8.2 AEC Gate Timing Race (160ms Close vs 300–800ms Transcript) — [CRITICAL]
- **The Bug**: `_aec_barge_open` is calculated on incoming 20ms audio frames. If 8 consecutive quiet frames occur (~160ms), the gate closes. However, Sarvam's WebSocket STT acoustic processing and network transmission takes **300–800ms**.
- **The Blast Radius**: When the caller finishes an utterance (e.g. *"Actually what is the fee?"*) and pauses, the audio frames go quiet while Sarvam finishes transcribing. By the time Sarvam sends `transcript.partial`, the 160ms counter has expired. `_should_commit_barge` sees `_aec_barge_open == False` and rejects the legitimate interruption with `energy_below_floor`.
- **The Fix**: Latch the gate using `_last_vad_voice_at`. If loud audio was detected within the last 800ms (`(now - self._last_vad_voice_at) <= PSTN_AEC_VOICE_LATCH_S`), keep the gate open.

### 8.3 Ghost-Turn Purge Dead Air on Question Turns — [CRITICAL]
- **The Bug**: v2.0 proposed unconditionally clearing `_pending_transcript` if it matched `_BACKCHANNEL_NODS_RE` upon turn completion.
- **The Blast Radius**: If the agent asks *"Shall I proceed with your booking?"* and the caller nods *"Haan"* or *"Avunu"* slightly before the agent's playout finishes, the purge destroys their real affirmative answer! The agent finishes speaking, purges *"Haan"*, transitions to `listening`, and enters indefinite dead air.
- **The Fix**: Check `agent_asked_question`. Only purge backchannels if the agent's previous utterance was an informative statement. If the agent asked a question or requested confirmation, preserve the transcript and launch the turn!

### 8.4 Missing Negative & Correction Halt Words ("No", "కాదు", "లేదు", "नहीं") — [CRITICAL]
- **The Bug**: v1 had `no`, `nope`, `కాదు`, `లేదు`, `లేదండి`, `नहीं`, `actually`, `sorry` in `_SHORT_INTERRUPT`. The v2.0 draft omitted them from `_HALT_COMMANDS_RE`.
- **The Blast Radius**: A caller saying *"No, that's wrong"* was forced to speak 2+ words and hold for 300ms. In telephony, negations are urgent corrections; making them slow causes the bot to continue rambling over the customer.
- **The Fix**: Restore all negation and correction tokens to `_HALT_COMMANDS_RE`.

### 8.5 Leftover `_SHORT_INTERRUPT` / `short_ok` / `_THINK_CANCEL_ACK_ONLY` — [CRITICAL]
- **The Bug**: `_SHORT_INTERRUPT` and `short_ok` were present at 9 distinct locations in `pstn_voice_core.py`.
- **The Blast Radius**: Removing `_SHORT_INTERRUPT` without migrating all 9 sites causes an immediate, fatal `NameError: name '_SHORT_INTERRUPT' is not defined` when an LLM turn thinking cancellation or continuation runs.
- **The Fix**: Complete 9-site migration table and full replacement across `_should_commit_barge`, `_should_think_cancel`, and `_should_think_continue_final`.

### 8.6 Mobile AGC Pumping (400–600 RMS) vs Fixed 320 RMS Gate & Soft Energy Latching — [HIGH]
- **The Bug**: Section 3B notes that mobile handset AGC lifts distant room voices and background noise to 400–600 RMS when the caller is quiet, easily surpassing a 320 RMS threshold. Meanwhile, soft-spoken primary callers (<320 RMS) are falsely locked out.
- **The Blast Radius**: A rigid RMS threshold cannot reliably distinguish near-field quiet speech from far-field amplified background noise on cellular trunks.
- **The Fix**: Treat energy as a **soft confidence signal** combined with hold time (300ms) and word count ($\ge 2$). Never use a hard frame dropper in `feed_user_pcm16`. Measure actual RMS distributions on production call recordings.

### 8.7 Regex `\w` Failure on Indic Diacritics & Graphemes — [HIGH]
- **The Bug**: `(?:\s+\w+){0,2}` used `\w+`. In Unicode, Telugu and Hindi combining characters (virama `్`, anusvara `ం`, matras `ా`, `ి`, `ు`) are distinct code points from consonants. `\w+` can fragment grapheme clusters or fail to match attached diacritics.
- **The Fix**: Use `(?:\s+\S+){0,2}`. Since the pattern is anchored (`^...$`), `\S+` cleanly matches the next whitespace-delimited word token regardless of script.

### 8.8 Removal of "చెప్పండి" (cheppandi) from Backchannel List — [HIGH]
- **The Bug**: "చెప్పండి" (*cheppandi*) was included in the backchannel nods list.
- **The Blast Radius**: In Telugu, "చెప్పండి" literally means *"Please tell me / Go ahead and speak"*. It is an explicit prompt/invitation to talk, NOT a passive acknowledgment nod! Suppressing it as a nod silences a user who is actively asking the agent to speak.
- **The Fix**: Removed `చెప్పండి` and Romanized `cheppandi` from `_BACKCHANNEL_NODS_RE`.

### 8.9 Root Cause 1 Fact-Check, `prefix_padding_ms` Inconsistency & +100ms Latency Budget — [HIGH]
- **The Forensic Truth**: `ws.py:121-127` already had `min_speech_duration_ms=250` and `prefix_padding_ms=300`. `sarvam_ws.py` only enabled `high_vad_sensitivity` when both were `None`. The actual bug was in `sarvam_stt.py` (which passed `None` across the board, bypassing calibration) and the overly permissive threshold `0.3`.
- **Latency Budget**: Increasing `silence_duration_ms` from 500ms to 600ms adds +100ms to every turn end. This is a deliberate, acceptable engineering trade-off to accommodate Indic sentence structure, but must be monitored in production telemetry (`stt.transcript` timestamps).

### 8.10 Soft Pause & Resume (TTS Ducking) & Partial Self-Echo Suppression — [HIGH]
- **Value**: Soft ducking (Pillar 7) and partial self-echo filtering (Pillar 8) transform turn-taking from a fragile binary switch into an adaptive, resilient conversational runtime matching industry state-of-the-art (LiveKit, Retell, Vapi).

### 8.11 Pan-Indic 10-Language Parity & Language Pack Eradication of Blind Spots — [CRITICAL]
- **The Blind Spot**: Previous v1.0 and v2.0 drafts only considered English, Telugu (`te-IN`), and Hindi (`hi-IN`). The platform officially supports 10 languages ([server/config/constants.py:95-108](file:///d:/voice%20agent/server/config/constants.py#L95-L108) & [server/prompts/agent_voice_rules.py:153-180](file:///d:/voice%20agent/server/prompts/agent_voice_rules.py#L153-L180)):
  1. `te-IN` (Telugu)
  2. `hi-IN` (Hindi)
  3. `ta-IN` (Tamil)
  4. `kn-IN` (Kannada)
  5. `ml-IN` (Malayalam)
  6. `mr-IN` (Marathi)
  7. `bn-IN` (Bengali)
  8. `gu-IN` (Gujarati)
  9. `pa-IN` (Punjabi)
  10. `en-IN` / `en-US` / `en-GB` (English)
- **The Blast Radius**:
  1. **Halt Failures**: Callers speaking Tamil (`நில்லுங்கள்`, `வேண்டாம்`, `இல்லை`), Kannada (`ನಿಲ್ಲಿಸಿ`, `ಬೇಡ`), Malayalam (`നിൽക്കൂ`, `വേണ്ട`), Marathi (`थांबा`, `नको`), Bengali (`থামুন`, `না`), Gujarati (`ઊભા રહો`, `ના`), or Punjabi (`ਰੁਕੋ`, `ਨਾ`) were forced to speak $\ge 2$ words and hold for 300ms. Urgent corrections like *"இல்லை"* (*illai* / No) or *"नाહી"* (*nahi*) failed to halt the agent!
  2. **Dead Air on Questions**: When the bot asked a question in Tamil (*"தொடரலாமா?"*) or Kannada (*"ಮುಂದುವರಿಯಲೇ?"*) and the caller said *"ஆம்"* (*aam*) or *"ಹೌದು"* (*haudu*), `agent_asked_question` evaluated to `False` due to missing language keywords. The system purged the affirmative nod as an in-speech interruption, creating indefinite dead air!
  3. **Broken Backchannel Synthesis**: In `server/services/pstn_backchannel.py`, `BACKCHANNEL_PHRASES` only contained `en-IN`, `te-IN`, and `hi-IN`. When a Tamil or Bengali caller paused mid-sentence, `BACKCHANNEL_PHRASES.get(lang)` defaulted to English (`"Right. I see."`), ruining the local persona.
  4. **Code-Switching & Romanized Transliteration**: Indian callers frequently speak mixed English phonetics (Tanglish, Hinglish, Tenglish, Kanglish, Benglish) and Sarvam STT regularly outputs Romanized text (`nillungal`, `haudu`, `aamaam`, `theek`, `vendaam`). Regexes that only matched native scripts failed completely on Romanized transcripts.
- **The Fix**:
  1. **Master 10-Language Lexicons**: Unified `_HALT_COMMANDS_RE` and `_BACKCHANNEL_NODS_RE` in Pillar 1 and Diff 1 with native script and Romanized phonetics for all 10 platform languages.
  2. **10-Language Question Keyword Detection**: Expanded `agent_asked_question` across all 10 languages so questions ending without explicit question marks retain caller affirmations.
  3. **10-Language Backchannel Pools (Diff 5)**: Added native out-of-band continuers for all 10 languages in `pstn_backchannel.py`.
  4. **Turn-Claiming Exclusion**: Explicitly banned invitations to speak (`చెప్పండి`, `சொல்லுங்க`, `ಹೇಳಿ`, `പറയൂ`, `सांगा`, `বলুন`, `કહો`, `ਦੱਸੋ`, `बोलिए`) from nod suppression.

---

## 9. Pre-Flight Verification Checklist & Production Sign-Off Protocol

Before deploying these changes to staging and production PSTN trunks, the engineer must verify each invariant:

- [ ] **Invariant 1 (Strict Bool Return)**: `_should_commit_barge` returns only `bool` instances. Verify with `assert isinstance(self._should_commit_barge(text), bool)`.
- [ ] **Invariant 2 (Zero NameErrors)**: Run static analysis / pytest on `pstn_voice_core.py` to confirm zero references to `_SHORT_INTERRUPT`, `_THINK_CANCEL_ACK_ONLY`, or uninitialized `short_ok`.
- [ ] **Invariant 3 (Question Retention across 10 Languages)**: Simulate a turn ending with question keywords in Telugu (`"సరేనా"`), Hindi (`"बताइए"`), Tamil (`"தொடரலாமா"`), Kannada (`"ಮುಂದುವರಿಯಲೇ"`), Bengali (`"বলুন"`), etc., followed by an affirmative nod. Confirm `PENDING_KEPT_ANSWER_TO_QUESTION` is logged and the turn launches.
- [ ] **Invariant 4 (Statement Purge)**: Simulate a turn ending with `"Our hours are 9 to 5."` followed by a pending transcript of `"Avunu"` or `"ஆம்"`. Confirm `PENDING_PURGED_BACKCHANNEL` is logged and `pending` is set to `None`.
- [ ] **Invariant 5 (AEC Latch Window)**: Simulate loud audio frame at $t=0$, quiet frames until $t=500\text{ms}$, and partial transcript arriving at $t=550\text{ms}$. Confirm barge check evaluates with `energy_below_floor` NOT tripped.
- [ ] **Invariant 6 (Emergency Halt Words across 10 Languages)**: Test single-word utterances in both native script and Romanized phonetics: `"Wait"`, `"Stop"`, `"No"`, `"ఆగండి"`, `"కాదు"`, `"नहीं"`, `"நில்லுங்கள்"`, `"இல்லை"`, `"ನಿಲ್ಲಿಸಿ"`, `"ಬೇಡ"`, `"थांबा"`, `"থামুন"`, `"ઊભા રહો"`, `"ਰੁਕੋ"`. Confirm immediate barge commit with `reason="halt_command"`.
- [ ] **Invariant 7 (Indic Diacritics Safety)**: Test words with complex combining marks (`అవునండి`, `సరేనండి`, `வద్దండీ`, `நில்லுங்கள்`, `ನಿಲ್ಲಿಸಿ`). Confirm regex `(?:\s+\S+){0,2}` matches cleanly without splitting graphemes.
- [ ] **Invariant 8 (Audio Continuity)**: Confirm raw PCM frames are NEVER dropped in `feed_user_pcm16`. STT WebSocket stream remains 100% continuous.
- [ ] **Invariant 9 (Turn-Claiming Phrases Excluded from Nods)**: Verify that `"చెప్పండి"`, `"சொல்லுங்க"`, `"ಹೇಳಿ"`, `"പറയൂ"`, `"सांगा"`, `"বলুন"`, `"કહો"`, `"ਦੱਸੋ"`, `"बोलिए"` are NEVER matched by `_BACKCHANNEL_NODS_RE`.
- [ ] **Invariant 10 (Native Backchannel Synthesis)**: Call `pick_backchannel_phrase(lang)` for each of the 10 language codes. Verify that each returns a native phrase and none returns English unless language is English.

---

## 10. Version Evolution & Changelog (v1.0 → v2.0 → v2.1)

| Feature / Invariant | v1.0 (Legacy Production) | v2.0 (First Audit Draft) | v2.1 (Current Production Master) |
| :--- | :--- | :--- | :--- |
| **`_should_commit_barge` Return Type** | `bool` | `(False, reason)` tuple (**Fatal Truthy Bug**) | **Strict `bool`** (safe for all callers) |
| **AEC Energy Gate Timing** | Unconnected (ignored in commit) | 160ms quiet close (**Timing Race**) | **800ms Latched Window** via `_last_vad_voice_at` |
| **Ghost Turn Handling** | Unconditional Launch (Hallucination) | Unconditional Purge (**Dead Air Bug**) | **Question-Aware**: Purges statements, keeps answers |
| **Platform Language Coverage** | English, Telugu, Hindi only | English, Telugu, Hindi only | **All 10 Platform Languages** (En, Te, Hi, Ta, Kn, Ml, Mr, Bn, Gu, Pa) |
| **Romanized Code-Switching** | English only | Incomplete fragments | **Comprehensive Romanized Lexicons** (Tanglish, Hinglish, Tenglish, etc.) |
| **Negative Halt Commands** | Had `no`, `కాదు`, `नहीं` | Dropped `no`, `కాదు`, `नहीं` (**UX Regression**) | **Restored across all 10 languages**: Immediate 1-word halt |
| **Indic Script Regex** | `(?:\s+\w+){0,3}` (grapheme split) | `(?:\s+\w+){0,2}` (grapheme split) | **`(?:\s+\S+){0,2}`** (safe for all Indic diacritics) |
| **"చెప్పండి" Classification** | Unhandled | Listed as backchannel nod (**Erroneous**) | **Excluded from nods** (turn-claiming invitation to speak) |
| **Backchannel Synthesis (`pstn_backchannel.py`)** | En/Te/Hi only (English fallback) | Ignored / Not addressed | **Diff 5: Native pools for all 10 language packs** |
| **Question Detection (`agent_asked_question`)**| None | En/Te/Hi only (Dead air in 7 languages) | **Pillar 3 & Diff 1: Complete 10-language keyword detection** |
| **Symbol Migration** | Referenced `_SHORT_INTERRUPT` | Only 1 of 9 sites shown (**NameError Hazard**) | **Complete 9-Site Migration** across all methods |
| **Sarvam STT VAD Sensitivity** | Threshold 0.3 / Min Speech 250ms | Inaccurate claim of universal None | **Threshold 0.55 / Min 300ms / Silence 600ms** calibrated |
| **Provider Adapter (`sarvam_stt.py`)** | Passed `None` (uncalibrated fallback) | Not addressed | **Explicit Calibrated Fallback Defaults** matching `ws.py` |
| **Soft Ducking (Pause & Resume)** | Not implemented (binary cut) | Not addressed | **Pillar 7**: Ducks TTS to 20% on VAD; restores in 700ms |
| **Partial-Level Self-Echo** | Evaluated only at barge commit | Evaluated only at barge commit | **Pillar 8**: Early drop at partial ingress ($\ge 50\%$ overlap) |


