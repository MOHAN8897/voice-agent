# PRD-03 — Identity, users, tenants & full account lifecycle

**Backend-first:** Implement and test everything in this document **before** wiring [Voxly](https://github.com/saiskm115/voxly-ai). Dev portal keeps **cookie** auth; subscriber API uses **JWT** (PRD-00 C2).

## Problem (today)

- App login: single env password → one `default_tenant_id` (`server/routes/auth.py`).
- No `users` table; `/api/agents` and brain routes are **not tenant-scoped**.
- No signup, password reset, account deletion, or per-user audit.

## Core entities

| Entity | Purpose |
|--------|---------|
| `tenants` | Customer org — billing, limits, `stripe_customer_id`, `status` |
| `users` | Global login identity (email unique) |
| `tenant_memberships` | `(user_id, tenant_id, role)` — user may belong to multiple tenants later |
| `refresh_tokens` | Hashed token family for rotation / revoke |
| `auth_events` | Optional security audit (login, logout, password change) |

### Tenant `status`

| Value | Effect |
|-------|--------|
| `active` | Normal |
| `suspended` | Login blocked; telephony blocked; read-only or 403 on API |
| `pending_deletion` | Grace period; no new purchases |
| `deleted` | Soft-deleted; no access |

### User `status`

| Value | Effect |
|-------|--------|
| `active` | Normal |
| `disabled` | Cannot login (admin or self-delete pending) |
| `pending_verification` | Can login; **block number purchase** until `email_verified_at` set (config) |

---

## Authentication model (subscriber API)

### Tokens

| Token | TTL | Storage (Voxly) | Claims |
|-------|-----|-----------------|--------|
| **Access** JWT | 15 min | Memory / short-lived | `sub`=user_id, `tid`=tenant_id, `role`, `email` |
| **Refresh** | 30 days | HttpOnly cookie **or** secure storage + rotation | opaque id → DB row |

- Sign with `JWT_SECRET` (env); algorithm HS256.
- `Authorization: Bearer <access>` on all subscriber mutating routes.
- `POST /api/auth/refresh` — body `{ refreshToken }` or cookie → new access (+ rotate refresh).

### Dev portal (unchanged pattern)

- `POST /api/dev/login` — env credentials → **cookie** session, not JWT.
- Dev routes never accept subscriber JWT as substitute unless explicit impersonation (PRD-06).

### Active tenant context

- Access token embeds **one** `tenant_id` (workspace).
- `POST /api/auth/switch-tenant` `{ tenantId }` — user must have membership → new access JWT.
- `GET /api/auth/me` returns user + current tenant + all memberships.

---

## User flows (end-to-end)

### 1. Signup (account + org creation)

**`POST /api/auth/signup`** (public, rate-limited)

```json
{
  "email": "user@company.com",
  "password": "…",
  "fullName": "…",
  "orgName": "Acme Pvt Ltd"
}
```

**Server (single DB transaction):**

1. Validate email format, password policy (min length, breach check optional).
2. Reject duplicate email → `409 email_taken`.
3. Insert `users` (password_hash bcrypt/argon2).
4. Insert `tenants` (`name=orgName`, `plan=starter`, `limits` defaults).
5. Insert `tenant_memberships` (`customer_admin`).
6. Create Stripe Customer → save `tenants.stripe_customer_id` (if Stripe configured; else defer to first purchase).
7. Write `auth_events` signup.
8. Return `{ accessToken, refreshToken, expiresIn, user, tenant }`.

**Email verification (v1 recommended):**

- Send link with signed token `POST /api/auth/verify-email?token=…`
- Until verified: allow agents/brain; **deny** `POST /api/telephony/buy` with `402` / `verification_required`.

### 2. Login

**`POST /api/auth/login`**

```json
{ "email", "password" }
```

- Verify hash; check `user.status`, `tenant.status` (primary membership or last-used tenant).
- Issue access + refresh.
- Failed attempts → rate limit + optional lockout after N tries.

### 3. Session refresh

**`POST /api/auth/refresh`** — rotate refresh token; invalidate old hash (reuse detection → revoke family).

### 4. Logout

**`POST /api/auth/logout`** — revoke refresh token row; client discards access.

**`POST /api/auth/logout-all`** — revoke all refresh tokens for user (password change, security).

### 5. Password reset (forgot password)

1. `POST /api/auth/forgot-password` `{ email }` — always 200 (no email enumeration in body); send reset link if user exists.
2. `POST /api/auth/reset-password` `{ token, newPassword }` — validate one-time token → update hash → `logout-all`.

### 6. Change password (authenticated)

**`POST /api/auth/change-password`** — `{ currentPassword, newPassword }` → `logout-all` except optional current session.

### 7. Profile

| Endpoint | Action |
|----------|--------|
| `GET /api/auth/me` | User, tenant, role, memberships, limits |
| `PATCH /api/auth/me` | `fullName` only (email change = separate verify flow) |

### 8. Invite teammate (customer_admin)

**`POST /api/tenants/members/invite`** `{ email, role }`

- If user exists: add membership.
- If not: create user with `status=pending_invite`, random setup token, email link to `POST /api/auth/accept-invite`.
- Roles: `customer_admin` | `voice_engineer` | `customer_viewer`.

**`DELETE /api/tenants/members/{userId}`** — remove membership (not delete global user unless last tenant).

### 9. Leave organization

**`POST /api/tenants/leave`** — member removes self; forbidden if sole `customer_admin` without transfer.

### 10. Transfer ownership

**`POST /api/tenants/transfer-ownership`** `{ newAdminUserId }` — current admin only.

### 11. Delete account (user)

**`POST /api/auth/delete-account`** — `{ password, confirm: "DELETE" }`

- If user is **sole admin** of tenant with active numbers/subscription → **409** — must delete org or transfer first.
- Else: disable user, revoke tokens, anonymize PII (`email` → `deleted+<uuid>@invalid.local`), keep audit referential integrity.
- Memberships removed.

### 12. Delete organization (tenant)

**`POST /api/tenants/delete`** — `customer_admin` + confirm

**Ordered teardown (async job):**

1. Cancel Stripe subscriptions for all `phone_numbers` on tenant.
2. Schedule Telnyx release (after grace if required).
3. Archive agents (`status=archived`); retain `calls` per retention policy.
4. `tenants.status=deleted`, `deleted_at`.
5. Notify dev admin audit.

### 13. Platform admin actions (dev)

See PRD-06: suspend tenant, disable user, reset password, force-delete with override.

---

## Authorization (every subscriber route)

Central **`tenant_guard`** (spec in PRD-00):

```text
resolve_principal(JWT) → user_id, tenant_id, role
assert_membership(user_id, tenant_id)
assert_tenant_active(tenant_id)
for resource in agent | number | call | purchase:
  assert resource.tenant_id == tenant_id  # else 404 (not 403, avoid ID leak)
```

Apply to:

- `/api/agents/**`
- `/api/agents/{id}/business-brain/**`
- `/api/telephony/**`
- `/api/calls/**`
- `/api/campaigns/**`

**RBAC** (reuse `server/auth/rbac.py` names):

| Permission | Roles |
|------------|-------|
| `app.agents.write` | customer_admin, voice_engineer |
| `app.telephony.write` | customer_admin, voice_engineer |
| `app.billing.write` | customer_admin |
| `app.members.write` | customer_admin |

---

## API summary (subscriber auth)

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/auth/signup` | Public |
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/refresh` | Refresh token |
| POST | `/api/auth/logout` | Refresh or access |
| POST | `/api/auth/logout-all` | Access |
| POST | `/api/auth/forgot-password` | Public |
| POST | `/api/auth/reset-password` | Public + token |
| POST | `/api/auth/change-password` | Access |
| POST | `/api/auth/verify-email` | Public + token |
| GET | `/api/auth/me` | Access |
| PATCH | `/api/auth/me` | Access |
| POST | `/api/auth/switch-tenant` | Access |
| POST | `/api/auth/delete-account` | Access |
| POST | `/api/tenants/delete` | Access + customer_admin |
| POST | `/api/tenants/members/invite` | Access + customer_admin |
| DELETE | `/api/tenants/members/{userId}` | Access + customer_admin |
| POST | `/api/tenants/leave` | Access |
| POST | `/api/tenants/transfer-ownership` | Access + customer_admin |
| GET | `/api/auth/session` | Public | Feature flags only (no PII) |

Legacy **`POST /api/app/login`** — deprecate when `SAAS_AUTH_ENABLED=true`; return 410 with message.

---

## Migration from shared password

1. `DATABASE_URL` required when `SAAS_AUTH_ENABLED=true`.
2. Dev login unchanged.
3. Bootstrap CLI: `python -m server.db.seed_saas_admin` (optional) — does not replace subscriber signup.

---

## Security checklist

- [ ] Passwords hashed (never log).
- [ ] JWT secret from env, rotation procedure documented.
- [ ] Refresh token stored hashed in DB.
- [ ] Rate limits on signup/login/forgot-password.
- [ ] CORS: explicit origins; no `*` with credentials.
- [ ] All resource IDs validated against `tenant_id`.
- [ ] Audit: signup, login failures, admin suspend, tenant delete.

---

## Related PRDs

- Schema: [PRD-09-postgres-schema.md](./PRD-09-postgres-schema.md)
- Admin UX: [PRD-06-dev-admin-panel.md](./PRD-06-dev-admin-panel.md)
- Backend gate before Voxly: [PRD-12-backend-saas-readiness.md](./PRD-12-backend-saas-readiness.md)
