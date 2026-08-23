# Token Optimization Guide (v5)

**Telugu Voice Agent** — single brain prompt architecture.  
**Goal:** one composed brain prompt per request, always cache-eligible, full token telemetry via `LOG_BRAIN`.

> **References**
> - [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
> - [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
> - [Responses API](https://developers.openai.com/api/docs/api-reference/responses)

---

## 1. Main issue

Today the brain sends **three separate prompt layers** to OpenAI on every turn:

| # | What | Where | ~Tokens | Problem |
|---|------|-------|---------|---------|
| 1 | `instructions` | top-level field | ~515 | Cannot use `prompt_cache_breakpoint` |
| 2 | Core (again) + behaviour tags + business tags | `developer` string | ~897 | **Duplicate core (~515 wasted)** |
| 3 | History + transcript | `input` user msgs | 400–1,500 | Resent every turn |

```95:98:server/services/openai_brain_service.py
    create_kwargs: dict = {
        "model": use_model,
        "instructions": CORE_SYSTEM_PROMPT,
        "input": input_messages,
```

**Measured today (factory defaults, no history):** ~1,412 static tokens/turn before history.

---

## 2. Target architecture — one brain prompt only

### 2.1 Principle

> **One document. One API message. One cache breakpoint.**

The user edits behaviour/business in the Fine-tune console for convenience. The server **composes them into one string** before any OpenAI call. OpenAI never sees `instructions` + `developer` + XML tags as separate layers.

```
┌──────────────────────────────────────────────────────────────────┐
│  SOURCE (server — not sent as separate API fields)               │
│                                                                  │
│  server/prompts/brain_prompt.py     factory sections             │
│  instruction_store (per session)    user behaviour + business  │
│  brain_prompt_composer.py           merges → ONE string          │
└────────────────────────────┬─────────────────────────────────────┘
                             │  validate ≤ brainPromptBudgetTokens
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  OPENAI REQUEST (per turn)                                       │
│                                                                  │
│  input[0]  developer / input_text  ← SINGLE brain prompt         │
│            [prompt_cache_breakpoint]  (always ON — min 1,500)    │
│  input[1..]  truncated history (dynamic, NOT cached)           │
│  input[N]    current transcript (dynamic, NOT cached)            │
│                                                                  │
│  ❌ NO top-level `instructions` field                            │
│  ❌ NO separate behaviour/business messages                      │
│  ❌ NO XML wrapper tags in the sent text                         │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 What changes in the codebase

| Today (remove) | Tomorrow (single source) |
|----------------|--------------------------|
| `instructions: CORE_SYSTEM_PROMPT` | **Omitted** |
| `build_agent_instructions()` with XML tags | `compose_brain_prompt()` → plain text |
| `system_prompt.py` alone | Merged into `brain_prompt.py` |
| `voice_defaults.py` separate sections | Default sections inside `brain_prompt.py` |
| 10,000-char caps per channel | Budget ceiling **1,500–5,000** tokens on composed string |

### 2.3 User budget: **1,500 – 5,000 tokens** (UI minimum)

| Setting | UI range | Default | Caching |
|---------|----------|---------|---------|
| `brainPromptBudgetTokens` | **1,500 – 5,000** | **1,500** | **ON when prompt ≥1,024 tokens** |

**Why UI minimum is 1,500 (not 100 or 1,024):**

- OpenAI requires **≥ 1,024 tokens** through the breakpoint for GPT-5.6 caching.
- Factory defaults compose to ~1,058 tokens — Phase 1 expanded examples so the default prompt exceeds OpenAI's 1,024 cache minimum.
- Setting the slider floor to **1,500** means users **cannot accidentally disable caching** by picking a small-looking budget.
- No runtime trimming logic is needed — the budget is a **ceiling**, validated on save (see §4.2).

| Budget | Use case |
|--------|----------|
| **1,500** (default) | Standard voice — safety + Telugu + behaviour + moderate business |
| **1,500 – 2,000** | Recommended sweet spot for most deployments |
| **2,001 – 5,000** | Heavy business context, long product catalogues |

UI shows a badge: **✅ Caching ON** when `estimatedTokens ≥ 1,024`, otherwise **⚠️ Caching OFF** (budget slider floor 1,500 still prevents low-budget trap).

### 2.4 Request shape (final)

```json
{
  "model": "gpt-5.6-luna",
  "prompt_cache_key": "telugu-voice:v5:cfg-a1b2c3d4",
  "prompt_cache_options": { "mode": "explicit", "ttl": "30m" },
  "input": [
    {
      "type": "message",
      "role": "developer",
      "content": [{
        "type": "input_text",
        "text": "<ONE composed brain prompt>",
        "prompt_cache_breakpoint": { "mode": "explicit" }
      }]
    },
    { "type": "message", "role": "user", "content": [{ "type": "input_text", "text": "<history / transcript>" }] }
  ],
  "max_output_tokens": 320,
  "store": false,
  "reasoning": { "effort": "none" }
}
```

---

## 3. Token layers after redesign

| Layer | Budget | Cached? | Sent how |
|-------|--------|---------|----------|
| **Brain prompt** (single) | 1,500–5,000 (default 1,500) | **Always** (min 1,500) | One `developer` `input_text` |
| **History** | ≤ 4 turns, truncated | No | Messages after brain block |
| **Transcript** | ~5–50 typical | No | Final `user` message |
| **Output** | `openaiMaxTokens` (default 320) | — | `max_output_tokens` |

**Dynamic context target:** ~150–400 tokens. Brain prompt is the only static/cached block.

---

## 4. Composition rules

When user saves behaviour/business, server composes and validates:

```
┌─ SAFETY (fixed, server-only, always first) ────────────────────┐
├─ TELUGU REGISTER + examples (factory) ─────────────────────────┤
├─ BEHAVIOUR (user textarea) ────────────────────────────────────┤
├─ BUSINESS  (user textarea) ────────────────────────────────────┤
└─ Language + style line ─────────────────────────────────────────┘
         ↓ validate estimate_tokens(composed) ≤ brainPromptBudgetTokens
    ONE string → instruction_store.brainPrompt
```

Plain-text section markers (not XML):

```
--- SAFETY ---
--- TELUGU VOICE ---
--- BEHAVIOUR ---
--- BUSINESS ---
Language: te-IN. Style: very brief, spoken Telugu.
```

### 4.1 Why section-priority trim is NOT needed

v4 proposed runtime trimming (drop whole bullets when over budget). **v5 removes that entirely** because:

1. **UI minimum 1,500** — factory content (~900–1,100 tokens) fits with ~400–600 tokens headroom for user text without cutting anything.
2. **Budget is a ceiling, not a target** — if composed prompt exceeds budget, **reject on save** and ask the user to shorten text or raise the slider. No `str[:n]` cuts, no mid-sentence damage.
3. **Simpler code** — `compose_brain_prompt()` merges sections; `validate_brain_prompt_budget()` checks size; no trim algorithm.

```python
def compose_brain_prompt(...) -> str:
    """Merge sections into ONE string. No runtime trimming."""

def validate_brain_prompt_budget(text: str, budget_tokens: int) -> None:
    est = estimate_tokens(text)
    if est > budget_tokens:
        raise PromptBudgetExceeded(
            f"Brain prompt is {est} tokens but budget is {budget_tokens}. "
            "Shorten behaviour/business or increase brain prompt budget."
        )
```

| On save | If over budget |
|---------|----------------|
| `POST /api/instructions` | Return `400` with `estimatedTokens`, `budgetTokens`, `overBy` |
| Fine-tune console | Show inline error: *"Prompt too long — remove N tokens or increase budget"* |

User controls size by **editing text** or **moving the slider up** (1,500 → 5,000). The server never silently drops content.

---

## 5. Prompt caching

Always enabled for GPT-5.6 when the composed brain prompt meets the OpenAI minimum (≥1,024 tokens).

```python
def caching_enabled(model: str, brain_tokens: int = 0) -> bool:
    return settings.enable_prompt_caching and model.startswith("gpt-5.6") and brain_tokens >= 1024
```

| Rule | Value |
|------|-------|
| Minimum prefix (OpenAI) | **1,024 tokens** — factory defaults ~1,058; short custom saves may be below |
| Cache read | 0.1× input |
| Cache write | 1.25× input (once per unique prefix) |
| TTL | `30m` |
| `prompt_cache_key` | `sha256(brain_prompt + budget)[:12]` — content hash, not sessionId |

### 5.1 Conversation state

Keep **`store: false`** + server-managed history (`conversation_manager`).

The two optimizations that matter:

1. **Don't send unnecessary context** — single brain prompt, trim history, no duplication.
2. **Cache stable context** — one composed brain prompt with explicit breakpoint.

No `previous_response_id` or Conversations API needed.

---

## 6. Token logging (env-controlled)

Use existing logging flags to capture **real API usage** for optimization and fine-tuning.

### 6.1 Environment flags

```env
LOG_ENABLED=true          # master switch — false silences everything
LOG_LEVEL=info            # debug for verbose; info for production tuning
LOG_BRAIN=true            # ← token usage, request config, response summary
LOG_PERF=true             # ← latency spans including brain token events
LOG_VOICE=false           # optional — disable if only tuning brain tokens
LOG_STT=false
LOG_TTS=false
LOG_WS=false
LOG_CLIENT=false
```

**Tuning brain tokens only:**

```env
LOG_ENABLED=true
LOG_BRAIN=true
LOG_PERF=true
LOG_VOICE=false
LOG_STT=false
LOG_TTS=false
LOG_WS=false
```

### 6.2 What to log (every brain call)

Normalize usage from Responses API `response.usage` — object or dict:

```python
def normalize_usage(usage) -> dict:
    if not usage:
        return {}
    if isinstance(usage, dict):
        details = usage.get("input_tokens_details") or {}
        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cached_tokens": details.get("cached_tokens", 0),
            "cache_write_tokens": details.get("cache_write_tokens", 0),
        }
    details = getattr(usage, "input_tokens_details", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", 0),
        "cached_tokens": getattr(details, "cached_tokens", 0) if details else 0,
        "cache_write_tokens": getattr(details, "cache_write_tokens", 0) if details else 0,
    }
```

### 6.3 Log line format (`LOG_BRAIN=true`)

Emit structured lines via `log_brain()` in `openai_brain_service.py`:

```text
[BRAIN] Request started model=gpt-5.6-luna session=abc historyLen=4 brainEst=1480 budget=1500
[BRAIN] TOKENS input=1720 output=58 total=1778 cached=1480 cache_write=0 brainEst=1480 budget=1500 model=gpt-5.6-luna session=abc request_id=resp_xxx
[BRAIN] CACHE_HIT rate=0.86 cached=1480 input=1720
```

| Log key | When | Fields |
|---------|------|--------|
| `Request started` | Before API call | `model`, `session`, `historyLen`, `brainEst`, `budget` |
| `TOKENS` | After response (stream + non-stream) | `input`, `output`, `total`, `cached`, `cache_write`, `request_id` |
| `CACHE_HIT` | When `cached_tokens > 0` | `rate=cached/input`, `cached`, `input` |
| `CACHE_MISS` | Turn 1 or prompt changed | `cache_write`, `input` |
| `CONFIG` | Model/params | `model`, `max_output_tokens`, `reasoning`, `caching` |

### 6.4 Perf spans (`LOG_PERF=true`)

```text
[PERF] BRAIN_STARTED model=gpt-5.6-luna session=abc
[PERF] BRAIN_FIRST_DELTA ms=340 model=gpt-5.6-luna session=abc
[PERF] BRAIN_COMPLETED ms=890 chars=120 input_tokens=1720 output_tokens=58 cached_tokens=1480 session=abc
```

Stream path must log tokens on `response.completed` (currently missing `cached_tokens` — fix in Phase 1).

### 6.5 Metrics aggregation (`/api/metrics`)

Extend `server/utils/metrics.py` to track rolling averages:

```json
{
  "brain_tokens": {
    "calls": 142,
    "input_p50": 1650,
    "input_p95": 2100,
    "output_p50": 52,
    "cached_p50": 1480,
    "cache_hit_rate": 0.84,
    "cache_write_rate": 0.08
  }
}
```

Reset via `POST /api/metrics/reset`.

### 6.6 `/api/prompt/effective` additions

```json
{
  "brainPrompt": "…full composed text…",
  "estimatedTokens": 1480,
  "budgetTokens": 1500,
  "headroom": 20,
  "cacheEligible": true,
  "sections": { "safety": 420, "telugu": 310, "behaviour": 180, "business": 520 }
}
```

Section token estimates help users fine-tune without guessing.

### 6.7 Implementation tasks (logging)

| # | Task | File |
|---|------|------|
| L.1 | `normalize_usage()` with `cached_tokens` + `cache_write_tokens` | `server/utils/token_usage.py` (new) |
| L.2 | Log `[BRAIN] TOKENS` after every response | `openai_brain_service.py` |
| L.3 | Log tokens on stream `response.completed` event | `openai_brain_service.py` |
| L.4 | `metrics.record_brain_tokens(usage)` | `server/utils/metrics.py` |
| L.5 | Expose `brain_tokens` in `GET /api/metrics` | `routes/metrics.py` |
| L.6 | Log `brainEst` before API call | `openai_brain_service.py` |

All logging respects `should_log("brain")` / `should_log("perf")` — no logs when `LOG_BRAIN=false`.

---

## 7. Three-phase implementation plan

### Phase 1 — Single brain prompt + logging (Week 1)

**Goal:** One composed string; budget 1,500–5,000; full token telemetry.

| # | Task | File(s) |
|---|------|---------|
| 1.1 | Create `brain_prompt.py` — factory sections merged from `system_prompt.py` + `voice_defaults.py` | `prompts/brain_prompt.py` |
| 1.2 | `compose_brain_prompt()` + `validate_brain_prompt_budget()` — merge only, no trim | `brain_prompt_composer.py` |
| 1.3 | Remove `instructions` from `responses.create()` | `openai_brain_service.py` |
| 1.4 | Replace `build_agent_instructions()` with composer | `openai_brain_service.py` |
| 1.5 | On save: compose, validate budget, store `brainPrompt` | `instruction_store.py`, `routes/instructions.py` |
| 1.6 | `brainPromptBudgetTokens` slider **1,500–5,000**, default 1,500, badge always Caching ON | `runtime_settings.py`, UI |
| 1.7 | `MAX_CONTEXT_MESSAGES=4`; history truncation | `conversation_manager.py` |
| 1.8 | `normalize_usage()` + `[BRAIN] TOKENS` logging (stream + non-stream) | `token_usage.py`, `openai_brain_service.py` |
| 1.9 | Metrics aggregation + `/api/prompt/effective` token breakdown | `metrics.py`, `routes/metrics.py` |
| 1.10 | `build_brain_request_input()` replaces old builders | `instruction_builder.py` |

**Acceptance:**
- [x] Zero `instructions` field in API request
- [x] One `developer` message, plain text, no XML
- [x] Slider 1,500–5,000 only; save rejected if prompt exceeds budget
- [x] `[BRAIN] TOKENS` logged when `LOG_BRAIN=true`
- [x] `cached_tokens` visible in logs and `/api/metrics`

---

### Phase 2 — Prompt caching (Week 2)

**Goal:** Turn 2+ reads brain prompt at 0.1× on GPT-5.6 Luna.

| # | Task | File(s) |
|---|------|---------|
| 2.1 | Developer `content` → typed `input_text` block | `instruction_builder.py` |
| 2.2 | `prompt_cache_breakpoint` on single brain block | `instruction_builder.py` |
| 2.3 | `prompt_cache_key` from content hash | `prompt_cache_key.py` |
| 2.4 | `prompt_cache_options: {mode: "explicit", ttl: "30m"}` | `openai_brain_service.py` |
| 2.5 | Log `[BRAIN] CACHE_HIT` / `CACHE_MISS` | `openai_brain_service.py` |
| 2.6 | Integration test: 2 turns → `cached_tokens > 0` on turn 2 | `tests/` |

**Acceptance:**
- [x] `prompt_cache_breakpoint` on brain block when `brain_tokens ≥ 1024`
- [x] `prompt_cache_key` + `prompt_cache_options` on GPT-5.6+
- [x] `[BRAIN] CACHE_HIT` / `CACHE_MISS` logging
- [x] Factory defaults expanded to ~1,058 tokens (cache-eligible)

---

### Phase 3 — Flat dynamic context (Week 3) ✅

| # | Task | File(s) |
|---|------|---------|
| 3.1 | `get_context_for_brain()` — last 2 turns truncated | `conversation_manager.py` |
| 3.2 | Optional summary when `ENABLE_SESSION_SUMMARY=true` | `session_memory.py`, `memory_summarizer.py` |
| 3.3 | Per-layer token breakdown in metrics | `metrics.py`, `routes/metrics.py` |

**Acceptance:**
- [x] Brain uses last `BRAIN_CONTEXT_TURNS` (default 2) — not full history
- [x] Stored `brainPrompt` reused when no per-request overrides (no recompose every turn)
- [x] Session summary injected as optional user message block
- [x] `/api/prompt/effective` shows per-layer `token_estimates`
- [x] `/api/metrics` → `brain_tokens.layer_avg_est`
- [x] Session clear wipes `session_memory` too

**Audit fixes (Phases 1–3):**
- `caching_enabled(model, brain_tokens)` gates cache params on ≥ `PROMPT_CACHE_MIN_TOKENS` (1024)
- `cache_eligible()` shared helper — used by instructions, metrics, and UI responses (no hardcoded `true`)
- Empty instruction fields (`""`) treated as not provided → stored `brainPrompt` reused
- `_resolve_instruction_overrides()` dedupes override logic between stream and non-stream paths
- `_apply_cache_kwargs()` uses precomputed `enable_cache` — no duplicate `caching_enabled()` call
- Removed duplicate `get_history()` in brain logging — uses `historyLen` from prepare step
- Brain/voice routes pass `None` for instructions when not explicitly overridden → stored brain prompt
- `_after_turn_memory()` only runs when `ENABLE_SESSION_SUMMARY=true`
- `session_memory` lock simplified — no nested lock in `record_turn`
- Instructions/session clear also wipes `session_memory`

---

## 8. Fine-tune console UX

| Control | Key | Range | Default |
|---------|-----|-------|---------|
| Brain prompt budget | `brainPromptBudgetTokens` | **1,500 – 5,000** | 1,500 |
| Max output tokens | `openaiMaxTokens` | 50 – 800 | 320 |
| Behaviour | `behaviourInstructions` | must fit in budget | factory |
| Business | `businessInstructions` | must fit in budget | factory |
| Cache status | `cacheEligible` | `estimatedTokens ≥ 1024` | factory defaults: yes |
| Estimated tokens | `estimatedTokens` | read-only on save | — |

```text
Brain prompt budget: [●========] 1,500 tokens   ✅ Caching ON (1,058 / 1,500 tokens)
```

If save would exceed budget:

```text
❌ Prompt too long: 1,820 tokens (budget 1,500). Shorten text or increase budget.
```

---

## 9. Environment variables

```env
# Brain prompt budget
BRAIN_PROMPT_BUDGET_TOKENS=1500
BRAIN_PROMPT_BUDGET_MIN=1500          # UI floor — caching always ON
BRAIN_PROMPT_BUDGET_MAX=5000
MAX_CONTEXT_MESSAGES=4
MAX_HISTORY_ASSISTANT_CHARS=120
MAX_HISTORY_USER_CHARS=300

# Caching (always eligible when brain prompt ≥ 1024 tokens)
ENABLE_PROMPT_CACHING=true
PROMPT_CACHE_TTL=30m
PROMPT_CACHE_KEY_PREFIX=telugu-voice:v5
PROMPT_CACHE_MIN_TOKENS=1024

# Phase 3 — flat dynamic context
ENABLE_SESSION_SUMMARY=false
SUMMARY_EVERY_N_TURNS=4
BRAIN_CONTEXT_TURNS=2

# Token logging (tune brain in production)
LOG_ENABLED=true
LOG_LEVEL=info
LOG_BRAIN=true                      # input/output/cached/cache_write per call
LOG_PERF=true                       # latency + token perf spans
LOG_VOICE=false
LOG_STT=false
LOG_TTS=false
LOG_WS=false
```

---

## 10. Cost illustration

**10-turn session, dynamic = 250 tokens/turn, gpt-5.6-luna:**

| Scenario | 10-turn input cost units* |
|----------|---------------------------|
| **Today** (duplicated ~1,412 static, no cache) | **~16,620** |
| **v5** (1,500 static, cached turn 2+) | **~5,725** |

\*Write ×1.25, cache read ×0.1, uncached ×1.0.

With UI min 1,500, every deployment gets caching. No low-budget trap.

---

## 11. Pre-ship checklist

- [x] One brain prompt string in OpenAI request
- [x] No `instructions` field, no XML tags
- [x] Slider **1,500–5,000** only
- [x] Over-budget → save rejected (no silent trim)
- [x] `[BRAIN] TOKENS` with `input`, `output`, `cached`, `cache_write` when `LOG_BRAIN=true`
- [x] Stream path logs tokens on completion
- [x] `/api/metrics` shows `brain_tokens` averages + `layer_avg_est`
- [x] `store: false` unchanged

---

## 12. What changed v4 → v5

| v4 | v5 |
|----|-----|
| UI 100–5,000 with Caching ON/OFF badge | UI **1,500–5,000** — caching always ON |
| Section-priority runtime trim (§4.2) | **Removed** — validate on save, user edits text |
| `fit_brain_prompt_to_budget()` algorithm | `validate_brain_prompt_budget()` — reject if over |
| Token logging mentioned briefly | Full §6 — `LOG_BRAIN`, `LOG_PERF`, metrics, log format |
| `trimWarnings` in UI | `estimatedTokens` + `headroom` + save error if over |

---

*v5 — single brain prompt. UI 1,500–5,000 (caching always ON). No runtime trim — validate on save. Token logging via LOG_BRAIN + LOG_PERF for fine-tuning.*
