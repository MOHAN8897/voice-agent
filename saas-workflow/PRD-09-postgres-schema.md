# PRD-09 — Postgres schema & migrations

`DATABASE_URL` required in production. Add migration **`009_saas_identity_billing`** (may split `010` for jobs if needed).

## Existing tables (keep)

- `tenants`, `agents`, `calls`, `business_brain_*`, `compiled_brain_snapshots`
- `phone_numbers`, `campaigns`, `dnc_list`, `audit_log`
- `dev_pstn_*` — **dev only**

## New tables — identity

### `users`

| Column | Type | Notes |
|--------|------|-------|
| user_id | UUID PK | |
| email | VARCHAR UNIQUE | lowercased |
| password_hash | VARCHAR | |
| full_name | VARCHAR | |
| status | VARCHAR | active, disabled, pending_verification, pending_invite |
| email_verified_at | TIMESTAMPTZ nullable | |
| deleted_at | TIMESTAMPTZ nullable | soft delete |
| created_at, updated_at | TIMESTAMPTZ | |

### `tenant_memberships`

| Column | Type |
|--------|------|
| id | UUID PK |
| user_id | UUID FK |
| tenant_id | UUID FK |
| role | VARCHAR |
| invited_by | UUID FK users nullable |
| UNIQUE(user_id, tenant_id) | |

### `refresh_tokens`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK | |
| token_hash | VARCHAR | never store raw |
| family_id | UUID | rotation family |
| expires_at | TIMESTAMPTZ | |
| revoked_at | TIMESTAMPTZ nullable | |
| created_at | TIMESTAMPTZ | |

### `password_reset_tokens`

| Column | Type |
|--------|------|
| token_hash | VARCHAR PK |
| user_id | UUID FK |
| expires_at | TIMESTAMPTZ |

### `auth_events` (optional, recommended)

| Column | Type |
|--------|------|
| id | UUID PK |
| user_id | UUID nullable |
| tenant_id | UUID nullable |
| event_type | VARCHAR |
| ip | VARCHAR |
| created_at | TIMESTAMPTZ |

## New tables — telephony commerce

### `number_catalog` — (unchanged from prior PRD)

### `number_reservations`

| Column | Type |
|--------|------|
| id | UUID PK |
| e164 | VARCHAR |
| tenant_id | UUID FK |
| purchase_id | UUID FK |
| expires_at | TIMESTAMPTZ |

Partial unique index: `e164` WHERE `expires_at > now()` (or enforce in app).

### `number_purchases` — (unchanged + link reservation)

### `provision_jobs`

| Column | Type | Notes |
|--------|------|-------|
| job_id | UUID PK | |
| purchase_id | UUID UNIQUE FK | |
| status | queued, running, done, failed | |
| attempts | INT | |
| last_error | JSONB | |
| created_at, updated_at | TIMESTAMPTZ | |

### `stripe_webhook_events`

| Column | Type |
|--------|------|
| event_id | VARCHAR PK |
| type | VARCHAR |
| processed_at | TIMESTAMPTZ |

### `telephony_contacts`

| Column | Type |
|--------|------|
| contact_id | UUID PK |
| tenant_id | UUID FK |
| name, phone, notes | |

## Alter `tenants`

| Column | Notes |
|--------|-------|
| stripe_customer_id | VARCHAR UNIQUE nullable |
| status | active, suspended, pending_deletion, deleted |
| limits | JSONB |
| default_agent_id | UUID FK agents nullable — inbound fallback |
| deleted_at | TIMESTAMPTZ nullable |
| billing_source | self_serve, manual (admin) |

## Alter `phone_numbers`

| Column | Notes |
|--------|-------|
| agent_id | UUID FK nullable |
| purchase_id | UUID FK nullable |
| telnyx_number_id | VARCHAR |
| billing_source | stripe, manual |
| inbound_enabled, outbound_enabled | BOOL |
| stripe_subscription_id | VARCHAR |
| released_at | TIMESTAMPTZ |
| UNIQUE(e164) | platform-wide |

## Alter `agents`

| Column | Notes |
|--------|-------|
| voice_settings | JSONB |

## Indexes

- `users(email)` WHERE `deleted_at IS NULL`
- `refresh_tokens(user_id)` WHERE `revoked_at IS NULL`
- `phone_numbers(e164)`, `(tenant_id, status)`
- `number_purchases(tenant_id, status)`
- `provision_jobs(status)` WHERE status IN ('queued','running')
- `calls(tenant_id, started_at DESC)`

## Tenant delete / user delete

- Do not hard-delete `calls` — retain per policy; anonymize PII on user delete.
- `agents.status=archived` on tenant delete job.

## Assignment dictionary (admin)

```sql
SELECT t.name AS tenant, pn.e164, a.name AS agent, pn.status,
       pn.billing_source, np.status AS purchase_status
FROM phone_numbers pn
JOIN tenants t ON t.tenant_id = pn.tenant_id
LEFT JOIN agents a ON a.agent_id = pn.agent_id
LEFT JOIN number_purchases np ON np.phone_number_id = pn.id
WHERE t.deleted_at IS NULL;
```
