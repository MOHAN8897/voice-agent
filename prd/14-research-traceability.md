# 14 — Research Basis and Requirements Traceability

Research date: 25 August 2026.

## 1. Evidence labels

- **SOURCE REQUIREMENT:** directly required by `fix.md`, `memory implemenation.md`, or `MEMORY_CALL_ARCHIVE_PLAN.md`.
- **CURRENT PRODUCT EVIDENCE:** verified in repository code/config/tests.
- **RESEARCH-DERIVED RECOMMENDATION:** based on current official or established documentation.
- **PRODUCT INFERENCE:** needed to make the requested product coherent; requires product approval if it expands scope.
- **RECOMMENDED ENHANCEMENT:** useful major-platform capability, not mandatory unless approved.

## 2. Authoritative external references

### OpenAI

- Prompt caching: https://platform.openai.com/docs/guides/prompt-caching
- Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Responses API: https://platform.openai.com/docs/api-reference/responses
- Models: https://platform.openai.com/docs/models

Applied principles:

- Put stable common content first and dynamic content later.
- Track cached input separately from total input where usage exposes it.
- Prefer schema-constrained structured output for machine-consumed results.
- Verify exact SDK fields and model support at implementation time.

### Cartesia

- Overview: https://docs.cartesia.ai/get-started/overview
- Ink 2: https://docs.cartesia.ai/build-with-cartesia/stt/latest
- STT WebSocket: https://docs.cartesia.ai/api-reference/stt/websocket
- 2026 changelog: https://docs.cartesia.ai/changelog/2026

Verified on the research date:

- `ink-2` is documented as stable streaming STT with turn events.
- Official documentation lists `ink-2` language support as English only.
- `sonic-3.5` is documented as current production TTS; exact language/voice compatibility remains registry metadata and live-test gated.

Product impact:

- Cartesia Ink must not be assigned to Telugu tiers until official support and live benchmark verification exist.
- Registry language compatibility is a hard validation, not presentation metadata.

### Google Gemini

- Structured outputs: https://ai.google.dev/gemini-api/docs/interactions/structured-output
- Context caching: https://ai.google.dev/gemini-api/docs/interactions/caching
- May 2026 migration: https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026

Applied principles:

- Gemini supports schema-based outputs, but only a documented JSON Schema subset.
- Interactions API uses provider-specific streaming events and implicit caching.
- Provider adapters normalize capabilities and usage; the core cannot assume OpenAI event names.

### DeepSeek

- Responses API: https://api-docs.deepseek.com/api/create-response/
- Responses guide: https://api-docs.deepseek.com/guides/responses_api/
- JSON output: https://api-docs.deepseek.com/guides/json_mode
- Models/pricing: https://api-docs.deepseek.com/quick_start/pricing

Applied principles:

- Current Responses docs expose `deepseek-v4-flash`, `deepseek-v4-pro`, and an experimental vision model. The voice LLM registry may expose only text models that pass capability/latency tests, and IDs remain environment/catalog driven.
- Responses streaming ends with semantic completion/failure events.
- Structured output and JSON mode differ; adapter capability metadata must identify which contract is supported.

### Plivo

- Audio Streaming overview: https://www.plivo.com/docs/voice-agents/audio-streaming/overview
- Stream XML: https://www.plivo.com/docs/voice-agents/audio-streaming/xml/stream
- Stream SDK guide: https://www.plivo.com/docs/voice-agents/audio-streaming/integration-guides/plivo-stream-sdk
- Voice signature validation: https://plivo.com/docs/voice/concepts/signature-validation
- Console: https://console.plivo.com

Applied principles:

- Plivo is telephony transport, not an STT/LLM/TTS provider.
- Bidirectional WebSocket audio uses Stream XML and START/MEDIA/DTMF/STOP lifecycle.
- Bidirectional mode receives inbound media and sends application audio through `playAudio`; it must not request `audioTrack="both"`.
- Audio format and barge-in/clear behavior must be validated against the selected Plivo mode and SDK.
- HTTP callbacks use Plivo V3 HMAC-SHA256 signature validation with the documented nonce, exact URL/parameters, and Auth Token. Media WebSocket admission separately requires WSS and an application-issued single-use call-bound token.

### LiveKit and Pipecat

- LiveKit observability: https://docs.livekit.io/agents/observability.md
- LiveKit observability data: https://docs.livekit.io/deploy/observability/data/
- LiveKit tracing: https://docs.livekit.io/deploy/observability/tracing/
- Pipecat context summarization: https://docs.pipecat.ai/pipecat/fundamentals/context-summarization
- Pipecat OpenTelemetry: https://docs.pipecat.ai/api-reference/server/utilities/opentelemetry
- OpenInference specification: https://arize-ai.github.io/openinference/spec/
- W3C PROV data model: https://www.w3.org/TR/prov-dm/

Applied principles:

- Per-call debugging benefits from one unified timeline of transcript, audio, traces, logs, and model metrics.
- Aggregate/fleet analytics should be separate.
- Measure per-component and end-to-end latency.
- Background summarization must not block the live pipeline.
- Correlate events by call/conversation and turn/speech IDs.

These products are reference patterns only; the PRD does not require adopting their frameworks.

## 3. Tool availability

- Context7: unavailable in the environment. This did not block the PRD. Exact installed-library and SDK behavior must be re-verified from official/current docs immediately before implementation.
- Ponytail: unavailable. UI requirements use the installed frontend/UI design skill guidance plus current product evidence and external voice-platform patterns.

## 4. Source requirements traceability

| ID | Requirement | Origin | Normative document |
|---|---|---|---|
| SR-001 | Provider-agnostic STT → LLM → TTS | `fix.md` §1, principle | 01 §22; 03 |
| SR-002 | Exactly LOW/MEDIUM/PREMIUM tiers | `fix.md` §2 | 01 §13; 03 |
| SR-003 | DeepSeek V4 integration | `fix.md` §3 | 03 |
| SR-004 | Central registry and capability metadata | `fix.md` §4 | 01 §14; 03 |
| SR-005 | ENV and FRONTEND configuration modes | `fix.md` §5–6 | 01 §20; 11 §15 |
| SR-006 | Disabled plugins hidden and rejected | `fix.md` §7 | 03; 13 |
| SR-007 | API keys server-side | `fix.md` §8 | 01 §25; 13 |
| SR-008 | Dynamic combination testing | `fix.md` §9 | 01 §15–16; 07 |
| SR-009 | Component and E2E metrics | `fix.md` §10 | 01 §19, §30; 07 |
| SR-010 | Configurable scoring, no arbitrary winner | `fix.md` §11 | 01 §16; 07 |
| SR-011 | Configuration precedence and locked session config | `fix.md` §12–13 | 01 §21; 03 |
| SR-012 | Tier/test UI behavior | `fix.md` §14 | 01 §13, §20; 11 |
| SR-013 | Preserve existing behavior | `fix.md` §15 | 00; 01 §33 |
| SR-014 | Backward compatibility and env documentation | `fix.md` §16–18 | 01 §33; 08 |
| SR-015 | Stable brain + working memory + ledger split | `memory implemenation.md` | 01 §24; 12 |
| SR-016 | Structured spoken response and memory operations | `memory implemenation.md` §6–8 | 12 §7 |
| SR-017 | Async rolling summary | `memory implemenation.md` §12 | 12 §11 |
| SR-018 | Full untruncated transcript/audio archive | `memory implemenation.md` §14–16 | 04; 12 §13 |
| SR-019 | Post-call summary/disposition | `memory implemenation.md` §16–17 | 04; 12 §14 |
| SR-020 | Raw + optimized business prompt | `memory implemenation.md` §2, §25 | 11 §6; 12 §2–3 |
| SR-021 | Compiled brain/version locking | `memory implemenation.md` §18, later recommendations | 12 §4 |
| SR-022 | Cached content stable; dynamic after boundary | `memory implemenation.md` §19 | 12 §5 |
| SR-023 | Call lifecycle and archive files | `MEMORY_CALL_ARCHIVE_PLAN.md` §5–7 | 04; 13 §4 |
| SR-024 | Browser not production source of truth | both memory docs | 04; 12 §13 |

## 5. Current product evidence traceability

| ID | Evidence | Location | Product implication |
|---|---|---|---|
| CP-001 | FastAPI app and static SPA | `server/app.py` | Preserve deployment shape initially |
| CP-002 | Sarvam realtime STT proxy | `server/routes/ws.py`, `server/services/sarvam_ws.py` | Adapter must preserve client protocol |
| CP-003 | Sarvam persistent browser TTS WS with upstream reconnect | same | Must-not-break |
| CP-004 | OpenAI Responses streaming brain | `server/services/openai_brain_service.py` | Preserve SSE hot path |
| CP-005 | Stable prompt/caching telemetry | `instruction_builder.py`, `prompt_cache_key.py`, `metrics.py` | Add dynamic memory after stable prefix |
| CP-006 | Last-turn bounded in-memory history | `conversation_manager.py` | Keep for live context, not archive |
| CP-007 | Session summary disabled and simplistic | `session_memory.py`, `memory_summarizer.py`, env | Replace with real memory/summary |
| CP-008 | Per-session runtime settings and model allowlist | `runtime_settings.py`, `settings.js` | Migrate through registry, preserve compatibility |
| CP-009 | Vanilla single-page console | `client/index.html`, `console_tabs.js` | PRD does not assume React rewrite |
| CP-010 | One free-form editable brain prompt | `client/index.html`, `settings.js`, `instructions.py` | Split platform vs structured business authoring |
| CP-011 | Client localStorage conversation archive | `conversation_store.js` | Keep preview/export only; server becomes source |
| CP-012 | In-memory p50/p95/token metrics | `server/utils/metrics.py` | Add durable per-call and aggregate dimensions |
| CP-013 | Existing tests for cache, context, API, TTS, barge-in, settings | `server/tests/` | Extend, never claim unrun tests |
| CP-014 | No provider abstraction/Plivo/call persistence | repository audit | Explicit missing scope |

## 6. Research-derived requirements

| ID | Recommendation | Evidence | Classification |
|---|---|---|---|
| RR-001 | Unified per-call audio/transcript/trace timeline | LiveKit observability | Research-derived |
| RR-002 | Separate per-call debugger and fleet analytics | LiveKit patterns | Research-derived |
| RR-003 | Async context summarization with observable result | Pipecat | Research-derived |
| RR-004 | Provider-specific cache/structured-output capability metadata | OpenAI/Gemini/DeepSeek docs | Research-derived |
| RR-005 | Hard language compatibility validation | Cartesia docs | Research-derived |
| RR-006 | Environment promotion and rollback | Product safety inference | Product inference |
| RR-007 | RBAC and tenant isolation | Requested production/multi-tenant quality bar | Product inference |
| RR-008 | Memory event log/provenance | User's Phase 16–17 request | User requirement |
| RR-009 | Live memory projection | User's Phase 15 request | User requirement |

## 7. Conflicts and decisions

### CD-016 — Single LLM structured turn (supersedes CD-001)

- **Decision:** Same live LLM returns `spoken_response` + `memory_update` in one structured response (`17` §5).
- **Impact:** `live_turn_orchestrator` uses one brain call; `memory_extraction.py` is optional fallback only.

### CD-017 — Generic platform and compact memory

- **Decision:** Generic voice agent platform; default memory schema `facts`, `preferences`, `important_context`, `summary`.
- **Impact:** Real-estate examples are samples only; not default schema lock-in.

### CD-018 — Outbound campaigns in MVP

- **Decision:** Campaign management, dialing, retries, DNC, consent, windows — **in MVP**; outbound prioritized.
- **Impact:** [18-campaign-outbound.md](./18-campaign-outbound.md).

### CD-019 — CRM deferred

- **Decision:** No CRM integration in MVP; webhook optional future.

### CD-020 — Benchmarks disabled until configured

- **Decision:** No benchmark runs until product owner enables/configures scenarios.

### CD-001 — Structured turn object vs streaming speech (historical)

- **Original decision:** async memory extraction after spoken stream.
- **Status:** **Superseded by CD-016.**

### CD-002 — Cartesia Ink for Telugu

- Conflict: source examples imply interchangeable Cartesia STT; current official Ink 2 documentation lists English only.
- Decision: register Ink 2 with `language_support=["en"]`; do not expose for Telugu.
- Impact: Telugu tiers stay on verified STT until Cartesia adds support and benchmarks pass.

### CD-003 — Tier vs voice preset

- Conflict: tier chooses provider/models; current voice preset chooses VAD/barge-in/TTS tuning.
- Decision: preserve both as independent versioned configurations.

### CD-004 — One brain textarea vs platform/customer separation

- Conflict: current UI has one editable prompt; memory source requires platform + customer brain.
- Decision: separate protected Platform Brain and customer Business Brain authoring, then compile into one stable prefix.

### CD-005 — Full memory vs token efficiency

- Conflict: historical/provenance memory grows; live context must remain small.
- Decision: full server-owned internal memory plus deterministic per-turn live projection.

### CD-006 — `VOICE_AGENT_CONFIG_MODE` default

- Decision: existing unset installations retain current frontend behavior; production templates explicitly set `env`.

### CD-007 — Local files vs production persistence

- Conflict: earlier drafts mentioned SQLite; production requires multi-tenant durability.
- Decision: **PostgreSQL for all environments** (dev + staging + prod); local `data/` for call file artifacts in dev; production uses Railway Postgres + object bucket (`prd/13` §9, `prd/17` §11).
- **CD-021 (resolved):** SQLite references in `06` are superseded — see [../implementation/PRD-TRACEABILITY-AUDIT.md](../implementation/PRD-TRACEABILITY-AUDIT.md).

### CD-021 — Memory events API path alias

- Conflict: `13` §4 lists `memory-events`; `13` §6 lists `memory/events`.
- Decision: **`GET /api/call/{id}/memory-events`** is canonical; `memory/events` optional alias to same handler.

### CD-008 — Plivo signature validation

- Prior PRD language risked implying a generic signature algorithm.
- Decision: require validation only according to current official Plivo documentation; exact algorithm/header remains implementation-time verification.

### CD-009 — memory_manager vs working_memory dual ownership

- Conflict: `04` referenced both `working_memory.py` and `memory_manager.py` as writers.
- Decision: **`memory_manager.py`** orchestrates B; projection and extraction are submodules; no parallel writer outside `call/memory_*` package.
- Normative: [15](./15-architecture-ownership-and-singularity.md) §4–5.

### CD-010 — call/end idempotent HTTP status

- Conflict: `06` said `200`; `13` said `202`.
- Decision: always **`202 Accepted`** with finalization status URL, including idempotent repeat.

### CD-011 — Provider catalog API path

- Conflict: `03` emphasized `/api/settings/catalog`; `13` listed `/api/providers/catalog` only.
- Decision: **`GET /api/settings/catalog`** canonical; providers path optional alias to same handler.

### CD-012 — customer_id vs agent_id

- Conflict: `04` used `customer_id`; `13` uses `agent_id`.
- Decision: **`agent_id`** canonical entity; `customer_id` deprecated in APIs and persistence.

### CD-013 — Brain Composer vs compiled_brain_service

- Conflict: `06` diagram labeled generic “Brain Composer” with routes writing memory.
- Decision: **`compiled_brain_service`** owns L2 compilation; **`instruction_builder`** only builds live input; routes delegate to orchestrators.

### CD-014 — Rolling summary triple exposure

- Conflict: rolling summary in B, projection C, and separate input[2] could duplicate narrative.
- Decision: [15](./15-architecture-ownership-and-singularity.md) §8 singularity rule — one narrative path to live LLM.

### CD-015 — Live LLM receives projection not full memory

- Conflict: older text said “working memory JSON” in live input.
- Decision: live LLM receives **projection C** only; full **B** never sent; ledger **A** never sent.

## 8. Resolved product decisions (formerly open questions)

Locked in [17-product-decisions.md](./17-product-decisions.md):

| # | Decision |
|---|----------|
| 1 | **Retention/consent:** 90-day default retention; production PSTN requires consent flow; dev testing simplified |
| 2 | **Infrastructure:** Railway (API + Worker + Postgres + Redis + bucket); local Postgres for dev |
| 3 | **Promotion approval:** One Administrator/Developer approval sufficient |
| 4 | **CRM:** Deferred post-MVP |
| 5 | **Plivo:** Inbound + outbound; **outbound prioritized**; customer self-serve number connect |
| 6 | **Disposition:** `new_lead`, `interested`, `qualified`, `site_visit_planned`, `callback_required`, `not_interested`, `wrong_number`, `converted`, `no_outcome` |
| 7 | **Languages:** Telugu live; English/Hindi planned; code-mix STT default |
| 8 | **Cross-call memory:** No in MVP |
| 9 | **Benchmarks:** Disabled until owner configures |
| 10 | **Auth:** Dev Portal P0 (env credentials); Business Console login P2 |
