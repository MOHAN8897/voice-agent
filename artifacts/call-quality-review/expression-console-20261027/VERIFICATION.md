# Speech delivery, configuration and console verification

Date: 27 October 2026 (Asia/Kolkata). Branch: `working-app-22-10-2026`.

VERDICT: PASS for the verified scope below. No PSTN call was placed. This does not certify every possible model response or carrier/audio condition.

## Confirmed findings and fixes

### 1. Expression guidance conflicted with the live reply contract

Gnani's documentation specifies case-sensitive inline tags in the `text` field for Timbre v3.0. Untagged text is neutral; there is no separate emotion switch to enable. See [audio tags](https://docs.gnani.ai/api/TTS/tts-audio-tags) and [WebSocket protocol](https://docs.gnani.ai/api/TTS/tts-websocket).

The composed prompt supported these tags, but described them as belonging only in the old `spoken_response` field. The later live transport contract requested only spoken words. This discouraged the plain-text model from producing cues even when appropriate.

Fixed `server/prompts/tts_delivery_rules.py` and `server/call/live_turn_orchestrator.py`: the final contract explicitly permits documented cues for the admitted Gnani v3 model. Positive enthusiasm uses `<excited>` and requested slower explanations use `<slow>`. Routine facts can remain neutral. Other models stay tag-free. No forced laughter, shouting or theatrical reactions on ordinary business calls.

### 2. WebSocket sequencing and final audio could fail

`server/services/gnani_tts_ws.py` sent subsequent synthesis requests before prior completion, contrary to the one-request-at-a-time provider protocol. Its terminal-packet branch also skipped audio carried by an `is_final` packet. A `complete` packet without `is_final` did not update completion accounting.

Fixed request serialization, bounded completion waits, final PCM delivery before completion, and release of waiting writers on provider failure or socket closure. Regression tests exercise complete-only packets, final-audio packets, duplicate terminal indicators and failures. Two real provider synthesis requests also returned nonempty audio and completed.

### 3. Telugu honorific examples encouraged repetitive filler

The full Telugu pack suggested `-andi` markers and several honorific acknowledgments. Both compact style examples also ended in `అండి`.

Removed these repeated examples and added consistent guidance at the language pack and final speech contract: answer directly, avoid standalone honorific filler and English-word suffixes, preserve normal polite grammar such as `చెప్పండి` and `చెప్తారా`. No blanket text replacement strips legitimate Telugu verb endings. The four final live samples contain zero standalone `అండి`; a natural attached form in a positive response remains allowed. This is model guidance, not a guarantee over every future response.

### 4. A language change could retain a contradictory style

`refresh_platform_sections` aligned the language marker before checking whether the runtime footer needed replacement. It could produce `Language: kn-IN. Style: American English.`

Fixed `server/brain/compiled_brain_artifact.py:108` to retain the original locale-change signal when rebuilding the footer. The existing regression now passes.

### 5. Backend tier edits did not refresh the main catalog automatically

The legacy phone voice list refreshed periodically and on focus. The newer tier/profile catalog refreshed only on mount, language change or manual retry. Operators could see outdated voices, availability and profile revisions.

Fixed `AgentStudioModule.jsx`: refresh current profiles on focus, visibility restoration and every 30 seconds while visible. Deduplicate overlapping requests, reject stale responses, preserve choices on transient failures and preserve unsaved script fields. Existing backend revision validation still rejects outdated choices; calls already admitted keep their pinned setup.

Catalog requests have a 15-second timeout; general JSON requests have a configurable 60-second default. A stalled request now produces a recoverable error instead of remaining pending indefinitely. These timeouts do not automatically retry writes. Profile and rate reads run concurrently in `server/routes/voice_stacks.py` rather than serially.

Read-only inspection of persisted profiles confirmed: enabled custom tier `medium_copy_1`, revision 37, uses Gnani `timbre-v3.0`; enabled Standard `medium`, revision 97, uses Sarvam Bulbul v3; enabled Economical `low`, revision 41, uses Gemini Flash Lite TTS. The built-in native Premium profile was disabled. No tier, rate, supplier cost or production configuration was changed.

No local API was listening on port 8000 during verification. Started the API, loaded the final code and checked `/api/health` returned HTTP 200. No recent real call was active when restarting the process started for this task.

### 6. Objections were compiled, but a preset conflicted with closing ownership

Traced console rule serialization → enabled FAQ section → reviewed publication → compiled artifact → call-owned prompt. Publication/runtime regression coverage now confirms preservation in all 11 website locales.

The rejection preset still included its own goodbye. Replaced it with a short acknowledgment. The FAQ instruction now explains that `end_call` is a close proposal for server approval; the server owns the configured farewell. Future interest and callback requests are distinguished from complete rejection. Tool permissions and successful-result requirements remain authoritative. Tenant-authored business text is preserved.

### 7. Console navigation and layout wasted available space

Added persistent desktop sidebar collapse with accessible icon labels; mobile retains its drawer. Widened the shared workspace for every console page. Main agent tabs and local category navigation remain available while scrolling.

Script categories: All sections, Conversation, Farewell, Objections. Wide screens place closing and objection controls beside the conversation editors; narrow screens retain reading order. Settings categories: All settings, Agent & phone, Call handling, Recording & compliance. Related cards use two columns on wide screens. Switching categories hides rather than unmounts form fields, preserving edits. Existing Overview, Calls and Voice grids use the expanded shared workspace.

Greeting synthesis, cached opening playback, greeting editor events and prewarm ownership were not changed. Only the greeting card's surrounding layout moved.

## Executed verification

- Python: **373 passed**, 2 warnings. Covered locale/model combinations, Gnani transport and speech contracts, all-locale objection publication, tier isolation, configuration alignment, interruption recovery, compilation and both prewarm suites. See `voice-config-regression.log`.
- Browser: **21 passed**. Covered sidebar persistence; desktop/mobile layouts; draft preservation; profile revision refresh and reselection; transient refresh recovery; request timeout without logout; publication, callback UI, voice catalog mapping and voice selection. Synthetic API fixtures ran the real React application. See `console-full-regression.log`.
- Node objection/script helpers: **4 passed**. See `objection-rules-tests.log`.
- Live pinned Sarvam LLM: **4 independent scenarios** (enthusiastic interest, slower price explanation, delivery enquiry, price objection). All returned usable text. Both requested expression tags survived the final speech boundary. Final standalone honorific count: zero in all four samples. See `live-results.json`.
- Real Gnani WebSocket: **2 successful synthesis samples**, `positive.wav` and `slow.wav`, with 16 kHz PCM and normal completion. No calls or external business writes.
- Production frontend build and six-page prerender: **passed**. See `console-build-current.log`.
- Reticle: **verified: yes** for sidebar collapse, direct farewell category access and direct recording/compliance category access. See the three Reticle JSONL evidence files. Reticle marks component-local state coverage as partial; Playwright independently asserts draft retention. An initial already-true predicate was rejected and replaced with a meaningful hidden-to-visible check.
- Full Semgrep SAST: **exit 0, zero findings**. Existing scan timeout warnings are retained in `voice-config-sast.log`; zero findings is not a proof of absence of vulnerabilities.
- Touched Python lint compared with HEAD: **zero introduced findings**; existing 40 findings remain. See `lint-results.json`.
- `git diff --check`: passed. Graft rebuilt successfully.

Two stale test expectations were updated without loosening the runtime: missing/invalid native models must fail closed rather than silently pick another model; the unchanged current static-rule revision is `sr_v39`, not the obsolete `sr_v35`. The original semantic length assertions remain.

## Limits and operation

No live PSTN, carrier hangup, microphone/STT, acoustic echo or human listening judgment was performed. Successful provider audio generation proves tag transport and completion; perceived expression still needs a listening test with the selected voice. The text-only LLM timings are not full call latency measurements.

The existing Vite server had a stale optimized Reticle SDK module. Verification used port 5174 with a separate temporary optimizer cache, preserving the user's existing server. Reticle evidence is local to this machine. The application API runs locally on port 8000 with the final fixes. No deployment, commit or push was performed.
