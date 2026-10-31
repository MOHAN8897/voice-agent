# Capability, memory and integration fixes — 26 October 2026

## Result

Implemented on `working-app-22-10-2026`, starting from `aaf82b93`. No production configuration, database migration, billing rate or greeting playback mechanism was changed. These changes have not been pushed as part of this task.

Google Calendar and Gmail were connected through the actual console using the requested Google account. Both provider metadata endpoints returned HTTP 200 and matched that account. The existing Todoist connection reappeared after connection discovery was corrected. All three display **Active** after a real workspace refresh and a new login.

The actual Premium text model selected Calendar availability, the server executed an authorized read against the connected calendar, and the model answered with the returned times. No real emails, invitations, appointments or tasks were created.

This verifies the repaired paths below. It does **not** prove perfect model behaviour or real phone audio/carrier hangup on a new PSTN call. Those need a fresh telephone acceptance call.

## Confirmed problems and changes

### 1. The brain did not accurately describe executable actions

Earlier capability metadata described order permission from business prose, while live integration discovery used separate agent permission filters. An old publication could therefore describe capabilities differently from the schemas supplied to the model.

The server now builds a compact action manifest using the same active tenant, active agent, connected apps, enabled rules, timing and action whitelist used for tool discovery. Publication, recompilation and call preparation apply that manifest. Composed calls refresh it from current discovery before tool selection, so a disconnected or disabled integration does not remain a permission in the model's prompt. Actual execution independently checks authorization again.

Business requirements remain intact. Their action steps are conditional on the manifest; gathering details is not a completed booking or submission. Required tool arguments are listed. Order confirmation is available only for a supported order-taking workflow and means a platform order record, not proof of payment, external fulfilment or an email.

The catalog's **Post-Call** default now agrees with discovery and execution. Merely connecting Gmail or Todoist does not expose their writes during a call. Explicit agent configuration can permit a particular action in-call. Automatic post-call writes continue to require an explicit enabled rule; connecting an account alone does not create an automation.

Relevant implementation: `server/brain/capabilities.py`, `server/brain/compiled_brain_service.py`, `server/call/call_brain_lock.py`, `server/services/tool_schema_registry.py`, `server/services/tool_router.py`.

### 2. Speech-only replies were not maintaining useful dynamic memory

The speech-only format correctly avoids the unstable large response envelope, but it also removed the previous source of memory operations. The fallback name capture could retain only the first part of a name. Corrections, quantities and delivery details could therefore disappear from the useful memory projection.

The existing small control request now also proposes a bounded set of caller facts, using the exact pinned model. It receives bounded current facts and the previous agent line, understands short answers and corrections, and extracts full names, counts, products, addresses and preferences. It returns no caller-facing speech. Memory shares that request rather than adding a separate memory-only model call. On tool-enabled Sarvam turns, native action selection and speech still use the existing two-phase tool protocol; making a local enquiry tool available can therefore add that selection phase to agents that previously had no tools.

Every retained value must be supported by a quote from the current caller turn. Invented details, instruction keys, passwords, PINs, OTPs and unproven completion conclusions are rejected. Structured-provider updates and the optional extraction fallback use the same grounding check. Semantic full names take precedence over the older single-token fallback.

A locality is stored separately from a complete address. A caller starting an unfinished address can finish without being interrupted by another request to repeat it. Quantities retain the spoken count separately from the product. Memory is still bounded; extraction failure leaves the call open and keeps conversation history available.

Relevant implementation: `server/call/close_classifier.py`, `server/call/memory_guard.py`, `server/call/live_turn_orchestrator.py`, `server/call/memory_extraction.py`, `server/call/caller_detail_capture.py`.

### 3. Late memory updates could overwrite a newer correction

Background work can finish out of order. Memory merges now compare each field's turn sequence against persisted events, preventing an older quantity from replacing a later correction, including after a restart. Snapshot replacement is atomic; state, event, disk and cache publication are serialized. Historical snapshots sort by logical turn sequence rather than assuming completion order.

Memory disk/cache work and rolling-summary reads/writes run in worker threads instead of blocking the call's event loop. The rolling summary keeps complete utterances rather than slicing into the middle of a word. Durable facts remain separate from that short recent-conversation summary.

Relevant implementation: `server/call/memory_manager.py`, `server/call/rolling_summary.py`, `server/call/live_turn_orchestrator.py`.

### 4. Interrupted requests and ambiguous acknowledgements were mishandled

A cancelled generation now retains the caller's unanswered turn and supplies it as pending context on the next turn. If the caller asks whether the agent is still there, it can answer the interrupted question instead of forgetting it.

A bare okay/thanks cannot complete an unfinished order or interrupted request. A clear statement that the caller is finished can still close even when a task is incomplete: callers may abandon a task. The server remains responsible for approval, pending-tool checks, the farewell, playback drain and carrier hangup. The model does not receive direct hangup authority.

The regression tests include incomplete address fragments with no unwanted speech or hangup, pending actions, caller interruptions, callback withdrawal, revocable closing, and the existing farewell/playback/carrier lifecycle.

### 5. An enquiry needed a real local action when integrations were absent

`SAVE_ENQUIRY` is now a platform tool that creates a tenant-owned lead for workspace review, using the actual owned call context. It works without an external CRM. Repeated identical requests are idempotent; corrected details update the same enquiry without resetting the tenant's lead stage. The contact number comes from the customer's side of the call, rather than the outbound business line. Foreign tenant/agent/call combinations are rejected.

Only a successful receipt permits the agent to say an enquiry was saved. That receipt does not permit claims that a team was notified, an email sent, an order fulfilled or a callback automatically scheduled. Failed or uncertain saves remain unconfirmed. Native voice and composed discovery both expose the same eligible platform actions.

Relevant implementation: `server/call/enquiry.py`, `server/call/action_proof.py`, `server/services/tool_router.py`.

### 6. Successful OAuth connections were rejected or invisible

The integration gateway uses zero-based pagination. The old server started at page 1, skipping the first 100 connections. This caused healthy authorizations to fail exact-connection verification and left existing accounts invisible.

Discovery now starts at page 0, retains tenant ownership/provider/error checks, and handles subsequent pages with a bounded limit. It still requires the exact authorized connection; no arbitrary account is selected.

The console closes its connection form after success or provider error. If verification temporarily fails after authorization, Retry verifies the same authorization instead of opening a second OAuth flow. Permanent rejection permits a fresh authorization. SDK errors reset the loading state. Connection identifiers stay in component references rather than logs, page text or persistent browser storage.

Relevant implementation: `server/services/nango_service.py`, `voxly-ai/src/console/modules/IntegrationsModule.jsx`.

## Verification evidence

- Python regression suite: **601 passed**, 42 warnings; see `pytest-final.log`. Covers memory, compilation, language consistency, native/composed tool protocols, integration ownership/idempotency, callbacks, hangup and prewarm greetings.
- Live pinned Premium control/memory: **55/55** cases, five cases in every currently supported locale: `te-IN`, `hi-IN`, `ta-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN`, `en-IN`, `en-US`. Tests full names, quantity corrections, acknowledgements with missing details, explicit endings with unfinished work, and incomplete address fragments. Evidence: `live-control-results.json`.
- One repeated language run caught a Marathi explicit ending being treated as continuation. The control rule was clarified to let callers abandon unfinished tasks. The final 55-case run passed. This is evidence of tested behaviour, not a guarantee of deterministic future LLM outputs.
- Live Calendar and Gmail account verification: HTTP 200, requested account matches for both. Evidence: `live-integration-results.json`.
- Calendar read through the actual router: eight available samples in `Asia/Kolkata`; real model selected the read tool and answered with the first two returned times. The manifest excludes default post-call actions. Evidence: `live-integration-results.json`, `live-integration.log`.
- Browser recovery tests: **3 passed** — temporary activation failure reuses the authorization, provider error permits retry, permanent rejection permits fresh authorization. These use synthetic accounts and real running frontend behaviour.
- Reticle: **verified: yes** for the actual workspace refresh and for the synthetic activation-retry flow. Network/DOM evidence is available in `reticle-live.jsonl` and `reticle-recovery.jsonl`. Store/frame coverage was partial; those unobserved channels are not claimed as verified.
- Frontend production build passed: `frontend-build.log`.
- SAST: full runner exited 0 with **0 findings / 0 blocking**. One rule timed out in two existing files, so coverage was not exhaustive. Evidence: `sast-final.log` and the local security report.
- Ruff comparison: no introduced findings in touched Python files; existing unrelated lint debt remains. Evidence: `lint-results.json`.

## Scope and remaining acceptance checks

The greeting editor, greeting text generation, cached audio consumption and prepared-session handoff were preserved. The only prewarm-related edits register eligible platform tools; greeting regression tests passed.

The live language run tests the text control/memory model, not eleven STT/TTS voices or physical phone connections. No real new PSTN call was dialled. Speech smoothness, acoustic interruption behaviour and an actual carrier hangup must still be checked on a new call using the selected stack.

Gmail authentication is verified. Email delivery, invitation creation and automatic follow-up execution were deliberately not tested against real recipients; the relevant failure and proof paths use mocks. Configure the intended per-agent post-call automation before expecting those actions to happen automatically.

No claim is made that every possible paraphrase, external provider outage or model response is now failure-free. The server retains fail-closed action proofs and fail-open close decisions for those cases.

![Connected Calendar and Gmail](</D:/voice agent/artifacts/call-quality-review/capabilities-memory-integrations-20261026/connected-integrations.png>)
