# PRD-08 — API contract mapping (Voxly ↔ voice agent backend)

Source: [Voxly README — Supported Backend Endpoints](https://github.com/saiskm115/voxly-ai/blob/main/README.md)

## Auth & sessions (PRD-03 — implement before Voxly)

| Voxly / spec | Current backend | Action |
|--------------|-----------------|--------|
| `POST /api/auth/signup` | Missing | **Phase 1** |
| `POST /api/auth/login` | `POST /api/app/login` (shared password) | **Replace** with email + JWT |
| `POST /api/auth/refresh` | Missing | **Phase 1** |
| `POST /api/auth/logout` | `POST /api/app/logout` | Revoke refresh token |
| `GET /api/auth/me` | Partial | user, tenant, memberships, role |
| `POST /api/auth/forgot-password` | Missing | Phase 1 |
| `POST /api/auth/reset-password` | Missing | Phase 1 |
| `POST /api/auth/change-password` | Missing | Phase 1 |
| `POST /api/auth/delete-account` | Missing | Phase 1 |
| `POST /api/tenants/delete` | Missing | Phase 1 job |
| `POST /api/auth/switch-tenant` | Missing | Phase 1 |
| `POST /api/auth/google` | Missing | 501 |
| `POST /api/auth/github` | Missing | 501 |
| `GET /api/auth/session` | Exists | Public feature flags only |

All subscriber routes: **`Authorization: Bearer`** (not cookie).

## AI voice employees (agents)

| Voxly | Current | Action |
|-------|---------|--------|
| `GET /api/agents` | `GET /api/agents` (no auth) | Tenant filter + auth |
| `POST /api/agents` | `POST /api/agents` | Tenant from session |
| `GET /api/agents/:id` | `GET /api/agents/{id}` | Auth + tenant check |
| `PUT /api/agents/:id` | `PATCH /api/agents/{id}` | Support PUT alias or document PATCH |
| `DELETE /api/agents/:id` | `DELETE /api/agents/{id}` | Auth |

Brain/publish (Voxly may embed in agent editor):

| Needed | Current |
|--------|---------|
| `GET/PUT business-brain` | `/api/agents/{id}/business-brain` |
| `POST publish` | `/api/agents/{id}/business-brain/publish` |

## Telephony & virtual DIDs

| Voxly | Current | Action |
|-------|---------|--------|
| `GET /api/telephony/numbers` | `GET /api/phone-numbers` (manual add) | Extend + Stripe-owned rows |
| `POST /api/telephony/buy` | Dev-only Telnyx order | **New** Stripe checkout flow |
| `POST /api/telephony/numbers/:id/assign` | No `agent_id` on model | **New** |
| `PUT /api/telephony/numbers/:id/routing` | Missing | **New** flags + agent |

Additional (backend-native, Voxly may add later):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/telephony/numbers/search` | Pre-checkout search |
| `GET /api/telephony/purchases/:id` | Provision status |
| `POST /api/telephony/calls/outbound` | PSTN dial |

Dev equivalents stay at `/api/dev/telephony/*`.

## Calls & transcripts

| Voxly | Current | Action |
|-------|---------|--------|
| `GET /api/calls` | `GET /api/calls` with `tenantId` | Default tenant from session |
| `GET /api/calls/:id` | Exists | Tenant guard |
| `POST /api/calls/outbound` | Dev telephony only | Subscriber route above |

## CRM leads

| Voxly | Current | Action |
|-------|---------|--------|
| `GET/POST /api/leads`, `PATCH stage` | Not found | Phase 3 — new module or stub 501 |

## Campaigns

| Voxly | Current | Action |
|-------|---------|--------|
| `GET/POST /api/campaigns`, `PATCH status` | `server/routes/campaigns.py` | Align path prefixes (`/api/campaigns` OK) |

## Billing & wallet

| Voxly | Current | Action |
|-------|---------|--------|
| `GET /api/billing/wallet` | Missing | Balance from Stripe Customer balance or internal ledger |
| `POST /api/billing/topup` | Missing | Stripe Checkout one-time |

## Stripe webhooks (not in Voxly client)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/stripe/webhook` | Provision numbers, subscription lifecycle |

## Response shape conventions

Voxly expects `{ success, message, data? }` in places — document adapter layer in `api.js` OR normalize backend responses:

```json
{ "ok": true, "agents": [...] }
```

**Recommendation:** thin FastAPI compatibility router that wraps existing handlers for Voxly paths without breaking Next `/app` clients.

## Error codes

| HTTP | Code | When |
|------|------|------|
| 401 | `auth_error` | No session |
| 403 | `forbidden` | Wrong tenant |
| 402 | `payment_required` | No active number subscription |
| 409 | `number_unavailable` | Telnyx search stale |
| 422 | `provision_failed` | Telnyx error after payment — support ticket id |
