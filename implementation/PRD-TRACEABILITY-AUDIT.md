# PRD Traceability Audit — Implementation & Architecture Plans

**Audit date:** 25 August 2026 (v2 — full PRD ↔ implementation ↔ architecture alignment pass)  
**Audited against:** `prd/00`–`prd/19`, `prd/17-product-decisions.md`, `ARCHITECTURE.md` (current build)

This document records gaps found when cross-checking the implementation plan and architecture pack against the PRD. Items marked **Fixed** were addressed in the same audit pass.

---

## 1. Executive summary

| Area | Status before audit | Action taken |
|------|---------------------|--------------|
| Core 5-phase sequencing | ✅ Aligned with `prd/08` MVP focus | No change |
| A/B/C memory + CD-016 same-LLM | ✅ Correct | Clarified `memory_extraction.py` as fallback only |
| Module ownership | ✅ Aligned with `prd/15` | Added `language_resolver` preservation |
| API path coverage | ⚠️ Partial | Canonical paths from `prd/13` added to phases |
| v2 UI sitemap (`prd/11`) | ⚠️ Incomplete in Phase 5 | Full nav + agent workspace sub-routes added |
| Benchmarks | ⚠️ Under-specified | Shell UI + stub APIs + `ENABLE_BENCHMARKS=false` |
| Promotion workflow | ⚠️ Missing | Added to Phase 5 + architecture doc |
| Observability / SLOs | ⚠️ Thin | New `architecture/03-observability-and-slos.md` |
| Security / RBAC | ⚠️ Thin | New `architecture/04-security-rbac-and-promotion.md` |
| Campaign entities | ⚠️ Missing `campaign_run` | Added to entities + Phase 5 |
| Gemini provider | ⚠️ Contradicted `prd/17` §13 | Moved to post-MVP backlog |
| Skills/MCP alignment | ⚠️ P0–P10 vs 5-phase | **Fixed** — `SKILLS-AND-MCP-GUIDE.md`, `prd/16` §3 updated |
| PRD `06` contradictions | SQLite, memory_extraction diagram | **Fixed** in `prd/06` (CD-016, CD-021) |

---

## 2. Master PRD (`01`) requirement mapping

| Master requirement | Phase | Architecture doc | Notes |
|--------------------|-------|------------------|-------|
| G-01 Provider independence | 1 | `integrations/provider-platform.md` | Adapter ABCs |
| G-02 Realtime quality preserved | All | `data-flows/live-voice-turn.md` | Cache, barge-in, WS |
| G-03 Reproducible configuration | 2, 3 | `data-models/brain-compilation.md` | Version lock at call/start |
| G-04 Complete call intelligence | 3, 4 | `data-models/memory-ledger-outcome.md` | A + outcome |
| G-05 Business brain sections | 2, 5 | `data-models/brain-compilation.md` | 8 sections + custom |
| G-06 Operational visibility | 4, 5 | `03-observability-and-slos.md` | Per-call trace |
| G-07 SEO / CWV | 5 | `integrations/nextjs-frontend-split.md` | Marketing only |
| Three tiers LOW/MED/PREMIUM | 1, 5 | `provider-platform.md` | Not pre-defined combos |
| Benchmark system | 5 shell, post-MVP runs | `03-observability` §5 | Disabled until configured |
| Plivo PSTN | 5 | `integrations/plivo-and-campaigns.md` | Inbound + outbound |
| Campaigns in MVP | 5 | `plivo-and-campaigns.md` | CD-018 |
| Promotion / environments | 5 | `04-security-rbac-and-promotion.md` | Dev→staging→prod |
| Tools & Actions / RAG / CRM | — | — | **Out of MVP** — stub nav only |
| WCAG 2.2 AA | 5 | `nextjs-frontend-split.md` | Added acceptance criteria |

---

## 3. Gaps fixed in this audit

### 3.1 Implementation plan

| Gap | Fix location |
|-----|--------------|
| Missing Overview, Analytics, Benchmarks, Providers, Integrations, Settings nav | `phase-05` §4.2 expanded |
| Agent workspace sub-routes (Memory Schema, Channels, Versions) | `phase-05` §4.2, `phase-02` §5.5 |
| Dev Portal CSRF, session cookies, env creds | `phase-05` §6.1, `04-security-rbac` |
| Extensible RBAC / custom roles | `phase-05` §6.2, `04-security-rbac` |
| `/api/dev/*` promotion APIs | `phase-05` §6.3, `04-security-rbac` |
| Benchmark stub APIs (`ENABLE_BENCHMARKS=false`) | `phase-05` §6.5, `phase-01` stub |
| Semantic validation on business brain | `phase-02` §5.8 |
| `GET /api/call/{id}/trace`, per-call metrics | `phase-03`, `phase-04`, `03-observability` |
| Canonical memory API paths (`memory-events`, `memory/projection`) | `phase-04`, `memory-ledger-outcome` |
| `call/start` `direction` for campaigns | `phase-03`, `call-lifecycle` |
| `campaign_run` entity | `phase-05`, `entities-and-persistence` |
| Plivo webhooks: stream-status, signature validation | `phase-05`, `plivo-and-campaigns` |
| `language_resolver.py` preservation | `phase-01`, `02-module-ownership` |
| Registry `pricing_metadata`, `FX_RATE_INR` | `phase-01`, `provider-platform` |
| Manual memory correction audit events | `phase-04`, `memory-ledger-outcome` |
| Production post-call on Worker (not in-process) | `phase-04`, `phase-05`, `post-call-pipeline` |
| Skills per phase | `implementation/README.md` |
| PRD Phase 6–9 explicit backlog | `implementation/README.md` |

### 3.3 PRD documents updated (this pass)

| PRD file | Fix |
|----------|-----|
| `prd/06` | PostgreSQL not SQLite; CD-016 live-turn diagram; `memory_extraction` fallback only; Gemini post-MVP |
| `prd/08` | Links to 5-phase implementation pack |
| `prd/11` | Environment promotion in MVP (not "recommended enhancement") |
| `prd/13` | Canonical `memory-events` path (CD-021) |
| `prd/14` | CD-007 PostgreSQL; CD-021 memory API alias |
| `prd/16` | 5-phase skill map; MCP section; deprecated P0–P10 |
| `prd/README` | Authority ladder + implementation/architecture links |
| `prd/01` | SQLite wording fixed |

### 3.2 Architecture pack + skills guide

| Gap | Fix location |
|-----|--------------|
| No observability / metrics doc | `03-observability-and-slos.md` |
| No security / RBAC / promotion doc | `04-security-rbac-and-promotion.md` |
| No skills/MCP per-phase guide | `SKILLS-AND-MCP-GUIDE.md` |
| Incomplete Plivo API list | `plivo-and-campaigns.md` |
| Missing trace span model | `03-observability-and-slos.md` |
| Error/fallback policy summary | `04-security-rbac` §6 |

---

## 4. Intentional deferrals (not gaps)

These PRD items are **correctly out of MVP** per `prd/17` and master PRD §4:

| Item | Deferred to | Reason |
|------|-------------|--------|
| Customer Business Console auth (P2) | Post-MVP | Dev Portal auth P0 |
| Knowledge base / RAG | Post-MVP | `prd/17` §1 |
| CRM webhook execution | Post-MVP | CD-019; UI fields exist as stub |
| Schema-defined tools/actions | Post-MVP | Master §4; nav stub only |
| Benchmark auto-runs | Post-MVP (Phase 6 PRD 08) | CD-020; UI shell in MVP |
| Gemini LLM adapter | Post-MVP | `prd/17` §13 |
| Cross-call memory | Post-MVP | `prd/17` §5 |
| Quality review queue | Enhancement | `prd/11` §13 |
| Fleet analytics v2 | Post-MVP | Basic analytics in Phase 5 |

---

## 5. Known PRD internal inconsistencies (resolved in our docs)

| Conflict | Resolution used |
|----------|-----------------|
| `prd/06` diagram shows async `memory_extraction` on hot path | **CD-016 wins:** same-LLM structured turn; extraction module is fallback only (`prd/15` §5, `14` CD-016) |
| `prd/06` SQLite dev vs `prd/13` PostgreSQL dev | **PostgreSQL** for all environments (`prd/13` §9, `prd/17` §11) |
| `memory-events` vs `memory/events` in `prd/13` | Canonical: `GET /api/call/{id}/memory-events` (CD-021); optional alias `memory/events` |
| `prd/11` §3 environment promotion "RECOMMENDED ENHANCEMENT" vs `prd/17` full workflow | **Product decision wins:** promotion in MVP via Dev Portal (`prd/17` §9–10) |
| `prd/16` P0–P10 vs implementation Phase 1–5 | **Implementation Phase 1–5** is canonical; P0–P10 deprecated (`prd/16` §3) |

---

## 6. Acceptance checklist cross-walk

From `prd/README.md` approval checklist → implementation coverage:

| Checklist item | Covered in |
|----------------|------------|
| Master scope / non-goals | This audit §4 |
| Architecture ownership map | `architecture/02-module-ownership.md` |
| Platform vs Business brain | Phase 2, `brain-compilation.md` |
| Structured business taxonomy | Phase 2 §5.2 |
| Async memory / projection | Phase 4 (same-LLM primary, async apply) |
| Disposition taxonomy | Phase 4, `memory-ledger-outcome.md` |
| Tier/promotion governance | Phase 5, `04-security-rbac-and-promotion.md` |
| Plivo scope | Phase 5, `plivo-and-campaigns.md` |
| Tenant roles / persistence | Phase 1, 5, `entities-and-persistence.md` |
| Recording/retention | Phase 5 §6.6, `database-and-storage.md` |
| Railway + Next.js | Phase 5, `railway-deployment.md` |
| SEO / CWV | Phase 5, `nextjs-frontend-split.md` |

---

## 7. Post-MVP roadmap (PRD `08` phases 6–9)

Not in the 5-phase MVP plan; track separately after launch:

| PRD phase | Scope |
|-----------|-------|
| Phase 6 | Benchmark sessions, combination matrix, promotion with evidence, rollback |
| Phase 7 | Cartesia/Gemini production adapters after benchmark pass |
| Phase 8 | Plivo inbound benchmark dimension (outbound already in Phase 5) |
| Phase 9 | Full multi-tenant hardening, load tests, legal hold |

See [implementation/README.md](./README.md) §Post-MVP.
