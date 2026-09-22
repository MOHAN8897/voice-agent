# PRD-00 — Architecture review & SaaS hardening (read first)

Records **issues in the initial PRD pack**, **fixes**, and **binding decisions**. Other PRDs were updated to match.

## Executive summary

Moving from a **dev-only PSTN panel** to **multi-tenant SaaS** fails if you: reuse dev stores without tenant guards, use cookie-only auth for a separate Voxly origin, provision Telnyx inside Stripe webhooks, or ship agents API without auth. This pack corrects that and adds a **full per-user lifecycle** (PRD-03) and a **backend readiness gate** before any frontend work (PRD-12).

**Implementation order:** PRD-12 Phase A → B → C → D → then Voxly (PRD-07).

---

## Critical issues (must fix before launch)

| # | Issue | Risk | Resolution |
|---|--------|------|------------|
| C1 | App telephony “reuses dev_telephony” | Global store, no tenant checks | **`TelephonyOrchestrator`**; dev + app routers are thin wrappers (PRD-02) |
| C2 | Cookie sessions + Voxly on another origin | Login broken cross-site | **JWT access + refresh** for subscriber API; dev keeps cookies (PRD-03) |
| C3 | Telnyx provision inside webhook handler | Timeouts, double provision | Webhook → **`provision_jobs`** row → worker; 200 after persist (PRD-04, PRD-09) |
| C4 | Search → pay race on same E.164 | Double sale | **`number_reservations`** TTL during checkout (PRD-04, PRD-09) |
| C5 | Unauthenticated agent/brain APIs | IDOR | **`tenant_guard`** on all `/api/agents/{id}/**` (PRD-03, PRD-10) |
| C6 | `APP_ENVIRONMENT=production` only | Wrong stack policy for SaaS | **`stack_policy=saas_subscriber`** on call start (PRD-05) |
| C7 | Inbound with no `agent_id` | Wrong agent / default leak | Tenant **default agent** or polite hangup — never global default (PRD-05) |
| C8 | No outbound rate/concurrency limits | Bill shock | Enforce `tenants.limits` (PRD-02, PRD-05) |
| C9 | **No account deletion / org teardown** | GDPR, orphaned Stripe/Telnyx | PRD-03 flows + async jobs |
| C10 | **No refresh token rotation** | Stolen refresh = long compromise | PRD-03 `refresh_tokens` table |
| C11 | **Sole admin can delete self** | Orphan tenant | Block delete; require transfer (PRD-03) |
| C12 | **Frontend before backend gate** | Integration churn | PRD-12 sign-off before Voxly |

---

## High-priority issues (v1 strongly recommended)

| # | Issue | Resolution |
|---|--------|------------|
| H1 | Two billing streams (number rent vs minutes) | PRD-01 — Stripe subscription (DID) vs usage wallet |
| H2 | Admin manual number without Stripe | `billing_source=manual`; audit (PRD-06) |
| H3 | Subscription cancelled, number on Telnyx | Grace period → release job; suspend routing immediately (PRD-04) |
| H4 | Purchase status polling IDOR | `purchase.tenant_id == JWT tid` |
| H5 | Telnyx search abuse | Auth + rate limit + cap results |
| H6 | Subscription vs one-time checkout | Provision on `checkout.session.completed` + renewals on `invoice.paid` only |
| H7 | Call ledger missing `tenant_id` | Every PSTN init includes tenant from number/agent |
| H8 | Recording / consent | Tenant setting; PRD-01 compliance note |
| H9 | Observability | Metrics: `provision_failed`, `webhook_lag`, `pstn_active_by_tenant` |
| H10 | Dual frontends | Voxly = customer; Next `/app` = internal QA only |
| H11 | Email verification | Block number buy until verified (configurable) |
| H12 | Legacy `/api/app/login` | Deprecate when `SAAS_AUTH_ENABLED` |

---

## Acceptable for v1 (documented tradeoffs)

| Topic | v1 | Upgrade |
|-------|-----|---------|
| Single Telnyx account | DB isolation | Per-tenant subaccounts |
| Job queue | Postgres `provision_jobs` + worker | Redis/SQS |
| OAuth | 501 | Google/GitHub |
| Leads CRM | 501 | Phase 6 |
| Multi-tenant per user | `switch-tenant` API; UI later | Org switcher in Voxly |

---

## Anti-patterns (do not implement)

1. Calling `/api/dev/telephony/outbound` from Voxly.
2. Subscriber history in `dev_pstn_history`.
3. Client `stackOverride` on subscriber routes (reject in schema).
4. Stripe Checkout without DB `purchase_id` in `checkout_created`.
5. Telnyx order before payment webhook verified.
6. `list_agents()` without `tenant_id`.
7. **Implementing Voxly signup UI before PRD-12 Phase A passes.**

---

## Target backend layout (spec only — no code in this pack)

```text
server/services/saas/
  tenant_guard.py
  auth_service.py          # signup, login, refresh, delete
  telephony_orchestrator.py
  number_purchase_service.py
  provision_worker.py

server/routes/
  app_auth.py              # /api/auth/*
  app_telephony.py
  stripe_webhook.py
  dev_admin.py             # /api/dev/admin/*
```

---

## Billing model (clarified)

| Charge | Mechanism |
|--------|-----------|
| Number rent | Stripe Subscription per DID |
| Voice usage | Wallet / metered (Phase 5) |
| Failed provision | Auto-refund + admin queue |

---

## Revision log

| Date | Change |
|------|--------|
| 2026-09-22 | Initial review; reservations, JWT, orchestrator, jobs |
| 2026-09-22 | C9–C12; PRD-03 full lifecycle; PRD-12 backend gate; PRD sync |
