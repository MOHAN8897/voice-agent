# Telugu Voice AI Agent — Detailed Implementation Plan (5 Phases)

> **Version:** 2.0 — 2026-08-23
> **Source Input:** `implementationplan.md.txt` (29 sections, Telugu-first voice agent)
> **Reference Docs Verified (Aug 2026):**
> - OpenAI Platform: `https://platform.openai.com/docs` + `https://developers.openai.com/api/docs` — **Responses API is the recommended primitive** for new projects (evolution of Chat Completions). Chat Completions (`POST /v1/chat/completions`) remains supported indefinitely. SDK: `openai` (Python ≥3.10, Node). Auth: `Authorization: Bearer $OPENAI_API_KEY`. Streaming via SSE (`stream: true`, events like `response.output_text.delta`). State: `previous_response_id` / `store` / Conversations API. Hosted tools & custom function calling in a single `/v1/responses` call.
> - Sarvam AI: `https://docs.sarvam.ai` — **Saaras v3** (STT, 23 languages inc `te-IN`, 5 modes) and **Bulbul v3** (TTS, 11 languages inc `te-IN`, 30+ voices). STT REST `POST https://api.sarvam.ai/speech-to-text` (multipart), Realtime WebSocket `wss://api.sarvam.ai/speech-to-text-realtime/ws` (model `saaras:v3-realtime`, stream_type `fast|balanced|simulated`). TTS REST `POST https://api.sarvam.ai/text-to-speech` (JSON, base64 `audios[]`), streaming `POST https://api.sarvam.ai/text-to-speech/stream` (binary stream), WebSocket `wss://api.sarvam.ai/text-to-speech/ws`. Auth: header `api-subscription-key`. SDKs: `pip install sarvam-ai` / `npm install sarvamai`.
> - Voice-agent best practices: cascaded **STT → LLM → TTS** with streaming at every stage, sentence-buffer bridging LLM tokens → TTS, VAD/endpointing as the largest latency term, barge-in <150 ms, standard latency budget measurement.

---

## Table of Contents
1. [Executive Summary & Design Principles](#1-executive-summary--design-principles)
2. [Reference Architecture](#2-reference-architecture)
3. [Technology Stack & Project Layout](#3-technology-stack--project-layout)
4. [Cross-Cutting Standards (apply to all phases)](#4-cross-cutting-standards-apply-to-all-phases)
5. [Phase 1 — Foundation & Secure Configuration](#5-phase-1--foundation--secure-configuration)
6. [Phase 2 — Telugu STT + OpenAI Brain (Conversation Core)](#6-phase-2--telugu-stt--openai-brain-conversation-core)
7. [Phase 3 — Telugu TTS + End-to-End Voice Loop](#7-phase-3--telugu-tts--end-to-end-voice-loop)
8. [Phase 4 — User-Customizable Brain, Memory & Language Resolver](#8-phase-4--user-customizable-brain-memory--language-resolver)
9. [Phase 5 — Realtime UX, Hardening & Production Readiness](#9-phase-5--realtime-ux-hardening--production-readiness)
10. [Appendices](#10-appendices)

---

## 1. Executive Summary & Design Principles

### 1.1 Objective
Build a production-quality **Telugu-first voice agent** from scratch with the pipeline:

`Mic → Sarvam STT (te-IN) → Conversation Manager + Instructions → OpenAI Responses API → Language Resolver → Sarvam TTS (te-IN) → Playback`

Hindi/English must be addable later by **configuration**, not rewrite. Telugu quality (code-mixed `Tenglish` like `నాకు రేపు weather ఎలా ఉంటుందో చెప్పు`) is the Phase 1 quality bar.

### 1.2 Non-negotiable Principles (Industry Standard)

| Principle | How it manifests |
|---|---|
| **Docs as source of truth** | Never guess model names/params. OpenAI model and Sarvam `model`/`speaker`/`language_code` are read from `docs.sarvam.ai` and `platform.openai.com` at build time and made configurable via env. |
| **Server-side secrets** | `OPENAI_API_KEY` and `SARVAM_API_KEY` never touch client bundle. All provider calls are proxied through backend. `.env` gitignored; `.env.example` shipped. |
| **Streaming-first, but not premature** | MVP proves correctness on non-streaming REST; then upgrades to streaming WebSocket/HTTP-stream for perceived latency (industry proves ~750 ms TTFA achievable by overlapping stages). |
| **Smallest correct architecture first** | Direct service calls (`SarvamSTTService`, `OpenAIBrainService`, `SarvamTTSService`) preferred over MCP unless a tool-use orchestration is actually needed. No invented MCP server. |
| **Instruction hierarchy is a security boundary** | System > Core > User > Conversation > Current turn. User instructions are wrapped/tagged, not concatenated blindly, to prevent prompt injection from overriding safety. |
| **Observable & measurable** | Every stage emits structured logs and latency spans; latency budget is measured per turn, not guessed. |
| **Phase gates** | No phase starts until previous phase's tests pass and API connectivity is verified live. |

---

## 2. Reference Architecture

### 2.1 Logical Pipeline
```
┌─────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────┐
│   Mic   │──▶│ AudioCapture │──▶│ Sarvam STT   │──▶│ ConversationMgr   │──▶│ OpenAI Brain │──▶│ Language     │──▶│ Sarvam  │──▶│Playback │
│ (Browser)│   │  Manager     │   │ saaras:v3    │   │ + Instruction     │   │ Responses API│   │ Resolver     │   │ TTS     │   │Manager  │
└─────────┘   └──────────────┘   │ te-IN/codemix│   │ Builder           │   │ gpt-4o class │   │ te-IN → te-IN│   │bulbul:v3│   └─────────┘
                                 └──────────────┘   └───────────────────┘   └──────────────┘   └──────────────┘   └─────────┘
                                        ▲                    │                       │                  │               │
                                        │                    ▼                       ▼                  ▼               ▼
                                   VoiceSessionController ───────────────────────────────────────────────────────────────
                                        │  owns State Machine: IDLE → LISTENING → PROCESSING_STT → THINKING → GENERATING_TTS → PLAYING → IDLE
                                        │  owns cancellation (AbortController) + TTS flush + session context
                                        ▼
                                   UI (VoiceAgentScreen / CustomizeAgentScreen) + SessionState + Logger
```

### 2.2 Deployment View (recommended)
- **Client:** Single-page web app (React + TypeScript + Vite). Captures mic via `MediaDevices.getUserMedia` + `AudioWorklet`/`MediaRecorder` (16 kHz, mono, 16-bit PCM → WAV). Renders state, transcript, AI response, Customize AI screen. Dark theme: black bg, ash cards, `#0F03FC` accent.
- **Server:** `Node.js + Fastify` *or* `Python + FastAPI` (choose one; spec below uses **Node** to share TS types, but maps 1:1 to Python). Proxies all provider calls, holds secrets, enforces rate limits/validation, manages session memory.
- **Why this split:** satisfies §19 Security (secrets server-side), enables streaming proxy (server forwards Sarvam/OpenAI streams to client without exposing keys), and keeps audio capture low-latency on device.

### 2.3 Verified Provider Contracts (do not invent)

**OpenAI — Responses API (recommended for new projects)**
- Endpoint: `POST https://api.openai.com/v1/responses`  *(also `POST /v1/chat/completions` if team prefers Chat Completions — both supported)*
- Auth: `Authorization: Bearer $OPENAI_API_KEY`  |  SDK: `openai` npm / pip (`client.responses.create(...)`)
- Core params: `model` (e.g., `gpt-4o`, `gpt-4o-mini` — verify current catalog at `platform.openai.com/docs/models` before locking), `input` (array of `role: system|developer|user|assistant` items), `instructions` (system), `stream`, `store`, `previous_response_id`, `temperature`, `max_output_tokens`, `tools`/`tool_choice` if needed.
- Streaming events: `response.created`, `response.output_text.delta`, `response.completed`, `error`.
- State: for voice sessions prefer **stateless per turn + server-managed history** (send trimmed `input` array each turn) over `store: true`; keeps cost/latency predictable. `previous_response_id` chaining is optional.
- Errors/429: respect `Retry-After`, exponential backoff, classify 401 (config invalid) vs 429 vs 5xx.

**Sarvam STT**
- REST: `POST https://api.sarvam.ai/speech-to-text` — `multipart/form-data` with `file` (WAV/MP3/…; ≤30 s for REST), `model: saaras:v3` (recommended) or `saaras:v4`, `language_code: te-IN` (or `unknown` for auto), `mode: transcribe` (default, preserves Telugu) — for Tenglish code-mix experiments use `codemix`. Auth `api-subscription-key`. Response: `{transcript, language_code, request_id, ...}`. Verify `model`/`mode`/`language_code` enums from `docs.sarvam.ai/api-reference/speech-to-text/transcribe`.
- Realtime WebSocket: `wss://api.sarvam.ai/speech-to-text-realtime/ws?language_code=te-IN&model=saaras:v3-realtime&stream_type=fast&endpointing=vad&encoding=linear16&sample_rate=16000&silence_duration_ms=500&threshold=0.3`. Client sends `{event:"audio_input", audio: base64PCM}`; server emits `vad.speech_start/end`, `transcript.partial`, `transcript.final`, `error`. Use `stream_type=fast` for voice agents (lowest partial latency).
- Limits: REST ≤30 s, batch ≤2 h; streaming supports `linear16`/`mulaw`/`alaw`. 16 kHz recommended.

**Sarvam TTS**
- REST: `POST https://api.sarvam.ai/text-to-speech` — JSON `{text, language_code:"te-IN", speaker, model:"bulbul:v3", pace:0.5-2.0, speech_sample_rate, output_audio_codec}`. Response `{request_id, audios: [base64WAV,...]}` — decode via `Buffer.from(audios.join(""), "base64")`. Limit 2500 chars/req.
- HTTP Stream: `POST https://api.sarvam.ai/text-to-speech/stream` — same params, returns binary audio stream (no base64). Limit 3500 chars.
- WebSocket: `wss://api.sarvam.ai/text-to-speech/ws` — persistent, 2500 chars/msg (recommend <500/msg for lowest TTFB), streams base64 chunks.
- Telugu voices (verify at `docs.sarvam.ai/api-reference/text-to-speech` at build time — do not hardcode blindly): recommended `shubh` (male) / `priya` or `neha` (female) for `te-IN`. Keep `speaker` configurable via `SUPPORTED_LANGUAGES`.
- Audio formats: `mp3` (default streaming), `wav`, `opus`, `flac`, `linear16`, `mulaw`, `alaw`.

---

## 3. Technology Stack & Project Layout

### 3.1 Recommended Stack (Node variant — industry standard, fully typed)

| Layer | Choice | Reason |
|---|---|---|
| Language | TypeScript 5.x (strict) | Shared types client↔server, OpenAI & Sarvam have first-class TS SDKs |
| Client | React 18 + Vite + Zustand (state) + Tailwind | Fast iteration, large touch targets, mic animation, state indicators |
| Audio (client) | `getUserMedia` + `AudioWorklet` (16k PCM) for streaming; `MediaRecorder` (WAV) for MVP REST | 16 kHz mono matches Sarvam optimal; Worklet avoids main-thread glitches |
| Server | Fastify 4 + `@fastify/websocket` | Low overhead, first-class WS, easy to proxy streaming |
| Validation | `zod` | Env + API payload validation, never trust client input |
| LLM SDK | `openai` (official) | Responses API + streaming + typed errors |
| Sarvam SDK | `sarvamai` (official) | Avoids hand-rolling multipart/WS framing |
| Tests | Vitest (unit), Playwright (e2e), `msw` (API mocks) | Fast, modern, good WS support |
| Lint/Format | ESLint + Prettier + `tsc --noEmit` | CI gate |
| Env | `dotenv` + `zod` validator, `pino` logger | Structured logs, secret-safe |

*Python alternative:* FastAPI + `openai` (Python) + `sarvamai` (Python) + `pytest` — identical architecture, swap file extensions.

### 3.2 Repository Layout
```
/
├── .env.example
├── .gitignore          # .env, .env.local, .env.*.local
├── package.json
├── tsconfig.json
├── vite.config.ts
├── server/
│   ├── src/
│   │   ├── config/
│   │   │   ├── env.ts              # zod-validated loader, fails fast, never logs secrets
│   │   │   └── constants.ts        # MAX_RESPONSE_LENGTH, MAX_CONTEXT_MESSAGES, timeouts
│   │   ├── services/
│   │   │   ├── sarvamSttService.ts # REST + realtime WS, codemix/transcribe modes
│   │   │   ├── sarvamTtsService.ts # REST + stream + WS, bulbul:v3, speaker map
│   │   │   └── openaiBrainService.ts # Responses API, streaming, instruction injection
│   │   ├── agent/
│   │   │   ├── agentController.ts
│   │   │   ├── instructionBuilder.ts # buildAgentInstructions({core,user,language,style})
│   │   │   ├── conversationManager.ts# history trim/summarize
│   │   │   └── languageResolver.ts   # LanguageContext {input, response, confidence, isCodeMixed}
│   │   ├── session/
│   │   │   ├── voiceSession.ts
│   │   │   └── sessionState.ts     # IDLE→LISTENING→... state machine
│   │   ├── audio/
│   │   │   ├── audioCaptureManager.ts
│   │   │   └── audioPlaybackManager.ts
│   │   ├── routes/
│   │   │   ├── stt.ts              # POST /api/stt
│   │   │   ├── brain.ts            # POST /api/brain
│   │   │   ├── tts.ts              # POST /api/tts (+ /api/tts/stream)
│   │   │   └── ws.ts               # WS /ws/voice (realtime phase)
│   │   ├── utils/
│   │   │   ├── logger.ts           # pino, level DEBUG in dev, redacts keys
│   │   │   ├── errors.ts           # AppError taxonomy, user-safe messages
│   │   │   └── audio.ts            # resample, WAV header, base64 helpers
│   │   └── prompts/
│   │       ├── systemPrompt.ts
│   │       └── responseRules.ts
│   └── tests/
├── client/
│   ├── src/
│   │   ├── ui/
│   │   │   ├── VoiceAgentScreen.tsx
│   │   │   ├── CustomizeAgentScreen.tsx
│   │   │   └── components/ (MicButton, StateIndicator, TranscriptCard)
│   │   ├── hooks/ (useVoiceSession, useAudioCapture)
│   │   ├── store/ (sessionStore)
│   │   └── types/ (agent.ts, audio.ts, language.ts)
│   └── tests/
└── docs/
```

---

## 4. Cross-Cutting Standards (apply to all phases)

### 4.1 Configuration
```ini
# .env.example — NEVER commit real keys
OPENAI_API_KEY=
SARVAM_API_KEY=
OPENAI_MODEL=gpt-4o-mini          # verify at https://platform.openai.com/docs/models
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER_TE=shubh
SARVAM_TTS_PACE=1.0
MAX_RESPONSE_LENGTH=600            # tokens/chars cap for concise voice
MAX_CONTEXT_MESSAGES=12
REQUEST_TIMEOUT_MS=15000
MAX_RETRIES=2
LOG_LEVEL=info
DEBUG=false
```
Loader (`server/src/config/env.ts:1`):
- `zod` validates presence/format; missing required key → throw `ConfigError` with user message *"AI service configuration is invalid. Check .env"*; **never** print key.
- `gitignore` includes `.env`, `.env.local`, `.env.*.local`.

### 4.2 State Machine (all phases must honor)
```
IDLE → LISTENING → PROCESSING_STT → THINKING → GENERATING_TTS → PLAYING → IDLE
                 ↘ (on error) → ERROR → IDLE
PLAYING ─(barge-in, Phase 5)→ INTERRUPTED → LISTENING
```
UI labels: `Listening…` `Understanding…` `Thinking…` `Speaking…` — user never guesses.

### 4.3 Logging (structured, secret-safe)
```
[VOICE] Recording started {sessionId}
[STT] Audio submitted {bytes, sampleRate, language_code}
[STT] Transcript received {chars, language_code, confidence}
[LANGUAGE] Resolved {input:te-IN, response:te-IN, isCodeMixed:true}
[BRAIN] Request started {model, historyLen}
[BRAIN] Response received {tokens, latencyMs}
[TTS] Synthesis started {chars, speaker, pace}
[TTS] Audio received {bytes, codec}
[AUDIO] Playback started / interrupted / completed
[ERROR] {code, service, retryable, userMessage}
```
Never log: API keys, raw PII beyond transcript (and then only at DEBUG), raw audio.

### 4.4 Error Taxonomy & Resilience

| Source | Example | HTTP | Retry? | User message |
|---|---|---|---|---|
| Auth | invalid `api-subscription-key` / `OPENAI_API_KEY` | 401/403 | No | "AI service configuration is invalid." |
| Rate limit | 429 | 429 | Yes (exp backoff + `Retry-After`) | "Service is temporarily busy. Please try again." |
| Validation | missing `text`/`language_code`, >2500 chars | 400/422 | No | "Request was invalid. Check input length." |
| Network/timeout | `ETIMEDOUT`, WS close 1011 | — | Yes (1-2×) | "Network issue. Retrying…" then graceful fallback |
| STT quality | empty transcript, low confidence | 200 w/ empty | No (prompt user to retry) | "Didn't catch that. Please try again." |

- Timeouts: STT 15 s, Brain 20 s, TTS 15 s (configurable).
- Retries: only idempotent, non-auth errors; exponential backoff `200ms * 2^n + jitter`; max 2 retries.
- Circuit breaker per provider (optional Phase 5).

### 4.5 Testing Strategy (per phase)
- **Unit:** instructionBuilder, languageResolver, conversationManager (trim/summarize), error mapping.
- **Integration (mocked):** `msw` mocks for OpenAI/Sarvam REST; WS mocks for realtime.
- **Live smoke (gated):** `LIVE_TEST=1` scripts hit real APIs with 3 s Telugu fixture; never in CI by default.
- **Manual matrix:** 10 canonical tests from §24 of original plan (pure Telugu, code-mix, tech term, instruction styles, conflict, memory, TTS pronunciation, auth failure, network failure) — executed at each phase gate.

---

## 5. Phase 1 — Foundation & Secure Configuration

**Goal:** Runnable skeleton with validated config, health checks, and UI shell. No provider calls yet.

**Why first (industry practice):** Fail fast on config; establish secret handling, logging, and CI before any API integration.

### Tasks
1. **Scaffold repo** per §3.2. Init `npm` + `tsc --init` (strict), Vite React TS, Fastify server. Add `eslint`, `prettier`, `vitest`.
2. **Config module** `server/src/config/env.ts:1` — `zod` schema, `dotenv` load, `validateEnv()` that throws typed `ConfigError`. Add `constants.ts` for `MAX_RESPONSE_LENGTH` etc.
3. **Security:** `.gitignore`, `.env.example`, secret-redacting `logger.ts` (pino `redact: ["*.apiKey", "*.authorization"]`). Verify no client import of `process.env.OPENAI_API_KEY` (ESLint rule `no-restricted-imports`).
4. **Server skeleton:** `GET /api/health` (returns `{ok, envValid, version}` without leaking keys), `GET /api/config-check` (returns which keys are *present*, not values). Structured error handler.
5. **Client shell:** `VoiceAgentScreen` with agent name, conversation placeholder, large mic button (disabled until Phase 2), state indicator, transcript/response cards, "Customize AI" button → placeholder route. Dark theme (black + ash + `#0F03FC`).
6. **CI:** GitHub Actions `lint → typecheck → test → build` on PR.

### Key Implementation Notes
```ts
// server/src/config/env.ts
import { z } from "zod";
const schema = z.object({
  OPENAI_API_KEY: z.string().min(1, "OPENAI_API_KEY is required"),
  SARVAM_API_KEY: z.string().min(1, "SARVAM_API_KEY is required"),
  OPENAI_MODEL: z.string().default("gpt-4o-mini"),
  SARVAM_STT_MODEL: z.string().default("saaras:v3"),
  SARVAM_TTS_MODEL: z.string().default("bulbul:v3"),
});
export function validateEnv() {
  const parsed = schema.safeParse(process.env);
  if (!parsed.success) throw new ConfigError(parsed.error.message);
  return parsed.data;
}
```

### Exit Criteria (Gate)
- [ ] `npm run dev` starts client + server; `/api/health` green with valid `.env`, red with missing keys and clear message.
- [ ] No secret appears in client bundle (`grep -r OPENAI_API_KEY client/dist` empty) or logs.
- [ ] CI passes; coverage baseline recorded.

### Tests
- Unit: `validateEnv()` missing/invalid keys; logger redaction.
- Manual: remove key → UI shows *"AI service configuration is invalid"* without leaking value.

---

## 6. Phase 2 — Telugu STT + OpenAI Brain (Conversation Core)

**Goal:** Speak Telugu → see Telugu transcript → get Telugu reasoning response (text only). TTS not yet; proves the hardest multilingual loop.

### Tasks
#### 2A. Audio Capture (client)
1. `hooks/useAudioCapture.ts` — `getUserMedia({audio:{sampleRate:16000, channelCount:1, echoCancellation:true}})`. Two modes:
   - **MVP (REST):** `MediaRecorder` → `audio/wav` Blob (≤30 s, enforced). Show recording timer + waveform.
   - **Realtime prep (hidden flag):** `AudioWorklet` resampling to 16k PCM Int16 for Phase 5 WS.
2. Permission/error states: `NotAllowedError` → "Microphone permission denied", `NotFoundError` → "No microphone found".

#### 2B. Sarvam STT Service (server)
1. `services/sarvamSttService.ts` — wrap `sarvamai` SDK:
   ```ts
   import { SarvamAI } from "sarvamai";
   const client = new SarvamAI({ apiKey: env.SARVAM_API_KEY });
   const res = await client.speechToText.transcribe({
     file: wavBuffer,               // Buffer from multipart
     model: env.SARVAM_STT_MODEL,   // saaras:v3
     language_code: "te-IN",
     mode: "transcribe",            // default; codemix as A/B for Tenglish
   });
   // res.transcript, res.language_code, res.request_id
   ```
   Verify params against `docs.sarvam.ai/api-reference/speech-to-text/transcribe` at build time — do not hardcode `saarika` (legacy).
2. Route `POST /api/stt` — `multipart/form-data` ( Fastify `@fastify/multipart`), validate `file` ≤ 10 MB, audio duration ≤30 s, forward to Sarvam, return `{transcript, language_code, request_id}`. Map Sarvam errors to taxonomy (§4.4).

#### 2C. OpenAI Brain Service (server)
1. `services/openaiBrainService.ts` — official `openai` SDK, **Responses API**:
   ```ts
   import OpenAI from "openai";
   const openai = new OpenAI({ apiKey: env.OPENAI_API_KEY });
   const response = await openai.responses.create({
     model: env.OPENAI_MODEL, // e.g., gpt-4o-mini — verify catalog
     instructions: coreSystemPrompt, // platform/system safety + Telugu-first rules
     input: [
       { role: "developer", content: wrappedUserInstructions }, // see Phase 4
       ...trimmedHistory, // {role:"user"|"assistant", content}
       { role: "user", content: transcript }
     ],
     max_output_tokens: 600,
     store: false,
   });
   const text = response.output_text ?? response.output.map(...).join("");
   ```
   Streaming variant (Phase 3+): `stream: true` and forward `response.output_text.delta` via SSE/WS.
2. `prompts/systemPrompt.ts` — Telugu-first system prompt (conversational Telugu, preserve English tech terms, never translate code-mix blindly, concise by default):
   ```
   You are a Telugu-first voice assistant. Respond in Telugu when user speaks Telugu.
   For Telugu+English code-mix, respond naturally with Telugu-English mix — do NOT
   force pure Telugu translations of technical terms (Settings, Notifications, API, etc.).
   Keep answers conversational, concise (1-3 sentences unless asked for detail).
   ```
3. `agent/conversationManager.ts` — in-memory per-session history (`Map<sessionId, Message[]>`), `MAX_CONTEXT_MESSAGES=12`, trim oldest, optional summarize (>20 turns).
4. Route `POST /api/brain` — body `{transcript, language_code, sessionId, userInstructions?}` → calls OpenAI → returns `{text, usage}`.

### Telugu Data Handling (critical)
- Preserve raw transcript + detected `language_code`; **do not** translate `te-IN → en` before brain. OpenAI handles Telugu natively.
- Code-mix examples must pass end-to-end: `"నాకు రేపు హైదరాబాద్‌లో weather ఎలా ఉంటుందో చెప్పు"` → brain sees original + `detected_language: te-IN`.

### Exit Criteria
- [ ] Press mic → speak Telugu → transcript appears in `te-IN` script correctly (manual + recorded fixture).
- [ ] Brain returns natural Telugu/code-mix response for 3 fixtures: pure Telugu, `laptop slow`, `API అంటే ఏమిటి?`.
- [ ] History: "నా పేరు Sai" → later "నా పేరు ఏమిటి?" → returns Sai (tests conversationManager).
- [ ] Errors: invalid key → 401 mapped to user-safe message; 429 retried with backoff.

### Tests
- Unit: `conversationManager.trim()`, `instructionBuilder` wrapping.
- Integration (mocked): `/api/stt` with fixture WAV → mocked Sarvam 200; `/api/brain` with mocked OpenAI.
- Live smoke (`LIVE_TEST=1`): 3 real utterances through Sarvam STT `te-IN` + OpenAI `gpt-4o-mini`.

---

## 7. Phase 3 — Telugu TTS + End-to-End Voice Loop

**Goal:** Complete `Mic → STT → Brain → TTS → Playback` voice conversation (non-streaming first, then streaming upgrade).

### Tasks
#### 3A. Sarvam TTS Service (server)
1. `services/sarvamTtsService.ts`:
   ```ts
   // REST (MVP)
   const res = await client.textToSpeech.convert({
     text: brainText.slice(0, 2500), // enforce limit
     language_code: "te-IN",
     model: "bulbul:v3",
     speaker: env.SARVAM_TTS_SPEAKER_TE, // e.g., shubh / priya — verify voices
     pace: Number(env.SARVAM_TTS_PACE), // 0.5-2.0
     speech_sample_rate: 22050,
   });
   const wav = Buffer.from(res.audios.join(""), "base64");
   // return wav with Content-Type audio/wav

   // HTTP Stream (upgrade, low latency):
   // POST https://api.sarvam.ai/text-to-speech/stream → proxy binary stream to client
   // WS (Phase 5): wss://api.sarvam.ai/text-to-speech/ws — send chunks <500 chars
   ```
2. Route `POST /api/tts` (JSON `{text, language_code, speaker?}`) → validates 2500 char cap, returns `audio/wav` (or `audio/mpeg` for stream). `POST /api/tts/stream` proxies binary stream.

#### 3B. Client Playback
1. `audio/audioPlaybackManager.ts` — `AudioContext` + `HTMLAudioElement` for MVP (blob URL). For stream: `MediaSource` or chunked `AudioBufferSourceNode` queue. Exposes `play(bytes)`, `stop()`, `flush()`, `onEnded`.
2. Handle: auto-play policy (user gesture required — mic press counts), decode errors → user message.

#### 3C. VoiceSessionController (glue)
1. `session/voiceSession.ts` — owns state machine, `AbortController` per turn, orchestrates:
   ```
   LISTENING --(mic stop)--> PROCESSING_STT --(transcript)--> THINKING
            --(brain text)--> GENERATING_TTS --(audio)--> PLAYING --(ended)--> IDLE
   ```
   On new mic press during PLAYING: `audioPlaybackManager.stop()` + `abortController.abort()` (Phase 5 barge-in).
2. Client `useVoiceSession` hook binds UI state to controller events.

### Latency Baseline (measure, don't guess)
Instrument each span and log:
```
[PERF] turn {sttMs, brainMs, ttsMs, e2eMs, transcriptChars, responseChars, audioBytes}
```
Target MVP (non-streaming): `e2e < 3.5 s` for 5 s utterance. Streaming target (after upgrade): `e2e < 1.5 s`, `TTS first-byte < 400 ms`.

### Exit Criteria
- [ ] MVP voice loop: speak `"హాయ్, నా పేరు సాయి. నాకు Python గురించి చెప్పు."` → Telugu transcript → Telugu brain response → Telugu audio playback, all visible in UI.
- [ ] Code-mix TTS: brain response with `Settings / Notifications` spoken naturally (not forced Telugu transliteration).
- [ ] Streaming variant (if implemented): first audio plays before full synthesis; measured improvement logged.
- [ ] All error states from §4.2 covered with UI messages.

### Tests
- Integration: mocked TTS returns base64 → client decodes and `audio.play` called.
- Manual: verify Telugu pronunciation naturalness; numbers/dates spoken correctly.
- Live smoke: full loop with real Sarvam TTS `te-IN` voice.

---

## 8. Phase 4 — User-Customizable Brain, Memory & Language Resolver

**Goal:** Make the brain personal, stateful, and extensible to Hindi/English without rewrite.

### Tasks
#### 4A. Instruction Builder (security-critical)
1. `agent/instructionBuilder.ts:1`
   ```ts
   type BuildArgs = { coreInstructions: string; userInstructions: string; language: string; responseStyle?: string };
   function buildAgentInstructions(args: BuildArgs): string {
     // Priority: 1 System safety 2 Core 3 User (wrapped) 4 Conversation 5 Current turn
     // Wrap user content to prevent injection:
     return [
       args.coreInstructions,
       `<user_custom_instructions>\n${sanitize(args.userInstructions)}\n</user_custom_instructions>`,
       `Language: ${args.language}. Style: ${args.responseStyle ?? "concise, conversational"}`,
     ].join("\n\n");
   }
   function sanitize(s: string) { return s.slice(0, 2000).replace(/<\/?user_custom_instructions>/g, ""); }
   ```
   User block is sent as **developer role** content, never as `instructions` (system), so it cannot override safety. Length capped, tags stripped.

#### 4B. Customize AI UI
1. `client/src/ui/CustomizeAgentScreen.tsx` — textarea, Save/Reset/Preview, active indicator, test flow:
   - Save → `POST /api/instructions` (persisted per user/session; MVP: `localStorage` + server echo).
   - Test → `POST /api/brain/test` with `{userInstructions, testInput}` → shows brain output without saving.
   - Reset → clears to default.
2. Server `routes/instructions.ts` — zod validates, stores (MVP: in-memory/file; prod: DB), returns sanitized.

#### 4C. Conversation Memory (production-ready)
1. `conversationManager` upgrade:
   - `MAX_CONTEXT_MESSAGES=12`, `MAX_TOKENS` budget (e.g., 4000 input tokens).
   - Strategy: keep system + last N; if over budget, summarize oldest via OpenAI (`summarize` prompt) into a `system` memory note.
   - Session persistence: `sessionId` (uuid) in client store; server `Map` with TTL (e.g., 30 min idle eviction).
2. Verify: "నా పేరు Sai" → 5 turns later → "నా పేరు ఏమిటి?" still correct; token usage logged.

#### 4D. Language Resolver (extensibility)
1. `agent/languageResolver.ts`:
   ```ts
   type LanguageContext = { inputLanguage: string; responseLanguage: string; confidence: number; isCodeMixed: boolean };
   const SUPPORTED_LANGUAGES = {
     "te-IN": { sttCode:"te-IN", ttsCode:"te-IN", speaker:"shubh", name:"Telugu" },
     "hi-IN": { sttCode:"hi-IN", ttsCode:"hi-IN", speaker:"shubh", name:"Hindi" }, // ready, UI hidden in Phase 1
     "en-IN": { sttCode:"en-IN", ttsCode:"en-IN", speaker:"shubh", name:"English" },
   } as const;
   function resolveLanguage(detected: string, transcript: string): LanguageContext {
     const isCodeMixed = /[a-zA-Z]/.test(transcript) && /[\u0C00-\u0C7F]/.test(transcript);
     return { inputLanguage: detected, responseLanguage: "te-IN", confidence: 0.9, isCodeMixed };
     // Phase 1: always te-IN; future: map hi-IN→hi-IN etc.
   }
   ```
   TTS speaker selection driven by `responseLanguage`, not hard-coded.

### Exit Criteria
- [ ] Custom instruction `"ఎప్పుడూ చిన్నగా సమాధానం ఇవ్వాలి."` → `Python అంటే ఏమిటి?` returns short answer; without it returns longer.
- [ ] Conflict test: user asks 5000-word answer but system cap (`MAX_RESPONSE_LENGTH`) wins — response stays concise.
- [ ] Test-before-save flow works; preview shows effect without persisting.
- [ ] Adding `hi-IN` requires only adding entry to `SUPPORTED_LANGUAGES` + voice test, no pipeline change.

### Tests
- Unit: `buildAgentInstructions` priority, sanitization, length cap; `resolveLanguage` code-mix detection.
- Integration: save → brain call includes wrapped instructions; reset → default behavior.
- Manual: friendly vs concise vs teacher styles all behave distinct.

---

## 9. Phase 5 — Realtime UX, Hardening & Production Readiness

**Goal:** Make it feel conversational, not request/response — and survive production.

### 9.1 Realtime & UX Tasks
1. **Streaming upgrade (server):**
   - STT WS proxy: client `AudioWorklet` PCM → server → `wss://api.sarvam.ai/speech-to-text-realtime/ws?...&stream_type=fast` → forward `transcript.partial`/`final` to client WS. Handle `vad.speech_start/end` for UI.
   - Brain streaming: `openai.responses.create({stream:true})` → forward `response.output_text.delta` via SSE/WS; client renders incremental text.
   - TTS streaming: sentence-buffer brain deltas (`split(/(?<=[.!?।\n])\s+/)`) → `POST /text-to-speech/stream` per sentence or WS TTS (chunks <500 chars) → stream audio chunks to client `MediaSource` queue for immediate playback.
2. **Barge-in architecture (interfaces now, perfect later):**
   - `VoiceSessionController`, `AudioCaptureManager`, `AudioPlaybackManager` expose `interrupt()` → `playback.flush()` + `brainAbort.abort()` + `sttWs.send({event:"flush"})` + reset to `LISTENING`.
   - Client VAD: while `PLAYING`, if mic energy > threshold for 300 ms → trigger `interrupt()`. Visual: speaking animation stops instantly.
3. **UI polish:** mic pulse (LISTENING), waveform (PROCESSING), typing dots (THINKING), audio bars (PLAYING); large touch targets; `prefers-reduced-motion`.

### 9.2 Production Hardening Tasks
1. **Retries/backoff:** per §4.4, with `Retry-After` respect; jitter; idempotency keys for TTS.
2. **Rate limits & cost controls:** server `rateLimiter` (e.g., `p-queue` per IP/session), `MAX_RESPONSE_LENGTH` enforced before TTS, `MAX_CONTEXT_MESSAGES` enforced before brain, dedup STT/TTS (cache identical text TTS for 5 min).
3. **Validation:** `zod` on all inputs; audio type/size checks; text length checks before provider calls (fail fast, save cost).
4. **Monitoring:** `pino` JSON logs + `/api/metrics` (latency p50/p95 per stage, error rates, 429 rate). Optional OpenTelemetry traces.
5. **Privacy:** no raw audio stored by default; transcripts retained only per session TTL; `.env` never logged.

### 9.3 Latency Optimization Order (measure first)
1. VAD tuning (`silence_duration_ms` 500→350, `threshold` 0.3) — biggest win.
2. Parallelize: start STT final → brain on partial? (speculative, Phase 5 stretch).
3. TTS sentence streaming (first sentence plays while brain finishes).
4. Model choice: `gpt-4o-mini` (fast) vs `gpt-4o` (quality) — A/B with `OPENAI_MODEL`.

### Exit Criteria
- [ ] Realtime: partial transcript updates live while speaking; first audio <1 s after user stops (measured).
- [ ] Barge-in: speaking agent stops within 300 ms of user re-speaking; no ghost audio.
- [ ] Hardening: 429 simulated → backoff + user message; invalid key → config error; network drop → graceful recovery with retry button.
- [ ] Cost: duplicate TTS for same text not re-synthesized; history trimmed.

### Tests
- **Perf:** 20 consecutive turns, assert `p95 e2e < 2.0 s` (streaming) and no memory leak.
- **Chaos:** kill Sarvam WS mid-turn → reconnect + resume; abort brain mid-stream → clean state.
- **Manual (10 canonical + UX):** all pass, plus barge-in, rapid mic taps, background noise.

---

## 10. Appendices

### A. Environment Template
```ini
# .env.example
OPENAI_API_KEY=
SARVAM_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER_TE=shubh
SARVAM_TTS_PACE=1.0
MAX_RESPONSE_LENGTH=600
MAX_CONTEXT_MESSAGES=12
REQUEST_TIMEOUT_MS=15000
MAX_RETRIES=2
LOG_LEVEL=info
PORT=3000
CLIENT_URL=http://localhost:5173
```

### B. Sample Payloads (verified shapes)

**STT REST (cURL)**
```bash
curl -X POST https://api.sarvam.ai/speech-to-text \
  -H "api-subscription-key: $SARVAM_API_KEY" \
  -F "file=@utterance.wav" \
  -F "model=saaras:v3" \
  -F "language_code=te-IN" \
  -F "mode=transcribe"
# → {"request_id":"...","transcript":"నాకు Python గురించి చెప్పు","language_code":"te-IN"}
```

**TTS REST (cURL)**
```bash
curl -X POST https://api.sarvam.ai/text-to-speech \
  -H "api-subscription-key: $SARVAM_API_KEY" -H "Content-Type: application/json" \
  -d '{"text":"హాయ్ సాయి! Python ఒక ప్రోగ్రామింగ్ భాష.","language_code":"te-IN","model":"bulbul:v3","speaker":"shubh"}'
# → {"request_id":"...","audios":["UklGR...base64WAV..."]}
# decode: Buffer.from(audios.join(""), "base64")
```

**OpenAI Responses API (Node)**
```ts
const r = await openai.responses.create({
  model: "gpt-4o-mini",
  instructions: "You are a Telugu-first voice assistant...",
  input: [
    { role: "developer", content: "<user_custom_instructions>Always answer briefly.</user_custom_instructions>" },
    { role: "user", content: "Python అంటే ఏమిటి?" }
  ],
  max_output_tokens: 600,
});
// r.output_text
```

### C. Definition of Success (Phase 5 gate)
User can: open app → press mic → speak natural Telugu (incl. code-mix) → see correct transcript → hear natural Telugu response that follows custom instructions → continue with memory → interrupt gracefully → see clear errors without leaked secrets → architecture accepts `hi-IN`/`en-IN` by config.

### D. Implementation Order & Estimates

| Phase | Focus | Est. | Gate |
|---|---|---|---|
| 1 | Foundation & config | 2–3 d | Health + secret hygiene |
| 2 | STT + Brain (text) | 4–5 d | Telugu transcript + Telugu reasoning |
| 3 | TTS + voice loop | 3–4 d | End-to-end voice MVP |
| 4 | Custom brain + memory + language | 3–4 d | Personalization + extensibility |
| 5 | Realtime + hardening | 5–7 d | Streaming, barge-in, prod readiness |
| **Total** |  | **~17–23 d** (1 dev) |  |

> **Rule:** Do not start next phase until gate tests pass live. Do not claim integration works until real API flow is measured.

### E. References
- OpenAI Docs: `platform.openai.com/docs`, `developers.openai.com/api/docs`, `github.com/openai/openai-node`, `github.com/openai/openai-python`
- Sarvam Docs: `docs.sarvam.ai` (STT, TTS, streaming, errors, rate limits), `github.com/sarvamai/sarvam-ai-sdk`
- Voice-agent latency & pipeline patterns: industry cascaded STT→LLM→TTS with sentence buffering and VAD tuning.

