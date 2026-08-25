# Observability, Metrics & SLOs

Per-call traces, fleet metrics, benchmark policy, and performance targets.

**Normative PRD:** [`prd/07-testing-metrics-observability.md`](../prd/07-testing-metrics-observability.md)

---

## 1. Philosophy

Measure what users experience — separate **per-call debugging** from **fleet analytics**:

| Layer | Purpose | UI location |
|-------|---------|-------------|
| Per-call trace | Diagnose one slow/failed turn | Call detail, Test Studio |
| Session metrics | Dev tuning during test | Test Studio sidebar |
| Fleet analytics | Trends, cost, disposition | Analytics nav |
| Benchmarks | Combination comparison | Benchmarks nav (disabled until configured) |

---

## 2. Performance SLOs (targets)

From master PRD §27 — validate per tier/channel in Test Studio:

| SLO | Target | Measurement |
|-----|--------|-------------|
| P95 first audible (tool-free turn) | ≤800 ms | `e2e_ms` where channel supports |
| Browser barge-in stop | ≤200 ms | Client `live-guards` + trace |
| Cache hit rate (steady state) | ≥85% (baseline ~90%) | `cached_tokens / input_tokens` after turn 2 |
| Post-call outcome ready (p95) | <60 s after `call/end` | `post_call_latency_ms` |
| Memory merge (async) | <500 ms after stream end | `memory_merge_ms` in trace |

**Regression gate:** No phase may regress E2E TTFA >10% vs Phase 0 baselines without explicit approval.

---

## 3. Per-turn metrics

**Owner:** extend `server/utils/metrics.py`; persist per-call in trace store.

| Metric | Definition |
|--------|------------|
| `stt_first_partial_ms` | First partial transcript |
| `stt_final_ms` | Last audio → final transcript |
| `llm_ttft_ms` | Request → first text delta |
| `llm_total_ms` | Request → stream done |
| `tts_first_audio_ms` | First text chunk → first audio byte |
| `tts_total_ms` | TTS start → last byte |
| `e2e_ms` | STT final → TTS first audio |
| `memory_merge_ms` | Stream done → B updated |
| `interruption` | Barge-in event flag |

### Token metrics (per LLM call)

`input_tokens`, `output_tokens`, `cached_tokens`, `cache_write_tokens` (null if not exposed), `cache_hit_rate`.

---

## 4. Per-call trace model

**API:** `GET /api/call/{call_id}/trace`  
**Phase:** 3 stub (ledger spans); Phase 4 full (memory spans); Phase 5 UI

```json
{
  "call_id": "uuid",
  "combination_id": "...",
  "compiled_brain_version": "...",
  "turns": [
    {
      "turn": 1,
      "stt_final_ms": 120,
      "llm_ttft_ms": 85,
      "tts_first_audio_ms": 42,
      "e2e_ms": 680,
      "token_usage": { "input": 2100, "cached": 1900, "output": 38 },
      "memory_ops_applied": 2,
      "provider_fallback": null,
      "errors": []
    }
  ],
  "interruption_count": 1,
  "provider_errors": []
}
```

### Extended metrics API

`GET /api/metrics/calls/{call_id}` — same payload + aggregates for Call detail UI.

Existing `GET /api/metrics` remains for **session-level** dev aggregates during interim SPA.

---

## 5. Cost estimation

Registry exposes `pricing_metadata` per provider/model (manually updated).

| Env var | Purpose |
|---------|---------|
| `FX_RATE_INR` | Default `95.64` — INR display |
| `PLIVO_NUMBER_MONTHLY_COST_USD` | Phone amortization per minute |

Formulas per `prd/07` §2.4 — shown in Analytics and call detail (estimated, not billing).

---

## 6. Benchmark policy (CD-020)

| Rule | Implementation |
|------|----------------|
| Auto-runs disabled by default | `ENABLE_BENCHMARKS=false` |
| UI present but inert | Benchmarks nav shows "Not configured" until enabled |
| Stub APIs return 403 or empty | `routes/benchmarks.py` gated |
| Owner configures scenarios | Post-MVP Phase 6 full implementation |

### Stub endpoints (Phase 5)

- `GET /api/benchmark-sessions` → `[]` or 403
- `GET /api/test-scenarios` → `[]` or 403
- Full contract in `prd/13` §5 — implement when `ENABLE_BENCHMARKS=true`

---

## 7. Fleet analytics (MVP basics — Phase 5)

Not full fleet v2; ship:

- Calls today / volume trend
- Disposition breakdown
- P50/P95 latency by stage
- Error rate by provider
- Estimated cost per call/minute

Full rubrics, quality scoring, composite winners → Post-MVP Phase 6.

---

## 8. Logging & correlation

- Every API error includes `request_id`
- Trace spans correlate `call_id`, `turn`, `request_id`
- Provider errors logged with `provider`, `model`, `retryable` — never raw secrets
- Fallback events: `fallback_used`, `original_provider`, `fallback_provider`

---

## 9. Testing

| Test | Phase |
|------|-------|
| `test_metrics_per_call.py` | 4 |
| `test_trace_api.py` | 3–4 |
| `test_brain_caching.py` (extend) | 1+ |
| Golden disposition fixtures | 4 |
| Optional `LIVE_TEST=1` latency | All |

---

## 10. Implementation phases

| Capability | Phase |
|------------|-------|
| Extend session `/api/metrics` with `call_id` | 3 |
| Per-call trace persistence | 3–4 |
| `GET /api/metrics/calls/{call_id}` | 4 |
| Call detail trace UI | 5 |
| Analytics dashboard basics | 5 |
| Benchmark shell UI + stub APIs | 5 |
| Full benchmark runs | Post-MVP |
