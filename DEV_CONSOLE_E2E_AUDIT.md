# Dev Console Deep Audit — E2E Testing, Versions, and Fine-Tuning

**Date:** 2026-08-26  
**Scope:** Developer portal (`/dev`), business console developer surfaces (`/app`), backend APIs, and PRD alignment  
**Auditor basis:** Code inspection, PRD cross-reference (`prd/01`, `05`, `07`, `11`, `13`, `15`, `17`), Playwright E2E (`web/e2e/dev-test-studio.spec.ts`), and implementation artifacts from Phases 8–11 (`VOICE_AGENT_PRESETS.md` §54)

---

## Executive summary

The platform delivers a **credible live voice engineering loop**: configure stacks, run real browser and PSTN sessions, inspect archived calls with pipeline traces, and promote tier assignments across environments. That is the core of day-to-day voice agent development and is largely working.

What is **not** yet at PRD target is the **evidence-driven release loop**: reproducible benchmark runs with real metrics, side-by-side combination/version comparison, and the full combination promotion state machine (`draft → benchmarked → reviewed → approved → active`). Business brain **version history exists in APIs** but the console exposes it as raw JSON with no diff, test-on-version, or promote-from-benchmark UX.

| Overall rating | **6.8 / 10** |
|----------------|--------------|
| Best for | Live iteration, per-call debugging, stack/tier tuning |
| Weak for | Version A/B, automated eval, promotion governance |
| PRD posture | Strong on call-centric observability; partial on benchmarks and release workflow |

---

## Rating summary

| Area | Rating | PRD alignment | Trend |
|------|--------|---------------|-------|
| Live E2E voice testing | **8.0 / 10** | High | ↑ (Test Studio lab) |
| Stack / tier tuning | **7.0 / 10** | Medium–high | Stable |
| Brain authoring & compile | **7.0 / 10** | Medium | Stable |
| Per-call debugging | **8.0 / 10** | High | ↑ (investigation console) |
| Multi-version comparison | **4.0 / 10** | Low | — |
| Automated benchmarks | **5.0 / 10** | Low (UI up, runner missing) | ↑ (Phase 11 UI) |
| Promotion & release | **6.0 / 10** | Medium | Stable |
| Fleet analytics | **7.0 / 10** | Medium–high | ↑ (Analytics workspace) |

---

## Audit methodology

1. **Normative PRD mapping** — Requirements from `prd/11-ui-information-architecture.md` (IA, journeys, acceptance criteria), `prd/05-ux-console-and-dashboards.md` (component patterns), `prd/07-testing-metrics-observability.md` (metrics and benchmarks), `prd/13-api-data-security-contracts.md` (API contracts), `prd/01-master-prd.md` (version locking, promotion).
2. **Implementation trace** — Next.js routes under `web/app/dev` and `web/app/app`, shared components, FastAPI routes under `server/routes`.
3. **Honesty rule** — UI shells without execution backends are scored separately from “workflow complete.” Placeholder metrics are not treated as benchmark success.
4. **E2E signal** — `web/e2e/dev-test-studio.spec.ts` covers catalog safety, call lifecycle API, and Test Studio page load (no `.map` crash).

---

## 1. Live E2E voice testing — **8.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §9 | Browser + PSTN Test Studio; lock config at start; transcript, state, memory projection, latency, errors |
| `prd/05` §3 | Live transcript, barge-in, per-turn latency, call state indicator |
| `prd/11` §5 journey | Configure → test agent before promote |

### Implemented (evidence)

| Capability | Location | Status |
|------------|----------|--------|
| Laboratory layout (config \| live \| diagnostics \| waterfall) | `web/components/test-studio/AgentTestStudio.tsx` | ✅ |
| Browser mic → STT → brain → TTS pipeline | `web/components/live/LiveVoiceSession.tsx` | ✅ |
| Barge-in, interrupted turns, trace events | `LiveVoiceSession.tsx` (`BargeState`, `interrupted` bubbles) | ✅ |
| PSTN / Plivo test panel (dev only) | `web/components/dev/test-studio/PstnTestPanel.tsx` | ✅ |
| Post-call review inline in Test Studio | `AgentTestStudio.tsx` → `CallDetailView` | ✅ |
| Dev global Test Studio | `/dev/test-studio`, `/dev/agents/[id]/test` | ✅ |
| Business Test Studio | `/app/test-studio`, `/app/agents/[id]/test` | ✅ |
| Call start/end lifecycle API | `POST /api/call/start`, `POST /api/call/end` | ✅ |
| E2E Playwright smoke | `web/e2e/dev-test-studio.spec.ts` | ✅ |

### Gaps

| Gap | PRD | Severity |
|-----|-----|----------|
| **No draft vs active brain version picker** in Test Studio | `prd/11` §9 “Select draft/active agent version” | High |
| **No per-turn STT/LLM/TTS ms on transcript hover** in lab UI (trace exists but not full PRD hover UX) | `prd/05` §3.3 | Medium |
| **FRONTEND mode stack override in Test Studio** — tier/language only; not full STT/LLM/TTS matrix in lab rack | `prd/05` §3.2, `prd/11` §15 | Medium |
| **“Save as benchmark run”** after session not wired | `prd/05` §3.2 | Medium |
| Mic-driven testing only — no scripted audio fixture injection in UI | `prd/05` §5.1 | Low (runner scope) |

### Score rationale

Strong real-time path and dev/business parity on Test Studio. Missing version selection and in-studio combination matrix keeps this below 9. The 8 reflects production-grade live testing without full PRD Test Studio completeness.

---

## 2. Stack / tier tuning — **7.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §15 | ENV vs FRONTEND mode; tier bundles vs full matrix |
| `prd/05` §5.1 | Combination matrix, run live test, compare |
| `prd/13` | Stable combination IDs over provider/model versions |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Stack & tiers workbench | `web/components/dev/StackTierWorkbench.tsx`, `/dev/stack` | ✅ |
| Per-tier STT/LLM/TTS assignment + save | `PUT /api/dev/stack/tiers/{tier}` | ✅ |
| Combination resolution test | `POST /api/dev/stack/test` | ✅ |
| Config mode display (`env` / `frontend`) | `server/config/env.py`, `StackTierWorkbench` | ✅ |
| Provider catalog from dev overlay | `/api/dev/stack/catalog`, Environment panel | ✅ |
| Runtime tuning panel | `web/components/dev/DevRuntimePanel.tsx`, `/dev/runtime` | ✅ |
| Tier resolution at call start | `server/providers/session_stack.py` | ✅ |

### Gaps

| Gap | Severity |
|-----|----------|
| **No side-by-side combination compare** in stack UI | High |
| Business console **voice page** shows tiers read-only in env mode — correct per PRD but limits operator-adjacent testing | Expected |
| Combination ID visibility in Test Studio / promotion flow is weak | Medium |
| No “run live test with locked selection” deep link from stack workbench to Test Studio with query params | Medium |

### Score rationale

Engineers can edit tiers, validate resolution, and test combinations in dev. Missing comparison UX and Test Studio integration prevents a higher score.

---

## 3. Brain authoring & compile — **7.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §6 | Sectioned business brain, raw vs optimized, publish, version immutability |
| `prd/11` §7–8 | Platform brain editor, compiled preview, precedence layers |
| `prd/12` | Deterministic compilation, version locking on calls |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Business brain editor (8 sections) | `web/components/agents/BusinessBrainEditor.tsx` | ✅ |
| Draft save, validate, optimize, **publish** | `server/routes/agents_business_brain.py` | ✅ |
| Dual-panel raw vs optimized | `web/components/agents/brain/BrainDualPanel.tsx` | ✅ |
| Dev agent brain workspace | `web/components/dev/DevAgentBrainClient.tsx` | ✅ |
| Platform brain editor + activate + regression scenarios UI | `web/components/dev/PlatformBrainEditor.tsx` | ✅ |
| Compiled preview (layers, precedence, token estimate) | `web/components/dev/DevCompiledPreview.tsx`, `/dev/compiled` | ✅ |
| Platform brain at `/dev/platform-brain` | Dev portal nav | ✅ |

### Gaps

| Gap | PRD | Severity |
|-----|-----|----------|
| **Blocking conflict / warning UX** for precedence (`prd/11` §8) — partial in platform editor, not full business journey | §8 | Medium |
| Customer console lacks platform brain (correct) but **compiled preview** not mirrored in business agent workspace | §8 | Low |
| Optimizer reject-and-keep-previous flow not prominently surfaced | §6 edge cases | Medium |
| Publish locks version for calls — **backend yes**; UI shows badge but not deployment impact summary | §5 journey | Medium |

### Score rationale

Authoring and compilation are materially implemented for both business and platform brains in dev. Version **governance UX** (diff, rollback in agent workspace, deployment impact) is thinner than PRD screen contracts.

---

## 4. Per-call debugging — **8.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §10 | Call list filters, detail: outcome, audio, transcript, trace, memory, metadata |
| `prd/05` §4 | Disposition badges, latency waterfall, working memory |
| `prd/11` §11 | Per-call unified timeline separate from fleet analytics |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Calls workspace (filter + list + inspector) | `web/components/calls/CallsWorkspace.tsx` | ✅ |
| Full investigation console | `web/components/calls/CallInvestigationConsole.tsx` | ✅ |
| Outcome, audio, transcript timeline | `web/components/calls/detail/*` | ✅ |
| Unified pipeline timeline | `CallUnifiedTimeline.tsx`, `buildUnifiedTimeline` | ✅ |
| Memory tree + memory events | `CallMemoryStatePanel.tsx` | ✅ |
| Trace + latency waterfall | `CallTracePanel.tsx` | ✅ |
| Metadata / stack snapshot | `CallMetadataPanel.tsx` | ✅ |
| List enrichment (summary, customer, disposition) | `server/routes/calls.py` `_enrich_call_list_item` | ✅ |
| Dedicated call detail route | `/app/calls/[id]` | ✅ |

### Gaps

| Gap | Severity |
|-----|----------|
| Filters: **tier, combination, agent, environment** not all exposed in `CallsFilterBar` | Medium |
| Transcript rows: **per-component latency columns** not always shown on each line | Medium |
| Memory panel: proposed vs accepted/rejected ops — partial depending on archive richness | Low |
| Dev portal has no dedicated Calls nav entry (business console primary) | Low |

### Score rationale

This is one of the strongest areas relative to PRD. Investigation console matches the “measure the pipeline” principle. Filter completeness and row-level latency annotations are the main gaps.

---

## 5. Multi-version comparison — **4.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §6–7 | Compare versions, validate, test, approve, activate |
| `prd/11` §5 journey | Compare models / versions before promote |
| `prd/05` §5.3 | Side-by-side two runs, winner per metric |
| `prd/01` | Immutable brain versions locked on calls |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Version list API | `GET /api/agents/{id}/business-brain/versions` | ✅ |
| Versions page | `web/app/dev/(portal)/agents/[id]/versions/page.tsx` | ⚠️ JSON only |
| Business versions page | `web/app/app/(console)/agents/[id]/versions/page.tsx` | ⚠️ JSON only |
| Platform brain version list + compare ID picker | `PlatformBrainEditor.tsx` | ⚠️ Partial |
| Active version badge on brain editor | `BusinessBrainEditor.tsx` | ✅ |
| Calls record locked versions in `meta.json` | `prd/04` archive layout | ✅ (backend) |

### Gaps (critical)

| Gap | Severity |
|-----|----------|
| **No side-by-side diff** (raw sections, optimized prompt, compiled output) | Critical |
| **No “Test this version”** — Test Studio always uses current draft/active resolution | Critical |
| **No A/B**: two brain versions or two stacks in one session | Critical |
| **No activate/rollback** for business brain versions in UI (publish only creates new) | High |
| Benchmark results cannot be tied to a specific brain version in UI | High |

### Score rationale

Version **storage and locking** exist at the data layer; the **developer workflow** for comparing and choosing versions is largely absent in UI. Platform brain editor has more version tooling than business brain — asymmetry vs PRD.

---

## 6. Automated benchmarks — **5.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §12 | Full benchmark creation workflow, progress states, winners per metric, export |
| `prd/07` §1–2 | Component + E2E latency, task quality, weighted scores |
| `prd/13` §5 | Benchmark session CRUD, start/cancel/results |
| `prd/17` §1 | Disabled by default until `ENABLE_BENCHMARKS=true` |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Benchmark laboratory UI | `web/components/benchmarks/BenchmarkLaboratory.tsx` | ✅ |
| Workflow strip (Create → … → Promote) | `BenchmarkLaboratory.tsx` | ✅ |
| Status endpoint (always on) | `GET /api/benchmarks/status` | ✅ |
| Scenario library (4 built-in) | `server/benchmark/session_store.py` | ✅ |
| Session CRUD + start/cancel/results | `server/routes/benchmarks.py` | ✅ (gated) |
| Honest placeholder results | `session_store.py` `runner_note`, `metrics: null` | ✅ |
| Winners-per-metric skeleton | `_compute_winners` in `benchmarks.py` | ⚠️ Empty until metrics |
| Disabled-by-default policy | `server/config/env.py`, tests | ✅ |
| Legacy script tests | `server/tests/benchmark_voice_cache.py` | ✅ (cache, not UI runner) |

### Not implemented

| Gap | PRD | Severity |
|-----|-----|----------|
| **Benchmark execution worker** — no scripted scenario runs | `prd/07`, `prd/11` §12 | Critical |
| Progress states: queued, running, partially complete | `prd/11` §12 | High |
| Real metrics: `stt_final_ms`, `llm_ttft_ms`, `tts_first_audio_ms`, `e2e_ms`, rubric scores | `prd/07` §2 | Critical |
| Export JSON/CSV manifests | `prd/11` §12 | High |
| Channel selection in benchmark session | `prd/11` §12 step 2 | Medium |
| PostgreSQL / durable `benchmark_runs` store | `session_store.py` comment | Medium |

### Score rationale

Phase 11 delivered **workflow UI and API contracts** with transparent placeholders — better than fake scores. Without a runner, developers cannot use benchmarks for combination decisions. Score 5 = “infrastructure + UX shell,” not “eval system.”

---

## 7. Promotion & release — **6.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §13 | State machine: draft → benchmarked → reviewed → approved → scheduled → active → … |
| `prd/11` §3 | Environment promotion dev → staging → production |
| `prd/08` | Tier assignments linked to benchmark evidence |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Tier promotion to staging/production | `web/components/dev/PromotionPanel.tsx`, `POST /api/dev/promote` | ✅ |
| Rollback from last promotion | Promotion panel + `POST /api/promotions/{id}/rollback` | ✅ |
| Audit log display | Promotion panel | ✅ |
| Benchmark → promote link | `BenchmarkLaboratory` → `/dev/promotion` | ⚠️ Manual |
| Platform brain activate with reason | `PlatformBrainEditor.tsx` | ✅ |

### Gaps

| Gap | Severity |
|-----|----------|
| **No combination promotion state machine** in data or UI | Critical |
| Promotion does not require **benchmark session IDs** as evidence | High |
| **Brain version promotion** (business) separate from tier stack promotion | High |
| No scheduled effective date / reviewer/approver fields | Medium |
| `prd/11` §19 RECOMMENDED — config diff/rollback — not implemented | Medium |

### Score rationale

Environment tier promotion works for daily ops. PRD’s **governed release** (benchmark evidence → reviewed combination → active) is not implemented; promotion is effectively “copy tier rows.”

---

## 8. Fleet analytics — **7.0 / 10**

### PRD requirements

| Source | Requirement |
|--------|-------------|
| `prd/11` §11 | Separate aggregate analytics from per-call debugging |
| `prd/05` §Metrics | Fleet P50/P95, disposition trends, combination comparison |
| `prd/07` | Fleet metrics, benchmark baselines |

### Implemented

| Capability | Location | Status |
|------------|----------|--------|
| Analytics workspace (8 modules) | `web/components/analytics/AnalyticsWorkspace.tsx` | ✅ |
| Fleet endpoint | `GET /api/analytics/fleet` in `server/routes/metrics.py` | ✅ |
| Client fallback from `/api/calls` | `aggregateFleetFromCalls` in `analytics-utils.ts` | ✅ |
| Cross-link to Calls (aggregate vs per-call) | Analytics workspace copy + links | ✅ |
| In-memory `/api/metrics` snapshot | `server` metrics route | ✅ |
| Provider + tier combination panels | Analytics workspace | ✅ |

### Gaps

| Gap | Severity |
|-----|----------|
| Fleet endpoint may 404 if API not restarted — fallback masks gap | Medium |
| **P50/P95** not always from durable trace store at fleet scale | Medium |
| Benchmark baseline comparison (“new combo vs baseline”) | `prd/07` §baselines | High |
| Memory health / extraction metrics thin vs PRD | Medium |
| Dev portal has no Analytics nav (business `/app/analytics`) | Low |

### Score rationale

Correct **separation of concerns** vs call investigation. Aggregate instrumentation is useful but partly derived from call list heuristics rather than a dedicated analytics warehouse.

---

## Cross-cutting findings

### Strengths

1. **Call-centric observability** — Archive layout, investigation console, and Test Studio waterfall align with 2026 voice observability practice (`prd/10`).
2. **Dev portal depth** — Environment, stack, runtime, platform brain, compiled preview, promotion, test studio form a real control plane (`DevNav.tsx`).
3. **Honest benchmarks** — Placeholder metrics with `runner_note` avoid false confidence (`session_store.py`).
4. **Mode awareness** — `VOICE_AGENT_CONFIG_MODE` env vs frontend is implemented server-side, not UI-only.
5. **E2E safety** — Playwright guards against catalog `.map` crashes and validates call lifecycle.

### Weaknesses

1. **Two half-loops** — Live testing loop is strong; **evidence loop** (benchmark → compare → promote) is incomplete.
2. **Version UX debt** — APIs and archives support versions; console treats versions as JSON dumps for business brain.
3. **Business vs dev split** — Correct RBAC direction, but business console cannot do stack tuning (by design) while dev portal lacks calls/analytics shortcuts.
4. **Durable stores** — Benchmark sessions in-memory; metrics in-memory (`prd/07` current vs target note).

### PRD traceability snapshot

| PRD journey step | Status |
|------------------|--------|
| Configure Business Brain | ✅ |
| Choose Voice Tier | ✅ (dev + business read) |
| Test Agent | ✅ browser; ✅ PSTN in dev |
| Compare Models | ⚠️ stack test only; ❌ A/B UI |
| Inspect Calls | ✅ |
| Analyze Performance | ✅ aggregate |
| Promote Configuration | ⚠️ tiers only; ❌ full combination SM |

---

## Path to **8.5 / 10**

Prioritized by impact on developer E2E fine-tuning:

| Priority | Initiative | Expected rating lift |
|----------|------------|---------------------|
| P0 | **Benchmark runner worker** — execute scenarios, populate trace-backed metrics, real progress states | Benchmarks → 7.5; Overall +0.6 |
| P0 | **Brain version diff + “Test this version”** in Test Studio | Multi-version → 7; Overall +0.5 |
| P1 | **A/B Test Studio mode** — two stacks or two versions, split transcript/waterfall | Live E2E → 8.5; Multi-version → 8 |
| P1 | **Combination promotion state machine** with benchmark session linkage | Promotion → 8 |
| P2 | Benchmark export (JSON/CSV); baseline comparison in Analytics | Benchmarks + Analytics +0.3 |
| P2 | Calls filters (tier, combination, agent); transcript row latencies | Per-call → 8.5 |
| P3 | “Save session as benchmark” from Test Studio | Live E2E → 8.5 |

**Estimated overall after P0–P1:** ~8.3–8.6 / 10.

---

## Operational notes

- Set `ENABLE_BENCHMARKS=true` in Dev → Environment and **restart uvicorn** so session routes and `/api/benchmarks/status` reflect enabled state.
- Web dev: `localhost:3000`; API: `localhost:8000`.
- Dev login: `/dev/login` — `dev` / `devpass`.
- Business E2E login: `/app/login` — `e2e` / `e2e-test`.

---

## Key file reference

| Area | Primary paths |
|------|----------------|
| Test Studio | `web/components/test-studio/`, `web/components/live/LiveVoiceSession.tsx` |
| Dev portal shell | `web/components/dev/DevShell.tsx`, `DevNav.tsx` |
| Stack / tiers | `web/components/dev/StackTierWorkbench.tsx`, `server/routes/dev_stack.py` |
| Business brain | `web/components/agents/BusinessBrainEditor.tsx`, `server/routes/agents_business_brain.py` |
| Platform brain | `web/components/dev/PlatformBrainEditor.tsx` |
| Calls | `web/components/calls/`, `server/routes/calls.py` |
| Analytics | `web/components/analytics/AnalyticsWorkspace.tsx`, `server/routes/metrics.py` |
| Benchmarks | `web/components/benchmarks/BenchmarkLaboratory.tsx`, `server/routes/benchmarks.py`, `server/benchmark/session_store.py` |
| Promotion | `web/components/dev/PromotionPanel.tsx` |
| E2E tests | `web/e2e/dev-test-studio.spec.ts` |
| PRD (normative IA) | `prd/11-ui-information-architecture.md` |
| PRD (metrics/benchmarks) | `prd/07-testing-metrics-observability.md` |
| PRD (API contracts) | `prd/13-api-data-security-contracts.md` |

---

## Appendix — Rating rubric used

| Score | Meaning |
|-------|---------|
| 9–10 | PRD acceptance criteria met; minor polish only |
| 7–8 | Core workflow works; clear gaps documented |
| 5–6 | UI or API present; execution or governance incomplete |
| 3–4 | Data layer only or raw dumps; workflow blocked |
| 1–2 | Not started or misleading (fake metrics) |

---

*This audit reflects repository state as of 2026-08-26. Re-run after benchmark runner, version comparison UX, or promotion state machine land.*
