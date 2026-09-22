# PRD implementation status (Phases 1–7)

Last updated: 2026-09-22 (audit pass)

## Phases 1–3 — Subscriber core ✅ (backend)

| Item | Status |
|------|--------|
| Identity JWT + full PRD-03 flows (incl. leave, transfer) | Done |
| Tenant guards: agents, brain, telephony, calls | Done |
| Inbound DID routing | Done |
| Teardown worker + reservation purge | Done |
| Stripe buy / webhook / provision | Done |
| `invoice.payment_failed` + subscription deleted | Done |

**Requires:** `alembic upgrade head` through `011_saas_leads_billing`.

## Phase 4 — Dev admin ✅

| Item | Status |
|------|--------|
| `/api/dev/admin/*` | Done |
| Audit on mutations | Done |
| `/dev/saas-admin` UI | Minimal |

## Phase 5 — Voxly (PRD-07)

| Item | Status |
|------|--------|
| Backend APIs + CORS | Done |
| [voxly-api-bearer.patch.md](./voxly-api-bearer.patch.md) | Doc for external repo |
| Voxly repo wired | `voxly-ai/` in monorepo — `api.js`, console sync, Razorpay billing UI |

## Phase 6 — Wallet ✅ (v1)

| Item | Status |
|------|--------|
| `billing_wallets` + transactions | Migration 011 |
| `GET /api/billing/wallet` | Done |
| `POST /api/billing/topup` | Stripe Checkout + webhook credit |

## Phase 7 — Leads & campaigns ✅ (v1)

| Item | Status |
|------|--------|
| Leads CRUD + stage patch | Done |
| Campaigns JWT via `require_api_tenant` | Done |
| `PATCH /api/campaigns/{id}/status` | Done |

## Known limits (not blocking PRD-12 D)

- Teardown: no live Telnyx release / Stripe cancel loop yet (archives + disables numbers)
- OAuth Google/GitHub: 501
- Metered voice usage billing: future
- PRD-12 integration tests: run manually with `DATABASE_URL` + Stripe CLI

## Next

1. `alembic upgrade head`
2. Staging PRD-12 checklist
3. Voxly Phase E per patch doc
