# Phase 1 — Foundation & Platform

**Duration estimate:** 2–3 weeks  
**PRD mapping:** Phase 0 (baselines) + Phase 1 (configuration & provider foundation)  
**Depends on:** PRD approval checklist  
**Blocks:** All subsequent phases

---

## 1. Objective

Establish the **platform substrate** without breaking the existing live Telugu voice loop. By the end of Phase 1, the codebase has a provider registry, tier resolution, PostgreSQL bootstrap, compatibility validation, and recorded regression baselines — while the browser path still works through Sarvam + OpenAI exactly as today.

## 2. Current state

| Area | Today | Gap |
|------|-------|-----|
| Providers | Hard-coded Sarvam STT/TTS, OpenAI LLM in route handlers | No registry, no adapter ABCs |
| Config | `runtime_settings.py` per `session_id`; env vars in `env.py` | No `VOICE_AGENT_CONFIG_MODE`, no tier bundles |
| WS STT model | Hard-coded in `sarvam_ws.py` | Not resolved from env/catalog |
| Persistence | None server-side | No PostgreSQL, no migrations |
| Tests | Strong cache/barge-in coverage | No registry/resolver tests |

**Must preserve:** See [`prd/00-current-state-audit.md`](../prd/00-current-state-audit.md) §4 and §6.

## 3. Target state

```text
server/
├── providers/
│   ├── base.py              # STTAdapter, LLMAdapter, TTSAdapter ABCs
│   ├── registry.py          # Catalog from env ENABLE_* flags
│   ├── resolver.py          # L1 stack resolution (sole authority)
│   ├── sarvam_stt.py        # Wrap existing sarvam_stt_service + sarvam_ws
│   ├── sarvam_tts.py        # Wrap existing sarvam_tts_service
│   └── openai_llm.py        # Wrap openai_brain_service
├── db/
│   ├── connection.py        # async SQLAlchemy / asyncpg
│   ├── migrations/          # Alembic
│   └── models/              # tenants, agents (stub), config_versions
└── config/env.py            # Extended: VOICE_AGENT_CONFIG_MODE, tiers
```

## 4. Deliverables

### 4.1 Regression baselines (Phase 0 embedded)

| Metric | How to capture | Target |
|--------|----------------|--------|
| STT final latency | `/api/metrics` p50/p95 | Record current values |
| Brain TTFT | `test_e2e_latency.py` or manual | Record |
| TTS first chunk | metrics | Record |
| E2E time-to-first-audio | `ARCHITECTURE.md` budget ~0.9–1.6s | No regression >10% |
| Cache hit rate | `prompt_cache_tracker` after turn 2 | ~90% cached input |
| Barge-in | `test_live_barge_policy.py` | 100% pass |

Store baseline snapshot in `benchmark_results.json` or new `baselines/phase0_metrics.json`.

### 4.2 Provider registry

**Owner:** `server/providers/registry.py`

- Load provider catalog at app lifespan from env flags (`ENABLE_SARVAM`, `ENABLE_OPENAI`, …)
- Expose metadata: models, languages, streaming capability, structured output support
- `get_catalog()` powers existing `GET /api/settings/catalog` (canonical path per CD-011)
- Optional alias `GET /api/providers/catalog` → same handler

**Adapter contract** (`base.py`):

```python
class STTAdapter(Protocol):
    async def transcribe_rest(self, audio: bytes, config: STTConfig) -> TranscriptResult: ...
    async def connect_realtime(self, config: STTConfig) -> RealtimeSTTSession: ...

class LLMAdapter(Protocol):
    async def stream_live_turn(self, input_messages, schema: LiveTurnSchema) -> AsyncIterator[StreamEvent]: ...

class TTSAdapter(Protocol):
    async def connect_stream(self, config: TTSConfig) -> RealtimeTTSSession: ...
```

Initial adapters **wrap existing services** — no behavior change, only indirection.

**Preserve:** `server/agent/language_resolver.py` — multilingual response routing (Telugu/Hindi/English path); registry must expose language compatibility, not replace resolver.

### 4.2.1 Registry pricing metadata

Catalog includes safe `pricing_metadata` per model (manually updated rates) for cost estimation in Analytics. Env: `FX_RATE_INR=95.64` per [`prd/07`](../prd/07-testing-metrics-observability.md) §2.4.

### 4.3 Stack resolver (L1)

**Owner:** `server/providers/resolver.py` — **sole L1 authority**

| Input | Source |
|-------|--------|
| `VOICE_AGENT_CONFIG_MODE` | `env` \| `frontend` (default `frontend` for backward compat) |
| `VOICE_AGENT_TIER` | `low` \| `medium` \| `premium` when mode=`env` |
| Client selection | Validated against catalog when mode=`frontend` |
| `stack_override` | Dev-only; rejected in production |

Output: `ResolvedStack` with `combination_id`, STT/LLM/TTS provider+model+config, locked at `call/start` (Phase 3).

Phase 1: resolver callable from settings routes; **not yet wired to live path** until Phase 3 call/start.

### 4.4 Tier bundles

Three tier env bundles (LOW/MEDIUM/PREMIUM) — **assignments not pre-defined** per product decision; developer configures via Dev Portal in Phase 5. Phase 1 ships:

- Env var schema in `.env.example`
- DB table `tier_assignments` (environment, tier, combination_id)
- Validation: tier references only **enabled** providers

### 4.5 PostgreSQL bootstrap

| Table (Phase 1 scope) | Purpose |
|-----------------------|---------|
| `tenants` | Multi-tenant root (single default tenant in dev) |
| `agents` | Stub agent records (`default` auto-created in dev) |
| `tier_assignments` | L1 tier → combination mapping per environment |
| `config_versions` | Audit trail for tier changes |

**Local dev:** `DATABASE_URL=postgresql://...` in `.env`; Alembic migrations in `server/db/migrations/`.

Railway Postgres for staging/production — schema only in Phase 1; full entity model expands in Phases 2–3.

### 4.6 WS factory pattern (prepare, don't switch)

Refactor `routes/ws.py` to resolve adapter via registry **behind feature flag** `USE_PROVIDER_REGISTRY=false` (default off). When enabled in dev:

```python
stack = resolve_stack_for_session(session_id)  # interim until call_id
adapter = registry.get_stt(stack.stt.provider)
upstream = await adapter.connect_realtime(stack.stt.config)
```

Fix known bug: WS STT model should respect `SARVAM_STT_MODEL` env, not hard-coded constant.

### 4.7 Environment extensions

Add to `env.py` / `.env.example`:

```text
VOICE_AGENT_CONFIG_MODE=frontend
VOICE_AGENT_TIER=medium
ENABLE_SARVAM=true
ENABLE_OPENAI=true
ENABLE_DEEPSEEK=false
ENABLE_GEMINI=false
ENABLE_CARTESIA=false
DATABASE_URL=postgresql://localhost:5432/voice_agent
USE_PROVIDER_REGISTRY=false
```

## 5. API changes

| Endpoint | Change |
|----------|--------|
| `GET /api/settings/catalog` | Enriched with registry metadata, enabled flags |
| `GET /api/providers/catalog` | Optional alias (same handler) |
| `GET /api/tiers` | **New** — list tier names + resolved preview |
| `GET /api/tiers/{tier}/resolved` | **New** — safe resolved stack for tier |
| `POST /api/providers/{id}/validate-selection` | **New** — pre-flight compatibility check |
| `GET /api/health` | Add DB connectivity check |

No `call/start` yet — that is Phase 3.

### 4.8 API/WS compatibility tests (Phase 0)

Document and test current contracts as regression fixtures:

- REST: `/api/brain/stream` SSE event shapes, `/api/settings/catalog` response
- WS: `/ws/stt-realtime` binary PCM + JSON events; `/ws/tts` text/chunk protocol
- Must not change client wire protocol during Phase 1 refactor

### 4.9 Benchmark route stub

`server/routes/benchmarks.py` — returns `403` or empty list when `ENABLE_BENCHMARKS=false` (default). Prevents UI integration surprises in Phase 5.

## 6. Files to modify

| File | Action |
|------|--------|
| `server/app.py` | Lifespan: registry init, DB pool |
| `server/config/env.py` | New settings fields |
| `server/routes/settings.py` | Catalog from registry |
| `server/routes/ws.py` | Adapter factory (flag-gated) |
| `server/services/sarvam_ws.py` | Read model from config |
| `.env.example` | Document new vars |

## 7. Tests

| Test file | Coverage |
|-----------|----------|
| `test_provider_registry.py` | Catalog load, ENABLE_* filtering |
| `test_stack_resolver.py` | env vs frontend mode, disabled provider rejection |
| `test_tier_validation.py` | Invalid tier/model combos rejected |
| `test_db_connection.py` | Migration up/down, health check |
| Existing suite | Full regression — no latency/cache regression |

## 8. Exit criteria

- [ ] All existing tests pass; baselines documented
- [ ] Registry returns Sarvam + OpenAI with correct capabilities
- [ ] Resolver rejects disabled/unsupported provider selections with `AppError`
- [ ] PostgreSQL migrations run clean locally
- [ ] `USE_PROVIDER_REGISTRY=true` works in dev without live path regression
- [ ] WS STT model respects env configuration
- [ ] No secrets in catalog responses

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Refactoring WS breaks live path | Feature flag; default off until Phase 3 integration |
| Over-abstracting before call lifecycle | Adapters wrap existing code; no new provider logic |
| PostgreSQL blocks local dev | Docker Compose optional; document install |

## 10. Persistence clarification

Use **PostgreSQL only** — not SQLite (`prd/13` §9 supersedes `prd/06` SQLite mention). Local dev: `createdb voice_agent` + Alembic migrations.

## 11. Out of scope (deferred)

- Cartesia, DeepSeek adapters (Phase 5); Gemini post-MVP per `prd/17` §13
- Brain compilation (Phase 2)
- Call lifecycle (Phase 3)
- Next.js frontend (Phase 5)
- Auth/RBAC enforcement (Phase 5; stub tenant only)

## 12. Skills, MCPs & testing

See [SKILLS-AND-MCP-GUIDE.md](./SKILLS-AND-MCP-GUIDE.md) §Phase 1.

| Item | Detail |
|------|--------|
| Skills | `pytest`; read `prd/15` before coding |
| Docs | Sarvam/OpenAI official docs (Context7 or WebFetch) |
| MCPs | None required |
| Gates | Full pytest suite; record `baselines/phase0_metrics.json` |

## 13. Architecture references

- [architecture/integrations/provider-platform.md](../architecture/integrations/provider-platform.md)
- [architecture/infrastructure/database-and-storage.md](../architecture/infrastructure/database-and-storage.md)
- [prd/03-provider-platform.md](../prd/03-provider-platform.md)
