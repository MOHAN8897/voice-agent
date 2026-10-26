# Callback, farewell and carrier hangup verification

Date: 26 October 2026. Call: `b0ea94d9-409c-4989-a2d5-c43437cf9a41` (Meera).

## What actually happened

**Confirmed:** this call did end through the carrier API. The authoritative CDR says `hangup_source: API Request`, `hangup_cause: NORMAL_CLEARING`, and `end_time: 2026-10-26T05:50:40Z` — **11:20:40 IST**. See [the redacted carrier evidence](./call-evidence.json).

The caller asked for a call next month. The server approved a callback close at 11:20:33. It initiated hangup and closed local media at approximately 11:20:38; the carrier ended the phone call at 11:20:40 and its hangup webhook arrived at approximately 11:20:42. The API was not rejected for this call.

The spoken line was “మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నోట్ చేసుకున్నాను. ధన్యవాదాలు.” It acknowledged the request but used the short callback-specific closing rather than the complete configured farewell. There was no tenant-managed future callback request behind that assurance.

The carrier bridge also had a separate confirmed code defect: it set `_closed = True` before awaiting the carrier request and counted a successful WebSocket close as successful disconnection even when the carrier API failed. The carrier client treated every 404/422 as an already-ended call. These weaknesses did not cause a carrier rejection in the reported call, but made failure reporting and teardown unreliable.

## Changes

### Durable callbacks

- `server/services/saas/callback_request_service.py:22` prepares the final callback closing. It saves the request before confirming it aloud. Failed storage produces an explicit localized failure message rather than a false assurance.
- `server/services/saas/callback_request_service.py:58` writes an idempotent request to the existing `CallCallback` table with `mode=requested`. The original call and agent are verified against the call's tenant. Requested timing and source words are retained in the existing call ledger.
- The tenant can view requests, start a manual callback through the existing outbound checks, mark converted, or remove a pending request. The last two actions retain the record for audit. The UI is in Leads, and in an agent's lead view.
- This is a manual follow-up queue. It does not promise or initiate an automatic scheduled call. Saving a request does not require a CRM integration.
- The reported call's genuine next-month request was recovered into its tenant's queue; the persisted status is `requested`. No new phone call was placed during recovery.

### Editable, complete farewells

- `voxly-ai/src/console/modules/AgentStudioModule.jsx:1594` adds **Farewell the caller hears** below Calling script. It has its own text field; the greeting editor and prewarm handlers were not changed.
- The field is saved as the `saas_call_end_policy` runtime configuration section. Its text is excluded from business-script optimization and inserted once into the compiled call-end policy.
- Both ordinary and precompiled publication paths apply it. Recompilation uses the published policy, so a newer unpublished draft cannot silently replace the farewell.
- `server/call/call_lifecycle_service.py:537` loads that published policy into the live call context. Platform-section refresh preserves it. A language change requires review of custom farewell text.
- `server/call/call_end_policy.py:75` appends the full configured farewell after a successful callback acknowledgement. Speech is synthesized at closing time; it is not a prewarmed audio greeting. The server owns the single farewell to prevent duplicate goodbyes.
- The normal speech-only reply format remains in place. The model's separate closing proposal and the server's validation/playback handoff remain responsible for closing.

### Carrier teardown

- `server/services/vobiz_pstn_bridge.py:625` keeps media open while the carrier hangup request is pending, uses the call's original account credentials, and permits teardown even if new dialing has subsequently been disabled.
- One bounded retry covers a transient API failure. A failed carrier request is propagated as a failure; a WebSocket close cannot make it look successful.
- A 404/422 is accepted as already ended only when a matching final CDR proves it.
- API acknowledgement and the authoritative hangup callback have separate fields: `carrier_hangup_acknowledged` and `carrier_hangup_confirmed`. The authenticated webhook records the latter in `server/routes/vobiz.py:620`.
- Existing farewell-playback completion and the caller-resumption check precede the carrier command.

## Verification

**VERDICT: PASS for the implemented behavior in the tested scope.**

- **604 server regression tests passed**, covering close decisions, multilingual intent handling, callback persistence, compiled brains, playback completion, interrupted/revoked closes, and carrier teardown. Evidence: [regression-results.xml](./regression-results.xml).
- The exact Telugu request from the reported call passed a regression through the real close gate, callback database save, complete farewell, and simulated carrier acknowledgement. The final outcome was `agent_ended`.
- **17/17 live Standard-model classification simulations passed** across Telugu, Hindi, Tamil, Kannada and English. The model was `sarvam-105b-conversations`; business speech, TTS/playback and carrier transport were simulated. This is not a claim that 17 real telephone calls were placed. Evidence: [live-results.json](./live-results.json).
- **9 browser tests passed** for the script editor and callback queue. The callback test was rerun successfully after adding HTTP-200 failure handling for a rejected manual dial. Both publication and conversion obtained Reticle `verified: yes` results against the running Vite app, with synthetic API fixtures: [farewell](./reticle-farewell.jsonl), [callback](./reticle-callback.jsonl).
- Browser tests check farewell save/reload, preservation of the calling script, no automatic dialing, explicit callback submission, retention on failure, conversion, and removal from the pending list after reload.
- Production Vite build passed. The full build including public-page prerender also passed earlier in this change.
- AST comparisons confirm the carrier start handler, voice-loop startup, buffered greeting playback, and opening-delivered note are unchanged from HEAD. Evidence: [prewarm-invariants.json](./prewarm-invariants.json).
- Ruff comparison found **zero introduced findings** across changed Python files; existing findings remain. `git diff --check` passed. Evidence: [lint-delta.json](./lint-delta.json).
- Graft was refreshed. No subagents were used.

## Limits and remaining operational checks

- No new real PSTN call was placed after the changes. Live carrier verification here was the read-only CDR check of the reported call. A real call after backend deployment/restart is still needed to verify the updated behavior on the phone network.
- The source changes are local; no deployment or Git push was performed in this task. Farewell edits become effective through the existing Save/publish flow.
- The SAST command could not run: Windows Application Control blocked `pysemgrep` (exit 127). This is **not a clean SAST result**. See [sast.log](./sast.log).
- An additional existing Vobiz telephony test expects WAV recording XML while the current unchanged answer XML uses MP3: `test_vobiz_answer_webhook_get_method`. It failed in a broader probe and was not changed as part of this closing-flow fix.
- Carrier/network failures can still prevent physical teardown. The new flow retries once and reports the failure rather than recording a media-only disconnect as a carrier acknowledgement.
