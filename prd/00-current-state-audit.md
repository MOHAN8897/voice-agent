# 00 — Current State Audit

**Phase 2 deliverable:** map the product before redesign.  
**Codebase version:** `0.2.0-phase5` (`server/config/constants.py`)

---

## 1. Executive summary

The repository is a **working Telugu-first voice agent** with a **production-grade live path** (WS STT → SSE brain → WS TTS), **strong OpenAI prompt caching**, and a **unified developer console** in a single SPA. It is **not yet** a provider-agnostic testing platform, **not** a call archive system, and **not** a multi-customer SaaS brain layer.

| Dimension | Maturity |
|-----------|----------|
| Live voice loop | **Strong** — primary UX, barge-in, streaming TTS |
| Token / cache optimization | **Strong** — explicit breakpoint, measured ~90% cache hit |
| Provider flexibility | **Weak** — Sarvam + OpenAI only, no registry |
| Memory / call persistence | **Weak** — in-RAM trim, client localStorage |
| Testing / benchmarking UI | **Partial** — metrics API, no combination matrix |
| SaaS customer onboarding | **Not built** — single-session prompt editor only |

---

## 2. Backend — what exists

### 2.1 Application entry

| Item | Location |
|------|----------|
| FastAPI app | `server/app.py` |
| Lifespan: env validation, conversation limits, OpenAI warm-up | `server/app.py` |
| CORS + rate limit (60/min general, 20/min voice/TTS) | `server/app.py`, `server/utils/rate_limiter.py` |
| Static client + catch-all asset routes | `server/app.py` |

### 2.2 REST API routes

| Path | Module | Function |
|------|--------|----------|
| `/api/health`, `/api/config-check` | `routes/health.py` | Liveness, safe config |
| `/api/stt` | `routes/stt.py` | Sarvam REST STT |
| `/api/brain`, `/api/brain/stream`, `/api/brain/test` | `routes/brain.py` | OpenAI Responses |
| `/api/session/clear` | `routes/brain.py` | Clear RAM history |
| `/api/tts`, `/api/tts/stream` | `routes/tts.py` | Sarvam TTS |
| `/api/voice/turn`, `/api/voice/stt-brain` | `routes/voice.py` | REST orchestration |
| `/api/instructions/*` | `routes/instructions.py` | Brain prompt CRUD |
| `/api/settings/*` | `routes/settings.py` | Catalog + runtime overrides |
| `/api/metrics`, `/api/prompt/effective` | `routes/metrics.py` | Observability |
| `/api/session/interrupt`, `/api/session/history` | `routes/session_control.py` | Barge-in ack, history |

**Missing:** `/api/call/start`, `/api/call/end`, `/api/calls/{id}`, provider-agnostic voice routes, **Plivo telephony** (see §09).

### 2.3 WebSocket routes

| Path | Module | Upstream |
|------|--------|----------|
| `/ws/stt-realtime` | `routes/ws.py` | Sarvam `saaras:v3-realtime` |
| `/ws/tts` | `routes/ws.py` | Sarvam `bulbul:v3` WS |

Proxy logic: `server/services/sarvam_ws.py`

### 2.4 Provider integrations (actual)

| Stage | Provider | Service file | Models (configured) |
|-------|----------|--------------|---------------------|
| STT REST | Sarvam | `sarvam_stt_service.py` | `saaras:v3` (env) |
| STT WS | Sarvam | `sarvam_ws.py` | `saaras:v3-realtime`, `stream_type=fast` |
| LLM | OpenAI | `openai_brain_service.py` | `gpt-5.6-luna` default; allowlist in `OPENAI_ALLOWED_MODELS` |
| TTS REST/stream | Sarvam | `sarvam_tts_service.py` | `bulbul:v3` |
| TTS WS | Sarvam | `sarvam_ws.py` | `bulbul:v3` |

**Not in codebase:** Cartesia (Ink STT, Sonic TTS), Gemini, DeepSeek, generic provider interfaces.

The live WebSocket STT model is currently hard-coded in `sarvam_ws.py`; it is not resolved from `SARVAM_STT_MODEL`, which configures the REST path.

Catalog metadata (partial registry): `server/config/constants.py` (STT/TTS models, speakers), `server/prompts/voice_defaults.py` (OpenAI models, voice presets).

### 2.5 Session and memory (current)

| Component | File | Behavior |
|-----------|------|----------|
| Conversation window | `conversation_manager.py` | Max 8 messages, 30m TTL, char caps (user 300 / assistant 120) |
| Brain context | `get_context_for_brain(max_turns=2)` | Only last 2 turns to LLM |
| Session summary | `session_memory.py` | Optional; **default off** (`ENABLE_SESSION_SUMMARY=false`) |
| Summary generator | `memory_summarizer.py` | **No LLM** — joins last 6 user lines |
| Instruction store | `instruction_store.py` | Per-session brain prompt, 24h TTL |
| Runtime settings | `runtime_settings.py` | Per-session STT/TTS/OpenAI overrides, voice presets |
| Voice session orchestrator | `voice_session.py` | REST `voice/turn` only; not live WS path |
| State enum | `session_state.py` | IDLE → LISTENING → … → PLAYING |

**No:** `call_id`, working memory JSON, call ledger, server audio files, post-call outcome.

### 2.6 Brain / token architecture (current — must preserve)

| Mechanism | Location |
|-----------|----------|
| Single composed brain prompt | `brain_prompt_composer.py`, `prompts/brain_prompt.py` |
| Request input builder | `instruction_builder.py` — one developer message + optional summary + history + transcript |
| Cache breakpoint | On brain prompt block when ≥1024 tokens and gpt-5.6* |
| Cache key | `prompt_cache_key.py` — hash(brain + budget), not sessionId |
| `store: false` | `openai_brain_service.py` |
| Token logging | `token_usage.py`, `LOG_BRAIN`, `/api/metrics` |

### 2.7 Configuration & environment

**Loader:** `server/config/env.py`  
**Template:** `.env.example`

Key vars today: `OPENAI_API_KEY`, `SARVAM_API_KEY`, model names, `BRAIN_CONTEXT_TURNS=2`, `ENABLE_PROMPT_CACHING`, logging flags, `VOICE_HTTP_TTS_FALLBACK=false`.

**Missing from env:** `VOICE_AGENT_CONFIG_MODE`, tier vars, plugin enables, Cartesia/DeepSeek/Gemini keys, scoring weights.

Current prompt-cache logic is model-gated to the `gpt-5.6*` path; selecting another allowed OpenAI model may disable the existing explicit cache behavior and must be visible in the future catalog/UI.

Current configuration nuance: `.env` TTS pace/temperature can differ from the UI “Natural” voice-preset defaults until runtime settings are saved. The target resolver must expose the effective value and its source.

### 2.8 Logging & metrics

| Capability | Location |
|------------|----------|
| Category logs | `logger.py`, `log_config.py` |
| Latency p50/p95 | `metrics.py` — stt, brain, tts, e2e |
| Brain token aggregates | `metrics.py` — input/output/cached/layers |
| Cache telemetry | `prompt_cache_tracker.py` |
| Effective prompt debug | `GET /api/prompt/effective` |

**Missing:** Per-provider spans, per-call traces, combination benchmark runs, disposition metrics.

### 2.9 Persistence

**None server-side durable.** All state in-process with TTL. Client: `localStorage` via `conversation_store.js`.

### 2.10 Tests (`server/tests/`)

| Area | Files |
|------|-------|
| Env / health | `test_env.py`, `test_health.py` |
| Brain / cache | `test_brain_caching.py`, `test_prompt_cache_tracker.py`, `test_token_usage.py` |
| Context / memory | `test_phase3_context.py`, `test_conversation_manager.py` |
| API mocked | `test_api_mocked.py`, `test_tts_instructions.py` |
| Console / settings | `test_finetune_console.py`, `test_tts_config.py` |
| Live / latency | `test_e2e_latency.py` (optional LIVE_TEST=1) |
| Barge-in parity | `test_live_barge_policy.py` ↔ `client/live-guards.js` |
| Benchmarks | `benchmark_voice_cache.py`, `verify_post_fix.py` |

**Missing tests:** provider registry, tiers, Cartesia/DeepSeek adapters, call lifecycle, working memory merge, disposition schema, disabled plugin rejection.

**Test infrastructure gap:** no dedicated frontend test runner or repository CI workflow was found. JavaScript policy behavior is exercised indirectly from pytest.

---

## 3. Frontend — what exists

### 3.1 Pages & navigation

| Asset | Role |
|-------|------|
| `client/index.html` | **Single SPA** — Voice Agent + 5 console panels |
| `client/settings.html` | Redirect to `/?tab=pipeline` |
| `client/console_tabs.js` | Tab routing (`/?tab=brain`, etc.) |

**Panels:** Voice Agent, Voice Pipeline, AI Brain, Prompting, CRM & Tools, Advanced.

### 3.2 Voice Agent UI (`client/app.js` ~2,370 lines)

| Feature | Status |
|---------|--------|
| Live full-duplex (default) | WS STT + SSE brain + persistent WS TTS |
| Barge-in | `live-guards.js`, echo gate, cooldown |
| Hands-free re-listen | After playback via `AudioPlaybackManager` |
| Push-to-talk REST | Code present; **UI forces live mode** (`realtimeMode` hidden + checked) |
| Session ID | `localStorage` UUID |
| Runtime settings fetch | Before each turn |
| Prompt save / dirty override | `/api/instructions` |
| Exports | TXT, JSON, WAV via `ConversationStore` |
| Metrics display | STT/brain/TTS/e2e in UI |

### 3.3 Settings console (`client/settings.js`)

- Loads `/api/settings/catalog` + runtime + instructions
- **Voice presets** (bundled VAD/barge/TTS tuning) — not the same as LOW/MEDIUM/PREMIUM tiers
- OpenAI model + reasoning effort
- CRM webhook fields — **stored only, not executed**

### 3.4 Client persistence (`conversation_store.js`)

- Turns in `localStorage` with optional TTS base64 per turn
- **User audio not saved**
- Not suitable for long calls (quota, no server archive)

### 3.5 Styling

`client/styles.css` — dark premium console theme, voice orb, chat thread, token meter.

---

## 4. WHAT WORKS (do not regress)

1. **Live streaming pipeline** — parallel brain SSE + TTS WS; sentence accumulator; PCM playback.
2. **OpenAI prompt caching** — stable brain prefix; dynamic tail only; ~90% cached tokens after turn 1.
3. **Barge-in** — client-side stop + abort; policy tested in `test_live_barge_policy.py`.
4. **TTS config single resolver** — `tts_config.py` for REST/WS/voice paths.
5. **Secret safety** — keys server-only; redacted logs.
6. **Rate limiting + error taxonomy** — `AppError`, quota fail-fast.
7. **Fine-tune console** — runtime overrides per session without redeploy.
8. **Voice preset bundles** — locked tuning groups for Telugu natural profiles.
9. **Test suite** — broad mocked coverage; live probes optional.

---

## 5. WHAT IS MISSING (product gaps)

| Gap | Source |
|-----|--------|
| Provider registry + STT/LLM/TTS interfaces | `fix.md` |
| LOW / MEDIUM / PREMIUM env tiers | `fix.md` |
| Cartesia, DeepSeek, Gemini adapters | `fix.md` |
| `VOICE_AGENT_CONFIG_MODE` (env vs frontend) | `fix.md` |
| Combination testing matrix + scoring | `fix.md` |
| Working memory JSON + memory_update operations | `memory implemenation.md` |
| Compiled brain + business prompt optimizer | `memory implemenation.md` |
| Call start/end, ledger, stereo audio | `memory implemenation.md`, `MEMORY_CALL_ARCHIVE_PLAN.md` |
| Post-call structured outcome / disposition | Both memory docs |
| Server-side call list + replay UI | Research + memory docs |
| CRM webhook execution | UI exists, no server POST |
| Database / multi-tenant customer model | `memory implemenation.md` |
| Auth | Open CORS `*` |

---

## 6. WHAT MUST NOT BE BROKEN

### 6.1 Cache architecture

- Brain prompt remains **one stable cached block** before breakpoint.
- **Never** inject working memory, rolling summary, or history into the cached developer string.
- `prompt_cache_key` must remain content-hash of brain + budget (not per-call dynamic state).
- Keep `store: false` for live turns unless explicitly migrating with full replay of `output` items.

### 6.2 Streaming TTS path

- One browser `/ws/tts` per live session; brain deltas forwarded while SSE open.
- Do not revert to POST `/api/tts` after every turn (`VOICE_HTTP_TTS_FALLBACK=false` default).
- Sarvam upstream reconnect per flush (`upstream_reset`) must remain functional.

### 6.3 Latency-sensitive paths

- Memory merge, rolling summary, ledger append, audio write: **async / fire-and-forget** on hot path.
- Post-call analysis: **only after hang-up**.

### 6.4 Context limits

- `BRAIN_CONTEXT_TURNS=2` for live LLM input (may add working memory block without increasing raw history turns).
- Char caps on history sent to brain.

### 6.5 Voice preset bundles

- `VOICE_PRESET_BUNDLED_KEYS` — do not expose individual VAD/barge knobs without preset migration path.

---

## 7. Architecture snapshot (today)

```
Browser (index.html + app.js)
  │  PCM ──► WS /ws/stt-realtime ──► Sarvam STT
  │  SSE ──► POST /api/brain/stream ──► OpenAI Responses (cached brain)
  │  WS ───► /ws/tts ──► Sarvam TTS
  │
  └── localStorage (ConversationStore) — client-only archive

FastAPI (server/)
  ├── conversation_manager (2-turn window, truncated)
  ├── instruction_store + runtime_settings (RAM, TTL)
  ├── openai_brain_service (cache, stream)
  └── metrics + prompt_cache_tracker
```

**Target architecture** documented in [06-technical-architecture.md](./06-technical-architecture.md).
