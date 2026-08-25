# 10 — PRD Re-Audit (25 Aug 2026)

Second-pass audit of PRD pack vs **`fix.md`**, **`memory implemenation.md`**, **`MEMORY_CALL_ARCHIVE_PLAN.md`**, codebase, and web research.

Historical note: this document records PRD coverage before the v2 master. A `✅` means the requirement was captured in documentation, not implemented in the repository. The authority order in `README.md` applies.

---

## 1. Audit summary

| Area | v1.0 PRD | Re-audit result |
|------|----------|-----------------|
| fix.md §1–18 provider/tiers/testing | Mostly covered | **Fixed:** scoring env names, STT metrics, Test A–E matrix, registry `pricing_metadata`, deliverables traceability |
| memory implemenation.md | Mostly covered | **Fixed:** working memory schema detail, file paths, outcome schema, instruction order, naming conventions, VOICE ENGINE layers |
| MEMORY_CALL_ARCHIVE_PLAN | Partially aligned | **Fixed:** `channel`, `callerId`, `transcript.json`, `audio/` subfolder, `outcome_status`, barge-in partial ledger |
| Plivo telephony | **Missing** | **Added:** [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md) |
| Context7 | Not available | Noted; re-verify SDKs at implementation |
| Ambiguities | Several open | **Resolved** in §3 below |

---

## 2. Requirement coverage matrix

### fix.md

| Section | Req | PRD location | Status |
|---------|-----|--------------|--------|
| §1 Core objective | STT→LLM→TTS interchangeable | 01, 03 | ✅ |
| §2 Three tiers | LOW/MEDIUM/PREMIUM env | 03 §4 | ✅ |
| §3 DeepSeek V4 | Adapter + env | 03 §7.3 | ✅ |
| §4 Model registry | Central registry + metadata | 03 §2 | ✅ (added `pricing_metadata`) |
| §5 Env mode | Tier only UI | 05 §3.1 | ✅ |
| §6 Frontend mode | Full matrix | 05 §3.2 | ✅ |
| §7 Plugin visibility | ENABLE_* gates | 03 §2.4 | ✅ |
| §8 API keys server-side | Never in browser | 03 §8, 06 §11 | ✅ |
| §9 Test combinations | A–E examples | 07 §4.4 | ✅ added |
| §10 Metrics | STT/LLM/TTS/E2E full set | 07 §2 | ✅ (added first-transcript, duration) |
| §11 Combination score | Configurable weights | 07 §5 | ✅ (aligned env names) |
| §12 Config priority | ENV → resolver → session | 02 §5 | ✅ |
| §13 Session config snapshot | Log at start | 03 §4.4, 04 §3 | ✅ |
| §14 Frontend UX | Tier chips + cost hint | 05 | ✅ |
| §15 Don't break existing | Preserve live path | 00, 02 EX-* | ✅ |
| §16 Backward compat | Fallback defaults | 03 §1 | ✅ |
| §17 Env example | Full .env block | 03, 09 | ✅ |
| §18 Deliverables | A–G list | 08 §11, README | ✅ |
| Cartesia docs URL | Reference | README refs | ✅ added |
| Provider-agnostic interfaces | STT/LLM/TTS ABCs | 03 §3 | ✅ |

### memory implemenation.md

| Topic | PRD location | Status |
|-------|--------------|--------|
| Three information layers | 04 §1 | ✅ |
| Working memory JSON | 04 §2 | ✅ expanded schema |
| memory_update operations | 04 §2.2 | ✅ |
| spoken_response + memory_update split | 02 C1, 04 | ✅ hybrid streaming |
| Rolling summary async 4–6 turns | 04 §2.4 | ✅ |
| call ledger never in live brain | 04 §1 ML-10 | ✅ |
| transcript.jsonl untruncated | 04 §4 | ✅ |
| user.pcm + agent.pcm + mix.wav | 04 §4 | ✅ paths aligned |
| outcome.json schema | 04 §5 | ✅ aligned with source |
| raw vs optimized business prompt | 04 §6 | ✅ |
| compiled brain versioning | 04 §6 | ✅ |
| Platform vs provider separation | 02 §2.6 VOICE ENGINE | ✅ added |
| Module list (working_memory, call_ledger, etc.) | 06 §4 | ✅ |
| Naming: cached_brain_prompt, call_ledger | 04 §2.3, 06 | ✅ |
| Cost picture (cached vs dynamic) | 04, 07 | ✅ |
| Post-call NOT spoken JSON | 02 C1, 04 §5 | ✅ |

### MEMORY_CALL_ARCHIVE_PLAN.md

| Topic | Status |
|-------|--------|
| `channel: browser\|pstn` | ✅ 04 §3, 09 |
| `callerId` on call/start | ✅ 04, 09 |
| `transcript.json` closed file | ✅ 04 §4 |
| `audio/` subfolder | ✅ 04 §4 |
| `outcome_status=failed` retry | ✅ 04 §5 |
| Partial agent on barge-in | ✅ 04 §4.3 |
| Idle TTL auto-finalize | ✅ 04 §3.4 |
| `call/end` 202 Accepted async | ✅ 04 §3 |

---

## 3. Ambiguities resolved (changelog)

| ID | Ambiguity | Resolution | Updated in |
|----|-----------|------------|------------|
| A1 | Scoring env: `BENCHMARK_WEIGHT_*` vs `VOICE_SCORE_*` | **Canonical:** `VOICE_SCORE_*` from fix.md; code may accept both as aliases | 07 §5 |
| A2 | Memory update Option A vs B | **Closed:** Option A (async second structured call) for v1 | 02 §7 Q2 |
| A3 | Working memory message role | **user** role with `[Working memory]` prefix (cache-safe); not inside cached developer block | 04 §2.3 |
| A4 | `compiled_brain` vs `cached_brain_prompt` | Same artifact; code name `cached_brain_prompt`, product term `compiled_brain` | 04 §6 |
| A5 | `extracted_fields` vs `extracted` | **Canonical:** `extracted` (matches source docs) | 04 §5 |
| A6 | `preferences` object vs array | **Canonical:** array of strings + structured sub-objects per memory doc | 04 §2.1 |
| A7 | File names at root vs `audio/` | **Canonical:** `audio/user.pcm`, `audio/agent.pcm`, `audio/mix.wav` | 04 §4 |
| A8 | Default CONFIG_MODE | **Production:** `env`; **dev compat:** `frontend` if unset | 02 §7 Q1 |
| A9 | Plivo in scope? | **Yes** — telephony transport layer, optional via `ENABLE_PLIVO` | 09 |
| A10 | `GEMINI_API_KEY` in fix §8 | Listed in provider secrets table | 03 §7 |

---

## 4. Gaps still deferred (intentional)

| Gap | Reason | Phase |
|-----|--------|-------|
| Plivo signature validation details | Exact official request-signing procedure must be re-verified during implementation; validation itself is mandatory in production | implementation gate |
| Outbound call UI | REST API doc only | v1.1 |
| Vector RAG cross-call memory | Performance risk mid-turn | Post-v1 |
| Multi-tenant auth | Out of PRD v1 scope | Post-v1 |
| OTLP export | Observability v2 | Phase F backlog |

---

## 5. External research applied

| Source | Principle applied |
|--------|-------------------|
| Pipecat / Vapi patterns | Async memory; no ledger on hot path |
| Plivo Audio Streaming docs | μ-law 8 kHz bidirectional WS; clearAudio barge-in |
| OpenAI caching guidance | Stable prefix first; dynamic tail after breakpoint |
| AWS LCA | Stereo mix caller-left agent-right |
| 2026 voice observability | Component + E2E latency, not model-only benchmarks |

---

## 6. Pre-implementation verification checklist

- [ ] Re-verify OpenAI Responses streaming + json_schema (Context7 or official docs)
- [ ] Confirm Cartesia model IDs from https://docs.cartesia.ai
- [ ] Confirm Sarvam accepts transcoded PCM from μ-law bridge
- [ ] Plivo India KYC if using +91 numbers
- [ ] Run baseline browser latency before PSTN comparison
