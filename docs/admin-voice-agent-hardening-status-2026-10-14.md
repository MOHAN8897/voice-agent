# Admin workspace and voice-agent hardening status

Date: 2026-10-14
Branch: `working_app-13/10/2026`

## Delivered

- The six requested backend-admin sections now share one workspace, grouped as Workspace, Customer operations, Trust, and Insights. Existing route URLs remain available and open the matching section; tenant context is retained in the URL.
- Multilingual close rules and compiled voice guidance now cover English, Telugu, Hindi, and Tamil end cues, callback/refusal handling, questions, and requests to stay on the line. Tool-accepted hangups allow the current farewell audio to finish before disconnect, and malformed tool arguments are rejected without crashing the event handler.
- Razorpay provider calls run outside the event loop with bounded timeouts. Payment details are checked against the expected order, currency, status, and amount before wallet changes are applied under a row lock.
- Carrier number purchases reserve the E.164 number before calling the provider, preventing concurrent duplicate orders. An uncertain provider result remains reserved for reconciliation instead of risking a second purchase.
- Legacy carrier/CRM-specific database column names are renamed through a data-preserving migration. Migration `037_active_phone_number_unique` is the current Alembic head; it checks for duplicate active numbers and stops with an error rather than deleting or rewriting rows.
- The security-audit runner no longer prints command arguments or provider targets that may contain secrets. The Strix runner passes the API-key environment variable name to Docker instead of placing its value in command arguments.
- Next.js is upgraded to 15.5.27. Production dependency audit is clean; PostCSS is pinned to a patched version in the resolved tree.

## Validation

- Focused server regressions: 177 passed across the admin purchase/support flows, tenant scoping, Razorpay, number-column migration models, multilingual scenarios, call lifecycle, hangup, compiled-brain size, and prewarm tests.
- A broader server run before the final small fixes reported 2,137 passed, 13 skipped, and 45 failed. The focused follow-up tests now pass, but the full suite was not rerun. One database-backed integration test hit a local schema mismatch (`tenant_integrations.connection_id` was absent because migrations 036/037 were not applied). The remaining failures covered database/config assumptions, API contract assertions, provider/model catalogs, TTS routes, campaign behavior, and voice fixtures; they were not all individually traced in this pass.
- `python scripts/security_audit.py --mode sast`: 0 findings across 470 tracked files and 290 rules. Semgrep reported one timeout in `server/brain/agent_script_compiler.py`; this is not a finding.
- Web Semgrep: 0 findings across 298 files and 95 rules. `npm audit --omit=dev`: 0 vulnerabilities. Full `npm audit` reports 7 development-toolchain findings (5 high, 2 moderate) through Tailwind CSS 3; the automatic fix requires a Tailwind 4 major migration, so it was not applied as part of this work.
- `npm exec -- tsc --noEmit --project tsconfig.json` passed. The Next.js production build did not emit progress for more than ten minutes and was stopped; a production build is therefore not verified. Lint could not run because the repository has no ESLint configuration and Next.js opened its first-run setup prompt.
- `graft build` refreshed the local graph. Chisle guidance from `.cursor/rules/chisle.mdc` was applied during implementation.

## Live checks not completed

- Reticle could not create a session on the requested main domain: it reported `sdk_never_dialled`, and no authenticated production browser session was available. The named test account, agent conversations, prewarm audio, tenant integrations, hangup over carrier, payment checkout, and number assignment were not live-tested.
- No real payment, carrier purchase, or production call was initiated. Razorpay and number-purchase coverage used mocked provider responses.
- ZAP and Strix were not run because Docker is unavailable in this environment; Strix also needs an API key that is not configured. Their configured target is staging and was not replaced with the production domain.
- Migrations 036 and 037 were not applied to any database. Apply and verify them in the intended deployment environment before relying on the renamed columns or active-number uniqueness constraint.

## Enigma

The Enigma passport now includes the implementation and verification constraints. `npm run enigma:status` reports 5 active memories and 16 receipts; `npm run enigma:verify` completed with no errors.
