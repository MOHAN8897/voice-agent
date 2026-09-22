# SaaS flow audit (Voxly console ↔ voice-agent backend)

**Branch overview (full description):** [docs/branch-working-app-23-09-2026.md](./docs/branch-working-app-23-09-2026.md) — `working-app-23-09-2026` on GitHub.

End-to-end path: **sign-in → dashboard sync → agents → numbers (search/buy/assign) → outbound/inbound PSTN → billing → leads/campaigns**.

> **Historical findings** below describe the state *before* the Mar 2026 hardening pass.  
> **Current status** is in [§ Verification (Mar 2026)](#verification-mar-2026) at the end — use that for “is it fixed?”

---

## 1. Authentication & session (original audit)

| Issue | Severity | Detail |
|-------|----------|--------|
| Access JWT in localStorage | High (XSS) | Bearer token readable by any script on the page. |
| optional_subscriber_context on /api/agents | Medium | JWT decoded without membership re-check. |
| /api/calls without Bearer when SAAS_AUTH_ENABLED | High | Default tenant fallback on list. |
| get_call tenant check with missing JWT | Medium | Same fallback. |
| Google consent branding (“venuefinder”) | Ops | GCP OAuth app name. |
| Email verify vs Google | Low | Policy inconsistency. |
| Settings “Production API key” | Medium | Hard-coded demo key. |
| Team / invite / switch-tenant APIs | Gap | Backend exists; console not wired. |

## 2. Agent creation & Agent Studio (original audit)

| Issue | Severity | Detail |
|-------|----------|--------|
| Create Agent wizard → API | Critical | Only name + languages on agent row. |
| Agent Studio “Save” | Critical | Script/voice not on PATCH /api/agents. |
| Business Brain not used from Voxly | Critical | No publish path in UI. |
| Talk to AI / voiceAgent.js | Unwired | Browser mock, not realtime brain. |
| Optimistic agent mutations | Silent failure | console.warn on API errors. |

## 3–11. Phone numbers, PSTN, billing, CRM, integrations, backend gaps, security, config

(See git history / prior chat for full tables.)

---

## Verification (Mar 2026)

Code review + smoke tests (`playwright e2e/smoke.spec.js`: **5 passed**).  
**Not everything in the original audit is fully fixed** — status per theme:

### Fixed or substantially addressed

| Original issue | Evidence |
|----------------|----------|
| Stale JWT / weak optional subscriber on agents + brain | `require_subscriber_jwt_if_enabled` → full `require_subscriber_jwt` when `SAAS_AUTH_ENABLED` (`server/auth/subscriber_dependencies.py`) |
| Unauthenticated `/api/calls` leak | `resolve_calls_tenant_id` requires JWT when SaaS on (`server/auth/calls_tenant.py`, `server/routes/calls.py`) |
| JWT in localStorage | Access token in **sessionStorage** (`voxly-ai/src/services/api.js`); refresh **HttpOnly cookie only** |
| Fake API key in Settings | Replaced with session/account copy (`SettingsModule.jsx`) |
| Business Brain + publish from console | `agentBrain.js`, create agent + Studio save call `saveAndPublishAgentBrain` |
| Fake outbound call on error | Removed; `triggerCallToLead` uses real API + throws (`WorkspaceContext.jsx`) |
| Outbound `fromE164` / `agent-david` | Server `resolve_outbound_from_e164`; client sends agent + optional from line |
| Lead notes API | `PATCH /api/leads/{id}` + `api.leads.updateNotes` |
| Campaign create / toggle | Backend returns `campaign` object; `toggleStatus(id, currentStatus)` sends `{ status }` |
| Stripe top-up demo fallback | Removed when signed in (`BillingModule.jsx`, `addFunds` → checkout or error) |
| assign / release silent failures (signed in) | Errors throw + `loadWorkspaceData` on failure |
| Release number | `POST /api/telephony/numbers/{id}/release` + client `releaseNumber` |
| Wallet PSTN gate + usage debit | `assert_wallet_allows_pstn`, `bill_pstn_call_if_applicable`, migration **014** |
| Billing wallet read for viewers | `app.billing.read` on GET wallet/invoices/transactions |
| Integrations fake CRM | “Coming soon” panel (`IntegrationsModule.jsx`) |
| Demo workspace on login | Empty arrays until sync; no mock fallback when authed (`WorkspaceContext.jsx`) |
| Workspace sync banner | Partial API failures surfaced (`ConsoleSyncBanner.jsx`) |

### Partial items — addressed (Mar 2026 pass 2)

| Topic | Status |
|-------|--------|
| Agent Studio voice + routing | Voice + inbound prefs saved in **business brain** custom sections; telephony tab updates **routing API** when number assigned |
| Phone buy | **IN** default catalog; reload on country; **purchase polling** + post-Stripe assign via `PurchaseProvisioningBanner` |
| Outbound | **Caller ID** dropdown on Leads (session-persisted) |
| Billing | Plan tiers labeled preview; **auto-recharge** labeled session-only |
| Campaigns | Contact import (lines), **auto-start**, **analytics** from API, **Start dialer**; local create fallback removed |
| Leads | **Add lead** modal |
| Overview | KPIs + hourly chart from **real `/api/calls`** |
| Agent mutations | **API-first** when authenticated (assign/update/toggle/delete) |
| Security | **`/api/analytics/fleet`** + call metrics tenant-scoped; **`setBackendUrl`** restricted to origin/localhost |

### Not fixed (by design or not started)

| Item | Notes |
|------|--------|
| Google “venuefinder” branding | GCP Console only |
| Talk to AI / `voiceAgent.js` | Still browser mock STT/TTS — not tenant realtime/PSTN |
| Team invites / switch-tenant in UI | Backend routes exist; Settings does not implement |
| Campaign worker / dialer queue | UI starts campaign; background dialer depends on worker/Telnyx env |
| Telnyx hard teardown on release | DB soft-release only; no carrier delete in API |
| Real-time browser test tied to agent | No WebSocket console path to published brain |
| `mockBackend` | Still used when `api.request` allows mock (no token / misconfig) — not used for signed-in dashboard path |

### Recommended next fixes (priority)

1. **Talk to AI**: wire console preview to realtime/session API + published brain (replace `voiceAgent.js` mock).
2. **Settings**: team invites, API keys, tenant switch — surface existing backend routes.
3. **Stripe subscriptions**: replace cosmetic plan tiers with real subscription SKUs (or remove tiers).
4. **Auto-recharge**: persist threshold/amount on tenant + Stripe off-session charge (if product wants it).
5. **E2E**: credentialed Playwright flow (`E2E_EMAIL` / `E2E_PASSWORD`) for full dashboard regression.
6. **Campaign dialer**: verify worker enqueue in your deployment; document required env for outbound campaigns.

### Ops checklist (unchanged + 014)

| Variable / piece | Affects |
|------------------|---------|
| `SAAS_AUTH_ENABLED`, `DATABASE_URL`, migrations **009–014** | Subscriber flows + wallet ledger |
| `JWT_SECRET`, refresh cookie Secure/SameSite (prod) | Auth 5173 ↔ 8000 |
| `STRIPE_*` + webhook | Numbers + USD wallet |
| `RAZORPAY_*` | INR wallet |
| `TELNYX_*` + provision worker | Numbers + PSTN |
| `PSTN_MIN_BALANCE_*`, `PSTN_RATE_*` | Outbound gate + usage debit |
| `SAAS_TELEPHONY_ENABLED` | Subscriber telephony |
| Google OAuth app name | Sign-in label |

---

*Last verified: 2026-03-23 against repo working tree.*
