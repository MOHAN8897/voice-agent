# 15 — Architecture Ownership, Singularity, and Conflict Resolution

This document is normative for **who owns what**, **what must not be duplicated**, and **how components interact without clashing**. It resolves ambiguities found across PRD documents 00–14.

If any topic document conflicts with this file on ownership or singularity, **this file wins** (after `01-master-prd.md` product scope).

---

## 1. PRD authority ladder

| Priority | Document | Owns |
|----------|----------|------|
| 1 | `01-master-prd.md` | Product scope, goals, non-goals, acceptance criteria |
| 2 | **`15-architecture-ownership-and-singularity.md`** | Ownership, singularity, orchestration, entity model, RBAC, API aliases |
| 3 | `14-research-traceability.md` | Research evidence, source traceability, conflict decisions CD-001+ |
| 4 | Topic PRDs (`03`, `04`, `12`, `11`, `13`, …) | Domain detail within assigned ownership |
| 5 | `05-ux-console-and-dashboards.md` | **Superseded IA** — use `11` for navigation |
| 6 | `10-prd-reaudit.md` | Historical audit only — not implementation authority |

---

## 2. Four independent configuration layers (no double assignment)

Changing one layer must **not** require changing another. Each layer has exactly **one resolver owner**.

| Layer | What it controls | Singular owner module | Versioned? | Locked at |
|-------|------------------|----------------------|------------|-----------|
| **L1 — Provider stack** | STT + LLM + TTS provider/model + voice preset | `providers/resolver.py` | Combination version | `call/start` |
| **L2 — Compiled brain** | Platform + optimized business + static output rules | `brain/compiled_brain_service.py` | `compiled_brain_version` | `call/start` |
| **L3 — Conversation state** | Full internal memory (B), projection (C), rolling summary, recent turns | `call/memory_manager.py` | `memory_version` per turn | Per turn (in-call only) |
| **L4 — Telephony transport** | Browser mic vs Plivo PSTN ingress/egress | `plivo_stream.py` + `audio_transcode.py` | Channel config | `call/start` |

**Not layers (do not conflate):**

| Concept | Role | Not a substitute for |
|---------|------|----------------------|
| **Tier** (LOW/MEDIUM/PREMIUM) | Env bundle selector for L1 | Voice preset, brain, or memory |
| **Voice preset** | VAD, barge-in, TTS pace/temperature, buffers | Provider models (L1) |
| **Session** (`session_id`) | Browser transport + dev runtime tuning scope | Call archive unit |
| **Call** (`call_id`) | Archival, metrics, ledger, outcome unit | Session |

---

## 3. Three conversation data objects (no conflation)

Normative detail: `12-brain-business-memory-spec.md` §17.

| ID | Object | Owner module | Live LLM? | Persisted by |
|----|--------|--------------|-----------|--------------|
| **A** | `call_ledger` | `call/call_ledger.py` | **Never** | `transcript.jsonl`, audio files |
| **B** | `full_internal_memory` | `call/memory_manager.py` | **Never** (full JSON) | `memory_events` + materialized state |
| **C** | `live_memory_projection` | `call/memory_projection.py` | **Yes** (dynamic tail) | Optional per-turn debug record |

**Singularity rules:**

1. Only **A** holds the full untruncated transcript.
2. Only **B** is mutated by memory operations (after validation).
3. Only **C** is sent to the live LLM as memory context.
4. **Rolling summary** lives inside **B** but may be sent as a **separate** live message only when not duplicated in **C** (see §8).

---

## 4. Singular runtime orchestrators

### 4.1 Live turn hot path (one orchestrator)

**Owner:** `call/live_turn_orchestrator.py` (new) — coordinates the per-turn sequence. Routes and WS handlers delegate to it; they do not each implement merge/ledger logic.

```text
STT final
  → live_turn_orchestrator.handle_user_turn()
    → call_ledger.append_user_turn()          [A only]
    → memory_projection.build()               [reads B → produces C]
    → instruction_builder.build_live_input()  [compiled + C + summary + recent + transcript]
    → llm_adapter.stream_structured_turn()     [same LLM: spoken_response + memory_update]
    → stream spoken_response → client/TTS      [hot path]
    → memory_manager.apply_proposals()         [from same response — not separate extraction call]
```

**Forbidden:**

- Brain SSE route directly mutating **B** without `memory_manager`
- `instruction_builder` applying memory operations
- `conversation_manager` writing **A** (it holds truncated live turns only)

### 4.2 Call lifecycle (one orchestrator)

**Owner:** `call/call_lifecycle_service.py` (new)

| Action | Sole responsibility |
|--------|---------------------|
| `call/start` | Resolve L1–L2 locks; create **A** files; init **B**; return `call_id` |
| `call/end` | Finalize **A**; queue post-call; return `202` |
| Auto-finalize | Same as `call/end` on idle disconnect |

### 4.3 Post-call (one pipeline)

**Owner:** `call/post_call_pipeline.py`

- Input: **A** (full ledger) + final **B** snapshot
- Output: `outcome.json`
- Does **not** mutate **B** except read-only

### 4.4 Brain compilation (one pipeline)

**Owner:** `brain/compiled_brain_service.py`

```text
platform_brain_version + business_brain_version + static_rules_version
  → compiled_brain text + compiled_brain_version + checksum
```

**Forbidden:** `instruction_builder` compiling business prompts or running optimizer.

### 4.5 Business optimization (one pipeline)

**Owner:** `brain/business_prompt_optimizer.py`

- Input: assembled raw business sections
- Output: `optimized_business_prompt` + optimizer report
- Triggers `compiled_brain_service` recompile — does not touch live calls

---

## 5. Module ownership map (canonical)

| Module | Owns | Does NOT own |
|--------|------|--------------|
| `providers/registry.py` | Provider catalog metadata | Stack resolution, call state |
| `providers/resolver.py` | L1 stack resolution (tier/mode) | Brain compilation, memory |
| `brain/compiled_brain_service.py` | L2 compiled prefix text + version | Live turn orchestration |
| `brain/business_prompt_optimizer.py` | One-time business optimization | Live calls, memory |
| `brain_prompt_composer.py` *(existing)* | **Migrate into** `compiled_brain_service` | Memory, ledger |
| `agent/instruction_builder.py` | Assembling live LLM `input[]` from locked artifacts | Memory merge, compilation, ledger |
| `agent/conversation_manager.py` | Truncated recent turns for live path | Full transcript (**A**), memory (**B**) |
| `call/call_ledger.py` | **A** append-only transcript + audio refs | Memory, brain compilation |
| `call/memory_manager.py` | **B** state, validation, event log, apply ops | Projection rendering, live LLM calls |
| `call/memory_projection.py` | **C** deterministic projection | Validating ops, ledger writes |
| `call/memory_extraction.py` | **Fallback only** if structured single-call path fails SLO | Applying ops (delegates to manager) |
| `call/live_turn_orchestrator.py` | Hot-path sequencing | Provider adapters internals |
| `call/call_lifecycle_service.py` | Start/end/finalize | Post-call LLM content |
| `call/post_call_pipeline.py` | Outcome generation | Live path |
| `services/runtime_settings.py` | Per-`session_id` dev overrides (frontend mode) | Per-`call_id` locked stack |
| `services/plivo_stream.py` | L4 PSTN events | STT/LLM/TTS provider logic |
| `routes/ws.py` | Wire proxy | Business logic (delegates) |
| `routes/calls.py` | HTTP call CRUD | Memory merge internals |
| `web/` live voice components | Browser live UI loop | Source of truth for calls |

**Deprecated (no parallel ownership):**

| Legacy | Replace with | Migration |
|--------|--------------|-----------|
| `session_memory.py` | `memory_manager.py` | Remove after `ENABLE_WORKING_MEMORY` |
| `memory_summarizer.py` (string join) | `rolling_summary_service` in memory package | Never production |
| `instruction_store` per-session brain | Agent `business_brain` versions | When `agent_id` set |
| Client `conversation_store` as SoT | Server `GET /api/calls` | Server authoritative |

---

## 6. Entity model (singular identifiers)

| Entity | ID | Scope | Notes |
|--------|-----|-------|-------|
| **Tenant** | `tenant_id` | Organization | All data scoped here in production |
| **Agent** | `agent_id` | Deployable voice agent within tenant | **Canonical** config unit (replaces loose `customer_id` in APIs) |
| **Call** | `call_id` | One voice interaction archive | Immutable L1/L2 lock |
| **Session** | `session_id` | Browser tab transport + dev runtime | Many calls per session allowed |
| **Combination** | `combination_id` | Stable hash of L1 stack | Benchmark/promotion unit |

**Naming cleanup:**

| Deprecated / ambiguous | Normative |
|------------------------|-----------|
| `customer_id` in `call/start` (04 legacy) | `agent_id` required; `tenant_id` from auth |
| `customer_id` in SaaS brain record | `agent_id` + `tenant_id` |
| “Customer brain” (UI label) | **Business brain** (technical name) |
| “Main brain” (developer UI) | **Platform brain** |

---

## 7. API path singularity

| Concern | Canonical path | Alias (optional) | Owner route module |
|---------|----------------|------------------|-------------------|
| Provider + tier catalog | **`GET /api/settings/catalog`** | `GET /api/providers/catalog` → same handler | `routes/settings.py` (existing) |
| Runtime dev overrides | `GET/POST/DELETE /api/settings/runtime` | — | `routes/settings.py` |
| Call lifecycle | `POST /api/call/start`, `POST /api/call/end` | — | `routes/calls.py` |
| Agent brain | `/api/agents/{agent_id}/business-brain/*` | — | `routes/agents.py` |
| Platform brain | `/api/platform-brain/*` | — | `routes/platform_brain.py` |

**`call/end` response:** Always **`202 Accepted`** with finalization status URL — including idempotent repeat (not `200`).

---

## 8. Live LLM input singularity (no duplicate content)

**Owner:** `instruction_builder.build_live_input()` — the **only** function that builds live LLM messages.

Fixed order:

```text
input[0]  developer: compiled_brain                    [L2 — STABLE]
input[1]  user: [Memory projection]\n{C}               [C — DYNAMIC]
input[2]  user: [Rolling summary]\n{text}              [OPTIONAL — see rule below]
input[3..] user/assistant: recent turns                [conversation_manager — DYNAMIC]
input[N]  user: current transcript                     [DYNAMIC]
```

**Rolling summary singularity rule:**

- If `rolling_summary` is sent as **input[2]**, projection **C** must **omit** narrative prose and include **structured slots only**.
- If `rolling_summary` is empty, projection **C** may include a one-line narrative tail.
- **Never** send full **B** JSON to the live LLM.
- **Never** send **A** ledger text to the live LLM.

---

## 9. Role model (single RBAC matrix)

Roles are **tenant-scoped** except Platform Admin and Auditor (platform-scoped).

| Role | Business brain | Platform brain | Providers/tiers | Benchmarks | Promote stack | Calls/audio | Tenant settings |
|------|----------------|----------------|-----------------|------------|---------------|-------------|-----------------|
| **Customer Viewer** | read summary | — | — | — | — | read | — |
| **Customer Operator** | read | — | — | — | — | read + annotate | — |
| **Customer Admin** | edit/publish | — | read tier | — | — | read | edit tenant |
| **Voice Engineer** | read + test | — | edit/test | create/run | review only | read + traces | — |
| **Platform Admin** | read | edit/activate | edit global | create/run | approve/promote | read | platform |
| **Auditor** | read versions | read versions | read | read | read history | read + export | read audit |

**No double assignment:**

- Only **Platform Admin** activates platform brain and global promotions.
- Only **Customer Admin** publishes business brain for their tenant.
- **Voice Engineer** cannot edit business brain in production tenant (test studio draft only unless also Customer Admin).
- **Customer roles** never read platform brain body text.

Enforcement: server-side on every endpoint (`13-api-data-security-contracts.md`); UI hides controls but is not authoritative.

---

## 10. Configuration mode singularity

| `VOICE_AGENT_CONFIG_MODE` unset | `env` | `frontend` |
|---------------------------------|-------|--------------|
| Behavior | **`frontend`** (backward compat with current dev console) | Explicit dev console |
| L1 source | `VOICE_AGENT_TIER` env bundle | Client selection validated by resolver |
| UI | Tier chip read-only + hidden provider matrix | Full provider matrix |

Production deployment templates must set **`env`** explicitly (`14-research-traceability.md` CD-006).

---

## 11. UX information architecture singularity

| Document | Status |
|----------|--------|
| **`11-ui-information-architecture.md`** | Normative v2 sitemap and screen contracts |
| `05-ux-console-and-dashboards.md` | **Superseded navigation** — content may inform components but not nav structure |

### Legacy tab → v2 mapping

| `05` legacy tab | `11` v2 location |
|-----------------|------------------|
| Voice | Agents → Test Studio (browser live) or Overview quick test |
| Calls | Calls |
| Test | Test Studio + Benchmarks |
| Brain | Agents → Business Brain + Platform Brain |
| Metrics | Analytics + per-call trace in Calls detail |
| Config | Providers + Settings + Agents → Voice & Models |

Implement v2 navigation from doc **11** only.

---

## 12. Resolved cross-PRD conflicts (CD-009+)

| ID | Conflict | Resolution |
|----|----------|------------|
| **CD-009** | `memory_manager.py` vs `working_memory.py` dual ownership (04) | **`memory_manager.py`** orchestrates; projection/extraction are submodules; no separate `working_memory.py` writer outside package |
| **CD-010** | `call/end` idempotent returns `200` (06) vs `202` (13) | Always **`202`** with status URL |
| **CD-011** | `/api/settings/catalog` (03) vs `/api/providers/catalog` (13) | **`/api/settings/catalog`** canonical; providers path is optional alias |
| **CD-012** | `customer_id` (04) vs `agent_id` (13) | **`agent_id`** canonical; `customer_id` deprecated |
| **CD-013** | `Brain Composer` (06 diagram) vs `instruction_builder` + `compiled_brain_service` | Diagram label maps to **compiled_brain_service**; instruction_builder only builds input |
| **CD-014** | Rolling summary in B, C, and separate input — triple exposure | **§8 singularity rule** — one narrative path to live LLM |
| **CD-015** | API routes mutate WM directly (06 diagram) | Routes delegate to **live_turn_orchestrator** / **call_lifecycle_service** |

Record updates in `14-research-traceability.md` §7.

---

## 13. Acceptance criteria (architecture coherence)

- [ ] No module outside `call/memory_*` applies memory operations to **B**
- [ ] No route builds live LLM input except `instruction_builder`
- [ ] `call_ledger` is the only writer of **A** transcript lines
- [ ] `compiled_brain_service` is the only writer of L2 compiled text
- [ ] `resolver.py` is the only L1 stack authority at `call/start`
- [ ] Live LLM request contains **C** never **B** or **A**
- [ ] Rolling summary not duplicated between **C** and input[2]
- [ ] RBAC enforced server-side per §9 matrix
- [ ] Catalog served only from canonical path (alias optional)
- [ ] v2 UI follows doc **11** nav, not doc **05** tab shell
