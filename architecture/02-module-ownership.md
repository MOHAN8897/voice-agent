# Module Ownership & Orchestration

Normative ownership map — prevents duplicate logic and module clashes during implementation.

**PRD authority:** [`prd/15-architecture-ownership-and-singularity.md`](../prd/15-architecture-ownership-and-singularity.md)

---

## 1. Singular orchestrators

Only one module per runtime concern. Routes and WS handlers **delegate** — they do not implement business logic inline.

| Concern | Owner module | Forbidden elsewhere |
|---------|--------------|---------------------|
| Live turn hot path | `call/live_turn_orchestrator.py` | `routes/brain.py`, `routes/ws.py` |
| Call start/end | `call/call_lifecycle_service.py` | `routes/calls.py` internals |
| Post-call analysis | `call/post_call_pipeline.py` | Lifecycle service, brain routes |
| Brain compilation | `brain/compiled_brain_service.py` | `instruction_builder`, routes |
| Business optimization | `brain/business_prompt_optimizer.py` | Live path, per-turn |
| L1 stack resolution | `providers/resolver.py` | WS handlers, settings |
| Live LLM input assembly | `agent/instruction_builder.py` | Any other module |
| Memory mutation | `call/memory_manager.py` | Orchestrator (orchestrator calls manager) |
| Ledger transcript writes | `call/call_ledger.py` | `conversation_manager` |
| Memory projection render | `call/memory_projection.py` | `memory_manager`, `instruction_builder` |

---

## 2. Live turn sequence (owner: `live_turn_orchestrator`)

```text
STT final
  → live_turn_orchestrator.handle_user_turn()
    → call_ledger.append_user_turn()              [A]
    → memory_projection.build()                   [B → C]
    → instruction_builder.build_live_input()      [compiled + C + turns]
    → llm_adapter.stream_structured_turn()        [spoken_response + memory_update]
    → stream spoken_response → client/TTS         [HOT — no await on memory]
    → memory_manager.apply_proposals()            [B + event log]
    → call_ledger.append_assistant_turn()         [A]
```

---

## 3. Call lifecycle (owner: `call_lifecycle_service`)

| Action | Responsibility |
|--------|----------------|
| `call/start` | Resolve L1–L2; create A files; init B; insert DB row; return `call_id` |
| `call/end` | Finalize A; queue post-call; return `202` |
| Auto-finalize | Same as end on idle disconnect |

---

## 4. Module map: existing → target

### Keep (modify minimally)

| Module | Role |
|--------|------|
| `server/app.py` | Register routes; lifespan registry + DB |
| `server/services/openai_brain_service.py` | OpenAI LLM adapter backend |
| `server/services/sarvam_*.py`, `sarvam_ws.py` | Sarvam adapters (wrapped by registry) |
| `server/agent/instruction_builder.py` | Sole live `input[]` builder |
| `server/agent/conversation_manager.py` | Truncated recent turns only |
| `server/utils/prompt_cache_key.py` | Version-based cache key |
| `server/utils/metrics.py` | Extend per-call spans |
| `client/live-guards.js` | Barge-in policy (port to Next.js) |
| `server/agent/language_resolver.py` | Multilingual response routing — preserve |

### New modules

| Module | Role |
|--------|------|
| `providers/registry.py`, `resolver.py` | L1 catalog + resolution |
| `brain/compiled_brain_service.py` | L2 compilation |
| `brain/business_prompt_optimizer.py` | One-time optimization |
| `call/memory_manager.py` | B state + ops |
| `call/memory_projection.py` | C render |
| `call/live_turn_orchestrator.py` | Hot path |
| `call/call_lifecycle_service.py` | Start/end |
| `call/call_ledger.py` | A writer |
| `call/post_call_pipeline.py` | Outcome generation |
| `call/audio_archive.py` | PCM capture |
| `routes/calls.py`, `plivo_ws.py` | HTTP/WS delegates |

### Deprecate

| Legacy | Replace with |
|--------|--------------|
| `session_memory.py` | `memory_manager.py` |
| `memory_summarizer.py` | `rolling_summary` in B |
| `brain_prompt_composer.py` | `compiled_brain_service.py` |
| Client `conversation_store` as SoT | `GET /api/calls` |

---

## 5. Live LLM input singularity

**Only** `instruction_builder.build_live_input()` builds messages.

```text
input[0]  developer: compiled_brain                    [L2 — STABLE / CACHED]
input[1]  user: [Memory projection]\n{C}               [C — DYNAMIC]
input[2]  user: [Rolling summary]\n{text}              [OPTIONAL]
input[3..] user/assistant: recent turns                [conversation_manager]
input[N]  user: current transcript                       [DYNAMIC]
```

### Rolling summary rule

- If `input[2]` carries rolling summary → projection **C** uses **structured slots only** (no narrative prose)
- If summary empty → **C** may include one-line narrative
- **Never** send full **B** or **A** to live LLM

---

## 6. Entity identifiers

| Entity | ID | Notes |
|--------|-----|-------|
| Tenant | `tenant_id` | All data scoped |
| Agent | `agent_id` | Canonical config unit (not `customer_id`) |
| Call | `call_id` | Archive + metrics unit; locks L1/L2 |
| Session | `session_id` | Browser transport; many calls per session |
| Combination | `combination_id` | Hash of L1 stack; benchmark unit |

---

## 7. API path singularity

| Concern | Canonical path |
|---------|------------------|
| Provider catalog | `GET /api/settings/catalog` |
| Catalog alias | `GET /api/providers/catalog` (optional, same handler) |
| Call lifecycle | `POST /api/call/start`, `POST /api/call/end` |
| Call end response | Always **`202 Accepted`** |

---

## 8. Acceptance checklist

- [ ] No module outside `call/memory_*` applies memory ops to B
- [ ] No route builds live LLM input except `instruction_builder`
- [ ] `call_ledger` is the only writer of A transcript lines
- [ ] `compiled_brain_service` is the only writer of L2 compiled text
- [ ] `resolver.py` is the only L1 authority at `call/start`
- [ ] Live LLM request contains C, never B or A
- [ ] Rolling summary not duplicated in C and input[2]
