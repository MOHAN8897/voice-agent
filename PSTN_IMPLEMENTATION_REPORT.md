# PSTN implementation and verification

Date: 2026-09-09. Requirements: `VOICE_AGENT_PRESETS.md`.

The existing Telnyx → streaming STT → shared PSTN FSM → OpenAI Realtime **text** → sentence chunker → TTS → carrier playback architecture is preserved. Brain remains the behavior authority, and Test Studio remains the testing interface.

**Verified:** 658 server tests passed, 12 explicitly live/database tests skipped, zero failures; TypeScript compilation passed. Chrome loaded Test Studio and passed the PSTN diagnostics test at desktop and mobile widths. **Not verified:** a real inbound or outbound handset call, production tunnel connectivity, carrier audibility, live provider latency, or sustained multi-worker load. No phone call was placed during this implementation. Automated success is not a claim that a production handset call has been proven fixed.

## Confirmed defects and repairs

1. Inbound initiation had no explicit answer command. Added Telnyx answer with a stable command ID, duplicate-event protection, bounded retry, and asynchronous webhook handling. Outbound initiation never invokes answer.
2. Missing inbound agent metadata could bypass call creation. The bridge now resolves the default agent and initializes the shared lifecycle, or fails explicitly. Direction and outbound session/stack metadata survive stream-token creation.
3. Unauthenticated media connections and query overrides could reach the bridge. The WebSocket now requires a server-issued stream token. Start metadata must match its bound call when supplied. Simultaneous duplicate local bridges are rejected.
4. Redis-backed call metadata could be overwritten by stale worker-local rows. Reads prefer Redis; updates atomically merge patches using Redis Lua. Token mirrors carry expiry and local expired entries are rejected. Redis is still required for cross-worker token sharing.
5. Public media URLs could be insecure. Both inbound streaming and outbound dialing reject non-WSS URLs. URL logs omit the query token. This validates the scheme, not public reachability or proxy upgrades.
6. Greeting history was written before audio delivery evidence. Greetings now start once per loop; only emitted opening audio is recorded. Realtime reconnection restores history without calling the audible greeting path. Interrupted greetings retain caller speech.
7. Realtime readiness could be reported after session creation, configuration errors, or disconnection. READY now requires `session.updated` and an open connection; startup errors propagate. Reconnection restores bounded conversation history and the spoken-opening marker. Empty-response retry does not insert the same caller message twice.
8. A blocked queue insertion and a paced sender could release stale audio after interruption. Enqueue and send paths now recheck generation validity immediately before their respective mutations. Local purge and carrier clear cannot leave a blocked old-generation insertion behind.
9. Carrier clear failure could obstruct local interruption. Local TTS cancellation, Realtime cancellation, and carrier clear are independent bounded operations. A dedicated final-transcript timeout works even when no further STT packet arrives. Realtime cancellation no longer starts a competing event reader while a turn is consuming events.
10. The greeting immunity window and packet-dependent hold confirmation could miss early, short interruptions. The onset guard is two audio frames; an owned confirmation timer handles a single partial, including one at playback onset.
11. A short repeated place question could be classified as echo. `Shamshabad?` and other one/two-word punctuated questions bypass the substring echo shortcut. Full echoed phrases retain the stricter checks.
12. TTS failure fallback could reacquire the speech lock while already holding it. Retry now occurs after releasing that lock, once. Failed/empty standalone synthesis raises an error. Startup failure hangs up and cleans up without cancelling its own cleanup task.
13. Frame-local resampling lost continuity, and negotiated G.711 could be interpreted with the wrong rate. Conversion now retains streaming state, respects negotiated sample rate, buffers L16 output frames, and uses an anti-alias filter before downsampling.
14. New PSTN lifecycle setup cleared the source browser session's memory. It now clears only the new call's own memory.
15. Diagnostics mixed greeting/earlier-turn audio into response timings. Response metrics now use the latest LLM turn and reject backwards timestamp pairs. Test Studio exposes direction, agent, phase, turn/generation, STT and Realtime state, model, chronological events, connection failures, and selected-call playback purge. Diagnostic speech also carries the selected call ID.
16. Unit tests silently reloaded local `.env`, persistent dev credentials, and shared request-limit counters. Test configuration/data are now isolated; explicit live tests remain opt-in. Provider mocks target the functions actually called by the current routes.

## Suspicions not confirmed / specification discrepancies

- The implemented outbound route is `POST /api/dev/telephony/outbound`, dispatching to `_outbound_telnyx`; the document's `/telnyx/dial` name is not the current route. Both directions already share the PSTN voice loop.
- Carrier playback clear is the Telnyx media-WebSocket `clear` event. No unsupported `clear_playback()` REST command was invented.
- Realtime was already text-only, with local turn detection and no GA temperature field. These settings were preserved.
- The current live model is `gpt-realtime-2.1-mini`. The document's 96-token example was not imposed: the implementation intentionally uses 240 output tokens to avoid cutting multilingual output, with a 200-character spoken ceiling.
- Indexed STT code uses Sarvam and the provider registry. No active Deepgram client was found. A Deepgram-specific KeepAlive message was therefore not added to unrelated transports.
- Quiet caller audio already had a path into STT. Regression tests preserve that behavior; RMS is not a hard transcript-ingestion gate.
- A successful media send is evidence of bytes delivered to the socket, not proof of audio heard on the handset.

## Final runtime defaults

Runtime/Test Studio overrides still apply where supported.

- STT silence default: **400 ms**, stream type **fast**. Existing upstream keep-alive interval: **12 s**.
- Listening coalesce: **550 ms**, with up to **three 200 ms** extensions while fresh partials continue. These defaults were retained; no measured speedup is claimed.
- Soft AEC RMS threshold: **320**; confidence opens after **2 loud frames**, closes after **8 quiet frames**. Quiet frames continue to STT.
- Barge hold: **120 ms**; onset guard: **40 ms**; minimum words: **1**, subject to substantive/short-interruption and echo rules.
- Barge debounce: **450 ms**; post-barge final window: **1.5 s**; final debounce: **300 ms**; missing-final timeout: **4 s**.
- Think-cancel hold: **250 ms**. Pure acknowledgements such as `yeah`/`ok` do not cancel an in-flight thinking turn. `Wait`, `No`, `కాదు`, and `లేదు` are supported interruption phrases.
- Echo tail: **350 ms**. Overlap combines **35% unigram / 65% bigram** evidence for longer phrases. Thresholds: barge **0.55**, tail final **0.65**, listening final **0.80**, post-barge final **0.85**. Two-word comparisons use the existing unigram rule.
- Realtime: model `gpt-realtime-2.1-mini`; `output_modalities=["text"]`; `audio.input.turn_detection=null`; `max_output_tokens=240`; existing `end_call` tool; no temperature field. Spoken limit: **200 characters**. Primary Brain guidance: one/two sentences, roughly 8–25 English/Tanglish words or comparably concise Indic speech; existing length bands remain secondary guidance.
- Static Brain rules version: **sr_v25**, invalidating older compiled-rule caches. Includes continuing to help when a caller declines to give a name.
- Carrier frames remain **20 ms**, with negotiated L16 16 kHz or G.711 8 kHz conversion. No new carrier codec was invented.

## Verification evidence

Final command:

```powershell
python -m pytest server/tests -q --tb=short --junitxml=data/pstn-acceptance-pytest.xml
```

Result: **658 passed, 12 skipped, 1 warning, 27.20 seconds**. The warning is Python's `audioop` deprecation. Tested with Python 3.12. The skips are one live database check and eleven live provider/latency checks; they were not converted into fake passes.

- [Full pytest output](data/pstn-acceptance-pytest.log)
- [JUnit results](data/pstn-acceptance-pytest.xml)
- [New acceptance regressions](server/tests/test_pstn_acceptance.py)
- Existing coverage also passed: PSTN production fixes, critical loop, Telnyx bridge/media flow, Realtime text, prewarming, barge history, audio conversion, call lifecycle, and Brain behavior suites.

Inbound automated evidence covers answer contract/idempotency, default-agent resolution and lifecycle creation. Outbound automated evidence covers answered-event streaming, preserved outbound metadata and the common bridge/voice path. Failure injection covers provider errors, interruption during intro/speech/thinking, quiet audio, missing post-barge finals, cancellation, stale generations, blocked playback, carrier clear failure, startup cleanup, and Realtime readiness/reconnection. The new single-reader cancellation and self-cleanup tests both pass.

Test fixtures were corrected for existing API contracts: catalog preset objects, Realtime-default pricing independent accounting, original-script caller-name capture, current compiler version, and TTS registry entry points. Factual-price, memory, rate-limit, and Brain policy assertions remain enforced. The 15-turn audit now checks shared platform behavior in the compiled Brain rather than requiring duplicate policy prose inside the agent script.

Frontend verification:

```powershell
node web/node_modules/typescript/bin/tsc --noEmit --incremental false --project web/tsconfig.json
# With the isolated API on 8100 and Next on 3100:
$env:PLAYWRIGHT_SKIP_WEBSERVER='1'
$env:PLAYWRIGHT_CHANNEL='chrome'
$env:WEB_URL='http://127.0.0.1:3100'
$env:API_URL='http://127.0.0.1:8100'
# Run from web:
node node_modules/@playwright/test/cli.js test e2e/pstn-media-diagnostics.spec.ts --workers=1
```

TypeScript passed. The dedicated Chrome run passed **2 tests including authentication setup**; an additional Test Studio page-load run also passed **2 including setup**. Diagnostics use synthetic telemetry and mocked purge/status endpoints; no PSTN call is made. The test checks selected-call targeting, desktop/mobile rendering, no page errors, and stale-connection alerts. Screenshots were inspected and the narrow-panel layout adjusted.

## Measurements and limits

- The synthetic latency regression supplies timestamps with **300 ms** LLM first token, **200 ms** first TTS audio, and **50 ms** audio-to-socket send delay. Those numbers are fixtures verifying calculation, **not measured live latency**.
- The signal regression verifies that a 6 kHz input tone downsampled from 24 kHz to 8 kHz has less than **3%** of the 1 kHz reference RMS after settling, and that odd-sized packet streaming exactly matches continuous conversion. This demonstrates anti-alias rejection/continuity, not perceptual speech quality.
- No live speech-start → speech-end → STT-final → first-handset-audio timings or carrier-clear acknowledgement timings were collected. STT telemetry is packet/recognizer evidence, not independently measured acoustic speech boundaries.
- Spoken history is phrase-level delivery evidence. Without provider word timestamps/carrier playout acknowledgements, it cannot prove exactly which words a caller heard before an interruption.
- Redis mirroring was exercised with test doubles, not a distributed worker/load test. Production still needs working Redis and routing/observability appropriate to process-local active bridges.
- Public WSS reachability, webhook signature configuration, trial-account destination restrictions, provider credentials, real echo conditions, and handset intelligibility require deployment/live-call verification.
- Python 3.13+ needs an `audioop` replacement before this runtime is upgraded.
- Local browser verification used fallback fonts because the Google Fonts request failed in this environment. Production font delivery was not verified.
- Graft MCP queries refreshed the wiring graph, and its final wiring check reported in-sync. A full semantic graph build was not completed: the local CLI was unavailable and the checker reported a missing semantic manifest/pending summaries.

## Files changed by this implementation

The workspace already contained extensive unrelated/uncommitted work. This list identifies files touched for this task, not ownership of every line in their Git diffs.

- Carrier/lifecycle: `server/services/telnyx_client.py`, `server/routes/telnyx.py`, `server/routes/telnyx_ws.py`, `server/routes/dev_telephony.py`, `server/services/telnyx_pstn_bridge.py`, `server/call/call_lifecycle_service.py`, `server/call/redis_memory_cache.py`.
- Voice/audio: `server/services/pstn_voice_core.py`, `server/services/pstn_playback.py`, `server/services/audio_transcode.py`, `server/services/echo_guard.py`, `server/services/transcript_gate.py`, `server/services/pstn_media_flow.py`, `server/services/voice_pipeline_limits.py`.
- Realtime/Brain: `server/realtime/providers/openai.py`, `server/realtime/text_session.py`, `server/brain/sections.py`.
- UI: `web/components/dev/test-studio/LiveMediaFlowDebugger.tsx`, `web/components/dev/test-studio/PstnTestPanel.tsx`.
- Verification: `server/tests/test_pstn_acceptance.py`, `server/tests/test_pstn_critical_loop.py`, `server/tests/conftest.py`, `server/tests/test_db_connection.py`, `server/tests/test_tts_instructions.py`, `server/tests/test_finetune_console.py`, `server/tests/test_human_salesperson_characteristics.py`, `server/tests/test_tts_length_brain_guardrails.py`, `server/tests/test_usage_pricing.py`, `server/tests/test_human_call_rules.py`, `server/tests/test_production_launch.py`, `server/tests/test_eight_turn_flow.py`, `server/tests/test_fifteen_turn_agent_brief_audit.py`, `web/e2e/pstn-media-diagnostics.spec.ts`, `web/playwright.config.ts`, `scripts/pstn_smoke_server.py`, and this report.

## Live acceptance still required

Use the normal application launcher/configuration, not `scripts/pstn_smoke_server.py` (an isolated test fixture). In Test Studio, select the agent and **Full PSTN flow**, verify Telnyx and public WSS configuration, then enter a destination you control. The destination is intentionally empty by default. Test both inbound and outbound: opening exactly once, several turns, the short interruption phrases above, provider reconnect, and final hangup. Keep the media timeline and recording for audibility/latency comparison. Do not infer real carrier success from the synthetic diagnostics screenshot.

## API contracts checked

- [Telnyx answer command](https://developers.telnyx.com/api-reference/call-commands/answer-call): explicit inbound answering and command ID idempotency.
- [Telnyx media streaming](https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming) and [streaming start](https://developers.telnyx.com/api-reference/call-commands/streaming-start): bidirectional media, clear messages, and codec configuration.
- [OpenAI Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations) and [model documentation](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini): text-mode session configuration and current model identity.
