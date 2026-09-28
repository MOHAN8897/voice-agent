# Telecaller audit and implementation plan

Date: 28 September 2026

Revision: second review, including the requested separation of core brain, language instructions, and business script.

**Status: checklist items B1–B8, C1–C5 (code paths), A1–A6, Phase 4 pytest repairs, and section 5 core compile/render unification are implemented locally (28 Sep 2026).** See section 6 for limits. Still outstanding: persisted structured artifact on all stores, section 7 live PSTN evidence, bulk DB brain republish, `audioop` migration plan.

## Requested design and expected outcome

**Yes: separating these parts is the right direction.** Each call should receive one shared core, exactly one selected language pack, and the relevant business script, with a small provider/tool section and call context. Shared rules must have one owner instead of being repeated in each part.

This should make the prompt smaller and easier to validate. Merely splitting files will not help if the compiler still sends duplicate or conflicting instructions. It also will not fix duplicate dialing, slow startup, audio pacing, or false interruptions by itself. Those fixes remain part of this plan.

Read sections 1–4 for findings and evidence, section 5 for the new brain design, section 6 for the complete implementation checklist, and section 7 for verification.

## Main findings in simple words

There are real problems in the current code and saved call configuration. The strongest findings are:

1. **A Telugu call contains English speaking instructions.** This is present in an actual saved call brain and survives conversion into the Gemini prompt.
2. **The brain says never change language, while the call handler can ask the model to change language.** Even a place name or Romanized Telugu can trigger the wrong language guess.
3. **Startup is slow even when the system prepared the agent in advance.** Five recent answered calls took 3.234–5.719 seconds from answer to the first audio frame sent to Telnyx.
4. **Duplicate-call protection has gaps.** It is not a durable, shared “one user request = one call” mechanism.
5. **The audio sender has timing and monitoring weaknesses.** These can expose pauses in model output as audible gaps, but the recordings need a controlled listening comparison to establish the exact cause of the reported glitches.
6. **Seven advertised languages currently fall back to Hindi instructions.** The second review reproduced this for Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, and Punjabi. See B8.

**The exact “first call silent, second call works” incident is not conclusively identified.** The available log contains six outbound API requests and six dial operations, rather than evidence of one request being automatically dialed twice. A second dial occurs one second after a hangup, but it has its own incoming API request. The log cannot tell whether that request came from another click, client retry, or another browser session.

This document records the investigation and the work required to resolve it. Application code and live configuration have not been changed as part of this document update, and no new phone calls were placed.

## What I checked and what the evidence means

- Followed the Graft graph into script compilation, saved brains, runtime prompt assembly, outbound dialing, Telnyx webhooks, prewarming, Gemini voice, audio playback, and the separate TTS pipeline.
- Inspected the actual brains and metadata of five recent calls: two Telugu and three English (US).
- Examined `data/dev-logs/api.log`, relevant tunnel errors, and call trace metadata.
- Ran 109 focused existing tests: **104 passed, 5 failed**. Details are below.
- Ran small offline probes for language guessing, language realignment, prompt contradictions, Gemini settings, and duplicate-call lookup.
- Checked official OpenAI, Google, Telnyx, Sarvam, and Cartesia guidance online.

“Confirmed” below means visible in code, reproduced offline, or recorded in the available logs. It does **not** automatically mean it caused the particular call you heard. “Risk” means the code permits a failure under stated conditions. No audio listening evaluation or fresh end-to-end call was performed. The sample does not establish what happens in every non-English language.

The recent calls use **Gemini `gemini-3.8-live`, with `pipeline=realtime_voice`**. Gemini generates the voice directly. Sarvam STT/TTS entries still appear in the saved stack, but those entries alone do not mean Sarvam generated this call's live speech. See `data/calls/7778252e-1112-4d4a-a21f-684d2b1d5db1/meta.json:16–46` and `server/services/pstn_realtime_voice_core.py:1438–1493`.

“Industry standard” here means applicable provider requirements and sensible production reliability practices, not a formal certification or one universal telecaller specification.

## 1. Brain and script problems

### B1 — Telugu language tag, English script instructions

**Priority: High. Confirmed in a real call and an offline prompt reconstruction.**

The saved Telugu call `7778252e-1112-4d4a-a21f-684d2b1d5db1` contains:

- `@language: te-IN` and a Romanized Telugu opening in the entity tags.
- An English opening under `CANONICAL OPENING`.
- `Speak this way: English (US), clear and professional.`

The effective Gemini prompt reconstructed from this brain contains both the English instructions and the instruction to speak only Telugu. There are therefore two competing descriptions of what the agent should say.

**Why it sounds unnatural:** the agent may start in one language, borrow English phrasing, or follow the wrong opening. This is a language and conversation defect; it does not by itself prove digital audio crackling.

**Cause:** language realignment updates tags and a section header. It does not rebuild all language-dependent opening, role, style, and policy text.

**Evidence:** saved call `meta.json:13`; `server/brain/script_entities.py:193–241,244–274`; `server/realtime/gemini_audio_session.py:251–309`.

**Fix:** create one complete language-specific brain before dialing. Check that the greeting, entity tags, script, style, and final model prompt agree. Reject mixed configurations instead of only changing their labels.

### B2 — “Never switch language” conflicts with runtime language switching

**Priority: High. Confirmed in code; a language-switch event is also logged.**

The platform and Gemini prompts forbid language switching. However, `_maybe_mirror_caller_language()` can queue an instruction telling the model to reply in another language from then on. It is called during normal caller-transcript processing.

The language detector counts writing systems. In an offline probe, all three inputs below were classified as English for a Telugu agent:

- `Hyderabad`
- `naaku car service kavali`
- `okay thanks`

A city name, Telugu written in English letters, or a short acknowledgment is not reliable proof that the caller wants English. The actual Telugu call logs `realtime_voice.mirror_language` to `en-IN`.

**Evidence:** `server/agent/language_resolver.py:20–40`; `server/services/pstn_realtime_voice_core.py:1272–1289,2691–2693`; `server/brain/sections.py:78`; `data/dev-logs/api.log:295`.

**Fix:** choose one policy: a fixed language with a handoff, or intentional multilingual switching. Apply that policy consistently. Do not switch from names, greetings, short acknowledgments, or Latin letters alone. Official OpenAI guidance recommends clear language rules and avoiding switches based on isolated words. [OpenAI voice prompting](https://developers.openai.com/api/docs/guides/voice-prompting)

### B3 — The brain gives opposite instructions about speaking after goodbye

**Priority: High. Confirmed.**

One static rule says to keep talking if the caller speaks after farewell. Other instructions say to stop after farewell because the platform disconnects. The runtime also stops accepting input after `_farewell_complete`.

**Caller impact:** “wait, one more thing” may be handled differently depending on which rule or timing wins.

**Evidence:** `server/brain/sections.py:102`; `server/brain/agent_script_compiler.py:1619–1622`; `server/services/pstn_realtime_voice_core.py:1031–1073,1593–1595`. The contradictory static text also survives the reconstructed Gemini prompt.

**Fix:** define one closing policy: allow meaningful interruption before the final disconnect is committed; after actual disconnect, the conversation is over. Use the same policy in the prompt, controller, and tests.

### B4 — Script completion can compete with listening to the caller

**Priority: Medium. Confirmed prompt conflict/risk.**

Platform rules tell the agent to resume the next open script objective after answering. Spoken-style rules can tell it to answer and stop without adding a qualification question. There is also a strong instruction to work through all objectives, alongside instructions to stop when enough information is collected.

**Caller impact:** the agent can sound like a checklist, ask an unnecessary question, or stop progressing because it is unsure which instruction wins.

**Evidence:** `server/brain/agent_script_compiler.py:1393–1400,1606–1616`; `server/brain/sections.py:77–86,94–99`; saved call `meta.json:13`.

**Fix:** explicitly rank the decisions: respect stop/refusal; answer the caller; use already-known facts; ask one relevant missing question only when needed; close after an agreed outcome. Distinguish required business facts from optional discovery questions.

### B5 — The script checker does not catch these contradictions

**Priority: High. Confirmed by an offline probe.**

`validate_agent_script()` checks things such as placeholders, identity, some invented amounts, and section shapes. A sample saying “Speak only English. Speak only Telugu.” returned **no validation issues**.

This does not mean every publishing route lacks validation: the versioned-brain publisher has separate section and optimizer checks. It means this script validator cannot guarantee a coherent final runtime prompt.

**Evidence:** `server/brain/agent_script_compiler.py:1060–1125`; `server/brain/compiled_brain_service.py:98–143`.

**Fix:** validate the final assembled prompt, not just the visible script. Add deterministic checks for language, opening, direction, closing policy, and available tools, plus realistic conversation evaluations. OpenAI specifically recommends auditing conflicting instructions and keeping tool references aligned with actual tools. [OpenAI voice prompting](https://developers.openai.com/api/docs/guides/voice-prompting)

### B6 — Phone-number confirmation is banned even when clarification is useful

**Priority: Medium. Confirmed design limitation.**

The brain repeatedly says never read phone digits back. Avoiding unnecessary repetition is good, but an absolute ban prevents a normal clarification when the caller supplies a different callback number and recognition is uncertain.

**Evidence:** `server/brain/agent_script_compiler.py:1573,1581`; `server/brain/sections.py:95`.

**Fix:** keep the dialed number as the default. When a caller supplies or corrects another number, confirm only the uncertain part or ask permission to confirm it. Do not read the known number on every call.

### B7 — The compiler can add repeated rules simply to reach a cache threshold

**Priority: Medium. Confirmed conditional behavior, not measured as a cause in these calls.**

If the brain is below the cache minimum, `_ensure_cache_floor()` repeatedly appends static rules and the spoken-language pack, up to eight iterations.

**Why this matters:** repetition makes contradictory rules harder to maintain and can make the agent overly rigid. A cache target is not evidence that extra instructions improve conversation quality.

**Evidence:** `server/brain/agent_script_compiler.py:2116–2152`.

**Fix:** keep a concise, stable shared prefix. Evaluate caching and response quality separately; do not add repeated behavioral instructions solely to increase prompt length.

### B8 — Seven supported languages receive Hindi-only instructions

**Priority: High. Newly confirmed during the second review by source inspection and an offline probe.**

The product lists 11 supported locales, but `SPOKEN_PACKS` contains only Telugu, Hindi, English (India), and English (US). For `ta-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, and `pa-IN`, the current `spoken_pack_for()` returns the Hindi pack. The runtime footer also describes the agent as Hindi-speaking and requires Hindi/Hinglish, even while labeling the selected language as Tamil, Kannada, or another requested locale.

**Caller impact:** a caller can select one language while the actual model instructions demand another. This is a confirmed cause of contradictory language configuration, not proof that it causes every audible glitch.

**Evidence:** `server/prompts/agent_voice_rules.py:488,719–737`; supported locale registry in `server/config/constants.py`. The offline probe checked all 11 supported locales and reproduced the Hindi fallback for all seven listed above.

**Fix:** provide and validate a dedicated pack for every enabled locale. Derive the UI and backend availability from the same validated registry. If a pack or provider/language combination is missing, return a clear unsupported-configuration error before dialing; never silently substitute Hindi or Telugu. Test the generated final prompt and localized speech samples for each locale.

## 2. Why the first call can be quiet, and why another call can appear

### What the recent logs actually show

Times below are as written in the local API log, consistent with IST. Destination numbers are intentionally omitted.

- **12:22:42:** dial to destination A. Answered 12:22:53. First outgoing audio at 12:22:57: **4.045 seconds after answer**. Hung up at 12:23:45.
- **12:23:46:** another dial to destination A. There is a separate outbound API request. This call has no answered event in the inspected log and ends with a timeout at 12:24:48.
- **12:24:00:** dial to destination B. Answer-to-first-audio: **3.234 seconds**.
- **12:25:14:** next dial to destination B. Answer-to-first-audio: **3.953 seconds**.
- **12:26:12:** dial to destination A. Answer-to-first-audio: **3.705 seconds**.
- **12:27:35:** next dial to destination A. Answer-to-first-audio: **5.719 seconds**.

Evidence: `data/dev-logs/api.log:140,179,231,497,529,553,615,620,643,696,953,1179,1181,1206,1262,1613,1625,1704,1754,2123,2126,2154,2215`.

These timings measure when the application sent the first audio frame, **not when speech became audible on the handset**. Some delay may also include waiting for pickup speech. Nevertheless, several seconds of silence is a real startup experience to improve.

Six incoming outbound requests are logged at lines **145,553,620,1181,1625,2126**, matching six dial operations. This is stronger evidence for separate requests in this sample than for an internal automatic redial. It does not identify who or what initiated each request.

### C1 — Preparing the greeting can still block the answered call

**Priority: High. Confirmed code path and observed latency.**

The system prepares a live session and a separate Gemini greeting session. If preparation is unfinished when the person answers, adoption can wait up to **12 seconds**. The greeting preparation in recent logs takes roughly 9–11 seconds from dial.

**Caller impact:** the phone is connected, but the application is still getting the agent ready.

**Evidence:** `server/services/pstn_prewarm.py:19,175–217,396–458`; `data/dev-logs/api.log:1227,1657,2182`.

**Fix:** prepare and validate the greeting before the dial where practical, retain a ready session, and put a short explicit limit on post-answer initialization. Use a coherent ready-state fallback on the same call if preparation fails. Do not solve startup failure by placing another call.

### C2 — Prepared sessions are discarded or reconnected at answer time

**Priority: High. Confirmed in logs; one underlying mismatch is visible in code.**

The logs contain both `prewarm.stale_brain` and `realtime_voice.prewarm.reconnect`. Some stale-brain events report the same version label on both sides (`session-v3`).

One concrete mismatch: prewarm hashes the **realigned** brain, while the adoption check hashes the text returned directly by the brain lock. If realignment changes the text, the comparison can reject a session even though the source version did not change. Separately, the live startup reconnects Gemini when the final instruction string differs from the prepared one. Prewarm can replace its greeting text with the generated transcript, another possible source of string differences.

**Evidence:** `server/services/pstn_prewarm.py:251–291,365–376,483–485,523–528`; `server/services/pstn_realtime_voice_core.py:1495–1513`; `data/dev-logs/api.log:196,664,1238,1730,2192`.

**Fix:** build one immutable call configuration and compare the same normalized brain and instructions at both stages. Keep intended greeting text separate from the generated transcript. Log a safe reason/diff category when a reconnect is necessary.

### C3 — Duplicate-call protection does not cover multiple workers reliably

**Priority: High. Confirmed architectural gap; not proven to explain these six dials.**

The outbound lock is an in-memory dictionary protected by an `asyncio.Lock`. It prevents simultaneous requests in one process. Two server workers can each accept the same destination before either sees a registered call.

The slot is released when the outbound request finishes. There is no persistent request ID in this flow that makes a repeat of the same user action return the original result after hangup or an uncertain response.

**Evidence:** `server/services/outbound_dial_guard.py:52–62,103–116`; `server/routes/dev_telephony.py:279–319,541–560`; `server/services/saas/telephony_orchestrator.py:190–207`.

**Fix:** persist a dial-attempt ID and use a shared atomic claim before contacting the carrier. Repeating the same request ID must return its original call/result. A deliberate new call gets a new request ID. Reconcile uncertain carrier responses instead of blindly redialing.

The current Telnyx client already makes only one attempt for `POST /calls`; that protection should be retained (`server/services/telnyx_client.py:65–91`). Provider command deduplication is useful where supported, but should not be assumed to replace application-level dial tracking. [Telnyx command retries](https://developers.telnyx.com/docs/voice/programmable-voice/command-retries)

### C4 — The existing-call lookup can miss or confuse calls

**Priority: High under concurrency. Confirmed with offline probes.**

- It checks only the 20 most recently updated calls. An active call outside those 20 is missed; the probe reproduced this.
- It compares only the last ten digits, discarding country-code distinctions. Different international numbers can collide.
- The matching key has no tenant/agent scope, so different customers or agents calling the same destination can interfere with reuse decisions.
- `list_recent()` prefers an existing local row over a Redis row with the same ID, so it can use stale state from another worker.

**Evidence:** `server/services/outbound_dial_guard.py:56–62,119–137`; `server/services/telnyx_client.py:531–555`.

**Fix:** use an exact, normalized E.164 destination and explicit ownership scope. Maintain a shared active-call index instead of searching a recent-history page. Define any global “do not call this destination concurrently” rule separately from call reuse.

### C5 — Media events and telephone-call state are mixed together

**Priority: High. Confirmed design risk.**

The webhook initially writes `status` from every event name. Events such as recording completion are not call lifecycle states. A clean `streaming.stopped` can also be treated as a normal end without first proving the telephone leg ended.

The duplicate guard treats `stream-stopped` and `stream-error` as terminal. That means an answered phone leg with broken media can be excluded from reuse. Another outbound request could then create another call while the original leg is unresolved.

**Evidence:** `server/routes/telnyx.py:452–460,610–667`; `server/services/outbound_dial_guard.py:20–34,65–69`. An offline check confirms that `recording.saved` and `stream-stopped` are not recognized as active.

**Fix:** keep separate states for the telephone leg, media connection, and recording. Use webhook event IDs and timestamps to handle repeats and old events. Recover or explicitly end the existing leg when its media dies. Telnyx documents duplicate and out-of-order delivery. [Telnyx webhook handling](https://developers.telnyx.com/docs/development/api-fundamentals/webhooks/receiving-webhooks)

### What is already protected

- Telnyx dial HTTP timeouts are not automatically retried.
- Media normally starts on answer, not during ringing.
- Answer events have a claim/deduplication mechanism, including Redis when available.
- The test panel has in-flight click locks.
- Voice-start exceptions attempt to hang up the failed call.

Evidence: `server/services/telnyx_client.py:65–91,482–511`; `server/routes/dev_telephony.py:542–548`; `web/components/dev/test-studio/PstnTestPanel.tsx:441–528`; `server/services/telnyx_pstn_bridge.py:618–662`.

These existing protections are why it would be inaccurate to claim the current code simply retries every dial twice.

## 3. Why non-English voice can glitch

Start with B1 and B2: the non-English path has proven language conflicts that the English path does not encounter in the same way. Then investigate the audio issues below. “Wrong language,” “unnatural pronunciation,” “mid-sentence cancellation,” and “missing audio packets” need different fixes.

### A1 — Some voice settings shown in configuration do not reach Gemini

**Priority: High. Confirmed by code and an offline configuration probe.**

The saved phone profile requests semantic VAD, high eagerness, far-field noise reduction, and 250 ms silence. In the Gemini adapter:

- `noise_reduction` and `speed` are accepted but explicitly ignored.
- The `semantic_vad` path is mapped to Gemini automatic activity detection with a start sensitivity. It does not configure the same semantic endpointing behavior implied by that name.
- `silence_ms` is applied in the `server_vad` branch, but not in this semantic branch. The probe confirms the outgoing configuration has no silence-duration field.

**Impact:** tuning a setting may appear to work in the UI while doing nothing for the active provider. **Do not assume the saved 250 ms is the actual Gemini endpointing threshold.**

**Evidence:** `data/saas_universal_phone_stack.json`; `server/realtime/providers/gemini_voice.py:75–95,171–188,219–228`.

**Fix:** expose provider-specific controls and record their effective values. Google currently recommends approximately 500–800 ms for automatic VAD silence duration; tune against real conversations rather than applying the same setting blindly to every provider. Native Gemini audio selects its language from context rather than an explicit language-code setting, making clean prompts especially important. [Google Live API capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)

### A2 — A loud sound can cut off the agent before speech is confirmed

**Priority: High. Confirmed mechanism; false triggering in these recordings is not proven.**

During agent playback, local input is checked using loudness and consecutive-frame thresholds. Crossing the threshold calls `_commit_local_barge()`, which clears/interrupts audio immediately. A loud echo or background sound can resemble a caller interruption. A quiet caller may instead be held back.

The logs contain several `realtime_voice.barge_open` events in both Telugu and English calls. Those events prove the mechanism fired, not that each interruption was wrong.

**Evidence:** `server/services/pstn_realtime_voice_core.py:1148–1174,1630–1658`; `data/dev-logs/api.log:309,371,390,465,1833,1864,2328`.

**Fix:** test quiet callers, speakerphone echo, traffic, and real interruptions. Use echo-aware speech detection and preserve a small amount of audio from before the trigger so the first syllable is not lost. Do not simply disable interruptions: callers must still be able to stop the agent.

### A3 — The sender's clock can drift and model-output pauses pass through directly

**Priority: High. Confirmed implementation weakness; contribution to these glitches needs measurement.**

The sender takes a 20 ms frame, sends it, performs bookkeeping, then sleeps another 20 ms. Thus each interval includes the send and processing time as well as the sleep. It does not schedule against an absolute audio clock. It also starts with the first available frame without a startup/rebuffer target in this worker.

**Impact:** queue buildup, slower delivery, or audible gaps when the provider supplies audio unevenly. If output cadence differs by language, the same weak playback strategy can expose one language's gaps more strongly. That last explanation is a hypothesis to measure, not an established language-specific defect.

**Evidence:** `server/services/telnyx_pstn_bridge.py:885–978`.

**Fix:** schedule from a monotonic playback deadline, measure queue depth and send lateness, and tune a small bounded buffer with an explicit interruption policy. Telnyx permits a range of RTP chunk sizes; the application’s chosen 20 ms frame size is valid and is not itself the bug. [Telnyx media streaming](https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming)

### A4 — A zero underrun counter does not currently prove smooth playback

**Priority: Medium. Confirmed monitoring gap.**

The code initializes and displays `playout_underrun_count`, but the current outbound worker does not increment it when it runs out of frames. An exhaustive indexed search found initialization/reporting and test increments, not a production increment in this sending path.

The inspected realtime trace also has empty latency fields such as `tts_first_audio_ms` and `e2e_ms`. This makes language comparisons harder.

**Evidence:** `server/services/telnyx_pstn_bridge.py:138,772–785,885–995`; `server/services/pstn_voice_core.py:930–950`; `data/calls/7778252e-1112-4d4a-a21f-684d2b1d5db1/trace.json`.

**Fix:** count unexpected queue-empty periods only while speech is still expected. Record provider audio arrival gaps, send lateness, interruption reasons, and first-audio timing. Separate normal end-of-speech silence from an underrun.

### A5 — The cached opening discards the caller's first words

**Priority: Medium. Confirmed behavior.**

While the deferred greeting is armed, the first caller audio is used for local energy detection and archived, but not sent to the model. Greeting-protected audio is also withheld. Later, greeting completion clears pickup text and input audio.

**Caller impact:** “Hello, I'm busy” or “Who is this? Don't call again” can be treated merely as permission to start the introduction. This feels deaf or scripted and is not specific to any one language.

**Evidence:** `server/services/pstn_realtime_voice_core.py:1599–1629,3203–3215`.

**Fix:** retain and interpret meaningful pickup speech. Suppress duplicate greetings, not the caller's intent. Refusal or an urgent interruption should take precedence over a canned opening.

### A6 — Separate TTS-path risk: partial speech timeout

**Priority: Medium. Confirmed conditional code behavior; not reproduced as a live incident.**

This is relevant to calls using Sarvam/Cartesia TTS, **not established as the cause of the recent Gemini direct-voice calls**.

`PstnTurnTtsSession.finish()` waits 12 seconds for completion, but marks timeout as an error only when no audio has arrived. If part of a reply arrived, an incomplete synthesis can be treated as finished without the same error signal. A later turn resets the reader state.

Evidence: `server/services/pstn_turn_tts.py:300–322,342–357,425–491`.

Use explicit completion/context tracking and report a partial timeout distinctly. Sarvam documents a flush/completion lifecycle, and Cartesia documents context and flush identifiers for associating text with generated audio. [Sarvam streaming API](https://docs.sarvam.ai/api-reference/text-to-speech/stream), [Cartesia context flushing](https://docs.cartesia.ai/api-reference/tts/working-with-web-sockets/context-flushing-and-flush-i-ds)

### Things I did not establish as causes

- A provider-wide Gemini outage or a defect affecting every non-English language.
- Sarvam/Cartesia synthesis causing these Gemini direct-voice glitches.
- A codec mismatch in the sampled calls: the logs show L16/16 kHz and 640-byte frames, consistent with the application's 20 ms PCM framing.
- A stateless resampler causing these calls to click: the inspected active voice output path uses a stateful resampler.
- The tunnel errors proving live-call audio failure: the inspected errors concern HTTP playback of saved recordings, not proof of failure of the live Telnyx media WebSocket.

## 4. Test results and their limits

**After implementation pass: 169 audit-related pytest cases passed** (same modules as below plus `test_brain_prompt_validate`, `test_outbound_dial_guard`, extended `test_pstn_realtime_voice`). Original baseline: **109 tests ran: 104 passed, 5 failed.** Tests use local doubles; they do not certify audible quality over the telephone network.

First group: **59 passed** across Gemini PSTN regressions, PSTN production fixes, brief/script compilation, Gemini script adherence, and TTS resampling.

Second group: **45 passed, 5 failed** across the call controller, Telnyx bridge, prewarm, greeting prewarm, and natural sales brain.

Failures:

1. `test_call_controller.py::test_structured_refusal_overrides_callback_and_waits_for_goodbye` — expects a further wait after goodbye; current code disconnects when farewell handling finishes. This exposes disagreement between the test and current closing policy, not proof that the live carrier cut off a farewell.
2. `test_call_controller.py::test_silence_prompts_once_then_soft_ends` — expects a nudge at 5 seconds; runtime uses configurable timing with an 8-second default. The test does not pin that setting.
3. `test_call_controller.py::test_user_resumes_before_disconnect` — expects a speech-start event to reopen a closing call; the controller remains ending. Decide the intended interruption policy and test it with actual meaningful speech and audio-drain state.
4. `test_pstn_prewarm.py::test_stale_brain_keeps_buffered_greeting` — its mock returns two values, but the implementation expects three. The resulting exception prevents this test from checking the intended stale-brain behavior.
5. `test_pstn_realtime_greeting_prewarm.py::test_gemini_side_session_greeting_closes_throwaway_adapter` — expects the old exact instruction string; the implementation now appends a language instruction.

There is also an `audioop` deprecation warning under Python 3.12. It is a future compatibility concern, not evidence for the current language glitches.

## 5. New brain design: core + one language + business script

### 5.1 What belongs in each part

**Core brain — shared across languages and businesses.** Owns truthful behavior, answering the caller before progressing, remembering known details, avoiding repeated questions, handling corrections, respecting refusal, and the single closing policy. It says how to conduct a call. It must not contain a business's prices, an English greeting, a Telugu-only rule, or another language's examples.

**Language pack — exactly one per call.** Owns the selected language and script, natural phrasing, pronunciation guidance, permitted everyday borrowed words, number/date/currency pronunciation, and short localized phrases for acknowledgment, unclear audio, callback, and farewell. Code mixing must be explicitly defined for that locale; accepting a familiar English business word is different from switching the whole conversation to English. Currency comes from business facts, not the language's country.

Required packs: `te-IN`, `hi-IN`, `ta-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN`, `en-IN`, and `en-US`. Each enabled pack needs a complete set of phrases and behavior checks. Treat these as separate locale variants even when two share English. Future languages must meet the same checks before appearing as available.

**Business script — business facts and objectives.** Owns agent/company identity, approved services, prices and policies when supplied, caller-facing disclosures, required versus optional questions, objections/FAQ, and valid next steps. Keep one source of business truth. Store language-specific spoken openings and any required translated wording as variants of that source, not unrelated copies of the whole brain. Never invent prices, benefits, booking availability, or successful follow-up actions during translation or compression.

**Provider/tool contract — a small technical section.** Contains only instructions needed by the actual model, audio mode, and tools available on that call. Realtime voice and text-to-TTS need different output details; they must share the same language and conversation policy. Define the closing policy once and map it to the real tool names without appending another contradictory closing story.

**Call context — small changing state.** Contains call direction, whether the opening has been delivered, known caller details, completed objectives, and the selected published version. Do not repeat the full script every turn. Caller data must not override the platform's language/tool permissions or business facts.

The logical result is:

```text
FINAL MODEL INSTRUCTIONS
  1. Shared core behavior
  2. Selected language pack (one locale only)
  3. Business facts + objectives + selected spoken script
  4. Actual provider/output/tool contract
  5. Minimal call context
```

These are sections of one validated instruction set. They do not require five model calls. Internal instructions can use clear English where effective; all text intended to be spoken must match the selected language policy. Do not send the other ten language packs to the model.

### 5.2 One compiler must serve every entry point

Create a structured compiled artifact rather than modifying language labels in a long string. Proposed fields include `schema_version`, `core_version`, `language`, `language_pack_version`, `business_version`, `direction`, `language_policy`, `provider`, `model`, `tool_contract_version`, `opening_text`, `final_instructions`, `checksum`, and per-section token counts. These are proposed fields, not existing functionality.

All current paths must use this artifact:

- Brief-to-script compilation: `server/brain/agent_script_compiler.py`.
- Session/Test Studio compilation and factory defaults: `server/brain/session_brain_compiler.py`, `server/agent/brain_prompt_composer.py`.
- Published business brains: `server/brain/compiled_brain_service.py`.
- Runtime model prompts: `server/realtime/text_session.py`, `server/realtime/gemini_audio_session.py`, `server/realtime/voice_instructions.py`.
- Saved session selection and language alignment: `server/call/call_brain_lock.py`, `server/brain/script_entities.py`.
- Prewarm and answer-time adoption: `server/services/pstn_prewarm.py`, `server/services/pstn_realtime_voice_core.py`.

Keep old APIs compatible through adapters while migrating. Those adapters must not append the old full spoken pack, static rules, or final language footer to the new prompt. The second review confirms that multiple current builders append their own rules; replacing only the brief compiler would leave contradictions elsewhere (`brain_prompt_composer.py:148–182`, `session_brain_compiler.py:56–93`, `text_session.py:39–60,82–136`).

### 5.3 Explicit rules that resolve the current contradictions

1. **Fixed-language mode is the initial target.** The selected locale remains fixed through greeting, answers, tool confirmations, and farewell. Remove automatic mirroring in this mode. If the caller needs another language, offer the supported language callback/handoff without pretending it was completed. A future multilingual mode must be an explicit separate policy with tested transitions, not an accidental override.
2. **One opening source.** Generate the localized opening once from the same identity, direction, and business facts. Entity metadata, visible preview, prewarm text, and model context all reference it. Keep intended text separate from generated audio transcription. The platform tracks whether the caller actually heard it.
3. **One closing policy.** Caller refusal/stop overrides unfinished sales objectives. A meaningful request to continue can cancel closing before disconnect is committed. After the farewell finishes and disconnect is committed, do not start another turn. Bare noise or a short acknowledgment must not repeatedly reopen the call.
4. **Answer before collecting details.** Ask one relevant missing question when needed. Do not require every optional question or ask a known detail again. Keep support, appointment, recruitment, and sales objectives distinct.
5. **Allow necessary clarification.** Confirm an uncertain caller-supplied callback number selectively; do not recite the known dialed number routinely.
6. **Preserve pickup intent.** “I'm busy” or “Don't call again” must be understood even during greeting preparation. A cached greeting must not erase that intent.

### 5.4 Make the prompt smaller without removing useful information

- Remove repeated language locks, repeated closing rules, duplicate openings, and cache-floor padding in every compiler path.
- Keep technical metadata outside spoken text. Render identity and facts once instead of repeating entity tags and the same prose unnecessarily.
- Include only the selected language, call direction, role, provider, and available tools. Do not include generic sales instructions in non-sales calls.
- Keep mandatory facts, disclosures, refusals, and permitted actions intact. Do not cut sentences or omit business requirements to reach a token target.
- For genuinely large knowledge bases, use a separate retrieval design with source-backed facts; do not silently drop FAQ content as part of this refactor.
- Measure tokens in the **final instructions sent to each provider**, including its additions. Record whether counts are exact or estimated and compare against the same business/language/provider baseline.

Target: no duplicated policy blocks and a measured reduction on the audited examples, with all behavior checks passing. Do not promise a fixed percentage reduction before measuring it. If required content exceeds the configured budget, show an actionable validation error; do not silently expand the budget, truncate requirements, or use an unrelated language pack.

### 5.5 Validation and migration

Before publish or dial, check the selected locale exists, all required localized phrases exist, business facts are preserved, direction/opening agree, and only available actions are described. Validate structured fields first, then lint the fully rendered provider prompt. A script-character check alone is insufficient because business names and normal borrowed words may legitimately use Latin letters.

Add scenario evaluations for contradictions that cannot be reliably caught by simple string rules. Preserve the original brief and published version so failures are reviewable. Do not describe these checks as a mathematical guarantee that an LLM will never make a mistake.

Migrate existing saved brains by regenerating from their original brief or structured business sections. Rebuild affected language variants; do not just replace `en-US` with `te-IN`. If the source is missing or ambiguous, flag that agent for review instead of guessing or overwriting its approved facts.

Calls already in progress keep their locked artifact. New calls use the validated new version. Prewarm and answer must compare the same artifact checksum, including locale and provider contract. Cache invalidation must follow changes to core rules, language packs, business data, tools, or relevant voice settings. Retain a rollback path to a known-good version; an invalid artifact must not enter a silent retry/redial loop.

## 6. Complete implementation checklist

All items are **pending**. Checkboxes mean implemented and verified, not merely documented. Original issues B1–B7, C1–C5, and A1–A5 are retained; the original TTS risk is now A6; the second-review discovery is B8.

### Phase 1 — Coherent, compact brains

- [x] **B1:** `script_entities.realign_calling_script_for_session` patches canonical opening and role speak lines from entity tags; language tag sync retained. **Limit:** not full section 5 artifact; no regenerated saved call `7778252e` snapshot in this pass.
- [x] **B2:** `_maybe_mirror_caller_language` no-op; stricter `infer_spoken_language_from_text` for short acks and Latin-only snippets.
- [x] **B3:** unified closing copy in `sections.py` / compiler; controller hangup paths aligned (farewell drain, presence abort, firm-refusal fast finish). Pytest: `test_call_controller`, `test_pstn_realtime_voice` hangup suite.
- [x] **B4:** objective ranking and “answer then one missing question” copy in `sections.py` / `agent_script_compiler.py`.
- [x] **B5:** `brain_prompt_validate.validate_rendered_brain`; wired at call start (`call_lifecycle_service`) and dial prep (`pstn_stack.assert_spoken_pack_available`). `test_brain_prompt_validate.py`.
- [x] **B6:** selective callback-number confirmation wording in compiler/sections (no blanket digit readback).
- [x] **B7:** `_ensure_cache_floor` uses neutral HTML comment pad only (no repeated spoken packs).
- [x] **B8:** `indic_spoken_packs.py` + `SPOKEN_PACKS` merge; `spoken_pack_for` / dial-time assert for missing packs. **Limit:** no 11-locale live prompt snapshot archive attached here.
- [~] **Migration:** runtime `realign_compiled_brain_for_session` on dial/lock; CLI `python -m server.brain.realign_stored_brains` for on-disk files. **Limit:** no automated DB republish of all agents.

### Phase 2 — Ready on the first call, repeat-safe dialing

- [x] **C1:** `PREWARM_ADOPT_WAIT_SEC = 1.5` bounds post-answer adoption wait (was up to ~12s); prewarm still prepares greeting while ringing. **Limit:** no measured 1–2s audible greeting SLA on live PSTN.
- [x] **C2:** `pstn_prewarm.take_prewarm_for_answer` realigns brain before checksum compare.
- [x] **C3:** `outbound_dial_attempt.execute_dial_attempt` (Redis/SQLite claims, replay, uncertain status); dev + subscriber orchestrator + `dialRequestId`; server assigns UUID when client omits ID on SaaS outbound.
- [x] **C3 failure recovery:** uncertain carrier outcomes persist `status: uncertain` and block redial with `dial_pending` until reconciled (`test_outbound_dial_attempt.py`).
- [x] **C4:** E.164 normalization and `list_recent(100)` in `outbound_dial_guard.py`; tests in `test_outbound_dial_guard.py`.
- [x] **C5:** `telnyx_event_state.event_state_patch` for leg/media/recording; streaming stop no longer overwrites live leg `status` with `stream-stopped` (`test_telnyx_event_state.py`). **Limit:** no same-call media-death recovery worker.
- [x] **Existing protections:** unchanged (Telnyx single attempt, answer dedup, UI locks, etc.).

### Phase 3 — Stable audio and natural turn-taking

- [x] **A1:** semantic VAD `silence_duration_ms`; `last_session.effective_vad` + connect log records real Gemini settings vs ignored UI fields.
- [x] **A2:** echo-tail stricter RMS gate (~550ms), STT echo overlap suppresses energy barge (`echo_guard` + `pstn_realtime_voice_core`).
- [x] **A3:** monotonic 20 ms playback deadline in `telnyx_pstn_bridge.py`.
- [x] **A4:** `playout_underrun_count` incremented when queue empty while agent audio expected.
- [x] **A5:** pickup refusal/hangup before clearing deferred greeting; ledger append for pickup text.
- [x] **A6:** partial vs no-audio TTS timeout distinction in `pstn_turn_tts.py`.

### Phase 4 — Tests, remaining diagnosis, and release evidence

- [x] Repair all **five baseline failures** listed in section 4 (plus extended realtime hangup regressions).
- [~] Track `audioop` compatibility — plan in `docs/changelog/2026-09/28-telecaller-audit/AUDIOOP_MIGRATION.md` (code migration not done).
- [ ] Duplicate-call pair correlation — still inconclusive per logs.
- [~] Live audio / carrier recording comparison — forensics panel + `compare_recording` hints in Test Studio PSTN live; manual listen still required.
- [x] Pytest: **177 passed** in audit module set (section 8); `test_locale_prompt_snapshots.py` covers 11 locales. **Limit:** no carrier recording timings or prompt dump files checked into repo.
- [x] `graft build` after this pass.

## 8. Implementation pass record (28 Sep 2026)

| Item | Primary files | Verification |
|------|----------------|--------------|
| B1–B8, B5 validate | `script_entities.py`, `sections.py`, `agent_script_compiler.py`, `agent_voice_rules.py`, `indic_spoken_packs.py`, `brain_prompt_validate.py` | `pytest server/tests/test_brain_prompt_validate.py server/tests/test_agent_brief.py` |
| B3/A5 hangup | `pstn_realtime_voice_core.py` | `pytest server/tests/test_call_controller.py server/tests/test_pstn_realtime_voice.py` (hangup tests) |
| C2 | `pstn_prewarm.py` | `pytest server/tests/test_pstn_prewarm.py` |
| C3 dev | `outbound_dial_attempt.py`, `dev_telephony.py`, `PstnTestPanel.tsx` | manual / guard tests |
| C4 | `outbound_dial_guard.py` | `pytest server/tests/test_outbound_dial_guard.py` |
| C5 partial | `telnyx.py` | not isolated test |
| A1 | `gemini_voice.py` | gemini PSTN regression suite |
| A3/A4 | `telnyx_pstn_bridge.py` | `pytest server/tests/test_telnyx_pstn_bridge.py` |
| A6 | `pstn_turn_tts.py` | TTS/resample tests |

**Command run:** `pytest` on modules listed in section 4 update — **177 passed**, 0 failed (28 Sep 2026, second pass).

**Still requires human / production evidence (section 7):** live PSTN matrix, duplicate-call pair correlation, carrier vs generated audio comparison, `audioop` deprecation migration plan.

**Section 5 (partial):** `compiled_brain_artifact.assemble_unified_brain` is the single compile assembler; live voice skips duplicate language overlays when `is_unified_compiled_brain`. **Still deferred:** storing `CompiledBrainArtifact` JSON on every publish/save, routing all legacy brains through republish; intentional multilingual mode; full media-death same-call recovery automation.

For each completed item record: changed files, verification performed, result, and any remaining limit. “Implemented locally,” “tests passed,” and “verified on real calls” are different milestones.

## 7. How to confirm that the problems are fixed

Use a controlled test with the same business script, phone, carrier, voice, model, and network. Change only language: start with English, Telugu, and Hindi, then test every other advertised language. Include both cold startup and warm startup, and repeat each case enough times to catch intermittent failures.

Before live calls, generate final prompt snapshots for all 11 locales, inbound and outbound directions, and each enabled provider/pipeline combination. Check that the selected pack appears once, the localized opening matches the artifact, tools are real, required facts survive, and no old footer or repeated static pack is appended. Include long briefs and custom business instructions that try to introduce conflicting language or closing rules. Measure prompt size separately from conversation history and tool-schema size.

Record:

- One request ID, one dial-attempt ID, carrier call ID, application call ID, worker ID, and brain checksum.
- Answer time, model-ready time, first generated audio, first sent audio, and first audible speech in the carrier recording.
- Provider audio gaps, queue depth, sender timing, buffer underruns, and every interruption reason.
- Whether the caller's first sentence was preserved and whether the agent used the selected language throughout.

Compare generated audio before playback with the carrier recording. If both contain the same defect, investigate model output/prompting. If generated audio is clean but the carrier recording has gaps, investigate playback and transport. If the carrier recording is clean but the review player sounds broken, investigate recording playback separately.

For duplicate calls, test a double-click, a repeated request with the same ID, a lost HTTP response, two server workers, and a retry after the first call ends. The **same request ID must never create a second phone call**. An explicitly new call must still work.

For human conversation, test: “I'm busy” at pickup, a firm refusal, a corrected phone number, an unanswered question, a short acknowledgment, a real interruption, and a final “wait” before disconnect. Judge the response and audio together.

Suggested internal acceptance target: first audible greeting within about 1–2 seconds after answer when using an immediate/short-wait greeting policy. This is a product target to test, not a universal provider guarantee. Do not trade away meaningful pickup speech merely to hit it.

The remaining incident-specific evidence needed is the exact bad/good call pair, its client request IDs, and carrier event/recording correlation. The current sample proves slow startup and prompt defects; it does not prove a single automatic-redial root cause or a universal non-English audio defect.
