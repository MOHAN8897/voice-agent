# Architecture — Voice Agent Platform

**Version:** 1.1  
**Date:** 25 August 2026  
**Status:** Target architecture for MVP — aligned with PRD v2.0

## Purpose

This folder is the **engineering architecture pack** for the voice agent platform. It translates the PRD technical documents into categorized, implementation-ready design artifacts. Use it alongside the [implementation plan](../implementation/README.md).

## Current vs target

| Aspect | Current (`ARCHITECTURE.md`) | Target (this folder) |
|--------|---------------------------|----------------------|
| Frontend | Vanilla SPA in `client/` | Next.js App Router in `web/` |
| Backend | FastAPI monolith | FastAPI API + Worker services |
| Persistence | In-RAM TTL + `localStorage` | PostgreSQL + object storage |
| Memory | 2-turn window, optional string summary | B/C/A split with structured ops |
| Providers | Sarvam + OpenAI hard-coded | Registry + resolver + tiers |
| Calls | `session_id` only | `call_id` with ledger + archive |
| Telephony | None | Plivo browser + PSTN |

## Document index

### Core

| File | Contents |
|------|----------|
| [01-system-context.md](./01-system-context.md) | C4 context, Railway topology, service boundaries |
| [02-module-ownership.md](./02-module-ownership.md) | L1–L4 layers, A/B/C objects, orchestrators, forbidden patterns |
| [03-observability-and-slos.md](./03-observability-and-slos.md) | Per-call traces, metrics, SLOs, benchmark policy |
| [04-security-rbac-and-promotion.md](./04-security-rbac-and-promotion.md) | Auth, tenant isolation, RBAC, promotion workflow |

### Data models (`data-models/`)

| File | Contents |
|------|----------|
| [memory-ledger-outcome.md](./data-models/memory-ledger-outcome.md) | Objects A, B, C, outcome schema, compact memory default |
| [brain-compilation.md](./data-models/brain-compilation.md) | Platform/business brain, optimizer, compiled version lock |
| [entities-and-persistence.md](./data-models/entities-and-persistence.md) | Tenant, agent, call, campaign entities; DB tables |

### Data flows (`data-flows/`)

| File | Contents |
|------|----------|
| [live-voice-turn.md](./data-flows/live-voice-turn.md) | Hot-path sequence: STT → orchestrator → LLM → TTS |
| [call-lifecycle.md](./data-flows/call-lifecycle.md) | start/end, version locks, idempotent finalization |
| [post-call-pipeline.md](./data-flows/post-call-pipeline.md) | Async outcome, summaries, disposition |

### Infrastructure (`infrastructure/`)

| File | Contents |
|------|----------|
| [railway-deployment.md](./infrastructure/railway-deployment.md) | web/api/worker/postgres/redis/bucket topology |
| [database-and-storage.md](./infrastructure/database-and-storage.md) | Schema overview, file layout, retention |

### Integrations (`integrations/`)

| File | Contents |
|------|----------|
| [provider-platform.md](./integrations/provider-platform.md) | Registry, resolver, tiers, adapter contracts |
| [two-way-voice-stream.md](./integrations/two-way-voice-stream.md) | Sarvam / Cartesia / Telnyx / browser audio formats and two-way PSTN |
| [telnyx-validation-pipeline.md](./integrations/telnyx-validation-pipeline.md) | TEST 0–10 Telnyx + agent validation phases (run in order) |
| [plivo-and-campaigns.md](./integrations/plivo-and-campaigns.md) | PSTN streaming, outbound dialer, campaigns |
| [nextjs-frontend-split.md](./integrations/nextjs-frontend-split.md) | Frontend/backend responsibilities, live voice port |

## Alignment with PRD & implementation

| Pack | Role |
|------|------|
| `prd/` | Product requirements and locked decisions |
| `implementation/` | 5-phase delivery plan + [SKILLS-AND-MCP-GUIDE.md](../implementation/SKILLS-AND-MCP-GUIDE.md) |
| [PRD-TRACEABILITY-AUDIT.md](../implementation/PRD-TRACEABILITY-AUDIT.md) | Cross-pack gap analysis |

**Conflict resolutions:** PostgreSQL not SQLite (CD-021); CD-016 same-LLM memory; `memory-events` canonical API path.

## Authority ladder

1. [`prd/01-master-prd.md`](../prd/01-master-prd.md) — product scope
2. [`prd/15-architecture-ownership-and-singularity.md`](../prd/15-architecture-ownership-and-singularity.md) — ownership conflicts
3. **This architecture pack** — categorized engineering design
4. [`prd/06-technical-architecture.md`](../prd/06-technical-architecture.md) — PRD technical reference
5. Topic PRDs (`03`, `04`, `12`, `13`, `19`, …)

## Related PRD documents

- Memory detail: [`prd/12-brain-business-memory-spec.md`](../prd/12-brain-business-memory-spec.md)
- APIs & security: [`prd/13-api-data-security-contracts.md`](../prd/13-api-data-security-contracts.md)
- UI sitemap: [`prd/11-ui-information-architecture.md`](../prd/11-ui-information-architecture.md)
- Product decisions: [`prd/17-product-decisions.md`](../prd/17-product-decisions.md)
- Traceability audit: [`implementation/PRD-TRACEABILITY-AUDIT.md`](../implementation/PRD-TRACEABILITY-AUDIT.md)
