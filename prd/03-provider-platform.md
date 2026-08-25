# 03 — Provider Platform

Provider registry, tier system, adapter interfaces, and environment configuration.

---

## 1. Target design principles

1. **Pipeline becomes provider-agnostic** — today `voice_session`, WS routes, and services call vendors directly; the target core calls standardized interfaces.
2. **Registry is declarative** — providers/models defined in one module; env enables/disables; UI reads same catalog.
3. **Tiers are env bundles** — LOW/MEDIUM/PREMIUM are not hard-coded in Python logic; they resolve to env vars.
4. **Secrets never leave server** — registry exposes capability metadata only via `/api/settings/catalog`.
5. **Backward compatible** — unset new env → current Sarvam + OpenAI defaults.

---

## 2. Provider registry

### 2.1 Module location (proposed)

```
server/providers/
  registry.py          # load + validate registry
  base.py              # STTProvider, LLMProvider, TTSProvider ABCs
  sarvam_stt.py        # wraps existing services
  sarvam_tts.py
  openai_llm.py        # wraps openai_brain_service
  cartesia_stt.py      # new
  cartesia_tts.py      # new
  gemini_llm.py        # new
  deepseek_llm.py      # new
  resolver.py          # tier + session resolution
```

### 2.2 Registry entry schema

```python
ProviderEntry = {
    "id": "sarvam",                    # stable slug
    "type": "stt" | "llm" | "tts",
    "display_name": "Sarvam AI",
    "enabled": bool,                   # from ENABLE_SARVAM_STT etc.
    "models": [
        {
            "id": "saaras:v3",
            "display_name": "Saaras v3",
            "languages": ["te-IN", "hi-IN", "en-IN"],
            "supports_streaming": True,
            "supports_realtime": True, # WS realtime path
            "language_support": ["te-IN"],
            "pricing_metadata": { "usd_per_min": null, "notes": "manual" },
            "latency_tier": "low" | "medium" | "high",
            "cost_tier": "low" | "medium" | "high",
        }
    ],
    "env_keys_required": ["SARVAM_API_KEY"],
    "default_model_env": "SARVAM_STT_MODEL",
}
```

### 2.3 Providers to register (from repo + fix.md)

| Type | Provider ID | Models (configurable via env) | Current implementation status |
|------|-------------|-------------------------------|--------|
| STT | `sarvam` | REST `saaras:v3`; live WS `saaras:v3-realtime` currently hard-coded | **Direct integration; adapter not built** |
| STT | `cartesia` | `ink-2` (EN only); `ink-whisper-2025-06-04` (multilingual incl. `te`) | **Not built** |
| LLM | `openai` | `gpt-5.6-luna`, allowlist in `OPENAI_ALLOWED_MODELS` | **Direct integration; adapter not built** |
| LLM | `gemini` | current model ID supplied by env `GEMINI_MODEL` and verified from Google catalog | **Not built** |
| LLM | `deepseek` | current model ID supplied by env `DEEPSEEK_MODEL` and verified from DeepSeek catalog | **Not built** |
| TTS | `sarvam` | `bulbul:v3`, speakers from constants | **Direct integration; adapter not built** |
| TTS | `cartesia` | `sonic-3.5` / `sonic-3.5-2026-05-04` (42 langs incl. Telugu) | **Not built** |

**Note:** Exact Cartesia Ink/Sonic model strings are **not hard-coded**; loaded from env and validated against provider catalog at startup (warn if unknown).

### 2.4 Plugin enable flags (env)

```bash
ENABLE_SARVAM_STT=true
ENABLE_SARVAM_TTS=true
ENABLE_OPENAI_LLM=true
ENABLE_CARTESIA_STT=false
ENABLE_CARTESIA_TTS=false
ENABLE_GEMINI_LLM=false
ENABLE_DEEPSEEK_LLM=false
```

When `false`:

- Registry marks provider `enabled: false`
- `/api/settings/catalog` omits or marks disabled
- API rejects session start with disabled provider (400 + clear code)
- UI hides option (frontend mode)

---

## 3. Adapter interfaces

### 3.1 STTProvider

```python
class STTProvider(Protocol):
    async def transcribe_rest(self, audio: bytes, config: STTConfig) -> STTResult
    async def connect_realtime(self, config: STTConfig) -> STTRealtimeSession
```

`STTResult`: `{ text, language, confidence?, latency_ms, provider, model }`

`STTRealtimeSession`: proxy pattern like current `sarvam_ws.connect_stt_realtime`.

### 3.2 LLMProvider

```python
class LLMProvider(Protocol):
    async def stream_response(self, request: BrainRequest) -> AsyncIterator[BrainStreamEvent]
    async def structured_response(self, request: BrainRequest, schema: dict) -> dict
```

`BrainRequest` carries:

- `compiled_brain` (cached prefix)
- `working_memory` (dynamic JSON block)
- `recent_turns` (1–2)
- `current_transcript`
- `session_id`, `call_id`
- `stream: bool`

`BrainStreamEvent`: `{ type: "delta"|"done"|"usage", text?, usage? }`

OpenAI adapter wraps existing `openai_brain_service.py`. Gemini/DeepSeek implement the normalized contract according to verified capabilities. A `structured_response` result is always locally schema-validated; provider support may range from strict JSON Schema to JSON-only output and must be represented in registry metadata.

### 3.3 TTSProvider

```python
class TTSProvider(Protocol):
    async def synthesize(self, text: str, config: TTSConfig) -> TTSResult
    async def connect_streaming(self, config: TTSConfig) -> TTSStreamSession
```

Preserves current Sarvam WS behavior (`bulbul:v3`, completion events).

---

## 4. Quality tiers (LOW / MEDIUM / PREMIUM)

### 4.1 Purpose

Tiers bundle **provider + model** per stage for cost/quality ladders. Operators set one tier in production without exposing the full matrix.

### 4.2 Env structure (from fix.md)

```bash
VOICE_AGENT_TIER=medium   # low | medium | premium (active tier in env mode)

# LOW tier
VOICE_LOW_STT_PROVIDER=sarvam
VOICE_LOW_STT_MODEL=saaras:v3
VOICE_LOW_LLM_PROVIDER=openai
VOICE_LOW_LLM_MODEL=gpt-5.6-luna
VOICE_LOW_TTS_PROVIDER=sarvam
VOICE_LOW_TTS_MODEL=bulbul:v3

# MEDIUM tier (example — tune after benchmarks)
VOICE_MEDIUM_STT_PROVIDER=sarvam
VOICE_MEDIUM_STT_MODEL=saaras:v3-realtime
VOICE_MEDIUM_LLM_PROVIDER=openai
VOICE_MEDIUM_LLM_MODEL=gpt-5.6-luna
VOICE_MEDIUM_TTS_PROVIDER=sarvam
VOICE_MEDIUM_TTS_MODEL=bulbul:v3

# PREMIUM tier (Telugu-safe example; benchmark before assignment)
VOICE_PREMIUM_STT_PROVIDER=sarvam
VOICE_PREMIUM_STT_MODEL=saaras:v3-realtime
VOICE_PREMIUM_LLM_PROVIDER=openai
VOICE_PREMIUM_LLM_MODEL=gpt-5.6-luna
VOICE_PREMIUM_TTS_PROVIDER=cartesia
VOICE_PREMIUM_TTS_MODEL=<cartesia-tts-model>
```

### 4.3 Tier vs voice preset

| Concept | Controls | Example |
|---------|----------|---------|
| **Tier** | Which STT/LLM/TTS vendor + model | MEDIUM = Sarvam realtime STT + OpenAI + Sarvam TTS |
| **Voice preset** | VAD, barge-in, TTS pace/temperature, buffer sizes | `telugu_natural` from `voice_defaults.py` |

Both apply at session start. Preset does not change provider unless explicitly configured in preset metadata (not default).

### 4.4 Tier resolution (`resolver.py`)

```python
def resolve_stack(
    mode: Literal["env", "frontend"],
    tier: str | None,
    user_selection: StackSelection | None,
    runtime_overrides: dict | None,
) -> ResolvedStack:
```

Output `ResolvedStack`:

```json
{
  "tier": "medium",
  "stt": { "provider": "sarvam", "model": "saaras:v3-realtime" },
  "llm": { "provider": "openai", "model": "gpt-5.6-luna" },
  "tts": { "provider": "sarvam", "model": "bulbul:v3", "speaker": "shubh" },
  "voice_preset": "telugu_natural",
  "resolved_at": "ISO8601"
}
```

Logged at `call/start` and attached to metrics.

---

## 5. Configuration modes

### 5.1 `VOICE_AGENT_CONFIG_MODE`

| Value | Behavior |
|-------|----------|
| `env` | Server resolves stack from `VOICE_AGENT_TIER` + tier env vars. UI shows tier chips only. |
| `frontend` | User picks providers/models from enabled plugins. Full developer console. |

**Default for backward compat:** `frontend` until deployment sets `env`.

### 5.2 API: catalog endpoint (extend existing)

`GET /api/settings/catalog` returns:

```json
{
  "config_mode": "frontend",
  "active_tier": "medium",
  "providers": { "stt": [...], "llm": [...], "tts": [...] },
  "tiers": ["low", "medium", "premium"],
  "voice_presets": [...],
  "scoring_weights": { "latency": 0.4, "cost": 0.3, "quality": 0.3 }
}
```

### 5.3 Session override rules

| Mode | Overrides allowed |
|------|-------------------|
| `env` | None from client (tier fixed server-side) |
| `frontend` | Per-session STT/TTS/LLM selection + voice preset + runtime tuning |

Overrides validated against registry; disabled plugins rejected.

---

## 6. Live path integration

### 6.1 Current flow (preserve)

```
Browser WS /ws/stt-realtime → Sarvam proxy
Browser SSE /api/brain/stream → OpenAI
Browser WS /ws/tts → Sarvam proxy
```

### 6.2 Target flow

```
Browser WS /ws/stt-realtime → STTProvider.connect_realtime(resolved.stt)
Browser SSE /api/brain/stream → LLMProvider.stream_response(...)
Browser WS /ws/tts → TTSProvider.connect_streaming(resolved.tts)
```

WS route factory selects upstream URL/headers from provider adapter. **No change to client wire protocol** for Sarvam path.

### 6.3 REST fallback path

`/api/voice/turn` and `/api/voice/stt-brain` use same `ResolvedStack` via `voice_session.py`.

`VOICE_HTTP_TTS_FALLBACK=false` remains default (WS TTS only in live UI).

---

## 7. New provider implementation notes

### 7.1 Cartesia (verified against official docs — re-verify at implementation)

**Documentation references:**

- Ink 2 STT: https://docs.cartesia.ai/build-with-cartesia/stt/latest
- Ink Whisper (older multilingual STT): https://docs.cartesia.ai/build-with-cartesia/stt/older-models
- Sonic 3.5 TTS: https://docs.cartesia.ai/build-with-cartesia/tts-models/latest
- STT migration/API conventions: https://docs.cartesia.ai/use-the-api/stt/migrate-from-deepgram-flux
- Changelog: https://docs.cartesia.ai/changelog/2026

#### STT models — what to use when

| Model ID | Type | Languages (official) | Status | Use in this platform |
|----------|------|----------------------|--------|----------------------|
| `ink-2` | Streaming STT + built-in turn detection | **English only** (`en`) | Stable | English benchmark / English-only agents only. **Do not register for Telugu.** |
| `ink-whisper-2025-06-04` | Streaming/batch STT | 99+ including **`te`** (Telugu) | Stable older model | Optional Cartesia STT for Telugu experiments — not default production path |
| `ink-whisper` (alias) | Points to latest whisper snapshot | Multilingual incl. Telugu | Stable | Env may set explicit snapshot for reproducibility |

**Ink 2 constraints (normative for adapter):**

- `model=ink-2` required
- `encoding=pcm_s16le` (not Deepgram `linear16` name)
- `cartesia_version=2026-03-01` required on WS/API
- `language_hint` — only English supported today; multilingual Ink 2 is roadmap only
- Built-in turn events: `turn.start`, `turn.update`, `turn.eager_end`, `turn.resume`, `turn.end`
- Turn params: `turn_eager_end_threshold`, `turn_end_threshold`, `turn_end_timeout_ms`

**Telugu STT routing rule:**

```text
IF agent.language primary is te-IN OR te:
  DEFAULT STT = Sarvam saaras:v3-realtime (live) / saaras:v3 (REST)
  DO NOT offer ink-2 in UI or tier resolver
  OPTIONAL benchmark slot = ink-whisper snapshot (verify Telugu WER before tier assignment)
IF agent.language primary is en:
  MAY offer ink-2 for turn-detection + English accuracy benchmarks
```

#### TTS models — what to use when

| Model ID | Languages (official) | Status | Use in this platform |
|----------|----------------------|--------|----------------------|
| `sonic-3.5` | **42 languages** including **`te`** (Telugu), `hi`, `en`, … | GA stable | Premium TTS option for Telugu; pin snapshot for production |
| `sonic-3.5-2026-05-04` | Same 42 languages | Stable snapshot | Recommended production pin |
| `sonic-3`, `sonic-2`, `sonic-turbo` (old snapshots) | Varies | Sunset / discontinued per changelog | **Do not** assign in new tiers |

**Sonic 3.5 constraints (normative for adapter):**

- Request `model_id: sonic-3.5` or pinned snapshot
- Telugu: `language` or `locale` = `te` or `te-IN` (set one, not both)
- `locale` codes like `te-IN` require Sonic 3.6+ for some features; bare `te` works on 3.5
- Output: `pcm_f32le` or `pcm_s16le` at 24000 Hz typical; resample to browser/Plivo bridge as needed
- Voice: `voice.mode=id` + `CARTESIA_TTS_VOICE_ID`
- Streaming via SSE or bytes API; WS proxy if offered
- Sub-90ms vendor latency claim — treat as hypothesis; benchmark on deployment network

**Telugu TTS routing rule:**

```text
DEFAULT production TTS (LOW/MEDIUM tiers) = Sarvam bulbul:v3, language_code=te-IN
PREMIUM tier MAY assign Cartesia sonic-3.5 when ENABLE_CARTESIA_TTS=true and benchmark proves quality/latency win
UI must show resolved model, language, voice id, and snapshot pin
```

#### Cartesia env vars

```bash
ENABLE_CARTESIA_STT=false          # enable only when adapter + keys ready
ENABLE_CARTESIA_TTS=false
CARTESIA_API_KEY=
CARTESIA_STT_MODEL=ink-2           # EN-only; use ink-whisper-2025-06-04 for multilingual experiments
CARTESIA_TTS_MODEL=sonic-3.5       # or sonic-3.5-2026-05-04 snapshot
CARTESIA_TTS_VOICE_ID=             # required when TTS enabled
CARTESIA_API_VERSION=2026-03-01    # required for Ink 2 STT
```

Auth: `CARTESIA_API_KEY` header. WS proxy pattern mirrors `sarvam_ws.py` per Cartesia streaming docs.

### 7.2 Sarvam (verified against official docs — current production default)

**Documentation references:**

- Index: https://docs.sarvam.ai/llms.txt
- Saaras STT: https://docs.sarvam.ai/api/getting-started/models/saaras.md
- Bulbul TTS convert: https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
- TTS language: https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/how-to/set-the-language

#### STT — Saaras v3

| Model ID | Modes | Languages | APIs | Use in this platform |
|----------|-------|-----------|------|----------------------|
| `saaras:v3` | transcribe, translate, verbatim, translit, **codemix** | 23 (22 Indian + English) | REST (≤30s), batch (≤1h), **realtime WS** | **Default production STT** |

**Live browser path (current repo):**

- WS model hard-coded: `saaras:v3-realtime`
- Env REST default: `SARVAM_STT_MODEL=saaras:v3`
- Telugu: `language_code=te-IN`
- Code-mixed Telugu+English: use **codemix** output mode when configured
- PSTN ingress: μ-law 8 kHz → PCM 16 kHz transcode before Sarvam (see Plivo doc)

**Resolver rule:** tier env vars should use `saaras:v3-realtime` for MEDIUM/PREMIUM live tiers unless benchmark shows REST path sufficient.

#### TTS — Bulbul v3

| Model ID | Languages | Voices | APIs | Use in this platform |
|----------|-----------|--------|------|----------------------|
| `bulbul:v3` | 11 (10 Indian + English), **Telugu `te-IN`** | 30+ speakers (e.g. `shubh` default) | REST, streaming WS | **Default production TTS** |

**Normative parameters:**

- `model=bulbul:v3`
- `language_code=te-IN` (required BCP-47)
- `speaker` lowercase (e.g. `shubh`, `ritu`, …)
- `pace` 0.5–2.0
- `temperature` 0.01–1.0 (v3 only)
- `sample_rate` default 24000; higher rates REST-only per docs
- **No pitch/loudness** on v3 (v2 legacy only)

**Live browser path (current repo):**

- WS: `bulbul:v3` via `/ws/tts` proxy
- Defaults from env: `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER_TE`, `SARVAM_TTS_PACE`, `SARVAM_TTS_TEMPERATURE`

#### Sarvam env vars

```bash
SARVAM_API_KEY=
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER_TE=shubh
SARVAM_TTS_PACE=1.0
SARVAM_TTS_TEMPERATURE=0.6
```

#### Provider selection matrix (Telugu voice agent — normative default)

| Stage | LOW tier | MEDIUM tier | PREMIUM tier (example) |
|-------|----------|-------------|------------------------|
| STT | Sarvam `saaras:v3` REST | Sarvam `saaras:v3-realtime` WS | Sarvam `saaras:v3-realtime` WS |
| LLM | OpenAI tier model | OpenAI tier model | OpenAI tier model |
| TTS | Sarvam `bulbul:v3` `te-IN` | Sarvam `bulbul:v3` `te-IN` | Sarvam `bulbul:v3` **or** Cartesia `sonic-3.5` if benchmark wins |

| Stage | English-only agent |
|-------|-------------------|
| STT | Cartesia `ink-2` eligible for benchmark/premium |
| TTS | Cartesia `sonic-3.5` or Sarvam `bulbul:v3` `en-IN` |

**Registry validation at startup:**

- Reject tier assignment if STT model languages do not include agent primary language
- Reject `ink-2` + `te-IN` combination with `language_incompatible` error
- Warn if Cartesia TTS enabled without `CARTESIA_TTS_VOICE_ID`
- Warn if unset `SARVAM_STT_MODEL` differs from live WS model (document effective model in catalog)

### 7.3 Gemini

- Use the current Google GenAI API selected during implementation; normalize provider-specific streaming events.
- Structured output supports a documented subset of JSON Schema and requires local validation.
- Env: `GEMINI_API_KEY`, `GEMINI_MODEL`, optional `GEMINI_BASE_URL`.
- Gemini 2.5+ documentation describes implicit prefix caching and provider-specific cached-token usage fields. Record the capability and usage rather than assuming OpenAI cache controls.

### 7.4 DeepSeek (MVP — brain processing)

- **In MVP** for live brain processing — dev configures via Dev Console (`17` §13).
- OpenAI-compatible API (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`).
- Default model target: **DeepSeek Flash** class (env-driven ID — verify catalog at implementation).
- Must support Structured Outputs / JSON schema for `{ spoken_response, memory_update }` or local validation after JSON mode.
- Adapter shares HTTP patterns with OpenAI adapter where possible.

---

## 7.5 Provider fallback (normative)

When configured primary provider fails mid-call or at request time:

```text
Try configured stack (tier or dev selection)
  → on retryable failure: fallback chain per stage (env + Dev Console UI)
  → example: Cartesia TTS fail → Sarvam TTS (same language)
  → example: Cartesia STT unavailable for Telugu → Sarvam STT (always Telugu production default)
```

| Rule | Detail |
|------|--------|
| Priority | **Always try configured provider first** |
| Logging | Record `provider_fallback` event in trace and ledger metadata |
| UI | Dev Console configures fallback pairs per stage |
| Telugu STT | **Sarvam only** for production Telugu/code-mix; Cartesia Ink-2 not eligible |

---

## 7.6 Dev Console stack configuration (UI)

**Only Developer/Administrator** configures global stacks — not business customers.

| Capability | Detail |
|------------|--------|
| UI | Dev Portal: pick STT/LLM/TTS per LOW/MEDIUM/PREMIUM + test combinations |
| APIs | `/api/dev/stack/*` or `/api/platform/stack/*` (see `13`) |
| Persistence | Tier assignments stored in DB; env vars bootstrap first deploy |
| Production tiers | LOW/MEDIUM/PREMIUM assigned after developer testing — **not pre-set by PRD** |
| Customer mode | `VOICE_AGENT_CONFIG_MODE=env` — customers see tier chips only |

Dev Console uses `VOICE_AGENT_CONFIG_MODE=frontend` behavior internally for testing.

---

## 8. Error handling

| Case | Response |
|------|----------|
| Disabled provider requested | 400 `provider_disabled` |
| Missing API key for enabled provider | 503 `provider_misconfigured` (startup warn + health degraded) |
| Provider timeout | Retryable `AppError` with `provider` field (existing pattern) |
| Model not in registry | 400 `model_not_allowed` |

Existing `AppError` + metrics `record_error(provider, code)` extended to all adapters.

---

## 9. API key policy

All provider API keys remain server-side. Never expose to browser:

`OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `SARVAM_API_KEY`, `CARTESIA_API_KEY`, `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`.

Catalog API returns capability metadata only (fix.md §8).

---

## 10. Telephony transport (not a registry provider)

Plivo is **channel transport** — not listed in STT/LLM/TTS registry. See [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md).

| Item | Env |
|------|-----|
| Enable | `ENABLE_PLIVO` |
| Credentials | `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN` |
| Number | `PLIVO_NUMBER` |
| Public URL | `PLIVO_PUBLIC_BASE_URL` |

---

## 11. Acceptance criteria

- [ ] Registry lists all 7 provider slots with correct enable flags from env
- [ ] `VOICE_AGENT_CONFIG_MODE=env` + `VOICE_AGENT_TIER=medium` resolves MEDIUM env bundle
- [ ] `frontend` mode allows selecting any enabled combination; saves snapshot at call start
- [ ] Disabling `ENABLE_CARTESIA_STT` hides Cartesia STT in UI and rejects API
- [ ] Live Sarvam path regression: same latency p50 as pre-registry (within 5%)
- [ ] `.env.example` documents all new vars with comments
- [ ] Unit tests: resolver, disabled plugin rejection, backward compat defaults
