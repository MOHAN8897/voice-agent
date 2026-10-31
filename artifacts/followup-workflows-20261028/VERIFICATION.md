# Callbacks, missed calls, DND and lead performance

Date: 2026-10-28. Scope: follow-up workflows and their tenant console controls.

Final release recheck: 2026-10-29 (Asia/Calcutta).

## What was missing

- **Confirmed:** caller-requested callbacks were saved as manual requests, without a durable due time or automatic dispatcher.
- **Confirmed:** missed inbound attempts were recorded, but had no configurable automatic callback queue.
- **Confirmed:** a DND registry and opt-out enrollment already existed under Campaigns. It was difficult to discover from Leads, and outbound workspace resolution could check a different tenant scope.
- **Confirmed:** the summary counted a capped timeline page, silently undercounting larger call histories.
- **Confirmed:** supplying a callback phone bypassed the source lookup. Missed-attempt journal rows also populated the original-call foreign key, and journal write failures could be swallowed before dialing.
- **Confirmed in live synthetic probes:** the conversation model returned 30 minutes for a six-hour request in English and Hindi; the Telugu timing was unresolved. Scheduling must not use the speech model as a clock. Baseline: `live-timing-voice-model-baseline.json`.

## Implemented behavior

### Permission and scheduling

- Follow-up permission defaults **off**. Caller-requested callbacks support review or automatic scheduling. Missed inbound calls support off, review, or automatic scheduling, with a configurable delay.
- Enabling permission or moving a category to automatic requires an explicit wallet-charge acknowledgment. Settings save through the existing save dock; failed saves retain the draft. Viewers can inspect these controls but cannot edit them.
- Jobs have a durable ID, original call/attempt reference, due time, expiry, reason, attempt history, authorizing user and billing account. There are no six-hour in-memory timers.
- Calling windows, IANA timezone, weekdays, existing agent operating hours and holidays, retry limits, daily limit, and same-number cooldown are configurable. DST gaps and ambiguous local timing go to review.
- Timing is a bounded background extraction through the **existing configured post-call analyzer**. Its model is pinned to the job. Speech tiers, live conversation models, greeting preparation and live reply formats are unchanged. Failures do not switch models or invent a time.
- “After six hours” sets an earliest time. Calling windows and limits can move it later. Vague/conflicting timing requires review. A different caller timezone requires review rather than an inferred area-code timezone.
- Newer caller requests replace older pending requests for the same agent and number. Explicit callbacks take priority over generic missed-call jobs. A later answered contact suppresses a missed-call callback.
- Manual callbacks replace pending automation; an already dispatched callback cannot be duplicated through that control.
- Disabling permission cancels pending jobs. It cannot recall a dial already accepted by the phone network.
- Tenant approval is stored separately from a job's changing status/reason, so moving an approved callback into the next calling window or retry does not discard approval. Window checks use the precise current time: a worker cannot dial up to a minute before opening.
- Timing extraction includes bounded recent caller/agent context. A separate answer such as “six hours later” anchors to that caller utterance, not the end of the call. An unaccepted agent suggestion cannot establish a requested time. Policy timezone changes and inconsistent absolute offsets require review.

### Dispatch and DND

- The worker resumes durable jobs after restart and reserves dispatch with row locks, leases and deterministic request IDs. A stale/uncertain dispatch goes to review instead of being dialed again automatically.
- Dispatch rechecks current account membership and permission, workspace status, DND, conversion, request status, expiry and configured limits. It then uses the existing outbound admission path for published brain, agent state, outbound permission, wallet, caller ID and capacity checks.
- The authorizer check uses the same effective membership roles and email-verification requirements as interactive account authentication. Losing eligibility blocks automatic dispatch.
- Retries happen only after a recorded unanswered/busy result, within configured limits. Missing or uncertain carrier results require review.
- DND management is available under Leads, using the existing tenant-wide registry and re-consent audit flow. DND numbers are visibly blocked from lead selection/call controls. DND remains enforced on the server.
- The call's DND tag comes from the recorded caller opt-out, not an unsupported post-call model label. A plain refusal does not become a permanent opt-out.
- Marking a lead converted retires pending requests and scheduling jobs. This does not prevent a tenant from initiating an ordinary, intentional customer-service call later.
- New follow-up data participates in tenant export and deletion. User/account deletion clears authorization references instead of blocking deletion; quarantined workspaces cannot dispatch jobs.

### Scoring and analytics

- Future outcomes receive an explainable priority assessment with configurable weights, thresholds and business-memory field mappings. Components and source outcome are visible in lead details.
- Scores are not conversion probabilities or call permission. Low-confidence/inconclusive outcomes are unscored. A later rejection reassesses an existing lead without changing its tenant-maintained stage; an older analysis cannot overwrite a newer assessment.
- Conversion remains tenant-confirmed. DND always overrides a high score.
- Agent analytics now include connect rate, completed-call average duration, new leads, confirmed conversion, settled call charges and cost per lead. The server processes the whole period, without the previous 100/500-row statistics ceiling.
- Connect rate means answered connections divided by attempts; it can include voicemail. Average duration uses completed connections. Conversion uses leads created in the period and their current confirmed status. CPL uses settled wallet call charges divided by period-created leads; it is unavailable when settlement coverage is incomplete or there are no leads. Provider wholesale costs are not exposed.

## Evidence

- Backend impact suite: **229 passed**, covering durable scheduling, permissions, approval retention, exact calling-window boundaries, callback journals, CRM, opt-out, call timeline, speech transport, tenant export/deletion and pricing configuration regressions. Six existing dependency deprecation warnings were reported.
- Combined browser run: **29 passed**: six follow-up checks, six pricing/calculator checks and 17 existing workspace/layout checks. They cover permission/charge acknowledgment, save persistence and failure retention, review consent, DND, metrics, Pipeline navigation, mobile layout, viewer restrictions and published tax/calculator configuration.
- Reticle: **24 affirmative desktop/mobile verdicts** for follow-up controls, metrics and the Pipeline destination, plus a final clean pricing run with **2/2 affirmative verdicts** for volume/URL/tax recalculation and share-link confirmation. Zero console errors in the follow-up fixtures. An earlier pricing harness incorrectly expected a focus action to change the estimate; keyboard activation and an exact status predicate corrected the harness. That failed/no-fault exploratory run is not counted as a pass.
- Reticle does not capture successful request bodies in this installed SDK. Exact permission payloads are asserted by Playwright; Reticle proves the successful request plus displayed confirmation. All browser verification uses isolated API doubles, not customer account mutations.
- PostgreSQL migration SQL generated offline. Additive upgrade/downgrade/upgrade exercised against a disposable SQLite database.
- Before activation: the configured local `voice_agent` database was reachable at revision `046_remember_me_sessions`.
- Live synthetic timing results after the scheduling-analyzer correction: see `live-timing-probes.json`. No telephone calls or TTS were used by the probe.
- Live timing probes: **12/12 passed**, covering English, Telugu and Hindi six-hour requests, vague timing, a separate Telugu timing answer with its own timestamp and unaccepted agent suggestions. Both text-voice and native-audio contexts use the configured background analyzer. These checks do not establish perfect language understanding for every possible utterance.
- Real PostgreSQL verification: **7/7 passed** in a disposable, helper-owned schema, removed afterward. Concurrent workers dispatched one job once; concurrent jobs for the same number respected cooldown. Missed-call delay/dedup/origin journaling, DND, overnight tenant approval, precise window boundaries and uncertain dispatch protection passed. Only the final outbound boundary and filesystem brain lookup were mocked; no network calls were dialed.
- Vite production build passed, including six public prerendered pages. Next production build passed with 50 pages; standalone TypeScript `tsc --noEmit --incremental false` also passed. Ruff syntax/unused-import checks passed. Required final full Semgrep SAST scanned 1,451 targets with 293 rules: **zero findings**.
- Repository graph refreshed with `graft build`.

## Activation and limits

Migration **047_durable_followups** creates three new tables: `agent_followup_policies`, `followup_jobs`, and `lead_assessments`. It changes no existing billing rates, tier assignments or call records. Existing manual callbacks remain available before migration.

The user explicitly approved applying migration 047. It was successfully applied to the configured local `voice_agent` database, advancing it from `046_remember_me_sessions` to `047_durable_followups`. All three new tables were verified, including primary keys, tenant/agent and origin uniqueness, and cascade/authorization-reference deletion rules. The tables were empty after migration. No tenant automation was enabled.

The local backend was started on `127.0.0.1:8000` because no backend was listening. Startup completed and `/api/health` returned HTTP 200 with `ok: true`. The worker's `run_once()` was executed against the migrated PostgreSQL database and processed zero jobs successfully. No follow-up storage or worker errors were reported in startup logs. The focused follow-up suite was rerun after activation: **32 passed**. Machine-readable activation evidence is in `activation.json`.

During the final recheck, the local backend process started by this task was restarted to load the fixes. Before restarting, the database had no calls in the preceding two hours and zero follow-up policies/jobs. The replacement process completed startup, health returned HTTP 200 with `ok: true`, and no follow-up startup errors appeared. The schema remains at 047; no automation setting was enabled.

Automatic calls remain off until tenants enable the desired modes through Agent Settings → Follow-ups & scoring and confirm permission/charges. Review jobs under Leads → Callbacks & missed calls; manage suppression under Leads → Do not call. Reticle was not rerun for this schema/runtime-only activation; the UI evidence above covers the implemented interface.

No customer numbers were dialed. A real carrier end-to-end callback and sustained multi-process contention/load test remain deployment checks. Real PostgreSQL concurrent-task tests passed, but they do not prove carrier delivery or production load capacity. The internal DND registry is workspace suppression, not automatic access to a national registry. No staging target was supplied for DAST or penetration testing.

Raw JSON, SQL and screenshots are local verification captures excluded from Git. The written findings and reproducible `fixture.js`, `verify_reticle.py`, `probe_timing.py` and `verify_postgres_queue.py` helpers are versioned. Run helpers from the repository root with its Python dependencies and, for UI checks, the existing console dev server. The PostgreSQL helper restricts itself to the local `voice_agent` database and deletes only its uniquely named disposable schema.

## Primary references used

- [Vapi scheduling and lifecycle](https://docs.vapi.ai/outbound-campaigns/scheduling-and-lifecycle): timezone-aware windows, bounded scheduling and capacity-aware execution.
- [Vapi outbound scheduling](https://docs.vapi.ai/calls/outbound-calling): earliest/latest scheduling boundaries.
- [HubSpot lead scoring](https://knowledge.hubspot.com/scoring/understand-the-lead-scoring-tool): explainable, configurable priority rules and thresholds.
- [Twilio call status definitions](https://help.twilio.com/hc/en-us/articles/223132547-What-are-the-Possible-Call-Statuses-and-What-do-They-Mean-): a completed network connection does not establish that a person answered.

The implementation uses these operational patterns with this platform's existing phone admission, wallet, agent configuration and opt-out controls.

## Reproducing the checks

From the repository root:

```powershell
python -m pytest server/tests/test_durable_followups.py server/tests/test_tenant_deletion.py server/tests/test_sarvam_composed_transport.py server/tests/test_call_callback.py server/tests/test_agent_scoped_leads.py server/tests/test_conversation_rules_crm.py server/tests/test_callback_requests_and_farewell.py server/tests/test_contact_preference_optout.py server/tests/test_call_timeline.py server/tests/test_compliance_dnc_and_onboarding.py server/tests/test_pricing_merchandising.py -q --tb=short
$env:PYTHONPATH = (Get-Location).Path
python artifacts/followup-workflows-20261028/verify_postgres_queue.py
python artifacts/followup-workflows-20261028/probe_timing.py
python artifacts/followup-workflows-20261028/verify_reticle.py
python scripts/security_audit.py --mode sast
```

The timing probe makes bounded paid model requests using existing local configuration; the PostgreSQL helper creates/removes an isolated test schema. Neither places calls. Reticle requires the running console at port 5173.

From `voxly-ai`, with its existing dev server running:

```powershell
$env:PLAYWRIGHT_SKIP_WEBSERVER = '1'
npx playwright test e2e/followup-workflows.spec.js e2e/pricing-calculator.spec.js e2e/console-layout-refresh.spec.js e2e/workspace-experience.spec.js --workers=2 --reporter=line
npm run build
```

From `web`: `npx tsc --noEmit --incremental false` and `npm run build`. An isolated Next output directory was used for this recheck so the existing development server was not disturbed.
