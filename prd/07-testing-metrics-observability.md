# 07 — Testing, Metrics, and Observability

Benchmark framework, SLOs, scoring weights, traces, and quality evaluation.

Combines **`fix.md` §10–11**, existing `metrics.py`, and 2026 voice observability research.

**Current vs target:** current `/api/metrics` is in-memory and exposes aggregate stage latency, brain token/cache data, and recent brain turns. Per-turn STT partial/final timing, durable call traces, benchmark sessions, and fleet analytics below are target requirements.

**Benchmark policy (locked `17` §1):** Automated benchmark runs are **disabled by default** until product owner configures scenarios and enables them. Dev Console may expose benchmark UI inert until `ENABLE_BENCHMARKS=true` or equivalent config.

---

## 1. Observability philosophy

Measure what users experience:

1. **Component latency** — STT final, LLM TTFT, TTS first audio
2. **End-to-end latency** — user stops speaking → agent audio starts
3. **Task quality** — scripted scenario rubrics, disposition accuracy
4. **Reliability** — error rate, retry rate, call completion rate
5. **Cost** — tokens, cache hit rate, INR/USD per minute

Avoid ranking combinations by a single benchmark number without weights.

---

## 2. Metric definitions

### 2.1 Latency metrics (per turn)

| Metric | Definition | Source |
|--------|------------|--------|
| `stt_first_partial_ms` | First STT partial transcript | WS STT events |
| `stt_final_ms` | Last audio frame → final transcript | WS STT events |
| `stt_duration_ms` | Utterance audio duration processed | STT events |
| `llm_ttft_ms` | Request sent → first text delta | Brain SSE |
| `llm_total_ms` | Request sent → stream done | Brain SSE |
| `tts_first_audio_ms` | First text chunk sent → first audio byte | TTS WS |
| `tts_total_ms` | TTS request → last audio byte | TTS WS |
| `tts_chars` | Characters synthesized | TTS |
| `audio_duration_ms` | Agent audio played duration | TTS/player |
| `e2e_ms` | STT final → TTS first audio | Client or server composite |

### 2.2 Token metrics (per LLM call)

| Metric | Source |
|--------|--------|
| `input_tokens` | OpenAI usage |
| `output_tokens` | OpenAI usage |
| `cached_tokens` | OpenAI usage details |
| `cache_write_tokens` | Provider usage when explicitly exposed; otherwise `null`, never inferred |
| `cache_hit_rate` | `cached / input` rolling |

### 2.3 Call metrics (per call)

| Metric | Definition |
|--------|------------|
| `duration_sec` | start → end |
| `turn_count` | user turns |
| `interruption_count` | barge-in events |
| `error_count` | provider errors |
| `disposition` | from outcome |
| `post_call_latency_ms` | end → outcome ready |

### 2.4 Cost metrics (estimated)

| Metric | Formula |
|--------|---------|
| `cost_stt_usd` | audio duration × provider rate |
| `cost_tts_usd` | characters × provider rate |
| `cost_brain_usd` | token usage × model price (minus cache discount) |
| `cost_total_usd` | sum |
| `cost_per_minute_inr` | `cost_total / (duration_sec/60) × FX_RATE` |

Env: `FX_RATE_INR=95.64`, provider rates in registry `pricing_metadata` (updated manually).

Phone number amortization (Plivo or any PSTN provider):

`phone_per_min = PLIVO_NUMBER_MONTHLY_COST_USD × FX_RATE_INR / EXPECTED_MINUTES_PER_MONTH`

Legacy alias: `PHONE_NUMBER_MONTHLY_COST` → same as `PLIVO_NUMBER_MONTHLY_COST_USD`.

---

## 3. Existing metrics API (extend)

### `GET /api/metrics` (current)

Returns session aggregates: p50/p95 stt, brain, tts, e2e, brain tokens, cache layers.

### Extensions

```json
{
  "session": { ... existing ... },
  "call_id": "uuid",
  "resolved_stack": { ... },
  "per_turn": [
    {
      "turn": 1,
      "stt_final_ms": 120,
      "llm_ttft_ms": 80,
      "tts_first_audio_ms": 45,
      "e2e_ms": 695,
      "token_usage": { "input": 2100, "cached": 1900, "output": 42 }
    }
  ],
  "provider_errors": []
}
```

### `GET /api/metrics/calls/{call_id}`

Full per-turn trace for call detail UI.

### `GET /api/metrics/benchmarks`

List benchmark runs with scores.

---

## 4. Benchmark runs

### 4.1 Entity

```json
{
  "run_id": "uuid",
  "created_at": "ISO8601",
  "combination": {
    "stt": { "provider": "sarvam", "model": "saaras:v3" },
    "llm": { "provider": "openai", "model": "gpt-5.6-luna" },
    "tts": { "provider": "sarvam", "model": "bulbul:v3" }
  },
  "scenario_id": "telugu_sales_5turn",
  "metrics": {
    "stt_p50_ms": 110,
    "llm_ttft_p50_ms": 85,
    "tts_first_p50_ms": 40,
    "e2e_p50_ms": 680,
    "e2e_p95_ms": 920,
    "cost_per_minute_inr": 1.70,
    "cache_hit_rate": 0.91
  },
  "quality": {
    "rubric_score": 0.85,
    "disposition_match": true
  },
  "weighted_score": 0.82
}
```

### 4.2 Scenarios (fixtures)

| ID | Description |
|----|-------------|
| `telugu_greeting_3turn` | Basic greeting + name capture |
| `telugu_sales_5turn` | Product interest + budget |
| `telugu_objection_4turn` | Objection handling |
| `english_mixed_3turn` | Code-switch Telugu/English |

Stored: `server/tests/fixtures/scenarios/`

### 4.3 Execution modes

| Mode | Entry |
|------|-------|
| Live manual | Test tab → save run |
| Scripted REST | `POST /api/benchmarks/run` |
| CI | `pytest` + `benchmark_voice_cache.py` pattern |

---

### 4.4 fix.md reference test matrix (Test A–E)

| ID | STT | LLM | TTS |
|----|-----|-----|-----|
| Test A | Sarvam | DeepSeek V4 | Sarvam TTS |
| Test B | Sarvam | DeepSeek V4 | Cartesia Sonic |
| Test C | Cartesia Ink | DeepSeek V4 | Cartesia Sonic |
| Test D | Sarvam | Gemini | Sarvam TTS |
| Test E | Cartesia Ink | OpenAI | Cartesia Sonic |

Run each on **browser** and **PSTN** (when Plivo enabled) for transport comparison.

---

## 5. Scoring weights (configurable)

**Canonical env names** from `fix.md` §11:

```bash
VOICE_SCORE_LATENCY_WEIGHT=0.40
VOICE_SCORE_COST_WEIGHT=0.30
VOICE_SCORE_QUALITY_WEIGHT=0.25
VOICE_SCORE_ACCURACY_WEIGHT=0.05
```

**Backward-compat aliases** (implementation may accept either):

```bash
BENCHMARK_WEIGHT_LATENCY=0.40
BENCHMARK_WEIGHT_COST=0.30
BENCHMARK_WEIGHT_QUALITY=0.30
```

If both sets are present, `VOICE_SCORE_*` wins. Canonical weights must be non-negative and sum to 1.0 (within validation tolerance). If only the legacy three aliases are supplied, `accuracy_weight=0` and the three supplied values are normalized to 1.0; the resolved weights are stored with every benchmark result.

### 5.1 Sub-score normalization

Each sub-score 0–1 within run batch:

| Sub-score | Formula (example) |
|-----------|-------------------|
| `latency_score` | `1 - clamp(e2e_p95 / LATENCY_TARGET_MS, 0, 1)` |
| `cost_score` | `1 - clamp(cost_per_min / COST_TARGET_INR, 0, 1)` |
| `quality_score` | rubric average (TTS naturalness, conversation quality, Telugu quality) |
| `accuracy_score` | STT WER / disposition match on scripted scenarios |

`LATENCY_TARGET_MS=800`, `COST_TARGET_INR=2.0` (env tunable).

### 5.2 Weighted score

```
weighted = w_lat × latency_score + w_cost × cost_score + w_qual × quality_score + w_acc × accuracy_score
```

Expose weights in Config tab (read-only from env).

---

## 6. SLOs and alerts (production)

| SLO | Target | Window |
|-----|--------|--------|
| E2E p95 | ≤ 800 ms | 1h rolling |
| Call completion rate | ≥ 99% | 24h |
| Post-call success | ≥ 98% outcome generated | 24h |
| Cache hit rate (turn 2+) | ≥ 85% | 24h |
| Provider error rate | ≤ 1% turns | 1h |

**Alert hooks (v1):** log threshold warnings; external APM deferred.

---

## 7. Trace model (OpenInference-aligned)

Span names for export:

```
voice.call
  voice.turn.{n}
    stt.transcribe
    llm.stream
    llm.memory_update      # async child
    tts.synthesize
voice.post_call
  llm.outcome
```

Attributes:

- `call_id`, `session_id`, `tier`
- `provider.stt`, `provider.llm`, `provider.tts`
- `model.stt`, `model.llm`, `model.tts`
- token usage fields
- `disposition` (on call span)

v1: JSON export `GET /api/call/{id}/trace`. OTLP export Phase F.

---

## 8. Quality evaluation

### 8.1 Rubric dimensions (scripted scenarios)

| Dimension | Weight |
|-----------|--------|
| Correct language (Telugu) | 0.25 |
| Task completion (captured name/intent) | 0.35 |
| Naturalness (human or LLM-judge) | 0.20 |
| Policy compliance | 0.20 |

### 8.2 Disposition accuracy

Golden set: 20+ transcripts with expected disposition.

Metric: exact match + partial credit for `disposition_detail` keyword overlap.

### 8.3 STT quality

WER on fixed audio fixtures (existing STT REST path).

### 8.4 TTS quality

Manual Telugu rating scale 1–5 on fixture phrases (semi-automated in v1).

---

## 9. Logging

Extend existing category logs (`LOG_BRAIN`, etc.):

| Category | Content |
|----------|---------|
| `call` | start/end, call_id |
| `memory` | operations applied (redact PII in prod) |
| `provider` | adapter errors with provider id |
| `benchmark` | run_id, score |

**Never log:** API keys, full compiled brain in prod (hash only).

---

## 10. Dashboards summary

| View | Primary metrics |
|------|-----------------|
| Voice (live) | last turn E2E, connection status |
| Metrics tab | session p50/p95, cache, tokens |
| Call detail | per-turn waterfall, disposition |
| Test tab | combination score, comparison |
| Ops (future) | SLO tiles, error rate by provider |

---

## 11. Test plan matrix

| ID | Test | Type |
|----|------|------|
| T-01 | Registry loads all providers | unit |
| T-02 | Disabled provider 400 | api |
| T-03 | Tier resolution MEDIUM | unit |
| T-04 | Working memory merge ops | unit |
| T-05 | call/start → end → outcome | integration |
| T-06 | Cache hit with memory enabled | integration |
| T-07 | Transcript not truncated in ledger | integration |
| T-08 | Benchmark weighted score | unit |
| T-09 | E2E latency LIVE_TEST | live optional |
| T-10 | Barge-in policy unchanged | js unit |
| T-11 | Disposition golden set | integration |
| T-12 | env mode catalog hides disabled | api |

---

## 12. Reference baselines (from repo probes)

Documented for comparison (Aug 2026, Telugu live path):

| Component | USD/min | INR/min |
|-----------|---------|---------|
| STT | 0.0052 | 0.50 |
| TTS | 0.0117 | 1.12 |
| Brain | 0.0009 | 0.09 |
| **Talking total** | **0.0178** | **1.70** |

Fully loaded with $5.30/mo number at 500 min/mo: ~$0.028/min (~₹2.71).

New combinations should be compared against these baselines in benchmark UI.

---

## 13. Acceptance criteria

- [ ] Per-turn metrics visible in call detail for all turns
- [ ] Benchmark run saved with weighted score from env weights
- [ ] Two runs comparable in UI with latency waterfall
- [ ] `GET /api/metrics` backward compatible for existing fields
- [ ] Cache hit rate reported per call and session
- [ ] Cost estimate within 10% of live probe for Sarvam+OpenAI baseline
- [ ] Golden disposition tests ≥80% pass rate before release
