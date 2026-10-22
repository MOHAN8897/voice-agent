# PRD-01 — Product vision & scope

## Summary

Launch a **B2B SaaS** where customers create **voice agents**, **purchase phone numbers on our website** (Stripe), and run **inbound/outbound Realtime PSTN** calls—without seeing STT/LLM/TTS stack configuration. Platform operators use the **dev portal** to manage users, tenants, Telnyx inventory, and failed provisions.

**Customer-facing UI:** [Voxly AI](https://github.com/saiskm115/voxly-ai) (Vite/React landing + console), configured via `VITE_API_URL` to this backend.

**Operator UI:** Existing **dev portal** (`/dev/*`) plus new admin modules for SaaS operations.

## Personas

| Persona | Needs |
|---------|--------|
| **Subscriber (customer admin)** | Sign up, pay for numbers, create agents, assign numbers, test/campaign calls, view transcripts/billing |
| **Subscriber (voice user)** | Place test calls, view call history (no stack access) |
| **Platform admin (dev)** | Buy/release Telnyx numbers, allocate pool, manage users/tenants, impersonate/debug, view Stripe/Telnyx failures |
| **System** | Idempotent Stripe webhooks, Telnyx provision, tenant-isolated routing |

## Goals

1. **One Telnyx platform account** — subscribers never hold Telnyx keys; we purchase DIDs after successful payment.
2. **Authoritative assignment map** — Postgres (and optional cache) records `tenant_id` ↔ `e164` ↔ `agent_id` for routing and billing.
3. **Same PSTN quality as dev** — `pipeline: realtime_voice`, confirmed-close hangup, compiled brain per agent.
4. **Stripe-first commerce** — checkout for number purchase (setup + recurring where applicable); wallet/top-up aligned with Voxly billing endpoints (phase 2).
5. **Voxly as primary subscriber shell** — marketing site + console; Next `/app` remains optional or internal.

## Non-goals (v1)

- Per-tenant Telnyx subaccounts (enterprise BYOC) — design hooks only.
- Subscriber-editable provider stack / tier workbench.
- OAuth (Google/GitHub) on v1 unless trivial — email/password first; Voxly stubs can return 501 until phase 2.
- Full CRM/leads pipeline — document API compatibility; implement after core telephony.

## Success metrics

- Subscriber can complete: signup → pay for number → assign to agent → outbound PSTN call → see call in history.
- Zero cross-tenant leakage on agents, numbers, calls (pen-test checklist in PRD-02).
- Provision failure rate &lt; 1% with automatic refund or credit (Stripe + support queue).

## Principles

- **Backend before frontend** — [PRD-12](./PRD-12-backend-saas-readiness.md) gate before Voxly wiring.
- **Per-user accounts** — signup, login, refresh, password reset, account/org deletion ([PRD-03](./PRD-03-identity-users-tenants.md)).
- **Server-owned telephony** — clients send `agentId`, `fromE164`, `toE164` only; `stack_policy=saas_subscriber` on server ([PRD-05](./PRD-05-agents-voice-pstn-subscriber.md)).
- **Pay before provision** — Stripe webhook → job → Telnyx ([PRD-04](./PRD-04-phone-numbers-stripe-telnyx.md)).
- **Idempotent everything** — Stripe events, provision jobs, reservations.
