# Branch `working-app-23-09-2026`

**Repository:** [MOHAN8897/voice-agent](https://github.com/MOHAN8897/voice-agent)  
**Base:** `working-app-12-09-2026` (Test Studio + PSTN hangup/lifecycle work)  
**Head commit:** single integration snapshot — SaaS subscriber product + Voxly console in-tree  
**Date:** 23 September 2026  

This branch is a **working integration snapshot**: multi-tenant subscriber auth, telephony commerce (Stripe + Telnyx), wallet billing (Razorpay + Stripe), CRM/campaigns APIs, tenant-safe call/metrics access, and the **Voxly AI subscriber console** vendored under `voxly-ai/` (no longer a nested git repo).

---

## What this branch is for

Use this branch when you want the **full stack** in one clone:

| Layer | Role | Location / port |
|-------|------|-----------------|
| Voice + PSTN backend | FastAPI, Realtime PSTN, Telnyx, business brain | `server/` — **8000** |
| Subscriber console | Marketing site + signed-in dashboard | `voxly-ai/` — **5173** (Vite proxies `/api` → 8000) |
| Dev portal (legacy) | Test Studio, internal tools | `web/` — separate Next dev stack |
| Product / ops docs | PRDs, env templates, integration audit | `saas-workflow/`, `changes.md` |

It does **not** claim production-hardening on every edge case; see [Known gaps](#known-gaps--intentional-deferrals) and `changes.md` § Verification (Mar 2026).

---

## Major deliverables (by area)

### 1. SaaS identity & auth (backend)

- **Migrations `009`–`013`:** users, tenants, memberships, email verification tokens, SaaS telephony/commerce tables, leads, billing primitives.
- **Routes:** `server/routes/app_auth.py` — signup, login, refresh (HttpOnly cookie), Google OAuth, `/api/auth/me`, email verification flows.
- **JWT + cookies:** `server/auth/jwt_tokens.py`, `subscriber_cookies.py`, `subscriber_dependencies.py`.
- **Guards:** When `SAAS_AUTH_ENABLED=true`, `require_subscriber_jwt_if_enabled` delegates to full `require_subscriber_jwt` (membership re-check, not decode-only).
- **RBAC:** Extended permissions (e.g. `app.billing.read`) in `server/auth/rbac.py`.

### 2. Telephony & number lifecycle

- **Orchestrator:** `server/services/saas/telephony_orchestrator.py` — catalog, reservations, assign, outbound `fromE164` resolution.
- **Stripe checkout** for number purchase; **provision/teardown workers** (`provision_worker.py`, `teardown_worker.py`) started from `server/app.py` when configured.
- **Routes:** `server/routes/app_telephony.py` — list numbers, buy, assign, release (`POST .../release`), purchase status.
- **Inbound routing helper:** `server/services/saas/inbound_routing.py`.
- **Telnyx PSTN** routes remain on `server/routes/telnyx.py` with SaaS-aware hooks where applicable.

### 3. Billing & wallet

- **Migration `014_wallet_ledger_reference`:** ledger `reference_id`, `amount_inr_paise` on wallet transactions.
- **Services:** `billing_wallet_service.py`, `razorpay_service.py`, Stripe webhook `server/routes/stripe_webhook.py`.
- **Routes:** `server/routes/app_billing.py` — wallet, invoices, Razorpay order/create, Stripe top-up, **`GET /api/billing/transactions`**.
- **PSTN economics:** `PSTN_MIN_BALANCE_*`, `PSTN_RATE_*` in `server/config/env.py`; pre-call gate `assert_wallet_allows_pstn`; post-call debit `bill_pstn_call_if_applicable` from call lifecycle.

### 4. CRM: leads & campaigns

- **Leads:** `server/routes/app_leads.py` — list/create/update stage, **`PATCH /api/leads/{id}`** for notes.
- **Campaigns:** `server/routes/campaigns.py` — tenant-scoped create (returns full `campaign` object), status, import, start, analytics (subscriber JWT).

### 5. Tenant isolation for calls & metrics

- **`server/auth/calls_tenant.py`:** `resolve_calls_tenant_id` — requires subscriber JWT when SaaS auth is on (no silent default tenant on list/detail).
- **Applied on:** `GET /api/calls`, `GET /api/call/{id}`, fleet analytics and per-call metrics in `server/routes/metrics.py`.

### 6. Agents & business brain

- **Agent rows:** `server/routes/agents.py` — create/list/update with tenant context.
- **Business brain:** `server/routes/agents_business_brain.py` — draft/publish paths used by the console.
- **Console mapping:** `voxly-ai/src/services/agentBrain.js` — script, objections, greeting, **voice tuning**, **inbound routing prefs** stored as custom brain sections; publish on create/save.

### 7. Voxly AI console (frontend, in-repo)

First-class inclusion under `voxly-ai/`:

- **Auth:** Google + email/password; access token in **sessionStorage**; refresh via **HttpOnly cookie** only (`api.js`, `authService.js`).
- **Workspace:** `WorkspaceContext.jsx` — API-first when authenticated; empty state until sync; no demo fallback on errors; `ConsoleSyncBanner` for partial failures.
- **Modules:** Overview (real call KPIs/chart), Agent Studio + wizard, Phone numbers (IN-default catalog, Stripe buy, release), Leads (add lead, notes, outbound with **caller ID** picker), Campaigns (import lines, start dialer, analytics), Billing (Razorpay/Stripe top-up; plan/auto-recharge labeled preview), Calls, Settings/Integrations (honest copy).
- **Post-Stripe:** `PurchaseProvisioningBanner.jsx` — poll purchase, pending assign from sessionStorage.
- **API client:** `api.js` — telephony, billing, leads, campaigns, brain, restricted `setBackendUrl` (same origin / localhost).
- **E2E:** Playwright specs in `voxly-ai/e2e/`; smoke **5 passed** without credentialed env (see `voxly-ai/TESTING.md`).
- **Optional:** Stagehand smoke script; Chrome DevTools MCP entry in `.cursor/mcp.json`.

### 8. Voice / PSTN engine (continued from 12-09 branch)

- Realtime PSTN core, hangup policy, caller detail capture, prompt/brain guardrails — incremental changes on top of `working-app-12-09-2026`.
- Latency audit doc moved to `docs/pstn-realtime-latency.md` (replaces deleted root `REALTIME_LIVE_LATENCY_AUDIT.md`).

### 9. Documentation & tooling

- **`saas-workflow/`:** Full PRD pack (00–12), phase status, `ENV-SaaS.example`, Google Cloud setup, Voxly integration notes, E2E SaaS audit.
- **`changes.md`:** Original audit tables + **Mar 2026 verification** (fixed / partial / open).
- **Scripts:** Google OAuth provisioning/sync (`scripts/provision-voxly-google-oauth.ps1`, etc.), dev stack updates in `scripts/dev_up.ps1`.
- **Dev admin:** `web/app/dev/(portal)/saas-admin/page.tsx`, `server/routes/dev_admin.py`.

### 10. Tests (backend)

New/updated coverage includes: `test_saas_auth.py`, `test_google_oauth.py`, `test_razorpay_wallet.py`, `test_wallet_pstn.py`, hangup/PSTN/realtime regression suites, and existing call-controller tests updated for policy changes.

---

## Repository layout (quick map)

```text
voice-agent/
├── server/                 # FastAPI backend (SaaS + PSTN + brain)
├── voxly-ai/               # Vite React subscriber + marketing UI
├── web/                    # Next.js dev portal (Test Studio, etc.)
├── saas-workflow/          # PRDs, env example, integration guides
├── docs/                   # Branch notes, PSTN latency doc
├── changes.md              # Console ↔ backend audit + verification
└── scripts/                # Dev + Google OAuth helpers
```

---

## How to run locally

### Prerequisites

- Python 3.12+ with project deps (`pyproject.toml`)
- PostgreSQL + `DATABASE_URL`
- Node 18+ (22+ for Chrome DevTools MCP)

### Backend

```powershell
cd "D:\voice agent"
# Copy and fill .env (see saas-workflow/ENV-SaaS.example + root .env.example patterns)
alembic upgrade head   # includes 009–014
uvicorn server.app:app --reload --port 8000
```

Enable SaaS features as needed:

- `SAAS_AUTH_ENABLED=true`
- `JWT_SECRET=...`
- `SAAS_TELEPHONY_ENABLED=true`
- `STRIPE_*`, `RAZORPAY_*`, `TELNYX_*` for paid flows
- `PSTN_MIN_BALANCE_*`, `PSTN_RATE_*` for outbound wallet gate/debit

### Voxly console

```powershell
cd "D:\voice agent\voxly-ai"
copy .env.example .env   # VITE_API_URL typically /api via proxy
npm install
npm run dev              # http://localhost:5173
```

Stripe CLI for number purchase webhooks: `saas-workflow/PRD-11-stripe-cli-local-dev.md`.

### Smoke test

```powershell
cd voxly-ai
npx playwright test e2e/smoke.spec.js
```

Optional full dashboard E2E: set `E2E_EMAIL` / `E2E_PASSWORD` (verified subscriber).

---

## Environment & migrations checklist

| Item | Purpose |
|------|---------|
| `DATABASE_URL` | Postgres |
| Migrations **009–014** | SaaS schema + wallet ledger columns |
| `SAAS_AUTH_ENABLED` | Subscriber JWT on protected routes |
| `JWT_SECRET` | Access/refresh signing |
| `STRIPE_*` + webhook | Number checkout, USD wallet |
| `RAZORPAY_*` | INR wallet top-up |
| `TELNYX_*` + workers | Provision numbers, PSTN media |
| `PSTN_MIN_BALANCE_*`, `PSTN_RATE_*` | Outbound allow + usage debit |
| Google OAuth client | Sign-in; fix app display name in GCP if still wrong |

---

## Security & integration highlights

- Subscriber **access token in sessionStorage** (not localStorage); refresh cookie HttpOnly.
- **Calls and fleet metrics** tenant-scoped when SaaS auth is enabled.
- **Backend URL override** in console limited to same origin / localhost.
- **Integrations** module does not fake CRM connections.
- **Signed-in billing** does not silently fall back to demo top-up.

---

## Known gaps & intentional deferrals

| Item | Status |
|------|--------|
| Talk to AI / `voiceAgent.js` | Browser mock STT/TTS — not wired to realtime/PSTN + published brain |
| Team invites, API keys, tenant switch UI | Backend routes exist; Settings not fully built |
| Subscription plan tiers | UI preview; not full Stripe Subscription SKUs |
| Auto-recharge toggle | Session-only preview; not persisted server-side |
| Campaign background dialer | UI can start campaign; worker/Telnyx env must be live |
| Number release | Soft-release in DB; no guaranteed Telnyx hard delete in API |
| Google OAuth consent branding | GCP Console configuration |
| `mockBackend.js` | Still used when unauthenticated or API misconfigured |

Prioritized backlog: `changes.md` § Recommended next fixes.

---

## Diff scale (vs `working-app-12-09-2026`)

- **~239 files** changed in the integration commit  
- **~35k insertions** — primarily `voxly-ai/`, `saas-workflow/`, `server/services/saas/`, migrations, and subscriber routes  

---

## Related reading

| Document | Content |
|----------|---------|
| [changes.md](../changes.md) | Audit + Mar 2026 fix verification |
| [saas-workflow/README.md](../saas-workflow/README.md) | PRD index |
| [saas-workflow/VOXLY-LOCAL-SETUP.md](../saas-workflow/VOXLY-LOCAL-SETUP.md) | Local pairing (paths updated: use in-repo `voxly-ai/`) |
| [voxly-ai/TESTING.md](../voxly-ai/TESTING.md) | Playwright, Stagehand, MCP |
| [saas-workflow/PRD-PHASES-1-7-STATUS.md](../saas-workflow/PRD-PHASES-1-7-STATUS.md) | Backend phase checklist |

---

*This file describes branch `working-app-23-09-2026` on GitHub (`github` remote). Update it if the branch receives additional commits.*
