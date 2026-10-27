# Agent workspace and lead pipeline verification

Date: 2026-10-27. Branch: `working-app-22-10-2026`.

Functional verdict: PASS. Full Semgrep security scan: NOT VERIFIED, blocked by Windows application-control policy.

## Delivered changes

1. **One floating save dock.** Script and Settings edits use the same parent save operation. The dock appears only for unsaved changes, includes Save and Discard, shows saving/error states, and stays within the content area when the sidebar or viewport changes. Its measured height reserves space at the end of the page, so the last settings card remains reachable above it. Publication validation, failed-save retention and leave guards remain covered by browser tests.
2. **Settings layout.** Identity, status, number and routing form one natural stack; recording and compliance form another. Cards no longer share stretched grid rows. Category filters preserve draft fields. Mobile uses one column.
3. **Paper-style script editor.** The complete script grows with its content and wrapped lines. The workspace page scrolls; the script textarea has no internal scrollbar. Farewell and objection sections follow the script, side by side on wide screens. Autocomplete is positioned near the caret and within the visible page instead of below a long document. Greeting synthesis, prepared sessions and opening-delivery mechanics were not modified.
4. **Lead workspace.** List and board views show actual contact, owner, stage, notes, creation and update metadata. Removed unsupported BANT scores and invented source/qualification claims. Added search, stage, agent/unassigned, phone-availability and update-window filters, sorting, pagination, and server-computed counts across all matching records. Errors are visible and retryable; counts are not calculated from just the current page.
5. **Lead actions.** Notes and stage save together on explicit submission, rather than PATCHing on every keystroke. Failed edits stay in the detail form. Agent-owned leads can be called directly, including leads absent from the shared workspace cache. Unassigned leads do not silently use the first agent. Selected contacts open the existing campaign setup with names, phones, email, notes and `custom_fields.lead_id` / `lead_stage`. Normalization, published-script validation, authorization confirmation, Do Not Call handling, draft creation and launch controls remain in that flow.
6. **Call-history linkage.** A lead opens its agent's recent call history with a phone search. Connected-call responses now retain caller/destination numbers from the matching tenant's ledger. Searches normalize formatting and check both ends of the call. Ledger/outcome file enrichment runs in a worker thread instead of blocking the server event loop.
7. **Voice availability.** Gender counts are calculated within the selected style; style counts reflect the selected gender. Summaries show the filtered result, including zero. Empty combinations offer Clear voice filters. Filtering does not replace the saved voice.

## Verification evidence

- **44 Playwright tests passed** across workspace experience, console layout, script publication, voice inventory/selection, campaign setup and call lifecycle. Includes desktop/mobile layouts, bottom-dock clearance, save errors, a 90-line script, autocomplete visibility, filtering/pagination, lead note errors, direct-call errors, and selected-lead campaign drafts.
- **72 backend tests passed** across lead HTTP/SQL filters, lead attribution, call timeline, call security, contact enrichment and primary PSTN lifecycle. Four existing deprecation warnings (`audioop`, Redis `setex`); no test failures.
- Lead HTTP tests use a disposable SQLite database with separate tenants. They verify counts beyond one page, scoped records, literal wildcard searches, date/contact filters, persisted combined edits, malformed IDs, cross-tenant assignment denial and authentication requirements.
- **16 matching-driver Reticle checks returned `verified: yes`**, without a version-skew flag. Evidence: [reticle-workspace.json](./reticle-workspace.json). Checks cover editing/discarding via the shared dock, autocomplete, Settings navigation, lead search/empty recovery, selection/campaign handoff and voice-filter zero results. The leased browser is yielded and released after verification.
- `npm run build` passed: Vite production build plus six prerendered public pages.
- Ruff passed for the lead route and new backend tests. The existing calls route has 31 baseline lint findings and 31 current findings: **zero introduced**, recorded in [calls-lint.json](./calls-lint.json).
- `git diff --check` passed; Graft graph refreshed.
- Local backend was started using the existing Playwright backend command. After reloading our idle process, `/api/health` returned HTTP 200, `ok: true`, `envValid: true`.

Browser command (from `voxly-ai`):

```powershell
$env:PLAYWRIGHT_SKIP_WEBSERVER='1'
npx playwright test e2e/workspace-experience.spec.js e2e/console-layout-refresh.spec.js e2e/primary-script-editor.spec.js e2e/voice-catalog-mapping.spec.js e2e/voice-setup-actions.spec.js e2e/campaign-setup.spec.js e2e/primary-call-lifecycle.spec.js --workers=1 --reporter=line
```

Backend command (repository root):

```powershell
python -m pytest server/tests/test_lead_call_history.py server/tests/test_lead_pipeline_filters.py server/tests/test_agent_scoped_leads.py server/tests/test_call_timeline.py server/tests/test_calls_security.py server/tests/test_primary_pstn_lifecycle.py -q
```

## Evidence limits

- Browser/Reticle actions use isolated synthetic API fixtures. Database behavior is independently exercised through real SQL and FastAPI HTTP requests. Real PSTN dialing, paid speech generation and external campaign launches were not performed by these tests.
- The recent-call link uses the existing call-history window of up to 100 fetched records. It is labelled **View recent calls**; it is not an unlimited historical phone search.
- Campaign selection applies to the current lead page and clears on pagination/filter changes. Larger imports continue through the existing file/list campaign flow.
- The development Reticle HUD intercepted bottom application controls. It was hidden only in isolated browser fixtures; the SDK and application assertions remained enabled. Feedback was submitted to Reticle. The installed app SDK is 3.7.0; verification uses an explicitly leased matching 3.8.2 driver.
- One existing billing test expected `Last Call Session` while both HEAD and the running component already said `Last call session`. Only the stale test capitalization was corrected. Amount, supplier-redaction and ledger assertions still pass.
- `python scripts/security_audit.py --mode sast` failed before scanning: **“An Application Control policy has blocked this file.”** The runner exited 1; its Semgrep subprocess reported exit 127. No clean full security-scan claim is made. No machine-policy workaround was attempted.

## Screenshots

- [Settings and floating save dock](./settings-desktop.png)
- [Paper-style script](./script-paper-desktop.png)
- [Lead workspace](./leads-desktop.png)
- [Mobile lead details](./leads-mobile.png)

Changes are local and uncommitted. No GitHub push was requested in this turn.
