# 08 — Recommended High-Level Delivery Order

This is the limited sequencing requested after completion of the PRD. It is not a code-level implementation plan and does not authorize implementation.

**Before each phase:** read [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) and [../implementation/SKILLS-AND-MCP-GUIDE.md](../implementation/SKILLS-AND-MCP-GUIDE.md).

## Engineering implementation pack (5 phases)

The PRD phases 0–9 above are consolidated for engineering into **5 delivery phases**:

| Engineering phase | File | PRD `08` mapping |
|-------------------|------|------------------|
| 1 — Foundation & Platform | [../implementation/phase-01-foundation-and-platform.md](../implementation/phase-01-foundation-and-platform.md) | 0 + 1 |
| 2 — Brains & Agents | [../implementation/phase-02-brains-and-agent-workspace.md](../implementation/phase-02-brains-and-agent-workspace.md) | 2 |
| 3 — Call Lifecycle | [../implementation/phase-03-call-lifecycle-and-persistence.md](../implementation/phase-03-call-lifecycle-and-persistence.md) | 3 |
| 4 — Memory & Intelligence | [../implementation/phase-04-memory-and-post-call-intelligence.md](../implementation/phase-04-memory-and-post-call-intelligence.md) | 4 |
| 5 — Production & Launch | [../implementation/phase-05-production-ui-telephony-and-launch.md](../implementation/phase-05-production-ui-telephony-and-launch.md) | 5 + 7–9 (MVP subset) |

Architecture detail: [../architecture/README.md](../architecture/README.md).  
Alignment audit: [../implementation/PRD-TRACEABILITY-AUDIT.md](../implementation/PRD-TRACEABILITY-AUDIT.md).

## Sequencing principles

1. Preserve and baseline current behavior before abstraction.
2. Establish versioned configuration before durable calls depend on it.
3. Establish durable call records before memory and post-call analysis.
4. Prove browser behavior before adding PSTN transport.
5. Enable a provider/language only after documentation, compatibility, and live benchmarks pass.
6. Introduce production tenancy/storage before onboarding multiple customers.

**Product decisions locked:** [17-product-decisions.md](./17-product-decisions.md).

## MVP focus (locked)

Build a **small end-to-end MVP** first:

1. Dev Portal (auth, stack UI, Platform Brain, tier assignment testing) — **UI shipped** at `web/app/dev` (`/dev/login`, `/dev`, `/dev/stack`, `/dev/platform-brain`, `/dev/promotion`, Test Studio). Remaining: token/visual alignment per [20](./20-visual-design-and-ui-style.md), not a new portal.
2. Live browser voice test with same-LLM structured turns + compact memory
3. Agent + compiled brain versioning
4. Call ledger + post-call disposition
5. PostgreSQL locally; **Railway** project: **Next.js web** + **API** + **Worker** ([19](./19-frontend-backend-nextjs-railway.md))
6. Outbound campaigns + Plivo (outbound prioritized)
7. Business Console (structured business brain, numbers) — customer auth may follow Dev Portal

Full v2 analytics/fleet UI can trail core E2E path.

## Phase 0 — Approval and baselines

Outcomes:

- Master PRD, conflicts, roles, disposition taxonomy, retention scope, and Plivo launch scope approved.
- Existing browser latency, caching, barge-in, quality, and test baselines recorded.
- Current API/WS contracts documented as compatibility tests.

Exit criteria:

- Required open questions have owners and dates.
- No implementation starts against an ambiguous prompt/memory/provider contract.

## Phase 1 — Configuration and provider foundation

Outcomes:

- Provider/model registry and capability/language validation.
- Standardized STT/LLM/TTS contracts around current Sarvam/OpenAI behavior.
- Exactly three versioned tier assignments.
- ENV/FRONTEND mode behavior.
- Agent, combination, environment, and configuration version identities.

Exit criteria:

- Current browser path performs within agreed regression limits.
- Disabled/unsupported provider selections are rejected.

## Phase 2 — Versioned brains and agent workspace

Outcomes:

- Separate protected Platform Brain and structured customer Business Brain.
- Raw-preserving section assembly, optimization, validation, compiled preview, and version lock.
- Agent workspace showing draft/active status and deployment impact.

Exit criteria:

- Raw text and deterministic compilation tests pass.
- In-flight calls remain on the version with which they started.

## Phase 3 — Durable call lifecycle

Outcomes:

- Start/end/read lifecycle with idempotent finalization.
- Server-owned transcript ledger, call metadata, audio archive, and durable production persistence.
- Calls list and baseline call detail.

Exit criteria:

- Process interruption does not lose finalizable calls.
- Browser localStorage is no longer the production source of truth.

## Phase 4 — Memory and post-call intelligence

Outcomes:

- Full internal memory, validated event log, live projection, async rolling summary, and bounded recent turns.
- Structured post-call outcome and retryable analysis status.
- Memory and outcome panels in call detail.

Exit criteria:

- Memory history/projection/safety fixtures pass.
- Memory processing does not materially regress TTFT/first audio.

## Phase 5 — Test Studio and observability

Outcomes:

- Live browser test workspace.
- Unified per-call transcript/audio/trace/memory/error timeline.
- Separate aggregate latency, quality, reliability, usage/cost, and memory analytics.

Exit criteria:

- A developer can diagnose the slowest/failed pipeline component for any test turn.

## Phase 6 — Benchmark and promotion lifecycle

Outcomes:

- Versioned scenarios, benchmark sessions, compatible combination enumeration, progress, results, exports, and reviewer annotations.
- Per-metric winners and transparent optional composite scores.
- Reviewed/approved/effective-dated tier/environment promotion with rollback.

Exit criteria:

- Every active tier assignment links to approved benchmark evidence and immutable versions.

## Phase 7 — Additional providers

Outcomes:

- DeepSeek and Gemini LLM adapters.
- Cartesia TTS and STT only for officially supported/verified languages.
- Provider-specific cache, structured-output, usage, and stream semantics represented accurately.

Exit criteria:

- Contract, resilience, quality, language, cost, and latency benchmarks pass before provider promotion.

## Phase 8 — Plivo PSTN

Outcomes:

- Safe server-side Plivo configuration/status.
- Inbound bidirectional audio streaming, codec bridge, barge-in, caller metadata, and hangup finalization.
- Browser-vs-PSTN benchmark dimension.

Exit criteria:

- Inbound test calls create the same durable call/memory/outcome artifacts as browser tests.
- PSTN latency and audio quality meet approved channel targets.

Outbound calling remains a separate launch decision.

## Phase 9 — Production multi-tenant hardening

Outcomes:

- Tenant isolation, RBAC, durable jobs, database/object storage, encryption, retention/deletion, audit, signed access, and operational alerting.
- Production deployment/environment governance.

Exit criteria:

- Security, resilience, privacy, load, recovery, and tenant-isolation tests pass.

## Recommended enhancement sequence

Only after core platform acceptance:

1. Knowledge base with separate retrieval evaluation.
2. Schema-defined tools/actions.
3. Human transfer/escalation.
4. Quality review queue.
5. Outbound campaigns/numbers with consent and calling-window controls.

These remain recommendations until separately approved.
