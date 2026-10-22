# PRD-10 — Implementation phases (backend before frontend)

**Rule:** Complete [PRD-12](./PRD-12-backend-saas-readiness.md) Phase **A–D** before Voxly integration (Phase E).

## Phase 0 — Docs & tooling

- [x] PRD pack in `saas-workflow/`
- [x] Stripe CLI installed (see PRD-11)
- [x] `SAAS_AUTH_ENABLED` flag defined in env

## Phase 1 — Identity & tenant isolation (PRD-03, PRD-12 Phase A)

**Backend only**

- [x] Migration `009`: users, memberships, refresh_tokens, password_reset_tokens, tenant columns
- [x] `server/routes/app_auth.py` — signup, login, refresh, logout, change-password, forgot/reset, delete
- [x] `server/services/saas/tenant_guard.py`
- [x] JWT dependency `require_subscriber_jwt` / `require_subscriber_jwt_if_enabled`
- [x] Guard `/api/agents/**` and `/api/agents/{id}/business-brain/**` when `SAAS_AUTH_ENABLED`
- [x] Account delete + tenant delete job row (`tenant_teardown_jobs`)
- [x] Deprecate `/api/app/login` when flag on

**Tests:** PRD-12 A1–A10 — run with `DATABASE_URL` + migration `010`

**No Voxly work in this phase.**

## Phase 2 — Telephony orchestrator (PRD-12 Phase B, partial)

- [x] `telephony_orchestrator.subscriber_outbound` + `app_telephony` outbound
- [x] Server `stack_override` realtime_voice (no client override)
- [x] Inbound DID routing (`inbound_routing.py` + Telnyx webhook)
- [x] `telephony_contacts` CRUD (create/list); routing PUT
- [x] Subscriber `GET /api/calls` scoped by tenant

## Phase 3 — Stripe + numbers (PRD-12 Phase C)

- [x] Migration `010`: purchases, reservations, provision_jobs, stripe_webhook_events
- [x] `POST /api/telephony/buy`, purchases GET, Stripe webhook, background worker
- [x] Assign number API
- [x] Email verification gate on buy (config)

## Phase 4 — Dev admin (PRD-12 Phase D)

- [x] `/api/dev/admin/*` — `server/routes/dev_admin.py`
- [x] Dev UI `/dev/saas-admin` (minimal)

## Phase 5 — Voxly frontend (PRD-12 Phase E)

- [ ] Bearer token in Voxly `api.js` (see `voxly-api-bearer.patch.md`)
- [x] Backend endpoints + `CORS_ORIGINS` ready

## Phase 6 — Wallet & usage

- [x] Wallet table + `GET /api/billing/wallet`
- [x] `POST /api/billing/topup` (Stripe Checkout + webhook)
- [ ] Metered voice usage

## Phase 7 — Leads & campaigns polish

- [x] Leads table + GET/POST/PATCH stage
- [x] Campaigns via `require_api_tenant` (JWT or legacy app session)

## Environment

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Required prod |
| `JWT_SECRET` | Subscriber tokens |
| `SAAS_AUTH_ENABLED` | Gate new auth |
| `STRIPE_*` | PRD-04 |
| `CORS_ORIGINS` | Voxly origin |

## Rollout

- `SAAS_TELEPHONY_ENABLED` per tenant
- Feature flag `SAAS_AUTH_ENABLED` globally for staging → prod
