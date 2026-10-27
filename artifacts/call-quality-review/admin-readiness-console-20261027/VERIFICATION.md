# Admin readiness and workspace corrections

Date: 27 October 2026, Asia/Kolkata. Branch: `working-app-22-10-2026`.

VERDICT: PASS for the scope and checks below. Existing uncommitted consolidation edits were preserved, reviewed and verified; the remaining failures found during verification were corrected.

## Economical readiness and visibility

Fresh inspection found Economical (`low`), revision 44, enabled and ready with no blockers. Its current public Telugu catalog contains 61 voice choices. All enabled saved tiers passed the stored readiness gate; the disabled native Premium configuration remains unverified and was not activated.

The frontend previously required `ready` before rendering a tier. An enabled tier with incomplete verification therefore disappeared. Enabled unverified tiers now remain visible with disabled selection controls. Ready tiers remain selectable. Disabled tiers remain excluded. The server still enforces readiness and current profile revisions when starting calls.

Fresh real provider checks against the exact saved Economical stack passed:

- Approved text model access: two completed responses from the configured model.
- Streaming recognition: a final transcript from synthetic speech over the streaming connector.
- Speech model/catalog: valid voice/language mappings and nonempty synthesized PCM.
- Tools: a synthetic tool name and arguments returned; no business tool executed.
- Capacity: two concurrent text requests and a positive configured call limit.
- Media: 16 kHz PCM converted to G.711 and decoded successfully.
- Credentials: required server-side provider configuration was available.

Capacity is a smoke check, not certification of 20 simultaneous full voice calls. Media conversion is not a physical carrier test. See `current-provider-checks.json` and `catalog-current.json`. These fresh checks were read-only with respect to saved tiers, activation and prices.

The admin workbench now has a **Verify saved setup** action for composed stacks. Checks are bounded, privileged, tied to the saved revision and rechecked under a row lock before persistence. Failed checks remain blockers. Native audio configurations require their separate Test Studio verification path; this composed verifier does not approve them.

Additional correctness guards:

- Enabling a tier no longer fabricates seven successful evidence flags.
- A new profile cannot self-attest readiness through its save payload.
- Cosmetic edits retain existing verified evidence; runtime tuple changes clear it.
- Stale edits cannot overwrite a newer verification result.
- Rechecking an unchanged already-approved stack retains its revision and saved agent voice selections while recording a fresh audit entry.

Relevant code: `server/services/saas/voice_stack_profiles.py`, `server/services/saas/voice_profile_verification.py`, `server/routes/dev_stack.py`, and `AgentVoicePanel.jsx`.

## Admin pages and pricing

- Overview is the first navigation item and the `/dev` landing page. `/dev/admin` redirects there.
- SaaS phone AI is removed from navigation; its old URL redirects to Stack & tiers.
- Agents & brain is removed from navigation; old agent workspace URLs redirect to Overview. Agent records and the working brain engine remain available to the application.
- Tenants and users share one main navigation entry and workspace, with Workspaces and Users & memberships sub-sections.
- Old Users links preserve query parameters, including the tenant filter. Verification found that an expired-session redirect lost the query string; middleware now retains it through the existing authentication refresh flow. Authentication and permission policy were not changed.
- Legacy Economical/Standard/Premium price controls are removed from the Pricing tab. Per-stack phone prices have one editor. Web calling, number rental and FX controls remain. The browser regression confirms their save payload excludes legacy `pstn*` fields.

No actual price amount, wallet balance, supplier cost or tier activation was changed during this verification run. Pricing writes in browser tests were intercepted with synthetic fixtures.

## Overview analytics

Reviewed the authenticated endpoint through SQL aggregation, API response and rendered page. The overview now:

- Excludes practice calls, fills missing dates and consistently groups calendar days in UTC, as labeled.
- Keeps USD and INR wallet/top-up totals separate.
- Groups busiest tenants by tenant identity, preserving separate tenants with identical names.
- Shows call channels, status counts and active account totals.
- Refreshes on focus and periodically; old responses cannot overwrite a newer selected window.
- Restricts conversation and top-up summaries to the same date interval, excluding future-dated records from conflicting totals.
- Renders zero-call days at zero height.
- Uses a valid solid theme color plus opacity for chart bars. The previous variable-color opacity class produced transparent bars despite their correct dimensions.
- Fits the two-column summary tables to their cards so counts are visible without horizontal scrolling.

Regression checks include real bar color and dimensions, zero days, future records, mixed currencies, duplicate tenant names and delayed responses. See `test_admin_overview_rollups.py`, `admin-consolidation.spec.ts` and `overview.png`.

## Workspace layout

- Entering an agent workspace automatically collapses the desktop sidebar. Expansion remains available while navigating its tabs.
- The icon rail preserves accessible names, icons and tooltips, with a visible **Expand** caption. Mobile retains the navigation drawer.
- The Settings save bar uses normal document flow after the settings grid. It no longer floats over controls.
- Greeting and script cards share a vertical column with a small fixed gap. The farewell and objection cards occupy an independent support column, avoiding grid-row stretching and the large empty space shown in the screenshot.
- Category switches preserve form edits. Narrow screens retain vertical reading order and avoid horizontal overflow.

Greeting synthesis, cached opening playback and prewarm ownership were not changed.

## Executed evidence

- Backend regression: **99 passed, 3 skipped**, 1 warning. The skipped tests require database setup outside the default unit environment. The new aggregation tests use an isolated database; Reticle also fetched analytics from the running API.
- Admin browser: **4 passed**. Navigation consolidation, retired links, tenant-filter preservation, analytics, readiness action, legacy pricing removal and save payload.
- Workspace browser: **19 passed**. Automatic/manual sidebar collapse, icon visibility, expansion caption, compact script spacing, save-bar position, mobile layout, edit retention, unavailable tier visibility, current voice selection and failure recovery.
- Fresh provider readiness: **7/7 passed** for Economical, with no PSTN call or integration write.
- Reticle: **verified: yes** for loaded overview, live date-window refresh, automatic workspace collapse, manual expansion and Settings navigation. Workspace Reticle checks used disposable API fixtures. A matching leased driver avoided the installed optional SDK's version mismatch; no dependency upgrade was made. See `reticle-admin.json`.
- Next.js production build: **passed**. TypeScript was checked separately with `tsc --noEmit --incremental false`: exit 0.
- Vite production build and public-page prerender: **passed**.
- Full Semgrep SAST: **exit 0, zero findings**. Scan warnings and limitations remain in `sast-final.log`.
- Changed-file Python lint versus HEAD: **zero introduced findings**. Existing baseline lint debt remains; see `lint-results.json`.
- `git diff --check`: passed. Graft rebuilt successfully.

## Running state and limits

The local API and both consoles are running with these changes. API health returned HTTP 200 after loading the final server code. Only processes started for this work were restarted; no recent real call was active. Temporary build-generated TypeScript configuration changes were restored.

No physical PSTN call, full carrier hangup, full-load capacity test or production deployment was performed. Disabled/unverified configurations continue to show genuine blockers. No commit or push was performed.
