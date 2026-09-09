# TASK: Full PSTN Voice Agent Audit, Repair & Optimization

You are working on an existing production voice-agent codebase (`telugu-voice-agent`).

The goal is to make the PSTN voice agent completely reliable end-to-end and make its conversational behavior as close as technically possible to a modern ChatGPT-style realtime voice agent.

**DO NOT replace the existing architecture.**

The architecture must remain:
```
Telnyx PSTN
  ↓ (SIP & Media WebSocket)
Telnyx Media WebSocket Bridge (server/services/telnyx_pstn_bridge.py)
  ↓ (L16 16 kHz / μ-law 8 kHz RTP frames)
Streaming STT Service (Deepgram / Sarvam)
  ↓ (partial / final transcripts)
PSTN Voice Loop & FSM Coordinator (server/services/pstn_voice_core.py)
  ↓ (finalized turn text)
Persistent OpenAI Realtime Text Session (server/realtime/text_session.py)
  ↓ (streaming text deltas)
Sentence Chunker (server/services/pstn_text_chunker.py)
  ↓ (complete sentences)
Streaming TTS Service (Sarvam / Cartesia / ElevenLabs)
  ↓ (20ms audio frames)
Telnyx Outbound Jitter Playback (server/services/pstn_playback.py)
  ↓
Caller PSTN Handset
```

- The existing **Brain / Agent Prompt Compiler** (`server/brain/`) must remain the sole authority for agent behavior, sales qualification flow, brevity rules, and guardrails.
- The **Test Studio / Dev Panel** (`web/components/dev/test-studio/`) must remain the primary development and live testing interface.

---

# NON-NEGOTIABLE ENGINEERING RULE

This task description contains suspected failures, expected behavior, and proposed implementation details.

**They are NOT automatically facts.**

Before changing code:
1. **Inspect the actual implementation.**
2. **Trace the actual runtime path.**
3. **Identify the actual failure.**
4. **Confirm the failure with tests and logs where possible.**
5. **Fix the smallest correct architectural layer.**
6. **Add a regression test.**
7. **Verify both inbound and outbound behavior.**

If this task description conflicts with the actual code, **trust the actual code and document the discrepancy**.
- Do not blindly implement every suggested code snippet.
- Do not optimize timing values before establishing that the current timing is actually responsible for the problem.
- Do not manufacture fixes for problems that do not exist.

---

# PRIMARY OBJECTIVES

Fix and optimize ALL of the following:

1. **PSTN Inbound Call Flow**: Diagnose and verify inbound agent resolution (`self.agent_id` when missing on inbound calls, `call_id` creation, greeting execution, and transcript ingestion).
2. **Telnyx Inbound Answering**: Inspect Telnyx call control handling for inbound calls; add `.answer()` to `TelnyxClient` (`server/services/telnyx_client.py`) only after verifying the exact API contract.
3. **PSTN Outbound Call Flow**: Synchronize `server/routes/dev_telephony.py` (`POST /api/dev/telephony/telnyx/dial`) with the same voice loop, FSM, and memory lifecycle.
4. **Telnyx Media WebSocket Connection**: Validate `build_stream_ws_url()` to ensure the public `wss://` URL is derived correctly from `public_api_base()`.
5. **Call Lifecycle Management**: Ensure `call_lifecycle_service.start()` (`server/call/call_lifecycle_service.py`) initializes call ledger, session memory, and locked brain text.
6. **Agent & Session Initialization**: Prevent multi-worker token loss using Redis mirrors (`telnyx_stream_tokens`) and ensure session contexts are isolated.
7. **Greeting & Introduction**: Guarantee deterministic opening line playback from `extract_opening_greeting()`; synchronize with model history via `realtime_text_manager.note_spoken()` with `[Opening already spoken aloud — do not greet or introduce yourself again.]`. Prevent duplicate greetings on reconnect.
8. **Streaming STT Integration**: Manage STT client lifecycle (`_connect_stt_upstream` in `server/routes/ws.py`), supervisor re-connections, and 12s keep-alive pings.
9. **VAD & Speech Detection**: Soft AEC energy gating (`PSTN_TTS_STT_ENERGY_MIN = 320`) as a barge confidence signal without dropping quiet speech from STT.
10. **End-of-Turn Detection & Coalescing**: Measure and tune STT endpointing and coalesce windows (`PSTN_LISTEN_COALESCE_S` baseline 0.55s, partial grace 0.20s) for responsive back-and-forth without cutting natural pauses.
11. **Transcript Gating & Indic Word Counts**: Enforce `effective_word_count()` with Unicode cluster fallback (`\u0900-\u097F`, `\u0C00-\u0C7F`) and `is_substantive_transcript()` in `server/services/transcript_gate.py`.
12. **Barge-In Timing & Early Protection**: Resolve the conflict between startup protection and fast barge-in. Allow legitimate early interruption while preventing speaker click / audio feedback.
13. **Immediate Agent Interruption**: Stop audio instantly upon speech detection; never wait for final STT before clearing playback.
14. **OpenAI Realtime Response Cancellation**: Dispatch `realtime_text_manager.cancel(call_id)` immediately during barge-in.
15. **TTS Interruption & Stale Tail Drop**: Abort streaming TTS sessions immediately; never flush incomplete trailing clauses after an interrupt.
16. **Dual Audio Queue Management**: Clear both the local application playback queue (`playback.drain()`) AND the remote carrier buffer (`client.clear_playback(call_control_id)`).
17. **Conversation History Synchronization**: Reconcile assistant history to reflect only what the caller actually heard (`_tts_heard_text`) via `conversation_manager.note_barge()`.
18. **Brain Prompt & Conversational Brevity**: Enforce natural spoken brevity (1–2 concise sentences, 8–25 words / concise Telugu equivalent) rather than a rigid character count.
19. **Call State & Generation IDs**: Enforce `emission_blocked()` so audio tagged with an invalidated `current_generation_id` can never leak to the caller.
20. **Dual-Rail Echo Guarding**: Tune `server/services/echo_guard.py` (bigram 65% + unigram 35% overlap) to prevent self-interruption without falsely dropping caller questions (e.g. *"Shamshabad?"*).
21. **Think-Cancel Implementation**: Cancel in-flight LLM generations during `PHASE_THINKING` if caller resumes speaking, while ignoring pure backchannels via `_THINK_CANCEL_ACK_ONLY`.
22. **Dev Panel & Test Studio Diagnostic Console**: Provide a dedicated PSTN diagnostic view and real-time event timeline in `web/components/dev/test-studio/`.
23. **Dev Panel PSTN Test Panel**: Validate provider status, outbound canary dialing, and audio loopback via `PstnTestPanel.tsx`.
24. **Automated Regression Suite**: Ensure all relevant existing tests pass without weakening assertions.
25. **TTS Audio Quality & Artifact Elimination**: Eliminate chirping, cracking, phase discontinuities, and downsampling aliasing across chunk boundaries and rate conversion filters.
26. **End-to-End Proof & Implementation Report**: Conduct complete audit of inbound, outbound, 19 failure scenarios, exact latency benchmarks, and document verified vs disproved root causes.

---

# PHASE 1 — AUDIT BEFORE MODIFYING CODE

First, trace the exact runtime lifecycle across both call directions in the current codebase.

## INBOUND CALL LIFECYCLE
```
1. Caller dials Telnyx Phone Number
2. Webhook `call.initiated` received at `server/routes/telnyx.py:telnyx_webhook()`
3. TelnyxClient issues `POST /v2/calls/{call_control_id}/actions/answer`
4. Telnyx establishes media WebSocket to `/ws/telnyx-stream?token=...` (`server/routes/telnyx_ws.py`)
5. Bridge instance `TelnyxPstnBridge._on_start()` (`server/services/telnyx_pstn_bridge.py`) receives `event: "start"`
6. Default agent resolved via `server.brain.agent_service.agent_service.resolve_default_agent_id()`
7. Call created: `call_lifecycle_service.start(channel="pstn", direction="inbound")` (`server/call/call_lifecycle_service.py`)
8. Realtime text session pre-warmed / started via `realtime_text_manager.create()` (`server/realtime/manager.py`)
9. `PstnVoiceLoop.start_call()` launches STT socket and greeting TTS concurrently (`server/services/pstn_voice_core.py`)
10. Greeting audio streams to wire via `TelnyxQueuePlayback` (`server/services/pstn_playback.py`)
11. `note_spoken()` primes greeting in Realtime session history
12. Loop transitions to `PHASE_LISTENING`
13. Inbound audio frames fed to STT (`feed_user_pcm16()`)
14. STT partials/finals received → idle coalesce window (`_arm_listen_coalesce()`)
15. Turn launched: `LiveTurnOrchestrator.handle_user_turn_stream()` (`server/call/live_turn_orchestrator.py`)
16. Streaming tokens chunked by `drain_complete_sentences()` (`server/services/pstn_text_chunker.py`)
17. TTS session (`PstnTurnTtsSession`) encodes audio frames → Telnyx WebSocket
```

## OUTBOUND CALL LIFECYCLE
```
1. Developer initiates dial in `web/components/dev/test-studio/PstnTestPanel.tsx`
2. Endpoint `POST /api/dev/telephony/telnyx/dial` in `server/routes/dev_telephony.py`
3. Stream token created with `agent_id`, `tier`, `source_session_id`, `direction="outbound"`
4. `TelnyxClient.create_outbound_call()` dispatches call via Telnyx REST API v2
5. Callee answers → Telnyx connects WebSocket `/ws/telnyx-stream`
6. `TelnyxPstnBridge._on_start()` extracts token meta → `call_lifecycle_service.start()`
7. Same `PstnVoiceLoop`, STT, Realtime session, and TTS pipeline execute identically to Inbound
```

---

# PHASE 2 — INBOUND CALL FLOW & DEFAULT AGENT RESOLUTION

Inspect:
- `server/services/telnyx_pstn_bridge.py` (`TelnyxPstnBridge._on_start`)
- `server/call/call_lifecycle_service.py` (`call_lifecycle_service.start`)
- `server/brain/agent_service.py` (`agent_service.resolve_default_agent_id`)

### Suspected Root Cause — MUST BE VERIFIED:
> [!IMPORTANT]
> **Do not implement any suspected root cause until you verify it against the actual current code and runtime flow.**
> If the current code differs from this description, trust the code and document the discrepancy. Do not manufacture fixes for problems that do not exist.

**Hypothesis to verify**:
When a real caller dials into Telnyx, `merged_local.get("agent_id")` and `self._token_meta.get("agent_id")` may be `None`.
In `TelnyxPstnBridge._on_start()`:
```python
self.agent_id = self.agent_id or merged_local.get("agent_id")
if self.agent_id:
    # If self.agent_id is None, call_lifecycle_service.start is skipped!
```
If `self.agent_id` is missing and not defaulted:
- `self.call_id` remains `None`.
- `start_call(play_greeting=bool(self.call_id))` sets `play_greeting = False`.
- The greeting is skipped with `log_pstn("greeting.skip", reason="no_call")`.
- When the caller speaks, `_run_turn()` rejects the transcript: `[PSTN] transcript ignored — no call_id (agent not linked)`.
- The call is completely silent.

**Verification & Fix**:
Verify whether inbound calls arrive with `agent_id` set. If `self.agent_id` is indeed `None`:
```python
if not self.agent_id:
    from server.brain.agent_service import agent_service
    self.agent_id = await agent_service.resolve_default_agent_id()
```
Ensure `call_lifecycle_service.start()` is always called for valid inbound calls, and `self.call_id` is passed to `PstnVoiceLoop`.

---

# PHASE 3 — INBOUND CALL ANSWERING & TELNYX API CONTRACT

Inspect:
- `server/services/telnyx_client.py` (`TelnyxClient`)
- `server/routes/telnyx.py` (`telnyx_webhook`)

> [!WARNING]
> **Do not dictate API fields blindly.**
> Before implementing any answer payload, inspect the existing `TelnyxClient` implementation and verify every field against the Telnyx API contract currently used by this project. Do not introduce an API field solely because it appears in this task description. Preserve existing working Telnyx conventions.

### Verification Steps:
1. Inspect whether Telnyx requires an explicit `/v2/calls/{call_control_id}/actions/answer` call when `call.initiated` arrives, or if your Telnyx portal setup auto-answers calls.
2. If `TelnyxClient` lacks `answer()`, implement it following existing `TelnyxClient` conventions (using `_request("POST", ...)` and configured timeouts).
3. Verify whether `stream_url` can be passed directly in the answer payload, or if Telnyx expects `answer` followed by `streaming_start`. Respect the existing pattern in `_ensure_telnyx_streaming()`.
4. On `event_type == "call.initiated"` for inbound calls, ensure the call is answered and media stream initiated without stalling the webhook ACK.

---

# PHASE 4 — OUTBOUND CALL FLOW ALIGNMENT

Inspect:
- `server/routes/dev_telephony.py` (`dev_telnyx_dial`)
- `server/services/telnyx_client.py` (`create_outbound_call`)

Verify:
- Outbound calls pass `direction="outbound"`, `source_session_id`, and `agent_id` in token metadata.
- When callee answers, `call.answered` triggers `_ensure_telnyx_streaming()`.
- The exact same `PstnVoiceLoop` and `TelnyxPstnBridge` classes manage the media session.
- Outbound and inbound MUST share 100% of the VAD, STT, Realtime LLM, and TTS code paths.

---

# PHASE 5 — PUBLIC WEBSOCKET CONNECTIVITY

Inspect:
- `server/services/telnyx_client.py:build_stream_ws_url()`
- `server/config/urls.py:public_api_base()`

Requirements:
- Telnyx requires a publicly accessible `wss://` URI.
- Validate that `public_api_base()` strips trailing slashes and validates the scheme.
- Ensure reverse proxies or Cloudflare tunnels forward WebSocket upgrades cleanly without dropping frames.
- Log the generated WebSocket URI (obscuring sensitive query tokens) for observability:
  `log_pstn("stream.ws_url", control=call_control_id, url=stream_url[:60] + "...")`.

---

# PHASE 6 & 7 — OPENAI REALTIME SESSION LIFECYCLE & RECONNECT PROTECTION

Inspect:
- `server/realtime/providers/openai.py` (`OpenAIRealtimeTextAdapter`)
- `server/realtime/text_session.py` (`RealtimeTextSession`)
- `server/realtime/manager.py` (`realtime_text_manager`)

### Deterministic Lifecycle States:
`CREATING` → `CONNECTING` → `CONNECTED` → `CONFIGURING` → `READY` → `ACTIVE` → `CLOSING` → `CLOSED` / `FAILED`

### GA Realtime Session Configuration Constraints:
In `OpenAIRealtimeTextAdapter.connect()`:
```json
{
  "type": "session.update",
  "session": {
    "type": "realtime",
    "model": "gpt-realtime-2.1-mini",
    "instructions": "<COMPILED_BRAIN_PROMPT>",
    "output_modalities": ["text"],
    "max_output_tokens": 96,
    "tools": [END_CALL_TOOL],
    "tool_choice": "auto",
    "audio": {
      "input": {
        "turn_detection": null
      }
    }
  }
}
```
**CRITICAL RULES**:
- `output_modalities` MUST be `["text"]` only. Audio tokens are strictly forbidden.
- `turn_detection` MUST be `null`. Local `PstnVoiceLoop` manages VAD.
- Do NOT include `temperature` (causes GA Realtime session rejection).
- Capture `error` event from OpenAI and surface `event.get("message")` into logs; never transition to fake `READY` on failure.

### Reconnect Protection (No Double Greeting):
If the Realtime WebSocket drops mid-call and reconnects:
```
Realtime disconnect
       ↓
Reconnect WebSocket
       ↓
Restore conversation state & last known history
       ↓
DO NOT replay opening greeting if greeting_already_spoken == True
       ↓
Continue listening / active conversation
```
Only replay the greeting if the system can prove it was never delivered to the caller.

---

# PHASE 8 — GREETING & CONCURRENCY RACE HANDLING

Inspect:
- `server/services/pstn_voice_core.py` (`start_call()`, `_note_opening_spoken()`)
- `server/services/pstn_text_chunker.py` (`extract_opening_greeting()`)

### Greeting Sequence:
```
Realtime READY
       │
       ├──────────────┐
       ↓              ↓
   Start STT      Start greeting
       │              │
       │              ↓
       │         Audio emitted to wire
       │              │
       │              ↓
       │        note_spoken() with do-not-repeat marker
       │              │
       └──────→ PHASE_LISTENING
```

### Race Condition Policy (Caller Speaks During Greeting):
If the caller speaks while the greeting is playing:
- **DO NOT** treat greeting echo as caller speech (echo guard must ignore agent's own greeting audio).
- Capture valid caller speech into `self._intro_queue`.
- When the greeting finishes (or if early barge-in stops it), transition to `PHASE_LISTENING` and immediately launch a turn with the queued caller speech.
- **Explicitly test this race condition in tests.**

---

# PHASE 9 — FINITE STATE MACHINE (FSM)

Enforce strict mutually exclusive states in `PstnVoiceLoop`:
- `PHASE_INTRO = "intro"`: Greeting playback in flight. Inbound speech queued to `_intro_queue`.
- `PHASE_LISTENING = "listening"`: Waiting for speech; idle coalesce timer armed.
- `PHASE_THINKING = "thinking"`: Model generating; wire silent. Think-cancel enabled.
- `PHASE_SPEAKING = "speaking"`: Audio actively streaming to wire. Barge-in enabled.
- `PHASE_INTERRUPTING = "interrupting"`: Interruption triggered. Cancellation in flight; awaiting post-barge final STT.
- `PHASE_ENDED = "ended"`: Call terminated. FSM locked against re-opening.

---

# PHASE 10 & 11 — VAD, COALESCING & SHORT INTERRUPTIONS

Inspect:
- `server/services/pstn_voice_core.py` (`_arm_listen_coalesce`, `_listen_coalesce_fire`)
- `server/services/transcript_gate.py` (`effective_word_count`, `is_substantive_transcript`)

### Tuning Coalesce Timing:
- `PSTN_LISTEN_COALESCE_S = 0.55s` and `PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S = 0.20s` (up to 3 extensions = potential 1.15s max) are **baseline tuning candidates, not sacred values**.
- Measure actual STT partial/final timing and tune endpoint detection for natural Telugu, Tanglish, and English conversation.
- The objective is the best perceived conversational latency while avoiding premature turn termination.
- Do not claim an arbitrary number is "OpenAI's exact VAD value" unless documented.

### Short Natural Interruption Regex (`_SHORT_INTERRUPT`):
Recognize single-word interruptions across Telugu, Hindi, and English:
```python
_SHORT_INTERRUPT = re.compile(
    r"^(?:yes|no|yeah|yep|nope|wait|stop|actually|hold on|one second|sorry|"
    r"కాదు|లేదు|లేదండి|అవును|వద్దు|అది కాదు|"
    r"नहीं|हाँ|रुको|ठीक)"
    r"(?:\s+\w+){0,3}[.!,]*$",
    re.I,
)
```
Words matching this pattern bypass multi-word thresholds and trigger barge-in after a 120ms hold.

### Indic Word Counting:
Use character-cluster fallbacks (`cluster // 4`) for Telugu/Hindi text lacking whitespace in `effective_word_count()`.

---

# PHASE 12, 13 & 14 — BARGE-IN TIMING CONTRADICTION & REMOTE QUEUE CLEARING

Inspect:
- `server/services/pstn_voice_core.py` (`_should_commit_barge`, `_commit_barge`, `interrupt_tts`)
- `server/services/telnyx_client.py` (`clear_playback`)
- `server/services/pstn_playback.py` (`TelnyxQueuePlayback`)

### Resolving the Barge-In Contradiction:
> [!WARNING]
> **Do not preserve `PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35s` blindly.**
> If `MIN_AFTER_SPEAK = 350ms`, an interruption during the first 350ms of agent speech cannot be committed, conflicting with "immediate interruption".
> Determine whether this 350ms immunity is actually protecting the playback ramp or unnecessarily suppressing legitimate caller interruptions.
> The final implementation must allow legitimate early barge-in while protecting against false triggers caused by TTS startup / audio leakage. Do not use a fixed 350ms immunity if it prevents natural interruption.

### Desired Sequence:
```
Agent starts speaking
       ↓
VERY SHORT initial playback protection (ramp shield)
       ↓
Caller speech detected
       ↓
120ms hold confirmation (PSTN_BARGE_HOLD_S = 0.12s)
       ↓
BARGE TRIGGER
       ↓
1. Mark generation interrupted: self._interrupted_generation = old_gen
2. Invalidate in playback tracker: playback.invalidate_generation(old_gen)
3. Drain local queue: playback.drain()
4. Dispatch remote Telnyx clear: await client.clear_playback(call_control_id) via _on_barge
5. Cancel active TTS: await tts_session.close()
6. Cancel Realtime LLM: await realtime_text_manager.cancel(call_id)
7. Reconcile history: conversation_manager.note_barge(session_id, heard)
8. Transition to PHASE_INTERRUPTING and await post-barge final STT
```

---

# PHASE 15 — THINK-CANCEL MECHANICS

Inspect:
- `server/services/pstn_voice_core.py: _should_think_cancel()` & `_think_cancel()`

Behavior:
- Active only during `PHASE_THINKING` before any audio reaches the wire.
- If caller continues speaking, cancel active OpenAI stream immediately after 250ms hold.
- Merge in-flight transcript with new continuation: `_merge_pending_transcript()`.
- Filter out pure backchannels with `_THINK_CANCEL_ACK_ONLY` (`yeah`, `ok`, `sure`, `mhm`, `haan`).

---

# PHASE 16 & 17 — GENERATION GUARDS & STREAMING TTS FALLBACK

Inspect:
- `server/services/pstn_voice_core.py: emission_blocked()`
- `server/services/pstn_turn_tts.py: PstnTurnTtsSession`
- `server/services/pstn_text_chunker.py: drain_complete_sentences()`

### Generation Invariant:
Assign a unique `current_generation_id` per assistant turn. `emission_blocked()` must drop any audio chunk matching `_interrupted_generation`.

### Safe TTS / STT Fallback (No Infinite Loops):
> [!CAUTION]
> If TTS fails, calling `speak()` again can trigger the same failure in a loop.
> Follow this safe fallback order:
```
TTS failure detected
    ↓
Retry once if safe (clean socket re-connect)
    ↓
Fallback to alternative TTS provider or cached emergency fallback audio
    ↓
If no audio path is available:
    ↓
Surface failure explicitly in Dev Panel / logs
    ↓
Do not silently continue with dead air
```
Same for STT: If STT drops, surface the upstream socket failure rather than pretending to listen.

---

# PHASE 17B — TTS AUDIO QUALITY: ELIMINATING CRACKS, CHIRPING & DISCONTINUITIES

Inspect:
- `server/services/audio_transcode.py` (`StreamingPcmResampler`, `pcm_resample`, `pcm16_to_mulaw`)
- `server/services/telnyx_pstn_bridge.py` (`_send_agent_wire`, `_l16_chunks_to_pcmu`, `_out_worker`)
- `server/services/pstn_turn_tts.py` (`_ensure_resampler`, `_flush_audio_tail`, `_audio_buf`)
- `server/services/tts_config.py` (`resolve_pstn_tts_config`, sample rate negotiation)

### Suspected Root Causes of Voice Cracks & Chirping — MUST BE VERIFIED:
> [!WARNING]
> **Audio artifacts (cracks, clicks, metallic chirping, buzz) severely degrade caller trust.**
> Investigate and eliminate the following 5 confirmed mechanisms of audio degradation:

1. **Hot-Path One-Shot Resampling Discontinuities (Phase Clicks)**:
   - In `server/services/telnyx_pstn_bridge.py`:
     ```python
     pcm_resample(mulaw_to_pcm16(chunk, 8000), 8000, 16000)
     ```
     Calling `pcm_resample()` per 20ms frame discards `audioop.ratecv` filter memory on every single chunk. This creates 50 phase discontinuities per second, manifesting as an audible 50 Hz buzz, crackling, and chirping under the voice.
   - **Fix**: Never use one-shot `pcm_resample()` on streaming audio chunks. Maintain a dedicated stateful `StreamingPcmResampler` across the entire turn so `audioop.ratecv` carries filter state smoothly.

2. **Resampler State Invalidation Mid-Turn**:
   - In `server/services/pstn_turn_tts.py`: `self._pcm_resampler = None` was executed when chunk payloads reiterated `speech_sample_rate`. Wiping the resampler in the middle of active speech causes a sudden wave-phase jump (pop/click).
   - **Fix**: Only reinitialize the resampler if `new_rate != self._tts_rate`.

3. **High-Frequency Spectral Aliasing (24kHz / 16kHz → 8kHz)**:
   - When downsampling TTS audio from 24kHz or 16kHz down to 8kHz μ-law without a steep low-pass filter, energy above 4kHz (Nyquist boundary for 8kHz) folds over into the audible 0–4kHz spectrum. This produces high-pitched chirps, metallic ringing, and harsh sibilants on Telugu consonants.
   - **Fix**: Match sample rates at the source. Request native 16kHz (`linear16`) from the TTS provider when streaming over Telnyx L16 RTP. When streaming over G.711 μ-law, request native 8kHz if provider quality permits, or apply an anti-aliasing low-pass filter before `audioop.ratecv`.

4. **Jitter Under-runs & Sentence Boundary Pops (Zero-Crossing Discontinuities)**:
   - When `self._out_queue` runs empty between sentences or during TTS generation pauses, RTP frame transmission halts abruptly. When speech resumes, starting on a non-zero sample value causes the handset speaker coil to step discontinuously, producing an audible pop/click.
   - **Fix**: Apply a 2–4ms smooth cosine fade-out at the end of speech clauses and 2–4ms cosine fade-in at the onset of new audio bursts. Ensure steady 20ms RTP frame pacing in `_out_worker()`.

5. **Odd-Byte Frame Alignment**:
   - 16-bit linear PCM requires an even number of bytes (2 bytes per sample). Slicing an odd number of bytes corrupts sample alignment (high/low byte swap), turning all subsequent audio into harsh white noise and metallic screeching.
   - **Fix**: Ensure `StreamingPcmResampler` carries trailing odd bytes (`self._odd`) and all frame slicing enforces `len(chunk) % 2 == 0`.

---

# PHASE 18 — DUAL-RAIL ECHO GUARD

Inspect:
- `server/services/echo_guard.py`

Constants & Thresholds:
```python
BARGE_ECHO_OVERLAP = 0.55           # While agent is speaking
FINAL_ECHO_OVERLAP = 0.65           # Inside 350ms echo tail window
LISTENING_FINAL_ECHO_OVERLAP = 0.80 # Normal listening (drop near-exact copies only)
BARGE_FINAL_ECHO_OVERLAP = 0.85     # Post-barge final STT
PSTN_ECHO_TAIL_S = 0.35             # 350ms echo tail window
```
- Overlap ratio calculation: 35% unigrams + 65% contiguous bigrams.
- Compare incoming STT **ONLY** against `_tts_heard_text` (audio actually played). Never compare against unplayed generated text.
- **Legitimate Repetition**: Ensure that caller repetitions (e.g., Agent: *"Plots in Shamshabad"*, Caller: *"Shamshabad?"*) are NOT classified as echo. Evaluate recency, speech timing, and question pitch.

---

# PHASE 19 & 20 — BRAIN PROMPT & NATURAL CONVERSATIONAL BREVITY

Inspect:
- `server/brain/sections.py` (`STATIC_OUTPUT_RULES`, `default_section_seeds`)
- `server/prompts/agent_voice_rules.py` (`LANGUAGE_LOCK`, `NUMBER_RULES`, `PHONE_SPEAK_BAN`)
- `server/prompts/voice_defaults.py` (`VOICE_PIPELINE_PRESETS`, `OPENAI_MODEL_PRESETS`)

### Flexible Conversational Brevity:
> [!NOTE]
> A rigid character limit (e.g. `< 120 characters`) damages natural Telugu phrasing where Unicode character counts accumulate rapidly.
> **Enforce this conversational constraint instead**:
> - **1–2 concise spoken sentences**.
> - **Normally 8–25 words** in English / Tanglish.
> - **Concise equivalent length** for Telugu.
> - **Answer the user's immediate question first**.
> - **Avoid unnecessary explanations; never produce a monologue**.
> - Use character count only as a secondary safety clamp (e.g. 180 chars max), not as the primary conversation policy.

### Core Directives:
1. **Turn Priority**: Understand meaning → Answer concern first → Never re-ask known facts → ONE useful discovery field OR recommend + next step.
2. **Number Verbalization**: English cardinal words (`rupees fifty lakhs`, `two crore`, `ten AM`). Never raw digits or Indic numeral words.
3. **Phone Privacy**: Never recite phone numbers aloud; accept caller details gracefully.
4. **Latest Correction Wins**: Explicit user corrections overwrite prior memory immediately.
5. **Unified Stack**: Inbound and outbound MUST share identical brain prompt compilers and conversation policies.

---

# PHASE 21, 22 & 23 — DEV PANEL AS PSTN DIAGNOSTIC CONSOLE

Inspect:
- `web/components/dev/test-studio/PstnTestPanel.tsx`
- `web/components/dev/test-studio/LiveMediaFlowDebugger.tsx`
- `server/routes/dev_telephony.py`
- `server/services/pstn_media_flow.py`

Provide an actionable, real-time diagnostic console in the Dev Panel:

```
┌─────────────────────────────────────────────────────────────┐
│ PSTN CALL DIAGNOSTIC CONSOLE                                │
├─────────────────────────────────────────────────────────────┤
│ Direction:       INBOUND / OUTBOUND                         │
│ Call ID:         abc-123-uuid                               │
│ Telnyx ID:       v3:call_control_id                         │
│ Agent ID:        sales-rep-priya                            │
│                                                             │
│ TELNYX SIP:      🟢 Connected                               │
│ MEDIA WS:        🟢 L16 @ 16000Hz                           │
│ STT STREAM:      🟢 Streaming (Deepgram/Sarvam)             │
│ REALTIME LLM:    🟢 Ready (gpt-realtime-2.1-mini)           │
│ TTS STREAM:      🟢 Ready (Sarvam/Cartesia)                 │
│                                                             │
│ FSM PHASE:       SPEAKING                                   │
│ Turn ID:         t_14                                       │
│ Generation ID:   g_28                                       │
│                                                             │
│ Last User STT:   "Shamshabad lo plots unnaya?"              │
│ Last Agent Spoke:"Avunandi, twenty-five lakhs nunchi unnai."│
│                                                             │
│ LATENCY:                                                    │
│ Speech End → TTFT: 620 ms                                   │
│ Speech End → Audio: 890 ms                                  │
│ Barge Latency:     140 ms                                   │
│                                                             │
│ [ HANGUP CALL ]   [ PURGE QUEUE ]   [ RECONNECT SOCKETS ]   │
└─────────────────────────────────────────────────────────────┘
```

### Real-Time Event Timeline:
Expose chronological events with timing delta in `LiveMediaFlowDebugger.tsx`:
```
15:42:01.100  CALL_STARTED               direction=inbound
15:42:01.250  TELNYX_CONNECTED           control=v3:xyz
15:42:01.280  AGENT_RESOLVED             agent=sales-rep-priya
15:42:01.350  REALTIME_READY             session=rt-123
15:42:01.400  GREETING_STARTED           chars=54
15:42:02.100  GREETING_FINISHED          note_spoken=success
15:42:02.110  PHASE_LISTENING            fsm=listening
15:42:04.500  SPEECH_STARTED             partial="nenu"
15:42:05.100  STT_FINAL                  text="plot kosam chustunnanu"
15:42:05.650  TURN_CONFIRMED             coalesce_ms=550
15:42:05.720  LLM_STARTED                model=gpt-realtime-2.1-mini
15:42:05.840  LLM_FIRST_TOKEN            ttft_ms=120
15:42:05.900  TTS_STARTED                provider=sarvam
15:42:06.050  TTS_FIRST_AUDIO            first_audio_ms=150
15:42:07.200  SPEECH_STARTED             partial="wait"
15:42:07.320  BARGE_IN_CONFIRMED         hold_ms=120
15:42:07.340  TTS_CANCELLED              stopped=true
15:42:07.360  TELNYX_REMOTE_CLEARED      cleared=true
15:42:07.380  REALTIME_CANCELLED         cancelled=true
15:42:07.400  NEW_USER_TURN              turn_id=t_15
```

---

# PHASE 24 & 25 — FAILURE RESILIENCE & TEST VERIFICATION

Zero Unexplained Silence:
- If STT connection fails: log error, attempt safe reconnect, and surface failure in Dev Panel.
- If Realtime session drops: reconnect and restore history without re-greeting.
- If TTS synthesis fails: attempt cached audio fallback; never loop recursively into failing TTS.
- If WebSocket drops: clean up call FSM and transition to `PHASE_ENDED`.

### Automated Verification:
```powershell
python -m pytest `
  server/tests/test_barge_history_and_pstn.py `
  server/tests/test_pstn_production_fixes.py `
  server/tests/test_pstn_critical_loop.py `
  server/tests/test_pstn_voice_core.py `
  server/tests/test_pstn_media_flow.py `
  -v
```

> [!IMPORTANT]
> **All relevant existing tests must pass.**
> - Do not weaken or delete tests to achieve a passing result.
> - If tests fail because expected behavior was obsolete, update the test only when the new behavior is demonstrably correct and document the reason.

---

# PHASE 26 — END-TO-END PROOF & IMPLEMENTATION REPORT

After making changes, do not stop at unit tests.

Perform a complete audit of both call directions.

## INBOUND TEST

Verify:
1. Caller dials the Telnyx number.
2. Telnyx answers successfully.
3. Media WebSocket connects.
4. Agent is resolved.
5. `call_id` is created.
6. Realtime session reaches `READY`.
7. STT reaches `STREAMING`.
8. Greeting audio is actually emitted to Telnyx.
9. Caller speech reaches STT.
10. Final transcript creates exactly one user turn.
11. OpenAI Realtime produces response tokens.
12. TTS produces audio.
13. Audio reaches Telnyx wire without cracks or chirping.
14. Caller hears the response.
15. Caller can interrupt the agent.
16. Barge-in stops local and remote playback within 180ms.
17. OpenAI generation is cancelled immediately.
18. The caller's interrupted utterance becomes the next turn.
19. Conversation history contains only audio actually heard (`_tts_heard_text`).
20. Call can continue for multiple turns without degradation.

## OUTBOUND TEST

Verify the same complete sequence for:
```
Developer Panel
  ↓
POST /api/dev/telephony/telnyx/dial
  ↓
Telnyx outbound call initiated
  ↓
Callee answers
  ↓
Media WebSocket connects
  ↓
Agent initialization & call_id creation
  ↓
Opening greeting plays
  ↓
STT streaming active
  ↓
Realtime LLM turn generation
  ↓
TTS streaming audio
  ↓
Smooth RTP playback (no buffer under-run cracks)
  ↓
Barge-in on caller interruption
  ↓
Multiple conversational turns
  ↓
Clean hangup & ledger finalization
```

## FAILURE TESTS

Explicitly test and verify:
- Realtime connection failure (graceful error handling, no silent hang)
- Realtime timeout (clean error recovery)
- STT disconnect (upstream socket drop surfaced in Dev Panel)
- TTS failure (fallback audio path / provider retry, no infinite loop)
- Telnyx WebSocket disconnect (clean transition to `PHASE_ENDED`)
- Telnyx playback clear failure (fallback to local buffer drain)
- Caller speaks during greeting (`_intro_queue` buffering, no echo feedback)
- Caller interrupts within first 350ms (ramp protection vs early barge-in)
- Caller says `"Wait"` (short interruption pattern matches and triggers barge)
- Caller says `"No"` (short interruption triggers barge)
- Caller says `"కాదు"` (Telugu short negation triggers barge)
- Caller says `"లేదు"` (Telugu short negative triggers barge)
- Caller says `"Shamshabad?"` (legitimate repetition not dropped by echo guard)
- Caller says `"yeah"` (backchannel ignored during `PHASE_THINKING`)
- Caller says `"ok"` (backchannel ignored during `PHASE_THINKING`)
- Caller speaks while LLM is thinking (Think-Cancel aborts generation and merges transcript)
- Caller speaks while TTS is streaming (immediate barge-in, queue drain, generation invalidated)
- Duplicate/repeated webhook events (atomic idempotency claim in `telnyx_call_registry`)
- Realtime reconnect mid-call (state restored, greeting skipped if already spoken)
- Call termination during generation (in-flight tasks cancelled cleanly)

## LATENCY MEASUREMENT

Measure actual timestamps for:
```
speech_start
  ↓
speech_end
  ↓
STT_final
  ↓
turn_confirmed
  ↓
LLM_first_token
  ↓
TTS_started
  ↓
TTS_first_audio
  ↓
Telnyx_first_audio
```

Also measure:
```
caller_speech_start
  ↓
confirmed_barge
  ↓
local_audio_stop
  ↓
remote_queue_clear
  ↓
OpenAI_cancel
```

> [!NOTE]
> **Do not claim latency improvements without measurements.**

## FINAL REPORT

After implementation, document:
1. **Root causes actually confirmed** (verified with code and runtime logs).
2. **Root causes that were disproved** (hypotheses shown not to be the issue).
3. **Files changed** (exact repository paths).
4. **Exact behavior changes** (before vs after).
5. **Final VAD/endpointer values** (`PSTN_LISTEN_COALESCE_S`, partial grace, extensions).
6. **Final barge-in values** (hold duration, immunity ramp window, debounce).
7. **Final echo thresholds** (unigram/bigram overlap weights, echo tail window).
8. **Realtime session configuration** (model, modalities, token limit, tool schema).
9. **Inbound test result**.
10. **Outbound test result**.
11. **Failure-injection test results** (outcomes across all 19 test cases).
12. **Latency measurements** (measured millisecond deltas).
13. **Full pytest results** (passing test count and suite status).
14. **Any remaining known limitations**.

> [!CAUTION]
> **Environment Verification vs Live PSTN**:
> If a real PSTN call cannot be executed from the development environment (e.g. lack of active Telnyx SIP trunk credentials or public webhook tunneling), **clearly state that** and distinguish automated verification from unverified real-world carrier behavior.
> **Do not claim the PSTN call is fixed unless the available evidence supports that conclusion.**

---

# FINAL ACCEPTANCE CRITERIA

The task is complete only when:
1. Inbound calls are answered automatically (if required by Telnyx contract) and media stream starts cleanly.
2. Inbound calls resolve the default agent and always initialize `call_lifecycle_service.start()`.
3. The opening greeting always plays aloud over PSTN and is never skipped.
4. Realtime history receives greeting context so Turn 1 never repeats the greeting.
5. Reconnecting mid-call restores conversation state without duplicate greetings.
6. Endpoint detection is tuned so natural pauses do not prematurely cut off caller speech.
7. Early barge-in is allowed while protecting against TTS startup ramp feedback.
8. Agent stops talking within 180ms of confirmed barge-in; local and Telnyx remote buffers are purged.
9. Think-Cancel aborts active LLM generation if caller speaks during `PHASE_THINKING`.
10. The agent delivers concise, natural responses (1–2 sentences, 8–25 words / concise Telugu equivalent) in Telugu/Tanglish or English.
11. Voice audio over PSTN is crisp, natural, and free of 50Hz resampling clicks, high-frequency aliasing chirps, or sentence-boundary pops.
12. Dev Panel displays live call diagnostic status and real-time event timeline.
13. All 19 failure scenarios are accounted for and resilient against silence/dead air.
14. All relevant unit and integration tests pass without weakened assertions.
15. End-to-end verification report distinguishes automated regression passes from live carrier PSTN testing.


# PHASE 26 — END-TO-END PROOF & IMPLEMENTATION REPORT

After making changes, do not stop at unit tests.

Perform a complete audit of both call directions.

## INBOUND TEST

Verify:

1. Caller dials the Telnyx number.
2. Telnyx answers successfully.
3. Media WebSocket connects.
4. Agent is resolved.
5. call_id is created.
6. Realtime session reaches READY.
7. STT reaches STREAMING.
8. Greeting audio is actually emitted to Telnyx.
9. Caller speech reaches STT.
10. Final transcript creates exactly one user turn.
11. OpenAI Realtime produces response tokens.
12. TTS produces audio.
13. Audio reaches Telnyx.
14. Caller hears the response.
15. Caller can interrupt the agent.
16. Barge-in stops local and remote playback.
17. OpenAI generation is cancelled.
18. The caller's interrupted utterance becomes the next turn.
19. Conversation history contains only audio actually heard.
20. Call can continue for multiple turns without degradation.

## OUTBOUND TEST

Verify the same complete sequence for:

Developer Panel
→ /api/dev/telephony/telnyx/dial
→ Telnyx outbound call
→ callee answers
→ media WebSocket
→ agent initialization
→ greeting
→ STT
→ Realtime
→ TTS
→ playback
→ barge-in
→ multiple conversational turns
→ hangup.

## FAILURE TESTS

Explicitly test:

- Realtime connection failure
- Realtime timeout
- STT disconnect
- TTS failure
- Telnyx WebSocket disconnect
- Telnyx playback clear failure
- caller speaks during greeting
- caller interrupts within first 350ms
- caller says "Wait"
- caller says "No"
- caller says "కాదు"
- caller says "లేదు"
- caller says "Shamshabad?"
- caller says "yeah"
- caller says "ok"
- caller speaks while LLM is thinking
- caller speaks while TTS is streaming
- duplicate/repeated webhook events
- Realtime reconnect
- call termination during generation

## LATENCY MEASUREMENT

Measure actual timestamps for:

speech_start
→ speech_end
→ STT_final
→ turn_confirmed
→ LLM_first_token
→ TTS_started
→ TTS_first_audio
→ Telnyx_first_audio

Also measure:

caller_speech_start
→ confirmed_barge
→ local_audio_stop
→ remote_queue_clear
→ OpenAI_cancel

Do not claim latency improvements without measurements.

## FINAL REPORT

After implementation report:

1. Root causes actually confirmed.
2. Root causes that were disproved.
3. Files changed.
4. Exact behavior changes.
5. Final VAD/endpointer values.
6. Final barge-in values.
7. Final echo thresholds.
8. Realtime session configuration.
9. Inbound test result.
10. Outbound test result.
11. Failure-injection test results.
12. Latency measurements.
13. Full pytest results.
14. Any remaining known limitations.

If a real PSTN call cannot be executed from the environment, clearly
state that and distinguish automated verification from unverified
real-world behavior.

Do not claim the PSTN call is fixed unless the available evidence
supports that conclusion.


USE WHATEVER FIX MAKE THE PSTN FLOW GOOD CHECK WEB FOR BETTER IMPLEMENTATION FOR THIS PSTN +WEB AGENT FLOW TO WORK.