# Follow-up workflows and console release

Branch: `working-app-22-10-2026`. Date: 2026-10-28.

Final release recheck: 2026-10-29 (Asia/Calcutta).

## What tenants can do

- Enable caller-requested automatic callbacks once, with explicit permission and a wallet-charge acknowledgment. A request such as “after six hours” becomes a persisted job, subject to the tenant's calling windows, timezone, expiry and limits. Ambiguous requests require review.
- Configure missed inbound calls separately: off, manual review, or automatic calling after a chosen delay.
- Review, schedule or cancel jobs in Leads → Callbacks & missed calls. Marking a lead converted retires pending follow-ups.
- Manage workspace suppression in Leads → Do not call, with audited re-consent before removal. Explicit caller opt-out drives call tags; ordinary rejection does not imply permanent suppression.
- Configure outcome-based lead priority weights and thresholds, inspect score reasons, and view connect rate, completed-call average duration, tenant-confirmed conversions, settled costs and cost per lead.

## Reliability and permission fixes

- Durable job records replace in-memory timers. Row locks, leases, deterministic dispatch IDs and original-call journals protect against duplicate execution and uncertain provider acceptance.
- Dispatch rechecks current membership, effective permissions, required email verification, workspace usability, DND, conversion, wallet and normal outbound admission.
- Explicit review approval survives calling-window rescheduling and permitted retries. Exact window checks prevent dialing before the opening time.
- Bounded conversation context preserves timing answers given separately from the callback request. Relative times use the relevant caller utterance timestamp. Unaccepted suggestions, inconsistent timezone offsets and changed policy timezones require review.
- The existing configured background analyzer interprets timing. Live speech tier assignments and greeting preparation remain unchanged.
- Callback targets no longer bypass original-call tenant checks; missed-attempt journals populate the correct foreign key. Journal failure prevents a paid dial.
- Statistics use the full selected period rather than a capped UI page. Incomplete billing settlement is shown as unavailable CPL rather than a misleading estimate.
- Follow-up policies, jobs and assessments participate in tenant export/deletion. Migration 047 adds three tables; it changes no existing rates or tier assignments.
- The dashboard Pipeline control opens leads rather than call history.
- Structured Sarvam completion now resolves the endpoint after applying its configured transport; regression coverage checks both explicit and configuration-selected modes.

## Pending pricing work included in this push

- Platform administrators can control public calculator features through published pricing configuration. Tenant and public calculators consume the same settings and published tier rates.
- The phone-usage calculator supports call/minute volume, breakdown, tier comparison, tax presentation and shareable estimates, with feature visibility controlled by configuration.
- Hiding a tax toggle preserves the meaning of tax-inclusive published prices. Estimate links contain only the supported estimate parameters and always open public pricing; existing private query/hash values are not copied.
- Pricing layout and calculator styles are updated. Demo billing text no longer makes an unsupported zero-charge promise for voicemail.
- These are presentation/configuration changes; this release does not modify existing billing rates or provider/tier assignments.

## Verification and activation

- 229 backend tests passed.
- 29 browser checks passed.
- Seven real PostgreSQL queue/locking scenarios passed in an isolated disposable schema.
- Twelve live synthetic timing probes passed, without telephone calls or TTS.
- Follow-up Reticle verification produced 24 affirmative desktop/mobile verdicts; the final pricing run produced two affirmative verdicts.
- Vite and Next production builds, standalone TypeScript checking and Python syntax/import lint passed.
- Full Semgrep SAST: 1,451 targets, 293 rules, zero findings.

Migration 047 was applied to the approved local database. The task-owned backend was restarted successfully and is healthy. Policies and jobs remain empty: automatic calling is off until a tenant enables it. Production requires the same migration and normal deployment procedure; pushing code alone does not deploy it.

No customer calls were placed. Real carrier delivery and sustained multi-process load remain deployment checks. Workspace suppression does not replace a national DND registry. See [VERIFICATION.md](VERIFICATION.md) for evidence, definitions, references and reproducible commands.
