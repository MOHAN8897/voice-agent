# Voice Agent Platform — PRD Index

Version: 2.0  
Date: 25 August 2026  
Status: Draft for approval; no implementation authorized by this documentation task

## Single source of truth

Start with [01-master-prd.md](./01-master-prd.md). It follows the required 35-section structure and contains the final product summary, journey, sitemap reference, feature matrix, release acceptance criteria, traceability link, genuine open questions, and high-level implementation order.

Topic documents are normative where the master delegates detail. If documents conflict:

1. `01-master-prd.md` — product scope and acceptance criteria
2. `15-architecture-ownership-and-singularity.md` — ownership, singularity, orchestration, RBAC, API aliases
3. `17-product-decisions.md` — locked product owner answers
4. Explicit conflict decisions in `14-research-traceability.md`
5. `../implementation/` + `../architecture/` — engineering delivery (must not contradict 1–4)
6. Topic PRD
7. Historical/re-audit notes (`10-prd-reaudit.md`)

## Categorized PRD pack

### Foundation and evidence

| File | Purpose |
|---|---|
| [00-current-state-audit.md](./00-current-state-audit.md) | Backend/frontend inventory, what works, gaps, and must-not-break behavior |
| [01-master-prd.md](./01-master-prd.md) | Normative product-level PRD |
| [02-requirements-reconciliation.md](./02-requirements-reconciliation.md) | Original source overlap and conflict analysis |
| [10-prd-reaudit.md](./10-prd-reaudit.md) | Earlier re-audit record; historical support, not master authority |
| [14-research-traceability.md](./14-research-traceability.md) | Research basis, evidence labels, traceability, conflicts |
| [**17-product-decisions.md**](./17-product-decisions.md) | **Locked answers from `douts.md`** — generic platform, memory flow, infra, roles |

### Provider, tier, and evaluation platform

| File | Purpose |
|---|---|
| [03-provider-platform.md](./03-provider-platform.md) | Provider registry, adapters, tiers, config modes, **Cartesia Ink-2 vs Ink Whisper vs Sonic 3.5**, Sarvam Saaras/Bulbul routing |
| [07-testing-metrics-observability.md](./07-testing-metrics-observability.md) | Benchmark metrics, scenarios, scoring, traces |

### Brain, memory, and calls

| File | Purpose |
|---|---|
| [04-memory-and-call-lifecycle.md](./04-memory-and-call-lifecycle.md) | Call/archive/outcome baseline |
| [12-brain-business-memory-spec.md](./12-brain-business-memory-spec.md) | Normative brain ownership, structured business logic, **exact memory schemas**, operations, merge/validation, event log, projection algorithm, token budgets, rolling summary, provenance, semantic validation, cache accounting |

### Product UX

| File | Purpose |
|---|---|
| [05-ux-console-and-dashboards.md](./05-ux-console-and-dashboards.md) | Earlier console concept; subordinate to document 11 |
| [11-ui-information-architecture.md](./11-ui-information-architecture.md) | Normative sitemap, screen contracts, responsive/SEO notes → **19** |

### Architecture, APIs, security, and telephony

| File | Purpose |
|---|---|
| [06-technical-architecture.md](./06-technical-architecture.md) | Target system/data-flow; Railway services; see **19** for Next.js frontend |
| [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md) | Plivo setup; **outbound priority**; number connect |
| [18-campaign-outbound.md](./18-campaign-outbound.md) | Campaigns, dialing, retries, DNC, consent, analytics |
| [19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md) | **Next.js only** frontend/backend split, **Railway web+api** deployment, SEO, performance |
| [13-api-data-security-contracts.md](./13-api-data-security-contracts.md) | Normative APIs, entities, persistence, RBAC, security, failures, SLOs |
| [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) | **Who owns what** — layers L1–L4, A/B/C data objects, orchestrators, RBAC, no double assignment |
| [16-mvp-implementation-skills.md](./16-mvp-implementation-skills.md) | Which Cursor/agent skills and Context7 to use per MVP phase |

### Delivery

| File | Purpose |
|---|---|
| [08-implementation-roadmap.md](./08-implementation-roadmap.md) | High-level PRD sequencing (phases 0–9) |
| [**../implementation/**](../implementation/README.md) | **Engineering 5-phase plan** — modules, APIs, tests, exit criteria |
| [**../architecture/**](../architecture/README.md) | **Engineering architecture pack** — data flows, ownership, infra |
| [**../implementation/SKILLS-AND-MCP-GUIDE.md**](../implementation/SKILLS-AND-MCP-GUIDE.md) | Skills, MCPs, and testing per phase |
| [**../implementation/PRD-TRACEABILITY-AUDIT.md**](../implementation/PRD-TRACEABILITY-AUDIT.md) | PRD ↔ implementation alignment audit |

## Source material inspected

- `fix.md`
- `memory implemenation.md` (repository filename; requested as memory implementation)
- `MEMORY_CALL_ARCHIVE_PLAN.md`
- `.env.example` and current environment loader
- Backend application, routes, services, agents, session handling, logging, metrics, errors, provider connections, and tests
- Frontend HTML, CSS, JavaScript, current navigation/settings/live voice behavior
- Supplied structured-instruction accordion screenshot
- Existing PRD documents 00–10

Exact inspection evidence and file mapping: [00-current-state-audit.md](./00-current-state-audit.md) and [14-research-traceability.md](./14-research-traceability.md).

## Tooling status

- **Implementation plan:** [../implementation/README.md](../implementation/README.md) — 5-phase engineering delivery.
- **Architecture pack:** [../architecture/README.md](../architecture/README.md).
- **Skills & MCPs:** [../implementation/SKILLS-AND-MCP-GUIDE.md](../implementation/SKILLS-AND-MCP-GUIDE.md).
- **Implementation skills (PRD):** [16-mvp-implementation-skills.md](./16-mvp-implementation-skills.md).
- **Architecture ownership:** [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) — read before coding.
- **Context7:** use doc 16 §2 when available; otherwise official provider docs via WebFetch.
- **Railway MCP:** authenticate for Phase 5 deploy (`plugin-railway-railway`); see SKILLS-AND-MCP-GUIDE.
- **Firebase MCP:** not required for MVP (Railway is normative per `19`).
- Ponytail was not installed. Use `web-mvp-design` and `ui-design` for console MVP work.

## Critical decisions already resolved

See [17-product-decisions.md](./17-product-decisions.md) for full list. Highlights:

- **Generic platform** — any business; Platform Brain developer-only.
- **Same LLM** structured `spoken_response` + `memory_update` per turn (CD-016).
- **Compact memory** default: `facts`, `preferences`, `important_context`, `summary`; no cross-call memory in MVP.
- **Multi-tenant** + unlimited agents + Dev/Staging/Production environments.
- **Dev Portal auth P0** (env credentials); Business customer login P2.
- **Deployment:** **Next.js only** on Railway **web** service + Railway **api/worker/data** (optional Vercel for web later) — [19](./19-frontend-backend-nextjs-railway.md).
- **Outbound campaigns in MVP**; CRM and RAG out of MVP.
- **Benchmarks disabled** until owner configures.
- **DeepSeek Flash** in MVP for brain; Sarvam STT/TTS default for Telugu; provider fallback chain.
- **Disposition taxonomy** locked (`new_lead`, `qualified`, `converted`, …).

## Approval checklist

- [ ] Master scope and non-goals approved
- [ ] Architecture ownership map approved ([15](./15-architecture-ownership-and-singularity.md))
- [ ] Platform Brain vs Business Brain ownership approved
- [ ] Structured business section taxonomy approved
- [ ] Same-LLM structured memory + projection design approved (CD-016; not separate extraction on hot path)
- [ ] Disposition taxonomy/rubric approved
- [ ] Tier/promotion governance approved
- [ ] Plivo inbound/outbound launch scope decided
- [ ] Tenant roles and production persistence direction approved
- [ ] Recording/retention jurisdictions identified
- [ ] Railway web+api deployment + Next.js-only frontend approved ([19](./19-frontend-backend-nextjs-railway.md))
- [ ] SEO and Core Web Vitals targets accepted

Implementation begins only after required approvals and affected open questions are resolved.
