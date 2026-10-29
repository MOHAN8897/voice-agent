# Callback, DND, console and campaign verification

Date: 29 October 2026. Branch: `working-app-22-10-2026`.

## Result

The traced callback, suppression and campaign paths had several confirmed gaps. The fixes below are implemented and tested. Callback campaigns now use the existing durable follow-up job rather than making a second queue entry. DND is checked again after voice preparation, immediately before the carrier request. Agent settings provide current callback permissions to the next session's compiled brain.

This verifies application behavior under the scenarios listed below. It does not establish that a model will interpret every possible utterance correctly, or that a real carrier will connect every scheduled call. No customer calls, TTS playback or fresh live-provider conversation tests were performed in this audit.

## Confirmed findings and changes

### 1. A later neutral intent could overwrite a caller's opt-out — high

The live preference previously accepted a later `none` after `do_not_call`. Finalization could then see the neutral preference. An opt-out now survives later labels, concurrent context updates and eviction of the live call context by consulting persisted metadata. The metadata writer also refuses to replace an existing opt-out.

Evidence: `server/call/contact_preference.py:26–77`, including `if meta.get("contact_preference") == "do_not_call":` and the corresponding live-context recheck after the database/file await. Regression cases exercise neutral labels and context loss in `test_contact_preference_optout.py`.

Ordinary rejection, abuse or ending one conversation still does not automatically mean permanent DND. Removing DND requires a separate tenant action with renewed permission.

### 2. Suppression or campaign permission could change during voice preparation — high

The first DND check happened before preparing voice/audio. Preparation can take long enough for a caller opt-out, account restriction, policy change or campaign pause to arrive before the physical dial.

A trusted internal check now runs after preparation and immediately before each supported carrier's create-call request. It rechecks current user verification and permission, workspace/account status, owned agent, DND, outbound enablement, wallet eligibility and applicable campaign/follow-up state and clock. Follow-up reservations must match their current dispatch identity. Client JSON cannot inject this private callback.

Evidence: `server/services/saas/predial_policy.py`, `server/services/saas/telephony_orchestrator.py:272–276`, and `_predial_block` plus its two call sites in `server/routes/dev_telephony.py`. The result code is `predial_policy_changed`; `call_admission.NO_DIAL_CODES` releases a reservation for this confirmed no-dial result.

The primary carrier regression adds an opt-out during preparation, executes the real policy check against isolated data and verifies zero carrier POSTs and one prepared-session cleanup. Secondary-carrier coverage verifies preparation/check ordering, no POST and cleanup. Allow-path coverage confirms a valid call still proceeds. Additional checks cover campaign pause, disabled follow-ups and stale reservations.

A known pre-dial block does not spend the follow-up's actual call-attempt budget. A separate monotonic `dispatchSequence` ensures a later human-approved attempt uses a new idempotency identity. An uncertain provider response retains its reservation and requires review; it is not blindly replayed.

### 3. Campaigns could compete with an already requested callback — high

An ordinary contact campaign did not give an existing callback reservation priority. Copying callback numbers into a new campaign would also lose the caller's requested time and create two potential callers.

Ordinary campaigns now skip a recipient with an existing pending callback/follow-up. The new callback/missed-call campaign sources bind owned job IDs to a campaign and keep one dispatcher. Campaign launch can delay a six-hour request, but cannot advance it. Draft, paused and review-required campaigns hold their linked jobs; cancellation stops pending work; expiration stops undispatched work; accepted calls are allowed to finish. Current campaign authorization, concurrency and both attempt limits are enforced.

Evidence: `server/services/saas/campaign_followups.py`, `server/services/saas/campaign_runner.py:151–324` (`row.status, row.attempts = "followup_reserved", max(0, row.attempts - 1)`), `server/services/saas/followup_service.py:356–495`, and `CampaignCreate.followupJobIds` in `server/routes/campaigns.py`.

Regressions cover six-hour timing, delayed launch, duplicate dispatch, DND after creation, pause/resume, cancellation, expiry, revoked authorization, foreign job IDs and duplicate claims.

### 4. Background campaign authorization and calling hours were inconsistent — high

The worker now checks current email verification and effective role instead of relying only on the actor originally stored on a campaign. DND uses the workspace that owns the recipient rather than a possibly different billing workspace.

Campaign hours now share the agent scheduling logic, including overnight windows, the opening day's ownership, holidays and outbound enablement. A claimed contact is checked again before invoking outbound dispatch. Campaigns support explicit start/expiry bounds. An invalid recipient time zone produces review rather than endless short retries; new imports with invalid named time zones are rejected.

Evidence: `campaign_runner._principal`, `within_calling_window`, `within_agent_hours` and `_dial_claim` in `server/services/saas/campaign_runner.py:43–239`. `CampaignCreate.validate_schedule` requires offset-aware timestamps and a valid ordering. Tests cover a window closing between claim and dispatch and the overnight/holiday boundary.

### 5. Settings failures could overwrite valid operating or voice settings — high

A failed operating-profile fetch was treated as an empty profile. Saving unrelated settings could write defaults over existing hours. Every save also attempted a legacy voice write, with a fallback voice value, and swallowed its errors.

The settings panel now blocks saving after an operating/compliance load failure, displays the error, and writes identity/profile data only when changed. Ordinary settings saves no longer write voice selection through the legacy endpoint. The voice panel retains its existing revision-controlled save path. Viewers cannot edit the main settings fieldset.

Evidence: `voxly-ai/src/console/modules/agent-workspace/AgentSettingsPanel.jsx`, particularly `if (!profileLoaded) throw new Error(...)`, `identityChanged`, and the conditional profile save. Browser regressions verify zero mutation requests after a profile-load failure and no voice/profile writes for a follow-up-only edit.

### 6. The brain did not explain the saved callback dispatch permission — medium

The existing capabilities section described recording a callback but did not distinguish automatic dispatch from review/manual handling. A script could therefore imply scheduling that the tenant had never enabled.

Compilation and session admission now load the owned agent's current follow-up policy and include one compact contract: `callback_dispatch: manual_only|review|automatic`, the missed-call mode and the need for a successful server result before claiming scheduling. Connected executable tools still come from the existing tenant/agent permission resolver. A future-interest request must collect desired timing instead of being treated as rejection or DND.

The same pass refreshes the selected language and current recording disclosure. A language edit also queues a rebuild of the stored snapshot. A running session keeps its admitted brain; changes apply to the next session.

Evidence: `server/brain/capabilities.py:113–196`; both entry paths in `server/call/call_brain_lock.py:25–77`; and `AgentService.patch_agent`'s `if disclosure_changed or language_changed:`. Tests compile current review/automatic policies in English, Telugu and Hindi, assert exactly one selected-language pack, and verify changed versus unchanged language saves.

### 7. Interrupted callbacks and completed requests could remain misleading — medium

An explicit callback request interrupted before the close handshake could be lost. Finalization now recovers an unfinished explicit request for human review only. It does not silently authorize an automatic call or revive a revoked/DND request.

A confirmed connected follow-up now completes its original callback request as well as the scheduled job. Tenant-confirmed conversion updates the owning agent's matching lead in the same transaction and uses the existing retirement path for pending follow-ups. Another agent's lead is not marked converted.

Evidence: `server/services/saas/callback_request_service.py:76–155,175–211`; the finalization recovery call in `server/call/call_lifecycle_service.py:730–731`; and `_reconcile_dials` in `server/services/saas/followup_service.py:498–525`.

### 8. DND management needed stronger removal and scheduling safeguards — high

Removal already existed. It now requires a meaningful trimmed reason and explicit reconsent. The UI supplies the entry's observed `added_at`, allowing the server to reject removing an opt-out renewed after the list was loaded. An audit record is committed with removal.

Manual/bulk additions and live opt-out enrollment serialize registry edits. Adding DND suppresses pending follow-ups in the same transaction. Saving an opt-out is allowed even if the workspace has subsequently been paused. Removing an entry does not resurrect previously cancelled jobs.

The list now handles stale fetches, explicit load errors and retry. The confirmation remains disabled until the required reason and permission are supplied. The API helper defaults permission to false.

Evidence: `server/routes/campaigns.py:122–151,789–964`; `server/services/saas/dnc_service.py:17–26`; and `voxly-ai/src/console/modules/DncRegistryPanel.jsx`. Tests cover renewed-opt-out conflict, tenant isolation, same-transaction suppression, confirmation gating and the successful removal request.

### 9. Callback tagging and valid campaign variables needed corrections — medium

The callback tag previously depended partly on an English next-action string. `followup:callback` now also follows the recorded typed callback preference, so a Telugu next-action sentence does not lose the callback signal.

The script validator also rejected valid `{{...}}` recipient variables as unfinished generated placeholders. It now accepts only valid variable signatures explicitly declared in the original brief. Undeclared, malformed and unfinished placeholders still fail. Per-contact campaign variable validation remains in place.

Evidence: `server/call/outcome_schema.py:250–301`, including `contact_preference == "callback"`; and `server/brain/agent_script_compiler.py:1269–1280`. Regressions cover Telugu callback tagging, valid campaign generation and invalid placeholder forms.

## What console options control

Not every setting belongs in the model prompt. Financial limits and calling permission must be enforced by the server even if a model gives a different answer.

- **Conversation inputs:** the published business script, objective/objection rules, selected language, current recording disclosure, executable tool capabilities and callback permission feed the existing compilation/admission path. Existing compiled-brain, rule and session-lock regressions passed alongside this audit's new policy/language checks.
- **Farewell and call control:** the saved closing policy remains server-owned. Callback confirmation requires a saved request before the configured farewell. The hangup/closing regression suites passed; this audit did not change greeting playback or carrier hangup implementation.
- **Voice/tier selection:** remains on the existing revision-controlled voice configuration and admitted stack. Unrelated settings saves no longer rewrite it. No rates, provider assignments or tier stacks were changed.
- **Phone routing, outbound enablement, operating hours and closed dates:** persisted operating profile and server admission/scheduler controls. Campaign and follow-up dispatch respect their intersection with the relevant calling window.
- **Follow-ups and scoring:** the persisted versioned policy controls modes, timing, retry/cooldown/daily limits, expiry and scoring. Automatic calling requires the existing tenant acknowledgement. Review mode does not call on its own.
- **Tags and lead status:** informational/custom tags do not grant dialing permission. `signal:do_not_call` is server-derived from explicit contact preference; a generic model tag cannot manufacture DND. Conflicting sentiment choices are removed, and rejection/DND cannot retain `signal:ready_to_buy`. Conversion is a tenant-confirmed workflow.
- **Wallet/compliance:** enforced independently of the prompt and checked again at the outbound boundary. An internal DND registry is not a national do-not-disturb registry or proof of regulatory compliance.

## Tenant workflow

1. In **Agent settings → Follow-ups & scoring**, choose review or automatic callbacks/missed calls, the time zone, hours and limits. Automatic calling requires the existing wallet-charge/permission acknowledgement. This audit did not enable it for anyone.
2. A caller's explicit request is saved before the agent says it was noted. Timing such as “after six hours” is resolved from caller evidence and request time. Unclear timing or an interrupted request goes to review. Business windows and capacity can move actual dispatch later; the agent must not promise an exact successful schedule without a server result.
3. In **Leads → Callbacks & missed calls**, review requests, approve/edit timing, cancel or create a follow-up campaign. The audience shows eligible existing jobs and their earliest times. Unclear callback times must be reviewed first.
4. **Import earlier calls for review** is an explicit bounded action. It never enables automatic calling and does not revive closed jobs. Missed-call imports require that flow to be enabled in settings.
5. In **Leads → Do not call**, add/import numbers or remove an entry with renewed permission and a reason. Pending suppressed work stays cancelled after removal.
6. Campaign launch requires contact validation and explicit authorization. A start time cannot override a later caller-requested callback time. Pause/review holds linked work, cancellation stops future dispatches, and accepted calls can finish normally.

## Verification observed

- **383 passed, 1 skipped** in the broad backend regression run: campaigns, durable follow-ups, callbacks/withdrawal, contact preference/DND, compiled brains, session locks, rules/CRM, timeline, primary opening/prewarm and carrier handoff. The skip is the historical migration test requiring a PostgreSQL-specific run; the default suite uses SQLite isolation.
- **12 passed** in an additional language-save/voice-revision/language-resolution run, including both new language-change cases. These ran after the broad suite.
- **33 passed** for the final campaign workflow audit against real local PostgreSQL, each test in a generated isolated schema. Existing customer tables were not altered.
- **7/7 PostgreSQL queue cases passed:** competing workers, same-number cooldown, missed-delay dedupe, DND, approved overnight adjustment, exact window boundary, and uncertain dispatch not being replayed. The existing outbound boundary was mocked; the queue and idempotency journal were real.
- **40/40 Playwright tests passed** across the new campaign-follow-up audit and existing campaign, follow-up, console-layout and workspace suites. Fixtures isolate customer/API mutations. They verify exact campaign job-reference payloads and safe settings writes.
- **26/26 Reticle assertions returned `verified: yes`** on desktop and mobile, with zero captured console errors. These prove rendered controls and API consumption against isolated fixtures, not live customer writes. Successful request-body capture is limited in this SDK; Playwright covers the exact bodies. Reticle also reports partial state-store coverage, so no unobserved store behavior is claimed.
- **Vite production build passed**, including the six static public pages.
- **Ruff F/E9 passed** on changed Python files and reproducible verification helpers.
- **Semgrep: 293 rules, 1,455 targets, zero findings**, using OWASP Top Ten, security-audit and the repository rules. The prescribed `security_audit.py --mode sast` launcher was blocked by Windows Application Control at `pysemgrep.exe`. The same installed Semgrep Python entry point successfully ran the full rules/configuration above; the blocked launcher itself is not reported as passing.
- Local backend started from current source, `/api/health` returned `ok: true` with database/schema/Redis healthy, and OpenAPI registered both new audience and historical-import routes. Migration revision remains `047_durable_followups`; no new migration or persisted tenant-policy changes were applied.

Reproducible UI probes: `verify_reticle.py` and `fixture.js` in this directory; Playwright scenarios: `voxly-ai/e2e/campaign-followup-audit.spec.js`; backend scenarios: `server/tests/test_campaign_workflow_audit.py`. Raw browser captures are intentionally local/ignored.

## Industry reference and limits

Bounded calling windows, known recipient time zones, shared concurrency and a last eligibility check before dialing match the practices documented in [Vapi's campaign scheduling guidance](https://docs.vapi.ai/outbound-campaigns/scheduling-and-lifecycle). Personalization validated per recipient and separate recipient outcomes follow the same general model as [Vapi's campaign overview](https://docs.vapi.ai/outbound-campaigns/overview). These are implementation references, not a claim that every vendor uses the same design.

No staging DAST/Strix scan was run because no staging target was provided. No production deployment, actual carrier dial, TTS test or fresh live LLM multilingual quality evaluation was performed. The opening/prewarm regressions passed, but a final controlled real-call acceptance check is still needed to verify carrier audio, timing and physical hangup together. Regulatory calling rules and external suppression registries remain separate configuration/integration concerns.

VERDICT: PASS for the tested application workflows, subject to the live-call and integration limits above.
