# PRD-12 — Backend SaaS readiness gate (before frontend)

Use this checklist to declare the **API ready for Voxly integration**. Frontend work starts only when **Phase A–C** are green in staging.

## Phase A — Identity & isolation (mandatory)

| # | Requirement | Verify |
|---|-------------|--------|
| A1 | `DATABASE_URL` + migration `009_saas_*` applied | Alembic head |
| A2 | Signup creates user + tenant + membership + Stripe customer | Integration test |
| A3 | Login returns JWT access + refresh | Test |
| A4 | Refresh rotation works; logout revokes | Test |
| A5 | `GET /api/agents` returns **only** current tenant | Two-tenant test |
| A6 | Cross-tenant `GET /api/agents/{id}` → **404** | Test |
| A7 | All `business-brain` routes tenant-guarded | Test |
| A8 | `tenant.status=suspended` blocks API + telephony | Test |
| A9 | Password reset + change password flows | Test |
| A10 | Delete account + delete tenant teardown spec implemented | Test / job |

## Phase B — Telephony core (mandatory for voice SaaS)

| # | Requirement | Verify |
|---|-------------|--------|
| B1 | `TelephonyOrchestrator` — no direct `dev_telephony_store` for subscribers | Code review |
| B2 | Outbound subscriber API; **no** `stackOverride` in schema | Test rejects field |
| B3 | Internal `stack_policy=saas_subscriber` → `realtime_voice` only | Test |
| B4 | Inbound DID → `tenant_id` + `agent_id` from `phone_numbers` | Simulated webhook |
| B5 | Unassigned DID → safe hangup or tenant default agent (documented) | Test |
| B6 | `call_ledger` / `calls` always have `tenant_id` | Test |
| B7 | Concurrent call limit per `tenants.limits` | Test |
| B8 | Subscriber contacts/history **not** in `dev_pstn_*` tables | Schema review |

## Phase C — Numbers & billing (mandatory for paid DIDs)

| # | Requirement | Verify |
|---|-------------|--------|
| C1 | `number_reservations` during checkout TTL | Race test |
| C2 | Stripe webhook → job row → worker (not sync in webhook) | Stripe CLI |
| C3 | Idempotent `stripe_webhook_events` | Duplicate event test |
| C4 | Purchase `GET` scoped to tenant | IDOR test |
| C5 | Assign number → agent same tenant | Test |
| C6 | Subscription cancel → suspend routing + grace release job | Test |
| C7 | Failed provision → refund or admin queue | Test |

## Phase D — Dev admin (mandatory for operations)

| # | Requirement | Verify |
|---|-------------|--------|
| D1 | List users / tenants | Manual |
| D2 | Suspend tenant / disable user | Manual |
| D3 | Assignment map API | Manual |
| D4 | Retry failed provision / refund | Manual |
| D5 | Audit log on admin mutations | DB rows |

## Phase E — Frontend (Voxly) — after A–D

| # | Requirement |
|---|-------------|
| E1 | `VITE_API_URL` + Bearer token in `api.js` |
| E2 | Signup/login/refresh wired |
| E3 | Agents + brain publish |
| E4 | Number buy + assign + PSTN dial |
| E5 | Calls list |

## Non-functional

| Area | Target |
|------|--------|
| API p95 auth | &lt; 200 ms |
| Webhook ack | &lt; 5 s (enqueue only) |
| Secrets | Not in repo; Stripe/Telnyx/OpenAI server-only |
| Logs | No passwords, no full JWT |

## Explicitly out of scope for “backend ready” v1

- Google/GitHub OAuth (501 OK)
- Leads CRM (501 OK)
- Per-tenant Telnyx subaccounts
- Next.js `/app` subscriber parity (internal QA only)

## Sign-off

| Role | Name | Date |
|------|------|------|
| Engineering | | |
| Product | | |

When signed, update [README.md](./README.md) status to **Backend SaaS gate passed**.
