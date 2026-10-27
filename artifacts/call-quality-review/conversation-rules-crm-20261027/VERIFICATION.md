# Conversation, handling rules, CRM and tag verification

Verified locally on 27–28 October 2026, branch `working-app-22-10-2026`.

The confirmed application defects below are fixed and covered by regression tests. The selected provider/model stacks were preserved, including `sarvam-105b-conversations`. No production configuration, billing rate, database migration, customer agent publication or real telephone call was changed by this verification.

The model can still occasionally return a completed response containing no speech. The application now handles that condition without depending on a second full-brain attempt: an approved ending receives the platform farewell; an open conversation receives a bounded contextual clarification. This is recovery from a provider defect, not proof that the provider defect has disappeared.

## 1. Findings from the supplied Gnani audit

**G1 and G2 — confirmed, fixed.** The model received a narrow tag recommendation and a conflicting final delivery contract. All 13 documented v3.0 tags now come from one catalog and one placement policy. Cues remain optional and context-sensitive; the agent should not manufacture laughter, coughing or excitement just to demonstrate a feature. The final speech instructions reference the selected catalog instead of introducing another whitelist or a one-cue restriction.

Evidence: [delivery rules](</D:/voice agent/server/prompts/tts_delivery_rules.py:48>), [final speech contract](</D:/voice agent/server/call/live_turn_orchestrator.py:1636>).

**G3 — confirmed placement problem, improved.** Guidance now places `<slow>` after a natural spoken lead-in. A live comparison produced 2.695 seconds with a mid-sentence cue versus 2.480 seconds without it. This demonstrates an effect in that sample; it does not guarantee a fixed speed change across every voice or phrase.

**G4 — vendor behavior, bounded.** Ordinary pauses use punctuation. The prompt no longer describes `<pauses>` as a reliably short pause. Trailing cue-only text remains stripped to avoid adding silence after the response. Exact pause duration remains provider-controlled.

**G5 — retained deliberately.** Exact `timbre-v3.0` tag gating is appropriate for the currently documented capability. No speculative v3.1 support was enabled. Unknown models continue to receive safe plain text until their capabilities are verified.

**G6 — the documentation claim is outdated.** Gnani's current WebSocket documentation explicitly describes audio tags. Its [WebSocket documentation](https://docs.gnani.ai/api/TTS/tts-websocket) and [audio-tag documentation](https://docs.gnani.ai/api/TTS/tts-audio-tags) support this path. Perceived expressiveness still needs human listening QA; waveform differences alone do not establish naturalness.

**G7 — confirmed, fixed.** An empty `errors: []` no longer terminates the socket. Recoverable errors end the affected synthesis request while retaining the warm connection. Authentication, credit/payment, explicitly fatal, and explicitly non-recoverable errors remain fatal.

**G8 — confirmed, fixed.** The fixed 20-second wait was replaced by a configured inactivity deadline. A long request can continue while audio makes progress; a stalled request still times out. The surrounding call watchdog remains responsible for the overall call limit.

**G9 — confirmed by a regression simulation, fixed.** Starting the next request no longer drains the local audio queue. The test queues the previous response's final PCM and EOS before the next request and proves both remain consumable in order. Completion counters remain monotonic across turns.

Evidence for G7–G9: [transport](</D:/voice agent/server/services/gnani_tts_ws.py:130>), [transport regressions](</D:/voice agent/server/tests/test_conversation_rules_crm.py:130>).

**G10 — partially addressed.** An explicit documented `hi-en` request is preserved by the Gnani language and voice routing layers. A new first-class Hinglish console language was not added: that would also require verified admission and language compilation across every configured STT/TTS stack. Hindi with English code-mixing remains available through the existing language option. Do not interpret the low-level routing fix as a new supported product language.

## 2. Sarvam reliability and prompt contradictions

**Confirmed provider behavior:** the original failing close/defer context returned three completed-empty responses in three non-streaming JSON requests too. Changing SSE parsing to ordinary JSON would therefore not solve the observed failure. The same conversations model was used throughout. The public [Sarvam chat documentation](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1) was checked alongside the transport implementation.

The application changes are:

- Treat completed-empty speech as a control event, not as consent to hang up and not as a reason to replay the entire brain.
- Complete the existing semantic close gate and callback persistence checks even when speech is empty. Only an approved close receives the server-owned farewell.
- For an open turn, request one short contextual clarification from the same approved model, with only the language, latest caller utterance and previous agent line. This separate recovery has a three-second deadline, 128 output tokens, no tools, no memory writes and no authority to close. Invalid structured output, timeout or provider failure falls back to the existing locale clarification.
- Pass recovered speech through the existing final speech and action-proof guards. Retain the unanswered request for the next turn.
- Preserve the final SSE usage chunk before reporting an incomplete completion, including reasoning-token usage. Empty or truncated responses must not disappear from cost accounting.

Evidence: [empty-response handling](</D:/voice agent/server/call/live_turn_orchestrator.py:638>), [bounded recovery](</D:/voice agent/server/call/speech_recovery.py:24>), [terminal usage handling](</D:/voice agent/server/providers/sarvam_llm.py:476>).

The compiler and final contract also stopped encouraging several contradictory behaviors:

- Missing prices no longer imply that a team will confirm them later without an available action.
- An answered enquiry no longer requires another question or sales pitch.
- Future interest/deferral is distinguished from rejection.
- Harmful requests call for a brief refusal without a sales bridge or discovery question.
- The instruction to leave `spoken_response` empty is explicitly limited to JSON close proposals. Speech-text sessions can acknowledge briefly; the platform remains the farewell owner.
- Callback collection does not claim that a request was saved or a call was arranged before platform confirmation.

Evidence: [compiler](</D:/voice agent/server/brain/agent_script_compiler.py:1546>), [fallback script builder](</D:/voice agent/server/brain/agent_spec_script_builder.py:99>), [close policy](</D:/voice agent/server/call/call_end_policy.py:177>), [callback instructions](</D:/voice agent/server/call/callback_close.py:59>).

An initial live rerun exposed a semantic contradiction: a Telugu busy/later turn was classified as refusal. The classifier now reports an independent intent, and its parser rejects a close that contradicts a defer/question/interested intent. It canonicalizes completion versus rejection reasons and rejects malformed intent/explicit-end values. Caller evidence and the existing server gate remain required. The final rerun kept this turn open.

Evidence: [classifier/parser](</D:/voice agent/server/call/close_classifier.py:177>).

## 3. Objection & Objective Handling

The Script editor now offers objections and objectives, each with a situation, multiline guidance, action and enabled state. The existing API field is retained for compatibility.

Structured editor metadata round-trips the rules faithfully. Only enabled guidance enters the compiled business prompt. Metadata JSON itself is excluded from the model context, even if accidentally marked enabled. Empty arrays explicitly mean all configured rules were removed; deleted rules cannot return from a stale fallback on reload. Existing free-form approved FAQ notes are preserved.

Saving uses the existing draft-revision, preview and publication flow. Rule changes therefore invalidate the saved configuration and recompile on publication. Objectives are subordinate to caller intent, safety, supplied facts, available tools, action confirmation and platform-owned closing.

Evidence: [rule representation](</D:/voice agent/voxly-ai/src/lib/handlingRules.js:1>), [save/merge flow](</D:/voice agent/voxly-ai/src/services/agentBrain.js:130>), [reload parsing](</D:/voice agent/voxly-ai/src/lib/studioScriptHelpers.js:228>), [metadata exclusion](</D:/voice agent/server/brain/business_brain_store.py:98>), [editor controls](</D:/voice agent/voxly-ai/src/console/modules/AgentStudioModule.jsx:1678>).

## 4. Lead CRM fixes

**Confirmed defects addressed:**

- Read-only users could reach lead mutations through permissions intended for reading calls. Create/edit/stage changes now require the existing write permission. The UI disables lead mutation, dialing, campaign selection and callback mutation for viewers while retaining inspection/history.
- Concurrent edits could overwrite newer notes/stages. Both update routes lock the tenant-owned row and accept `expectedUpdatedAt`; stale writes return 409. The console sends that revision. Explicit null can clear notes or unassign ownership.
- Identity-less calls could reuse an unrelated lead. Automatic matching now requires the same tenant and agent plus a valid phone, matching email, or the exact call marker for a replay. Invalid phone text falls back to carrier identity or stays unidentified.
- Concurrent automatic upserts could create duplicate contacts. They now serialize through a tenant-row lock. PostgreSQL phone matching runs in the database rather than loading every tenant lead into memory.
- Later model-extracted names could overwrite tenant-maintained contact identity. Automatic enrichment now fills blanks instead.
- A merely planned site visit was labelled `meeting_booked`. It now qualifies the lead; the existing tenant editor can confirm a booked meeting. This intentionally does not claim a booking from an LLM disposition alone. Converted remains tenant-confirmed and terminal records are protected from automatic regression.

Evidence: [authenticated routes/revision checks](</D:/voice agent/server/routes/app_leads.py:137>), [matching and transaction](</D:/voice agent/server/services/saas/lead_sync.py:130>), [stage mapping](</D:/voice agent/server/services/saas/lead_sync.py:29>), [console controls](</D:/voice agent/voxly-ai/src/console/modules/LeadsModule.jsx:25>).

SQLite-backed HTTP tests verify isolation, stale edits, explicit clearing, identity-less replay separation, contact preservation and stage behavior. The PostgreSQL locking path was reviewed in code; a production PostgreSQL concurrency/load test was not performed.

## 5. Tag creation fixes

Automatic call tags now preserve Unicode letters, vowel marks and numbers instead of destroying Indic-language labels. Normalization is idempotent, including existing `custom:` prefixes. Obvious phone/email/URL/markup data and non-string items are excluded from custom tags.

Conflicting sentiment labels are discarded rather than arbitrarily choosing one. Definite rejection/wrong-number/no-outcome records cannot also receive `ready_to_buy`. Do-not-call and wrong-number records suppress follow-up/action labels, preventing contradictory suggested follow-up metadata. Existing bounded vocabularies and server-owned outcome/contact/compliance categories remain in place. Tags do not constitute proof that an external action occurred.

This covers the existing automatic call-tag pipeline; it does not add a separate manual lead-tag taxonomy/database feature.

Evidence: [custom normalization](</D:/voice agent/server/call/outcome_schema.py:218>), [conflict reconciliation](</D:/voice agent/server/call/outcome_schema.py:288>).

## 6. Verification results

- **593 backend tests passed.** Includes native speech, action proof with mocked connected/failed tools, multilingual closing, empty-response recovery, transport/error ordering, compiler behavior, tenant isolation, CRM conflicts and conversion protection. See [pytest log](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/pytest.log>) and [JUnit results](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/pytest-results.xml>).
- **6 Node tests passed** for script parsing and handling-rule normalization/round-trip. [Log](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/node-tests.log>).
- **27 browser tests passed**, covering publication/reload/removal, failure states, lead ownership/conversion/campaign handoff, viewers, responsive layouts and existing agent workspace behavior. [Log](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/playwright.log>).
- **9 Reticle verdicts passed** in the running Vite app, including objective publication/removal and read-only CRM inspection. API responses were isolated fictional fixtures. Reticle reports SDK 3.7.0 behind driver 3.8.2 and a shell-host stub; these verdicts establish the web-app flows, not behavior of the real desktop shell or production API. Initial harness mistakes are retained separately; only the corrected final run is counted. [Evidence](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/reticle-verification.json>).
- **Production Vite build passed**, including prerendering. [Log](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/vite-build.log>).
- **Semgrep passed: 293 rules, 1,422 targets, zero findings/zero blocking findings.** This run completed successfully on this machine. [Log](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/security-sast.log>).
- Ruff found **zero new diagnostics** against scoped source baselines; pre-existing lint debt remains. `git diff --check` passed with line-ending warnings. Graft refresh completed. [Lint delta](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/ruff-delta.json>).

### Live provider tests

Three messy fictional briefs were generated through the current compiler, then exercised through the real Sarvam adapter and full turn orchestrator: English solar enquiries, Telugu auto service, Hindi education enquiries. Six sessions completed **17 turns with zero silent/error server turns**. Questions, unknown fees/availability, unsupported bookings, injection/discount claims, harmful requests, thanks-with-another-question, natural endings and explicit opt-outs were covered.

The final sample contained **two raw completed-empty provider replies**, both on genuine ending turns; both received the approved platform farewell. Three opt-outs closed through the platform's direct rule path. Questions and the busy/later turn stayed open. See [transcripts](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/live-conversations.json>) and [runner](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/run_live_validation.py>).

Separate forced-empty simulations exercised **real same-model recovery in Telugu, English and Hindi**. All three produced a clarification and kept the call open. The Telugu busy case asked the preferred callback day/time. Here the main empty reply was injected deliberately; the recovery/model and server gates were real. [Evidence](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/live-recovery.json>).

Six sequential live Gnani requests on a warm WebSocket all returned audio. Whisper RMS was about 0.363 times its control; the mid-sentence slow sample was about 1.087 times its control duration. These are transport/acoustic measurements, not human listening scores. [Evidence](</D:/voice agent/artifacts/call-quality-review/conversation-rules-crm-20261027/gnani-wire.json>).

Full voice-loop regression simulations prove farewell playback finishes before the mocked carrier receives one hangup command, and the lifecycle records `agent_ended`. No real PSTN carrier hangup, OAuth login, external booking, microphone/STT quality or human listening test was performed in this task. Live conversation tests used no external integration and mocked callback persistence; connected/failed tool behavior was verified in regression simulations. Dynamic-memory persistence and every language's live provider behavior were not exhaustively retested.

## 7. Remaining limits and rollout

Occasional unnecessary follow-up questions and generic topic invitations still appeared in live model replies despite the improved instructions. The harmful request was refused, but refusal style is not perfectly consistent. Provider-empty completions still occur. These facts prevent a claim of flawless agent behavior in every edge case.

The changes are local and uncommitted. Deploy the updated backend/frontend through the normal release process. Existing published agents were not silently rewritten: review/regenerate scripts made with the old templates and publish the updated configuration to refresh their saved brains. Handling-rule edits use the normal Save/publication flow and apply to subsequent sessions; an already-active call retains its existing session context. First-class Hinglish admission and human audio-quality QA remain separate follow-up work.
