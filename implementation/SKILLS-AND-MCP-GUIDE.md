# Skills, MCPs & Testing Guide — Per Phase

**Version:** 1.0  
**Date:** 25 August 2026  
**Normative PRD:** [`prd/16-mvp-implementation-skills.md`](../prd/16-mvp-implementation-skills.md)

This document aligns the **5-phase implementation plan** with Cursor skills, available MCPs, and verification steps. Use it at the start of every implementation session.

---

## 1. Document authority (no contradictions)

When documents disagree, use this order:

| Priority | Document |
|----------|----------|
| 1 | `prd/01-master-prd.md` |
| 2 | `prd/15-architecture-ownership-and-singularity.md` |
| 3 | `prd/17-product-decisions.md` |
| 4 | `prd/14-research-traceability.md` (CD-001+) |
| 5 | [`architecture/`](../architecture/) + [`implementation/`](./) (engineering packs) |
| 6 | Topic PRDs (`03`, `04`, `12`, `13`, …) |
| 7 | Historical (`10-prd-reaudit.md`) |

**Resolved conflicts (do not re-debate):** see [PRD-TRACEABILITY-AUDIT.md](./PRD-TRACEABILITY-AUDIT.md) §5.

---

## 2. Phase mapping (PRD `08` ↔ implementation `01`–`05`)

| Implementation phase | PRD `08` phases | Primary deliverable |
|---------------------|-----------------|---------------------|
| **Phase 1** | 0 + 1 | Registry, tiers, PostgreSQL, baselines |
| **Phase 2** | 2 | Brains, agents, compiled L2 |
| **Phase 3** | 3 | Call lifecycle, ledger A, audio |
| **Phase 4** | 4 | Memory B/C, post-call, traces |
| **Phase 5** | 5 + 7 (partial) + 8 + 9 (MVP) | Next.js, Plivo, campaigns, RBAC, deploy |

PRD `08` phases **6–9** (full benchmarks, Gemini prod, load hardening) → post-MVP backlog.

---

## 3. Skills per phase (mandatory)

### Phase 1 — Foundation & Platform

| When | Skill / action |
|------|----------------|
| Before coding | Read `prd/15`, `architecture/02-module-ownership.md` |
| Provider adapters | Context7 or `WebFetch` on Sarvam/OpenAI official docs (`prd/16` §2) |
| DB setup | Local PostgreSQL + Alembic |
| Tests | `pytest` — `test_provider_registry.py`, `test_stack_resolver.py` |
| Pre-merge | `review-bugbot` (optional) |

**Do not use:** `web-mvp-design` (no UI this phase).

### Phase 2 — Brains & Agent Workspace

| When | Skill / action |
|------|----------------|
| Brain compile | Read `prd/12` §1–4, §27 semantic validation |
| Optimizer | Verify OpenAI Structured Outputs via official docs |
| Tests | `pytest` — `test_compiled_brain_service.py`, `test_semantic_validation.py` |
| Cache regression | Extend `test_brain_caching.py` |

### Phase 3 — Call Lifecycle & Persistence

| When | Skill / action |
|------|----------------|
| Orchestration | Read `architecture/data-flows/call-lifecycle.md`, `prd/15` §4.2 |
| Live regression | `pytest` + optional `LIVE_TEST=1` (`test_e2e_latency.py`) |
| Barge-in | `test_live_barge_policy.py` must stay green |
| Tests | `test_call_lifecycle.py`, `test_call_ledger.py` |

### Phase 4 — Memory & Post-Call Intelligence

| When | Skill / action |
|------|----------------|
| Memory spec | Read `prd/12` §17–28, `architecture/data-models/memory-ledger-outcome.md` |
| CD-016 | Same-LLM structured turn — **not** separate extraction call |
| Fallback only | `memory_extraction.py` if parse/SLO fails |
| Tests | Golden disposition fixtures, `test_memory_projection.py`, `test_structured_live_turn.py` |
| Hot path | Assert TTFT not blocked by memory merge |

### Phase 5 — Production UI, Telephony & Launch

| When | Skill / action |
|------|----------------|
| **Start UI** | **`web-mvp-design`** (orchestrator) → read `.better-react-web-ui.md` |
| Design context | **`setup`** skill if `.better-react-web-ui.md` missing/stale |
| Next.js perf | **`vercel-react-best-practices`**, `vercel-composition-patterns` |
| Components | **`shadcn`** if adopting shadcn/ui; **`tailwind-design-system`** |
| New sections | **`add-ui`** for Business Brain accordion (5 variations → pick one) |
| Polish | **`ui-design`**, **`polish`**, **`web-design-guidelines`** (WCAG 2.2 AA) |
| Motion | **`motion-patterns`** only where needed (Test Studio, modals) |
| Deploy | **`use-railway`** skill + Railway MCP (see §4) |
| Plivo | Official Plivo stream docs via `WebFetch`; `prd/09` |
| Pre-production | **`review-security`** (mandatory), `review-bugbot` |
| CI | `autopilot` for PR/CI loops |

**Do not extend:** `client/` SPA — port behavior to `web/` only.

---

## 4. MCP servers (available in Cursor)

| MCP namespace | Use for | Auth | MVP phases |
|---------------|---------|------|------------|
| **`plugin-railway-railway`** | Deploy web/api/worker, Postgres, Redis, env vars, logs | Run `mcp_auth` first | **5** |
| **`plugin-firebase-firebase`** | Not required by PRD | Optional | — |
| **`cursor`** | `CreateGoal` for multi-session tracking (optional) | Native | All |

### Railway MCP — when to use

1. Authenticate: `CallDynamicTool` → `plugin-railway-railway` / `mcp_auth`
2. **Phase 5 deploy:** provision services per `architecture/infrastructure/railway-deployment.md`
3. **Staging E2E:** verify API health, worker logs after campaign test
4. **Not for:** local pytest, unit tests, or provider API calls

### Firebase MCP — do not use for MVP

PRD locks **Railway** for hosting (`prd/17` §11, `prd/19`). Firebase skills/MCP are out of scope unless product explicitly changes hosting.

### Context7 — not currently available

Per `prd/16` §2: before any provider SDK work, verify via **Context7** when available; otherwise **`WebFetch`** on official docs listed in `prd/14` §2.

---

## 5. Testing matrix per phase

| Phase | Automated (required) | Manual / staging | MCP |
|-------|---------------------|------------------|-----|
| 1 | `pytest` full suite + new registry tests | Record baselines to `baselines/phase0_metrics.json` | — |
| 2 | Brain compile, cache, semantic validation tests | Compiled preview API smoke | — |
| 3 | Call lifecycle, ledger, trace stub | `LIVE_TEST=1` live call → files on disk | — |
| 4 | Memory, disposition golden fixtures, cache regression | 20-turn memory retention manual check | — |
| 5 | `pytest` + **Playwright** smoke + RBAC matrix | Staging E2E: browser call + outbound campaign | **Railway** (deploy, logs) |

### Regression gates (every phase)

| Gate | Command / check |
|------|-----------------|
| Full unit suite | `cd server && pytest` |
| Cache | `pytest tests/test_brain_caching.py` |
| Barge-in | `pytest tests/test_live_barge_policy.py` |
| Live latency (optional) | `LIVE_TEST=1 pytest tests/test_e2e_latency.py` |
| Next.js build | `cd web && npm run build` (Phase 5+) |

### Pre-production checklist (Phase 5)

- [ ] `review-security` subagent on full diff
- [ ] `web-design-guidelines` audit on Test Studio + Calls
- [ ] Railway staging: web + api + worker + Postgres + Redis
- [ ] Two-tenant isolation test
- [ ] No secrets in `web` bundle (`npm run build` + grep)

---

## 6. Subagents (Cursor)

| Subagent | When |
|----------|------|
| **`bugbot`** | Pre-merge code review (`review-bugbot` skill) |
| **`security-review`** | Before production deploy (`review-security` skill) |
| **`ci-investigator`** | When GitHub Actions fails on PR |
| **`explore`** | Broad codebase search only — not for known file paths |

---

## 7. Agent session startup (every phase)

1. Read `prd/15-architecture-ownership-and-singularity.md`
2. Read current phase file: `implementation/phase-0N-*.md`
3. Read relevant architecture docs from phase §Architecture references
4. If UI: run **`web-mvp-design`** skill first
5. If providers: official docs via Context7 or WebFetch
6. If deploy: **`use-railway`** skill + Railway MCP auth
7. Before PR: `review-bugbot`; before prod: `review-security`

---

## 8. Quick reference — skills path

All skills live under user Cursor/agents skills directories. Key paths:

| Skill | Path hint |
|-------|-----------|
| `web-mvp-design` | `~/.agents/skills/web-mvp-design/SKILL.md` |
| `use-railway` | Cursor plugins cache `railway/.../use-railway/SKILL.md` |
| `review-security` | `~/.cursor/skills-cursor/review-security/SKILL.md` |
| `review-bugbot` | `~/.cursor/skills-cursor/review-bugbot/SKILL.md` |

Project design context: [`.better-react-web-ui.md`](../.better-react-web-ui.md)  
Cursor rules: [`.cursor/rules/web-mvp-design-skills.mdc`](../.cursor/rules/web-mvp-design-skills.mdc)
