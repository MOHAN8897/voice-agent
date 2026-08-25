# Voice Agent Platform — Master Product Requirements Document

Version: 2.0  
Date: 25 August 2026  
Status: Draft for product and engineering approval  
Normative scope: This file is the single product-level source of truth. Topic PRDs linked from it provide normative detail. If a topic document conflicts with this master, this master and [14-research-traceability.md](./14-research-traceability.md) conflict decisions take precedence. **Ownership and singularity** are defined in [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md).

## 1. Executive Summary

The product is a **generic**, configurable, testable, production voice-agent control plane. Telugu is the first live language; English and Hindi are planned. It is **not** limited to real estate — any business configures structured sections that compile into one optimized prompt. It preserves the current low-latency `STT → streaming LLM → streaming TTS` application while adding provider-agnostic adapters, configurable LOW/MEDIUM/PREMIUM tiers, a full model-combination benchmark system, protected platform and structured customer business brains compiled into one stable prompt, traceable server-owned memory, durable call archives, Plivo PSTN testing, per-call debugging, aggregate analytics, multi-tenant security, and controlled configuration promotion.

The current repository is a strong browser-based Telugu voice-agent prototype. It is not yet a durable multi-provider or multi-tenant platform. This PRD defines what must be added without replacing working realtime behavior unnecessarily.

## 2. Product Vision

Enable a customer or developer to configure business behavior, choose or test a voice stack, have natural low-latency calls, understand exactly what happened, and safely promote a reproducible configuration to production.

The finished workflow is:

`Configure Agent → Configure Business Brain → Choose Voice Tier → Test Agent → Compare Models → Inspect Calls → Analyze Performance → Promote Configuration`.

Quality pillars:

- Product: clear workflows and safe defaults.
- Voice: natural Telugu/Indian-language behavior and low interruption friction.
- Developer: provider switching without core rewrites.
- Token: stable cached brain plus compact dynamic projection.
- Memory: structured, persistent, historical, traceable, and server-owned.
- Operations: reproducible benchmarks and correlated production traces.
- Scale: tenant-safe provider/configuration architecture.
- Safety: backend-only secrets, role boundaries, consent, retention, and audit.

## 3. Goals

### G-01 Provider independence

The core pipeline interacts only with standardized STT, LLM, and TTS interfaces.

### G-02 Production realtime quality

Preserve streaming, sentence buffering, barge-in, audio callbacks, prompt caching, and bounded live context.

### G-03 Reproducible configuration

Every call and benchmark records immutable provider, model, brain, tier, memory schema, and scenario versions.

### G-04 Complete call intelligence

Every finalized call produces a durable ledger, audio archive, trace, memory history, and structured outcome or an explicit retryable failed state.

### G-05 Usable customer brain authoring

Customers divide instructions into understandable sections while the backend assembles and optimizes them into one business brain.

### G-06 Operational visibility

Support per-call diagnosis and separate fleet analytics for latency, quality, reliability, usage, memory, and cost.

### G-07 Discoverability and performance

Public marketing meets industry SEO and Core Web Vitals on the Next.js **web** service; consoles responsive on all devices ([19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md)).

## 4. Non-Goals

- Replacing the working cascade with speech-to-speech in v1.
- Sending the full transcript or full internal memory to the live LLM every turn.
- Making the browser/localStorage the production archive.
- Exposing API keys or platform-owned prompt content to customers.
- Hard-coding tier combinations or declaring a universal model winner.
- Claiming Telugu support for a provider/model without current documentation and live validation.
- Knowledge base / RAG, CRM integrations, and human-transfer marketplace in v1 (campaigns **are** in scope — see [18-campaign-outbound.md](./18-campaign-outbound.md)).

## 5. Current Product Audit

Detailed audit: [00-current-state-audit.md](./00-current-state-audit.md).

### What exists

- FastAPI application in `server/app.py`.
- REST routes for health, STT, brain, TTS, voice orchestration, instructions, settings, metrics, and session control.
- `/ws/stt-realtime` Sarvam realtime STT proxy and `/ws/tts` persistent browser-to-Sarvam TTS proxy.
- Sarvam REST `saaras:v3` STT, hard-coded live WebSocket `saaras:v3-realtime`, Sarvam `bulbul:v3` TTS, and OpenAI Responses brain configured as `gpt-5.6-luna` in current defaults. The live STT model is not currently resolved from `SARVAM_STT_MODEL`.
- Stable composed brain prompt, explicit cache behavior, `store: false`, bounded recent history, and token telemetry.
- In-memory session history and optional simplistic disabled summary.
- Legacy vanilla SPA in `client/` (reference only — **not** target stack; see [19](./19-frontend-backend-nextjs-railway.md)).
- Provider/model allowlist for current OpenAI selection and Sarvam model/speaker catalogs.
- Client localStorage conversation history/export.
- In-memory p50/p95 latency, token, cache, error, and recent-brain-turn metrics.
- Tests for configuration, health, API mocks, prompt/cache/token behavior, context/history, settings, TTS, barge-in parity, and optional live latency.

### What works

- Browser PCM → realtime STT → streamed brain SSE → sentence-buffered WS TTS.
- Persistent browser TTS socket with upstream turn reconnect.
- Telugu-first prompt/model/preset behavior.
- Client barge-in and interruption controls.
- Prompt cache stability and measured high steady-state cache hit.
- Fine-tune/runtime settings and safe server-side provider keys.

### What is missing

- Provider registry and standardized adapters.
- Cartesia, Gemini, and DeepSeek adapters.
- Tier resolver and ENV/FRONTEND mode gating.
- Durable call ID/lifecycle, server transcript/audio archive, real working memory, projection, provenance, post-call outcome, and production storage.
- Tenant/role/environment/promotion model.
- Benchmark sessions and comparison UI.
- Separate platform/customer business brains.
- Plivo implementation.
- Durable per-call/fleet observability.

### What needs modification

- Hard-coded provider routes must resolve adapters while preserving current wire behavior.
- Single prompt editor must become protected Platform Brain plus structured Business Brain.
- Session settings must resolve and lock versioned call configuration.
- Metrics must become correlated and durable.
- Client archive becomes preview; server becomes source of truth.

### What must not be broken

- Existing Sarvam browser WS protocols and reconnect behavior.
- OpenAI streaming and `store: false`.
- Stable-prefix prompt caching and telemetry.
- `BRAIN_CONTEXT_TURNS=2` default and live history caps.
- Barge-in policy/parity tests.
- Voice presets and `VOICE_HTTP_TTS_FALLBACK=false`.
- Existing env behavior when new configuration is unset.

## 6. Source Requirements Reconciliation

Detailed reconciliation: [02-requirements-reconciliation.md](./02-requirements-reconciliation.md) and [14-research-traceability.md](./14-research-traceability.md).

### Requirements Conflicts / Decisions

1. Structured `spoken_response + memory_update` from the **same live LLM** per turn (CD-016); stream speech to TTS without blocking on full JSON when possible.
2. Full historical memory vs token efficiency: maintain full server state/event history and send only a compact live projection.
3. Tier vs current voice preset: tiers choose providers/models; presets tune VAD, interruption, buffering, pace, and voice settings.
4. Single current prompt vs platform/customer ownership: create separate editors, compile one stable prompt.
5. Cartesia Ink 2 STT is English-only; Telugu STT default is Sarvam Saaras; Cartesia Sonic 3.5 TTS supports Telugu for optional premium tier.
6. Local call **files** vs production multi-tenancy: local `data/` for dev artifacts; **PostgreSQL** for all metadata (dev + prod); production requires object storage for audio (`prd/13` §9, CD-021).
7. Unset configuration mode: preserve current FRONTEND behavior; production templates explicitly set ENV mode.

## 7. User Types / Personas

- Customer Admin: defines business instructions, selects allowed tier, configures channels, reviews deployment.
- Customer Operator: tests calls, reviews outcomes, annotates calls.
- Customer Viewer: reads calls and analytics.
- Voice Engineer: manages provider combinations, benchmarks, and model diagnostics.
- Platform Admin: owns platform brain, global policies, provider enablement, and promotion.
- Quality Reviewer: scores calls/scenarios and approves benchmark evidence.
- Auditor: inspects immutable configuration, access, retention, and promotion history.

## 8. User Journeys

### First configuration

1. Sign in and select tenant.
2. Create agent and choose default language/use case.
3. Fill Business Brain sections.
4. Optimize and review warnings.
5. Choose a tier or enabled provider stack according to mode.
6. Run browser smoke test.
7. Inspect transcript, memory projection, latency, and errors.
8. Run benchmark/PSTN tests where required.
9. Submit configuration for review.
10. Approve and promote to environment/tier.

### Production call review

1. Open Calls and filter.
2. Select a call.
3. Review outcome and audio/transcript timeline.
4. Inspect pipeline spans and memory events.
5. Annotate quality or trigger authorized post-call retry.

### Provider evaluation

1. Create benchmark session.
2. Select scenario/language/channel and compatible combinations.
3. Review expected count/cost.
4. Run and monitor progress.
5. Compare winners per metric and composite components.
6. Review evidence and promote approved combination.

## 9. Information Architecture

Primary areas:

- Overview
- Agents
- Test Studio
- Calls
- Analytics
- Benchmarks
- Providers
- Integrations
- Settings

Agent workspace:

- Summary
- Business Brain
- Platform Brain (authorized only)
- Voice & Models
- Memory Schema
- Tools & Actions
- Channels
- Versions & Deployment

Normative details: [11-ui-information-architecture.md](./11-ui-information-architecture.md).

## 10. Website / Page Structure

The full sitemap is in [11-ui-information-architecture.md](./11-ui-information-architecture.md) §4.

Desktop uses persistent navigation and task-specific workspaces. The live debugger may use a split pane. The product must not be redesigned as identical dashboard cards; tables, timelines, forms, open sections, and focused inspector panels should match the information task.

The current visual language may evolve incrementally; a framework rewrite is not a PRD requirement.

## 11. Agent Configuration UX

### Requirement

Provide one agent workspace showing draft/active state, setup completion, language, selected tier/stack, brain versions, channels, and deployment.

### Why

Current controls are distributed across technical tabs and do not show one deployable agent configuration.

### User behavior

Edit draft, validate, test, and submit/publish according to role.

### System behavior

Persist immutable versions and lock calls to resolved versions.

### Validation

Require valid brain, compatible providers/language, channel readiness, and smoke test.

### Edge cases

Disabled model in saved draft, concurrent edits, active calls during publish.

### Acceptance criteria

Every production-impacting action identifies agent, environment, version, effective time, and rollback target.

## 12. Business Brain Configuration UX

Customers edit structured sections: Identity & Purpose, Facts, Actions & Limits, qualification/callback flows, Scope & Redirects, Guardrails, FAQ, and approved custom sections.

Enabled sections are assembled in deterministic order and optimized as one business prompt. Raw text remains exact source-of-truth. Optimizer output is internal, reviewable, and versioned.

Separate protected Platform Brain UI is provided for platform developers. It owns global identity, language, safety, memory/output contract, and static behavior. Customer roles cannot read it.

Complete contract: [12-brain-business-memory-spec.md](./12-brain-business-memory-spec.md) §1–4 and [11-ui-information-architecture.md](./11-ui-information-architecture.md) §6–8.

## 13. Model Tier UX

Exactly three customer-facing tiers:

- LOW: lowest cost, high volume, low latency, acceptable quality.
- MEDIUM: balanced production cost, quality, and latency.
- PREMIUM: highest verified conversational/STT/TTS quality, especially Telugu/Indian languages; cost secondary.

Each tier points to a versioned combination containing STT provider/model, LLM provider/model, TTS provider/model, plus compatible voice preset.

Tiers are assignments, not hard-coded combinations. UI shows resolved models, language support, estimated cost, version, environment, and effective date.

## 14. Provider / Plugin UX

Registry displays provider, model, stage, enabled/configured/health, streaming/realtime, languages, capabilities, safe pricing, and metadata timestamp.

Disabled providers are absent from selectors and rejected by the backend. API keys never reach the browser.

Planned integrations:

- STT: Sarvam `saaras:v3` / `saaras:v3-realtime` for Telugu (default); Cartesia `ink-2` for English-only; Cartesia `ink-whisper` snapshot for multilingual STT experiments.
- TTS: Sarvam `bulbul:v3` `te-IN` (default); Cartesia `sonic-3.5` for premium Telugu after benchmark.

Exact IDs come from current repo/env and official docs or server catalog, never guessed in UI logic.

## 15. Model Testing UX

FRONTEND mode allows constructing any enabled compatible `STT × LLM × TTS` combination without code changes.

Definitions:

- Combination ID: stable identity for versioned stage/config selection.
- Benchmark Session: one controlled evaluation run.
- Test Scenario: versioned input, language, expected behavior, rubric, and artifacts.
- Result: immutable measured output linked to all versions.

The system can enumerate the Cartesian product only after filtering for language, streaming, channel/audio, and capability compatibility.

## 16. Benchmarking UX

Track:

- STT: first transcript, final transcript, transcription duration, accuracy/quality, errors.
- LLM: TTFT, total generation, input/cached/cache-write/output tokens where provider exposes them, output quality, errors.
- TTS: first byte/audio, total generation, characters, audio duration, quality, errors.
- End-to-end: one authoritative clock from detected user turn completion to first audible response, plus component clocks.
- Conversation: task completion, policy adherence, naturalness, Telugu quality, interruption behavior, reliability.

No unexplained single score. Optional composite score exposes weights and components. Results identify winner per metric and confidence/sample size where applicable.

Full details: [07-testing-metrics-observability.md](./07-testing-metrics-observability.md).

## 17. Memory UX

The user-facing debugger distinguishes:

- Full Internal Memory
- Live Memory Projection
- Rolling Summary
- Recent Turns
- Memory proposals
- Accepted/rejected event history

Customer users see business-relevant state. Developer/auditor roles may inspect provenance, confidence, validation, and projection reasons. The LLM never directly mutates persistent state.

## 18. Call History / Transcript UX

Call list filters by agent, environment, channel, tier, combination, status, outcome, time, and errors.

Call detail includes:

- Telugu/English outcome
- stereo/user/agent audio
- transcript aligned with timestamps
- interruption and actually-audible partial text
- provider/model/config versions
- latency waterfall and event trace
- usage/cost
- memory updates/projection
- errors/fallbacks

Browser localStorage is a cache/preview only.

## 19. Analytics / Observability UX

Per-call debugger: unified audio, transcript, trace, logs/events, provider metrics, memory, tools, and errors.

Aggregate analytics: call volume/completion, P50/P95 latency, reliability/fallback, STT/LLM/TTS quality, task/disposition, usage/cost, memory success, and combination performance.

These are separate experiences with cross-links, not one overloaded dashboard.

## 20. Frontend Mode / ENV Mode

### ENV mode

Frontend shows LOW/MEDIUM/PREMIUM and read-only configured stack. Individual provider/model controls and promotion are hidden. Server ignores/rejects client overrides.

### FRONTEND mode

Developer selects enabled compatible STT/LLM/TTS and voice preset. Backend registry remains authoritative.

Production deployment templates default explicitly to ENV mode; existing unset installations retain current frontend-compatible behavior.

## 21. Configuration Rules

Precedence:

1. Platform/tenant security policy.
2. Provider enablement and credentials.
3. Configuration mode.
4. ENV tier assignment or validated FRONTEND selection.
5. Voice preset/audio tuning.
6. Agent and environment version.
7. Per-call immutable snapshot.
8. Platform/business/compiled brain version lock.

Tier assignment and combination promotion are versioned and auditable. No mid-call mutation.

## 22. Backend Requirements

- Standard STT, LLM, and TTS adapter interfaces.
- Central provider/model registry and compatibility resolver.
- Current Sarvam/OpenAI behavior implemented behind adapters first.
- Durable call lifecycle, ledger, audio archive, memory events/projections, and post-call jobs.
- Tenant/role/version/environment/promotion data model.
- Background work must be durable/recoverable in production.
- Provider-specific cache, structured output, usage, event, codec, and language capabilities normalized without pretending they are identical.
- Keep live path independent of post-call, analytics, and optimization work.

Detailed architecture: [06-technical-architecture.md](./06-technical-architecture.md), [13-api-data-security-contracts.md](./13-api-data-security-contracts.md).

## 23. API Requirements

Required domains:

- Agents and versions
- Business/platform brain drafts, optimize, validate, publish
- Provider catalog/status/validation
- Tier resolution
- Call start/end/list/detail/transcript/audio/trace/memory/outcome
- Benchmark sessions/scenarios/results
- Combination review/promotion/rollback
- Plivo answer/WebSocket/status/hangup

Contracts and behavior: [13-api-data-security-contracts.md](./13-api-data-security-contracts.md).

## 24. State / Memory Requirements

The complete memory system is normative in [12-brain-business-memory-spec.md](./12-brain-business-memory-spec.md).

Mandatory properties:

- Server-owned full internal memory.
- Add/set/remove/replace proposals under strict schema.
- Historical/current/alternative values, priorities, source, confidence, and turn.
- Immutable accepted/rejected event log.
- Protected fields and size/type limits.
- Deterministic relevance-based live projection with token limit.
- Async rolling summary.
- Small recent-turn window.
- Full ledger never sent live by default.
- Structured post-call outcome.

## 25. Security

- Backend-only provider/Plivo secrets.
- Authentication, tenant isolation, server-enforced RBAC.
- Separate platform-brain permission.
- Audio/transcript export permission.
- Encryption in transit/at rest.
- Configurable retention, deletion, legal hold, consent, and PII masking.
- Audit for versions, promotions, access, exports, and deletion.
- Signature/webhook validation only according to current official provider documentation.
- Safe selection allowlists and SSRF-safe integration configuration.

## 26. Error Handling

Every failure has explicit call behavior, fallback policy, user message, correlation ID, and metrics.

- STT: bounded reconnect; never invent transcript.
- LLM: approved retry/fallback only; static apology when needed.
- TTS: reconnect/fallback; browser may show text.
- Provider/model unavailable: block before call or use only approved fallback.
- Streaming: do not replay already audible text.
- Cache miss/unavailable: continue correctly and measure.
- Memory failure: keep previous state and continue.
- Post-call failure: retain ledger/audio, mark failed, durably retry.
- Plivo disconnect: idempotent finalization.

No silent fallback or secret-bearing provider errors.

## 27. Performance Requirements

- Preserve `STT → compact context → streaming LLM → sentence buffer → streaming TTS`.
- Memory extraction, summaries, archive I/O, analytics, and post-call work do not block TTFT or first audio.
- Maintain one perceived end-to-end clock and component clocks.
- Initial SLO candidate: P95 first audible ≤800 ms for tool-free turns where channel/provider supports it; validate by tier/channel.
- Browser barge-in stop target ≤200 ms.
- Cache effectiveness and steady-state TTFT must not regress beyond agreed benchmark threshold.
- Production call state and finalization survive worker/process restart.

## 28. Accessibility

Target WCAG 2.2 AA:

- keyboard operation and visible focus
- semantic landmarks/labels
- no color-only status
- accessible audio controls and transcript
- controlled `aria-live` for streaming content
- Telugu-capable typography
- reduced motion
- accessible chart summaries/tables
- validation and error summaries associated with fields

## 29. Responsive Design

- Desktop: persistent navigation, split-pane debugger, dense comparison.
- Tablet: collapsible navigation and stacked inspector.
- Mobile: configure essentials, run voice test, inspect call/outcome; benchmark comparisons become metric-by-metric.
- Do not hide critical capability solely due to viewport; adapt interaction and layout.

## 30. Analytics / Product Metrics

Product:

- agent setup completion/time
- test-to-promotion conversion
- draft validation failure reasons
- call review usage

Voice/operations:

- calls, completion, duration, interruptions, transfer/fallback
- first transcript/final STT, LLM TTFT/total, TTS first audio/total, first audible E2E P50/P95
- provider/model errors and availability
- task completion, disposition accuracy, quality rubrics
- token/cache/cache-write usage where available
- cost per call/minute by stage/channel/tier
- memory extraction success, rejection, stale turn, projection tokens
- post-call success/latency

## 31. Testing Strategy

- Unit: registry, resolver, compatibility, tier, memory operations/projection, version assembly, scoring.
- Contract: each provider adapter, normalized events/usage, schema support.
- API: auth/tenant/RBAC, disabled models, call idempotency, brain versioning, benchmarks, promotion.
- Integration: full browser call, archive, memory, outcome.
- Plivo: inbound stream/audio codec, START/MEDIA/STOP, hangup, barge-in.
- Regression: cache stability, TTFT, first audio, barge-in, current Sarvam/OpenAI behavior.
- Quality: Telugu/mixed-language scripted scenarios, STT WER, TTS human rubric, task/disposition fixtures.
- Security: secret leakage, cross-tenant access, signed URL, webhook validation, SSRF.
- Resilience: provider failure/fallback, worker restart, duplicate events, partial post-call.
- Accessibility/responsive manual and automated checks.

Tests are reported as passed only when actually executed.

## 32. Acceptance Criteria

1. Registry can add a provider/model without changing core pipeline behavior.
2. Exactly three configurable tiers resolve to valid versioned combinations.
3. ENV and FRONTEND modes enforce server-authoritative behavior.
4. Disabled/unsupported language models are hidden and rejected.
5. Current Sarvam/OpenAI browser streaming and barge-in regressions pass.
6. Customer raw sections are byte-preserved and compile deterministically into one business prompt.
7. Platform brain is inaccessible to customer roles.
8. Calls lock all brain/config versions at start.
9. Full memory preserves history/provenance; projection is relevant, deterministic, and token-bounded.
10. Invalid/protected memory operations are rejected and audited.
11. Memory processing does not materially delay TTFT/first audio.
12. Every finalized call has durable ledger, transcript, metadata, and explicit outcome status.
13. Audio archive contains user/agent and playable mixed output where recording is enabled.
14. Per-call detail correlates transcript/audio/latency/usage/errors/memory/outcome.
15. Aggregate analytics expose P50/P95, reliability, quality, cost, memory, and combination performance.
16. Benchmarks support compatible combination enumeration, progress, per-metric comparison, export, and review.
17. Promotion is versioned, approved, environment/tenant scoped, effective-dated, and rollback-capable.
18. Plivo configuration accepts server-side credentials, exposes safe status, and creates PSTN call records.
19. Cross-tenant and unauthorized sensitive reads/writes are denied.
20. No safe metadata/error/log endpoint exposes API keys.
21. Failure states are visible and fallbacks are explicit.
22. Retention/deletion/consent behavior is configurable and audited.

## 33. Migration / Backward Compatibility

1. Wrap current Sarvam/OpenAI integrations behind adapters before adding providers.
2. If new config is absent, current env behavior remains valid.
3. Preserve current API/WS contracts until clients migrate.
4. Preserve voice presets independently from tiers.
5. Migrate current one prompt into an initial platform/business split through explicit admin review; never silently reclassify customer rules.
6. Keep client localStorage export during transition, label it local-only, then make server Calls primary.
7. Map `ENABLE_SESSION_SUMMARY` to the new memory feature only through explicit migration; do not treat current string join as valid rolling summary.
8. Existing metrics fields remain available while durable dimensions are added.

## 34. Rollout Plan

High-level sequence only:

1. Freeze baselines and contracts.
2. Provider registry/resolver with current adapters.
3. Versioned agent/business/platform brain foundation.
4. Durable call lifecycle/ledger.
5. Full memory/event/projection and async summary.
6. Post-call outcome/audio archive.
7. UX mode gating, Calls, Test Studio, analytics.
8. Benchmark and promotion lifecycle.
9. New provider adapters gated by documentation/language/live tests.
10. Plivo inbound PSTN.
11. Multi-tenant hardening, durable jobs/storage, retention/audit.

Detailed sequence: [08-implementation-roadmap.md](./08-implementation-roadmap.md). Implementation must not begin until required decisions and PRD approval are complete.

## 35. Open Questions / Decisions Needed

**Resolved** — see [17-product-decisions.md](./17-product-decisions.md). Remaining implementation-time verification only (exact Plivo signature headers, SDK field names via Context7/docs).

---

# Required Final Output Appendices

## A. Executive Product Summary

A provider-agnostic, multi-tenant voice-agent platform that lets users structure and version business behavior, test compatible STT/LLM/TTS combinations over browser or phone, run natural low-latency calls with safe projected memory, inspect durable calls and traces, compare benchmark evidence, and promote approved configurations to production.

## B. Final User Journey

`Login/Tenant → Create Agent → Author Structured Business Brain → Review Optimized/Compiled Brain → Select Tier or Test Stack → Browser/PSTN Test → Inspect Live Trace/Memory → Run Benchmark → Review Per-Metric Results → Approve/Promote → Monitor Calls/Analytics → Iterate New Version`.

## C. Full Sitemap

Normative sitemap: [11-ui-information-architecture.md](./11-ui-information-architecture.md) §4.

## D. Feature Matrix

Each row is the compact Requirement/Why/User/System/Validation/Edge/Acceptance contract. Topic PRDs provide full examples and schemas.

| Feature / requirement | Why | User behavior | System behavior | Validation | Edge cases | Acceptance / result | Priority |
|---|---|---|---|---|---|---|---|
| Agent workspace | One deployable object replaces scattered controls | Admin edits draft and views active state | Persist agent/environment/version pointers | Brain, stack, channel, smoke test | Concurrent edit; disabled model | Every action identifies draft/active/effective version | P0 |
| Structured Business Brain | Users need understandable logic without fragmented prompts | Edit/toggle ordered sections; optimize/publish | Preserve raw; assemble and optimize one prompt | Required sections, conflicts, literals, budget | Optimizer changes meaning; stale edit | Byte-preserved raw and deterministic compiled component | P0 |
| Protected Platform Brain | Global safety/language/output rules cannot be tenant editable | Platform admin edits/tests/approves | RBAC, immutable versions, regression gate | Required contracts and precedence | Emergency rollback; tenant conflict | Customers cannot read/write; calls record version | P0 |
| Three tiers | Simple customer choice with controlled quality/cost | Choose LOW/MEDIUM/PREMIUM | Resolve versioned STT/LLM/TTS combination | Enabled models, language/channel compatibility | Assignment becomes invalid | Exactly three valid, auditable assignments | P0 |
| Provider registry | Add/test providers without core rewrites | Engineer inspects/enables safe catalog | Normalize adapters/capabilities/status | Keys, stage, language, stream, codec | Capability changes | Disabled/unsupported selection hidden and rejected | P0 |
| ENV/FRONTEND modes | Separate production simplicity from developer flexibility | Customer sees tiers; developer builds stack | Ignore unauthorized overrides; validate selection | Mode and server registry | Saved frontend selection becomes disabled | UI and API enforce same authoritative rules | P0 |
| Test Studio | Diagnose live behavior before production | Run browser/PSTN test and inspect events | Lock config; create test call/trace | Mic/Plivo/provider readiness | Disconnect; late memory; provider failure | Slowest/failed component identifiable each turn | P0 |
| Full memory + projection | Recall must not grow live tokens unbounded | Reviewer inspects state/projection/events | Validate proposals; preserve history; project relevance | Schema, types, protected paths, token cap | Contradiction; malformed update | History preserved; projection deterministic and bounded | P0 |
| Durable call archive | Browser storage is not a production record | Operator searches/replays call | Persist ledger, metadata, audio, outcome status | Tenant/access/file integrity | Missing end; duplicate end; partial audio | Finalized call has durable explicit artifact status | P0 |
| Post-call analysis | Operations need summary/outcome without live latency | Reviewer reads/retries authorized failure | Async structured analysis over full ledger | Strict schema; unknown→null | Model failure; too-short call | Complete or explicit retryable failed outcome | P0 |
| Benchmarks | Model choice needs reproducible evidence | Engineer runs scenarios/combinations | Version runs/results/artifacts | Compatibility, sample integrity, weights | Partial run; cancellation; pricing change | Per-metric winners, transparent composite, export | P1 |
| Promotion/rollback | Tested configurations need controlled production use | Reviewer approves and schedules assignment | State machine, audit, effective date, rollback | Required evidence/permissions | Provider disabled after approval | Active assignment links to immutable evidence/version | P1 |
| Per-call and fleet observability | Debugging and operations are different jobs | Inspect timeline or aggregate trends | Correlated traces and durable aggregates | Metric semantics and call/turn IDs | Missing provider usage field | Transcript/audio/trace align; P50/P95 available | P1 |
| Plivo PSTN | Real phone behavior differs from browser | Configure server credentials and test number | Answer/WS/audio bridge/call finalization | Safe status, codec, public URL, number | STOP missed; network jitter; KYC | PSTN call creates same archive/memory/outcome classes | P1 |
| RBAC/tenant/privacy | Customer data and platform prompts must remain isolated | User sees permitted data/actions | Auth, tenant scoping, encryption, retention, audit | Cross-tenant/role/security tests | export, deletion, legal hold | No unauthorized read/write or secret exposure | P0 |
| Knowledge/tools/transfer | Common production-agent extensions | Approved user configures capability | Separate versioned policies/traces | Capability-specific safety/evals | Tool timeout; unsafe action; transfer unavailable | Requires separate approved acceptance criteria | Recommended |

## E. Complete Acceptance Criteria

Section 32 is the release-level measurable acceptance list. Topic-level criteria appear in documents 03, 04, 07, 09, 11, 12, and 13.

## F. Requirements Traceability Matrix

Full matrix: [14-research-traceability.md](./14-research-traceability.md).

## G. Open Questions

Section 35 contains only unresolved product/deployment decisions.

## H. Recommended Implementation Order

Section 34 gives the approved high-level order. [08-implementation-roadmap.md](./08-implementation-roadmap.md) supplies topic sequencing but is subordinate to this master PRD.

## Research Basis

The authoritative URLs, verification date, evidence labels, source-to-requirement matrix, product inferences, and conflict decisions are in [14-research-traceability.md](./14-research-traceability.md).

Interpretation labels used by this PRD:

- Source requirement: directly from `fix.md`, `memory implemenation.md`, or `MEMORY_CALL_ARCHIVE_PLAN.md`.
- Current product evidence: verified in repository code/config/tests.
- Research-derived recommendation: informed by current official provider/framework documentation.
- Product inference: required to make the requested production/multi-tenant product coherent.
- Recommended enhancement: useful major-platform capability that is not mandatory until approved.
