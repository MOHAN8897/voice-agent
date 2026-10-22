# SaaS workflow — product requirements (PRD pack)

Multi-tenant SaaS for the **voice agent** backend: per-user auth, Stripe number purchase, Telnyx provision, Realtime PSTN, dev admin.

**Customer frontend (later):** [Voxly AI](https://github.com/saiskm115/voxly-ai) — integrate only after backend gate ([PRD-12](./PRD-12-backend-saas-readiness.md)).

## Reading order

| # | Document | Purpose |
|---|----------|---------|
| **0** | [PRD-00-architecture-review.md](./PRD-00-architecture-review.md) | **Read first** — risks, anti-patterns, decisions |
| 1 | [PRD-01-product-vision.md](./PRD-01-product-vision.md) | Goals, personas, scope |
| 2 | [PRD-02-system-architecture.md](./PRD-02-system-architecture.md) | Orchestrator, JWT, call paths |
| 3 | [PRD-03-identity-users-tenants.md](./PRD-03-identity-users-tenants.md) | **Full user lifecycle** — signup → delete |
| 4 | [PRD-04-phone-numbers-stripe-telnyx.md](./PRD-04-phone-numbers-stripe-telnyx.md) | Stripe, reservations, provision jobs |
| 5 | [PRD-05-agents-voice-pstn-subscriber.md](./PRD-05-agents-voice-pstn-subscriber.md) | Agents, PSTN, no stack UI |
| 6 | [PRD-06-dev-admin-panel.md](./PRD-06-dev-admin-panel.md) | Platform operator console |
| 7 | [PRD-07-voxly-frontend-integration.md](./PRD-07-voxly-frontend-integration.md) | Voxly — **after backend ready** |
| 8 | [PRD-08-api-contract-mapping.md](./PRD-08-api-contract-mapping.md) | Voxly ↔ API gaps |
| 9 | [PRD-09-postgres-schema.md](./PRD-09-postgres-schema.md) | Migrations |
| 10 | [PRD-10-implementation-phases.md](./PRD-10-implementation-phases.md) | Build order |
| 11 | [PRD-11-stripe-cli-local-dev.md](./PRD-11-stripe-cli-local-dev.md) | Stripe CLI |
| **12** | [PRD-12-backend-saas-readiness.md](./PRD-12-backend-saas-readiness.md) | **Gate checklist before Voxly** |

**Also:** [VOXLY-LOCAL-SETUP.md](./VOXLY-LOCAL-SETUP.md) · [ENV-SaaS.example](./ENV-SaaS.example)

## Backend-first rule

```text
Phase 1 Auth + guards → Phase 2 Orchestrator → Phase 3 Stripe/numbers → Phase 4 Dev admin
→ PRD-12 sign-off → Phase 5 Voxly
```

Do **not** wire Voxly signup or payments until Phase A–D in PRD-12 are green.

## Codebase anchors

| Area | Location |
|------|----------|
| Tenants, agents, calls | `server/db/models/entities.py` |
| Phone numbers | `server/db/models/phase5_models.py`, `server/routes/campaigns.py` |
| Dev PSTN + Telnyx | `server/routes/dev_telephony.py` |
| Realtime PSTN | `server/services/pstn_realtime_voice_core.py` |
| Auth (legacy) | `server/routes/auth.py` |
| PSTN UI dev-only | `AgentTestStudio.tsx` (`showPstn = portal === "dev"`) |

## Status

| Item | State |
|------|--------|
| PRD pack | Reviewed 2026-09-22 — optimized for backend SaaS |
| Backend implementation | Phases 1–7 backend — see [PRD-PHASES-1-7-STATUS.md](./PRD-PHASES-1-7-STATUS.md) |
| Voxly integration | Blocked on PRD-12 |
