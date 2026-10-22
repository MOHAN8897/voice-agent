# PRD-06 — Dev admin panel (platform operations)

## Purpose

Platform operators manage **everything subscribers cannot**: Telnyx inventory, Stripe reconciliation, user/tenant lifecycle, manual overrides, and incident response—without SSH or SQL.

## New dev routes (under `/dev` UI + `/api/dev/admin/*`)

### Dashboard

- Active tenants, MRR proxy (Stripe), numbers in use, failed provisions (24h), concurrent PSTN calls

### Tenants

| Action | API |
|--------|-----|
| List / search | `GET /api/dev/admin/tenants` |
| Detail | `GET /api/dev/admin/tenants/{id}` — agents, numbers, users, recent calls |
| Suspend / activate | `PATCH /api/dev/admin/tenants/{id}` `{ status }` |
| Set plan limits | `PATCH` `{ plan, limits: { maxAgents, maxNumbers } }` |

### Users

| Action | API |
|--------|-----|
| List | `GET /api/dev/admin/users?tenantId=` |
| Detail | `GET /api/dev/admin/users/{id}` — memberships, last login |
| Create invite | `POST /api/dev/admin/users` |
| Disable | `PATCH /api/dev/admin/users/{id}` `{ status: disabled }` |
| Enable | `PATCH` `{ status: active }` |
| Reset password | `POST /api/dev/admin/users/{id}/reset-password` |
| Force tenant membership | `POST /api/dev/admin/memberships` |
| **Delete user (platform)** | `POST /api/dev/admin/users/{id}/delete` — override rules; audit required |
| View auth events | `GET /api/dev/admin/users/{id}/auth-events` |

### Number inventory & assignment map

| Action | API |
|--------|-----|
| Global assignment table | `GET /api/dev/admin/phone-assignments` |
| Pre-buy (no Stripe) | `POST /api/dev/telephony/telnyx/numbers/order` (existing) + `POST /api/dev/admin/numbers/allocate` `{ e164, tenantId }` |
| Release | `POST /api/dev/admin/numbers/{id}/release` — Telnyx release + Stripe sub cancel |
| Reassign tenant | `PATCH /api/dev/admin/numbers/{id}` `{ tenantId }` |
| Reassign agent | `PATCH` `{ agentId }` |

Display columns: `e164`, `tenant`, `agent`, `purchase_status`, `stripe_subscription_id`, `telnyx_number_id`, `created_at`.

### Purchases & Stripe ops

| Action | API |
|--------|-----|
| List purchases | `GET /api/dev/admin/purchases?status=failed` |
| Retry provision | `POST /api/dev/admin/purchases/{id}/retry-provision` |
| Refund | `POST /api/dev/admin/purchases/{id}/refund` |

### Telephony debug (existing + links)

- Keep current dev telephony: media flow, production canary, Telnyx setup status
- Link from tenant detail → "Test outbound as tenant" (impersonation token, time-limited)

## RBAC

- New permissions in `server/auth/rbac.py`:
  - `dev.admin.users`
  - `dev.admin.tenants`
  - `dev.admin.numbers`
  - `dev.admin.billing`
- Only `platform_admin`, `developer` by default.

## Audit

Write `audit_log` on every admin mutation: actor (dev session subject), `tenant_id`, payload JSON.

## UI placement

New dev nav section: **SaaS Admin**

- Users
- Tenants
- Phone assignments
- Failed purchases

Reuse skeuo/dev styling from `web/app/dev/(portal)/*`.

## Impersonation (optional v1.1)

- Dev generates short-lived app session for `tenant_id` to reproduce subscriber issues—logged in audit.
