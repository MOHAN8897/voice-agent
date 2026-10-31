# Last two calls: silence and repeated interruptions

## Findings

The calls reviewed were Meera's Telugu Premium calls `bdb7fe33-b962-4c79-aa98-0621875bca91` (22:05 IST) and `92064910-e19a-46e5-ba19-420cd8041154` (22:08 IST), on 26 October 2026. Both used the pinned `sarvam-105b-conversations` text model. Call-control evidence is saved in `call-evidence.json`; the existing customer recordings and full business brain were not copied into this report.

**Confirmed — the first call became stuck in the server's interruption state.** At 22:06:09 an interruption cleared playback after generation had already finished. At 22:06:12 an STT final was rejected as echo. The server cleared its waiting flag but left its phase as `interrupting`. No running turn remained to restore `listening`. Later STT finals still arrived at 22:06:14, 22:06:25 and 22:06:43, but no new LLM turn started. The caller eventually disconnected. This was a server state bug, not an output-token-budget failure.

**Confirmed — the second call repeatedly cancelled replies while processing caller continuations.** It contained several committed interruptions, two thinking cancellations, and repeated/expanded STT finals. The model completed four archived answers. Its final turn began around the time the caller disconnected, so that particular cancelled ending does not prove a provider outage. The server needs to preserve genuine new caller details while ignoring duplicate partials of the question already being answered.

**Confirmed — the previous slow-down rule only detected long utterances.** Several short interruptions did not trigger it. Also, it marked the request as used when generation began, so cancellation could consume it before a useful response existed.

**Confirmed during live retesting — final reply instructions were ordered incorrectly.** The compiled brain arrives as a `developer` message. The old insertion logic checked only for `system`, putting the speech contract before the business script. Its final delivery rules could therefore be outweighed by the repeated sales flow. A live run also exposed two differently worded slow-down requests in one answer when both the model and the server tried to write that sentence.

## Fixes

1. After handling a final interrupted transcript, an idle call returns to `listening` even when that transcript was rejected as echo. A rejected echo also clears its unused final-debounce epoch. The next real question is accepted normally. Echo protection itself remains enabled.
2. Repeated partials already contained in the current caller request no longer cancel its reply. Genuine new information and explicit stop/wait commands retain their interruption behaviour.
3. Three committed caller interruptions within 30 seconds request one polite slow-down sentence. Raw VAD, background noise and ordinary acknowledgement words are not counted. Opening delivery is excluded. The request is retained if generation is cancelled before producing a usable reply.
4. On the buffered speech path, the platform owns that single localized sentence. The model is told to answer the actual question without repeating or paraphrasing the slow-down request. Once included in a completed response, it is not added to every later reply. It does not disable the caller's ability to interrupt.
5. The final speech contract now follows all leading platform/business `system` and `developer` messages. It reinforces answering the question first, admitting missing facts, and avoiding contact-detail collection before the caller chooses to proceed. The original business script and greeting text were preserved.

Relevant files: `server/services/pstn_voice_core.py`, `server/services/user_turn_hints.py`, `server/call/call_context.py`, `server/call/live_turn_orchestrator.py`. Regression coverage: `server/tests/test_interruption_recovery.py`.

## Three live LLM simulations, without TTS

The simulation runner uses the latest call's exact compiled brain and pinned Premium text model. Context, memory and archives are isolated in a temporary directory. It exercises the real server input builder, control classifier, native action-selection/speech protocol and close gate. Tools retain the current schema shape, while external writes are prohibited. No phone calls or TTS synthesis are performed.

- **Echo-discard recovery:** replay the interruption/echo state, deliver a real Telugu price question, and verify that normal coalescing launches an LLM turn. The model answered the approved per-card price and kept the conversation open.
- **Repeated interruptions:** supply three committed-interruption signals, ask an unknown minimum-budget question while explicitly not ordering, then ask about payment. The response contained one Telugu slow-down request, acknowledged that the minimum-budget information was unavailable, and continued answering. It did not fabricate a minimum or execute an action. The following reply did not repeat the slow-down sentence.
- **Cancelled request recovery:** cancel an actual live text generation, then say “hello, are you there?”. The server retained the unanswered price question and the model answered it. “Thanks, but one more question” stayed open; a later explicit Telugu ending received the server farewell and an approved close decision.

Final result: **3/3 simulations passed** for these acceptance checks. Exact synthetic transcripts, timings, finish reasons and close decisions are in `llm-simulation-results.json`; the runner is `run_llm_simulations.py`.

A sales-style optional order question still appeared in some answers. That is a remaining conversational-quality limitation, not a silent turn or a completed order. The tests do not claim perfect script adherence across every paraphrase.

## Regression and runtime checks

The targeted suite passed **328 tests** (42 warnings). It covers the reproduced deadlock, acknowledgement/echo guards, explicit halts, duplicate partials, interruption counting, cancelled slow-down delivery, prompt ordering, callbacks, hangup playback, greeting prewarm, memory and the composed LLM protocol. Results are recorded in `pytest.log`.

Ruff comparison against the existing branch baseline reports no introduced findings. The full SAST runner exited 0 with **0 findings / 0 blocking**; it is recorded in `sast.log`. Any rule timeouts remain limitations of static coverage rather than successful checks of those timed-out rules.

Reticle was skipped because this change concerns backend call-control and LLM behaviour; no console UI was changed.

No real PSTN call or TTS provider was tested in these simulations. The close decision was verified, but a new physical carrier hangup and acoustic playback still require a fresh telephone acceptance call.
