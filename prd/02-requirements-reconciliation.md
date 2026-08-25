# 02 — Requirements Reconciliation

Merges **`fix.md`**, **`memory implemenation.md`**, **`MEMORY_CALL_ARCHIVE_PLAN.md`**, and the **current codebase** into one coherent requirement set.

---

## 1. Overlap matrix

| Theme | fix.md | memory implemenation.md | MEMORY_CALL_ARCHIVE_PLAN | Current code |
|-------|--------|-------------------------|--------------------------|--------------|
| Provider plugins | **Primary** — registry, tiers, Cartesia/DeepSeek/Gemini | Mentions Sarvam/Cartesia in examples | — | Sarvam + OpenAI only |
| Testing matrix + metrics | **Primary** — §10–11, scoring weights | — | — | `/api/metrics`, benchmarks scripts |
| Env vs frontend config mode | **Primary** — §5–6, §14 | — | — | Always full console |
| Working memory | — | **Primary** — JSON slots, operations | Slots + summary (lighter schema) | `session_memory` off; string join |
| Call ledger + audio | — | **Primary** — JSONL, PCM, mix.wav | **Primary** — phased implementation | `ConversationStore` local only |
| Post-call outcome | — | **Primary** — disposition schema | Same | Not built |
| Compiled / optimized brain | — | **Primary** — SaaS onboarding | Uses single brain prompt today | `brain_prompt_composer` per session |
| Prompt versioning | — | **Primary** — platform + business versions | — | Cache key on content hash only |
| Prompt caching rules | Implied (don't break perf) | **Explicit** — breakpoint boundary | **Explicit** — same | **Implemented** |
| CRM webhook | — | — | Optional hook | UI store only |
| Voice presets (VAD/barge) | — | — | — | **Implemented** (`voice_defaults.py`) |
| Plivo PSTN telephony | — (transport) | `caller_id` in memory | `channel: pstn` | **Not built** — see §09 |

**Merge rule applied:** Where `memory implemenation.md` is more specific on memory/SaaS brain, it becomes canonical. Where `fix.md` is more specific on providers/testing, it becomes canonical. `MEMORY_CALL_ARCHIVE_PLAN` supplies file paths and phase order aligned to this repo. Plivo is specified as optional telephony transport in §09 (not in source docs but required for real phone testing).

---

## 2. Unified requirement catalog

### 2.1 Provider platform (from fix.md)

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| PR-01 | STT, LLM, TTS standardized interfaces | P0 |
| PR-02 | Central registry: provider, model, type, enabled, streaming flags, language_support | P0 |
| PR-03 | Env plugin switches `ENABLE_*` — disabled hidden + API rejected | P0 |
| PR-04 | LOW / MEDIUM / PREMIUM tier env vars (provider+model per stage) | P0 |
| PR-05 | `VOICE_AGENT_CONFIG_MODE=env\|frontend` | P0 |
| PR-06 | DeepSeek V4 LLM adapter (env: key, base URL, model) | P1 |
| PR-07 | Cartesia STT (Ink) + TTS (Sonic) adapters | P1 |
| PR-08 | Gemini LLM adapter | P1 |
| PR-09 | Session config snapshot at start (JSON, no secrets) | P0 |
| PR-10 | Backward compat if new env unset → current Sarvam/OpenAI | P0 |

### 2.2 Testing & observability (from fix.md + research)

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| TO-01 | Per-turn metrics: STT final latency, LLM TTFT, TTS first audio, E2E | P0 |
| TO-02 | Token counts + model id per LLM call | P0 |
| TO-03 | Benchmark run record per combination test | P1 |
| TO-04 | Configurable score weights via env | P1 |
| TO-05 | Comparison UI: latency waterfall, P95 not just average | P1 |
| TO-06 | Per-call trace: conversation_id links STT/LLM/TTS spans | P1 |

### 2.3 Memory & call lifecycle (from memory docs)

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| ML-01 | Three information types: stable brain, working memory, call ledger | P0 |
| ML-02 | Working memory JSON schema (customer, requirements, preferences, objections, rolling_summary) | P0 |
| ML-03 | `memory_update.operations[]` merge (set/add), not full memory rewrite each turn | P0 |
| ML-04 | Live LLM input: cached brain + **live memory projection (C)** + optional rolling summary + last 1–2 turns + current utterance | P0 |
| ML-05 | Rolling summary every 4–6 turns, async, off hot path | P1 |
| ML-06 | `POST /api/call/start`, `POST /api/call/end`, `GET /api/call/{id}` | P0 |
| ML-07 | `transcript.jsonl` full untruncated turns | P0 |
| ML-08 | User PCM + agent audio append during call; stereo `mix.wav` on end | P1 |
| ML-09 | Post-call structured `outcome.json` (summary_te/en, disposition, next_action, extracted) | P0 |
| ML-10 | Do not send full ledger to live brain | P0 |

### 2.4 SaaS brain layer (from memory implemenation.md)

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| SB-01 | Store `raw_business_prompt` + `optimized_business_prompt` | P1 |
| SB-02 | One-time optimizer on save (not every turn) | P1 |
| SB-03 | `compiled_brain` = platform + optimized business + static output rules | P1 |
| SB-04 | Versioning: `platform_brain_version`, `business_brain_version`, `compiled_brain_version` | P1 |
| SB-05 | In-flight calls keep brain version from `call/start` | P1 |
| SB-06 | Frontend displays raw prompt only | P1 |

### 2.5 Preserve from current product

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| EX-01 | Live WS STT + SSE brain + WS TTS pipeline | P0 |
| EX-02 | OpenAI prompt cache breakpoint on brain prompt | P0 |
| EX-03 | `store: false` live turns | P0 |
| EX-04 | Barge-in policy (`live-guards.js` parity) | P0 |
| EX-05 | Voice preset bundles (separate from tiers) | P0 |
| EX-06 | Fine-tune console panels (when frontend mode) | P1 |
| EX-07 | `/api/prompt/effective`, `/api/metrics` | P0 |

### 2.6 Telephony — Plivo (PRD §09; not in fix.md)

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| TL-01 | `ENABLE_PLIVO` gate; credentials server-side only | P1 |
| TL-02 | Answer URL + bidirectional WS `/ws/plivo-stream` | P1 |
| TL-03 | `call/start` with `channel=pstn`, `caller_id` from Plivo START | P1 |
| TL-04 | μ-law 8 kHz ↔ STT/TTS audio transcoding bridge | P1 |
| TL-05 | PSTN barge-in via Plivo `clearAudio` | P1 |
| TL-06 | Same call ledger + outcome as browser path | P1 |
| TL-07 | `GET /api/plivo/status` (no secrets) | P1 |
| TL-08 | Benchmark runs record `channel: browser\|pstn` | P2 |

### 2.7 VOICE ENGINE layers (`memory implemenation.md` §988)

Four independent configuration layers — changing one must not require changing others:

```
VOICE ENGINE
├── Provider configuration (STT, LLM, TTS)     → fix.md, §03
├── Brain configuration (platform + business)  → §04 SaaS
├── Conversation state (working memory, summary, turns) → §04
└── Telephony transport (browser vs Plivo PSTN) → §09
```

## 3. Contradictions & resolutions

### C1 — Streaming spoken response vs structured dual output

| Source A | Source B |
|----------|----------|
| `memory implemenation.md`: LLM returns `{ spoken_response, memory_update }` as structured output | Current `app.js`: SSE text deltas streamed to TTS in real time for low latency |

**Decision (CD-016 — supersedes this section):** **Single live LLM** returns structured `{ spoken_response, memory_update }` using the same model as conversation. Stream spoken text to TTS; validate memory without separate extraction call. See [17-product-decisions.md](./17-product-decisions.md) §5.

**Historical note (CD-001):** Async second structured call was previously recommended for latency; product owner chose unified structured turn output.

**Requirement:** Memory merge must not block first audible speech beyond existing sentence-buffer behavior.

---

### C2 — Entity slots vs full working memory JSON

| Source A | Source B |
|----------|----------|
| `MEMORY_CALL_ARCHIVE_PLAN.md`: simple slots + rolling summary | `memory implemenation.md`: nested JSON with operations |

**Decision:** Adopt **memory implemenation.md** schema as canonical. The archive plan’s “slots” are the `customer` + `requirements` sections of that schema. Implement merge operations in **`call/memory_manager.py`** (orchestrator); projection in **`call/memory_projection.py`**; no duplicate writers. See [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) §3–5.

---

### C3 — LOW/MEDIUM/PREMIUM tiers vs Voice Presets

| Source A | Source B |
|----------|----------|
| `fix.md`: tiers = STT+LLM+TTS provider bundles | `voice_defaults.py`: presets = VAD/barge/TTS buffer tuning |

**Decision:** **Both coexist.**

- **Tier** selects provider/model triple (cost/quality ladder).
- **Voice preset** selects acoustic/turn-taking tuning (Telugu natural, fast, etc.).
- Resolution order: `tier defaults` → `voice preset overrides` → `session runtime overrides` (dev mode).

**UI:** In env mode, tier chip selects bundle; preset may be fixed per tier in env or hidden. In frontend mode, both selectable.

---

### C4 — `ENABLE_SESSION_SUMMARY` vs new working memory

| Current | New |
|---------|-----|
| `compact_history_summary()` when flag true | Rolling summary inside working memory |

**Decision:** Deprecate `compact_history_summary` and `session_memory` summary field. Replace with `working_memory.rolling_summary` + async LLM summariser from **call ledger** turns (full text), not truncated `conversation_manager` history.

**Migration:** `ENABLE_SESSION_SUMMARY` → `ENABLE_WORKING_MEMORY` (default true in production).

---

### C5 — Env mode hides all controls vs existing unified console

| Source A | Source B |
|----------|----------|
| `fix.md`: env mode shows only LOW/MEDIUM/PREMIUM | `index.html`: full 6-panel console always visible |

**Decision:** Implement **mode gating** in `settings.js` / `console_tabs.js`:

| Mode | Visible UI |
|------|------------|
| `env` | Tier selector + Start + Calls list + transcript (read-only config summary) |
| `frontend` | Full developer console: provider matrix, presets, brain editor, metrics, advanced |

Default for **existing deployments:** `frontend` until explicitly set to `env` (backward compat).

---

### C6 — Compiled customer brain vs single global brain prompt

| Source A | Source B |
|----------|----------|
| SaaS: per-customer compiled brain | Today: per-session `instruction_store` brain prompt |

**Decision:** Introduce **`agent_id`** (nullable for single-tenant dev). When `agent_id` set:

- Compiled brain from agent record replaces session-composed business sections.
- `prompt_cache_key` = hash(`compiled_brain_version` + budget), not sessionId.

Legacy `customer_id` in older docs maps to `agent_id` (deprecated). See [15](./15-architecture-ownership-and-singularity.md) §6.

---

### C7 — Cartesia model names in fix.md examples

Examples use `ink`, `sonic-3.5`, `deepseek-v4-flash` as illustrations.

**Decision:** Registry loads **actual model IDs from env**, validated against provider API catalog at startup (soft warn) or from static catalog in registry module. Do not hard-code example names in application logic. Document in `.env.example` with placeholder `<configured-model>`.

---

### C8 — Working memory block role in OpenAI input

| Source A | Source B |
|----------|----------|
| `MEMORY_CALL_ARCHIVE_PLAN`: `input[1]` user message `[Working memory]` | PRD v1: developer message for memory JSON |

**Decision:** **User-role message** with `[Working memory]` prefix after cached developer block. Keeps entire developer `input[0]` byte-stable for cache; memory updates only change `input[1]`.

---

## 4. Disposition enum (merged — locked in `17` §6)

Canonical values for `outcome.disposition` (post-call):

| Value | Meaning |
|-------|---------|
| `new_lead` | First contact / lead captured |
| `interested` | Positive engagement |
| `qualified` | Meets qualification criteria |
| `site_visit_planned` | Site visit or appointment scheduled |
| `callback_required` | Must call back |
| `not_interested` | Declined |
| `wrong_number` | Wrong party / misdial |
| `converted` | Deal closed / goal achieved |
| `no_outcome` | Too short or ambiguous |

Business may map to CRM labels later. Schema allows `disposition_detail` string.

---

## 5. Configuration precedence (unified)

```
1. ENV: plugin enables (hard gate)
2. ENV: VOICE_AGENT_CONFIG_MODE
3a. env mode: VOICE_{TIER}_* provider/model
3b. frontend mode: user selection (validated)
4. Voice preset bundle (tuning)
5. Session runtime overrides (frontend mode only)
6. Per-call locked snapshot at call/start (immutable for call duration)
7. Brain version locked at call/start (SaaS)
```

---

## 6. Traceability to source sections

| PRD section | fix.md | memory implemenation.md |
|-------------|--------|-------------------------|
| §03 Provider | §2–4, §7–9, §12–13, §17 | §988–1018 (brain vs provider separation) |
| §04 Memory | — | §2–25, diagrams |
| §05 UX env mode | §14 | — |
| §07 Metrics | §10–11 | — |
| §04 Outcome | — | §16–17 |
| §08 Phases | §15–16 | §854–878 module list |

---

## 7. Resolved decisions (formerly open questions)

| # | Decision |
|---|----------|
| Q1 | Production: `env` mode; unset env: `frontend` backward compat |
| Q2 | **CD-016:** Same LLM structured `spoken_response` + `memory_update` (see `17`) |
| Q3 | Storage: local Postgres dev; Railway Postgres + bucket production |
| Q4 | **No cross-call memory** in MVP |
| Q5 | Plivo inbound + outbound; outbound prioritized |
| Q6 | Full decisions: [17-product-decisions.md](./17-product-decisions.md) |

---