# Telugu Voice Agent — End-to-End Architecture (Current Build v0.2.0-phase5)

## 1) High-Level Topology

```
┌─────────────────────────────── BROWSER (client/) ───────────────────────────────┐
│                                                                                 │
│  index.html (Agent)                          settings.html (Fine-tune Console)  │
│  ┌───────────────────────────┐               ┌────────────────────────────────┐  │
│  │ 🎙 MicButton  ⚡Live toggle│               │ STT model/mode/VAD sliders     │  │
│  │ Voice-Loop toggle          │               │ TTS model/speaker/pace/temp    │  │
│  │ Hands-free ☑  Partials     │               │ OpenAI model/temp/maxTokens    │  │
│  │ Dual prompts 🧠/🏢         │               │ Behaviour + Business prompts   │  │
│  └───────────┬───────────────┘               └──────────────┬─────────────────┘  │
│              │                                              │                    │
│  ┌───────────▼──────────────────────────────────────────────▼─────────────────┐ │
│  │ app.js — Session Controllers                                               │ │
│  │                                                                            │ │
│  │ [A] Push-to-Talk (REST)      [B] ⚡ LIVE SESSION (full-duplex, default ⚡)   │ │
│  │  MediaRecorder(webm/opus)     getUserMedia(AEC+NS+AGC @16k)                 │ │
│  │        │ blob                       │                                       │ │
│  │        ▼                            ▼ pcm-worklet.js (Int16 PCM ~128ms)    │ │
│  │  POST /api/stt                RMS Echo Gate (2-tier: speaking/cooldown)    │ │
│  │        │ transcript                 ▼ binary frames                        │ │
│  │  POST /api/brain              WS /ws/stt-realtime ──── persistent ─┐       │ │
│  │        │ text                                                  │       │ │
│  │        ▼                                                       │       │ │
│  │  POST /api/tts                                                 │       │ │
│  │        │ wav                                                   │       │ │
│  │        ▼                                                       │       │ │
│  │  AudioPlaybackManager                                          │       │ │
│  │  • FIFO queue • AUTO-play • no overlap                         │       │ │
│  │  • 1-tap unlock overlay (browser policy)                       │       │ │
│  │  • onFinished → hands-free re-listen                           │       │ │
│  │  Hands-free loop: empty×3 guard → pause                        │       │ │
│  └────────────────────────────────────────────────────────────────┘       │ │
│                                                                           │ │
│  [B] Turn pipeline (runTurn):                                             │ │
│   transcript.final ─► POST /api/brain/stream (SSE deltas) ─┐              │ │
│                          │ deltas                          │             │ │
│                 SentenceAccumulator (~80c / punctuation)    │             │ │
│                          │ chunks                          │             │ │
│                          ▼                                 │             │ │
│                 WS /ws/tts (warm per turn) ◄───────────────┘             │ │
│                          │ base64 mp3 chunks                             │ │
│                          ▼                                               │ │
│                 MediaSource(audio/mpeg) ─► <audio> AUTOPLAY ⚡            │ │
│   Barge-in: ≥2-word partial while speaking → stop audio +                │ │
│             abort SSE + close TTS + 1.2s cooldown → keep listening       │ │
└───────────────────────────────────────────────────────────────────────────┘
        │ HTTPS/REST (JSON, multipart, SSE)          │ WSS (binary PCM ⇅ JSON events)
        ▼                                            ▼
┌────────────────────────── SERVER (FastAPI, server/) ────────────────────────────┐
│ Middleware: CORS → RateLimit (60/min general · 20/min tts+voice) → Routes       │
│                                                                                 │
│ routes/stt.py ──────► services/sarvam_stt_service.py ──► Sarvam STT REST        │
│ routes/brain.py ────► services/openai_brain_service.py ► OpenAI Responses API   │
│   ├ /api/brain        (JSON one-shot, retries+quota-failfast)                   │
│   ├ /api/brain/stream (SSE: output_text.delta → client)                         │
│   └ /api/brain/test   (ephemeral prompt preview)                                │
│ routes/tts.py ──────► services/sarvam_tts_service.py ──► Sarvam TTS REST/Stream │
│ routes/voice.py ────► session/voice_session.py                                  │
│   └ POST /api/voice/turn = STT→Brain→TTS orchestrator + [PERF] spans            │
│ routes/ws.py ───────► services/sarvam_ws.py                                     │
│   ├ WS /ws/stt-realtime : PCM b64 ⇅ transcript.partial/final + VAD events       │
│   └ WS /ws/tts          : config/text/flush ⇅ mp3 chunk stream                  │
│ routes/instructions.py ► agent/instruction_store.py (behaviour+business,10k ea) │
│ routes/settings.py ───► services/runtime_settings.py (model/voice/temp allowlists)│
│ routes/session_control.py (barge-in ack) · routes/metrics.py (p50/p95)          │
│ agent/: conversation_manager(RLock,TTL30m,MAX12) · language_resolver            │
│         instruction_builder (System>Core>Behaviour>Business>Style)              │
│ utils/: errors taxonomy · logger(redacted) · metrics · rate_limiter · audio     │
│ config/env.py: zod-style fail-fast, secret redaction                            │
│ session/session_state.py: IDLE→LISTENING→PROCESSING_STT→THINKING→               │
│                           GENERATING_TTS→PLAYING→IDLE (+ERROR/INTERRUPTED)      │
└─────────────────────────────────────────────────────────────────────────────────┘
        │                                      │
        ▼                                      ▼
┌──────────────────────┐            ┌──────────────────────────────────┐
│ OPENAI  /v1/responses│            │ SARVAM  api.sarvam.ai            │
│ model: gpt-4o-mini*  │            │ STT REST  /speech-to-text        │
│ instructions=SYSTEM  │            │           saaras:v3 · te-IN ≤30s │
│ input=[developer,    │            │ STT WS    /speech-to-text-       │
│         history,user]│            │           realtime/ws            │
│ stream=deltas        │            │           saaras:v3-realtime     │
└──────────────────────┘            │           stream_type=fast VAD   │
                                    │ TTS REST  /text-to-speech        │
 *allowlist via                     │ TTS HTTP  /text-to-speech/stream │
  OPENAI_ALLOWED_MODELS             │ TTS WS    /text-to-speech/ws     │
                                    │           bulbul:v3 · shubh…37v  │
                                    └──────────────────────────────────┘
```

## 2) ⚡ Live Session — One Full-Duplex Conversation (sequence)

```
 USER                CLIENT(app.js)                PROXY(server/routes/ws.py)        SARVAM                OPENAI
  │ click 🎙 (gesture)      │                              │                           │                    │
  ├────────────────────────►│ unlock playback ✓           │                           │                    │
  │                         │ getUserMedia(AEC)+Worklet   │                           │                    │
  │                         ├─WS connect─────────────────►├─WSS connect──────────────►│                    │
  │                         │◄─session.begin──────────────┤◄──────────────────────────┤                    │
  │ speaks continuously ────┼─PCM16 frames(gated)────────►├─{audio_input,b64}────────►│                    │
  │                         │◄─transcript.partial─────────┤◄──────────────────────────│                    │
  │ stops (VAD 400ms)       │◄─transcript.final───────────┤◄──────────────────────────│                    │
  │                         │                             │                           │                    │
  │                         ├──POST /api/brain/stream────►│──POST /v1/responses───────┼───────────────────►│
  │                         │◄─delta,delta,delta…(SSE)────┤◄──output_text.delta───────┼────────────────────┤
  │                         │  └─accumulate→push──────────┤                           │                    │
  │                         ├─{type:text}×N──────────────►├─text msgs────────────────►│ (buffers/splits)   │
  │ hears FIRST SENTENCE ⚡ │◄═mp3 chunks═════════════════│◄══audio(b64)══════════════│                    │
  │                         │  MSE→autoplay (no button)   │                           │                    │
  │ interrupts mid-answer 👤 │  (≥2-word partial detected) │                           │                    │
  │                         │ ✂ stop audio (<150ms)       │                           │                    │
  │                         │ ✂ abort brain fetch         │                           │                    │
  │                         │ ✂ close TTS sock            │                           │                    │
  │                         │ …1.2s echo cooldown…        │                           │                    │
  │ keeps talking ──────────┼─PCM────────────────────────►│ (socket never closed)     │                    │
  │ stops                   │◄─transcript.final───────────┤                           │                    │
  │                         ├──next runTurn()────────────►│ …same streaming cycle…    │                    │
  │ clicks 🎙 again = STOP  │ {end}→close; hands-free off │                           │                    │
```

## 3) Prompt Hierarchy sent to the Brain (every turn)

```
┌─ instructions (SYSTEM, untouchable) ────────────────────────────────┐
│ Safety rules · "never reveal system/API keys"                       │
├─ developer role content ────────────────────────────────────────────┤
│ CORE: Telugu-first · code-mix natural · concise spoken style        │
│ <agent_behaviour_instructions>  HOW to respond      ≤10,000 chars   │
│ <business_context_instructions> WHAT you know       ≤10,000 chars   │
│   ("grounding knowledge — never invent beyond it")                  │
│ Language: te-IN · Style: <console dropdown>                         │
├─ input[] ───────────────────────────────────────────────────────────┤
│ history: last 12 msgs (RLock, TTL 30m, trim-oldest)                 │
│ user: current transcript (raw Telugu/Tenglish — never translated)   │
└─────────────────────────────────────────────────────────────────────┘
Runtime overrides (Fine-tune console): openaiModel · temperature · maxTokens
```

## 4) State Machine (client mirrors server enum)

```
IDLE ──mic──► LISTENING ──final──► THINKING ──first audio──► SPEAKING ──ended──► LISTENING
  ▲                │  ▲                 │ abort(≥2w partial)     │ manual mic-click
  │                │  └─ queued finals ─┘                        ▼
  │                └──empty×3 (hands-free guard) ──► PAUSED    INTERRUPTED
  └──────────────────────── stop/error ◄──── ERROR ◄── provider failure (401/429/timeout→retry≤2)
```

## 5) Resilience & Guardrails Map

| Concern | Where |
|---|---|
| Secrets never client-side | `config/env.py` redaction; all calls proxied |
| Autoplay blocked | `audio_playback_manager.onBlocked` → single 🔊 tap card |
| Overlapping speech | PlaybackManager FIFO + `agentSpeaking` flag + RMS gate |
| False barge-in | ≥2-word partial guard + 1.2s cooldown + AEC |
| Quota/billing | `insufficient_quota` → fail-fast actionable message (no retry loop) |
| 429 storms | exp backoff ≤2 + server rate-limits + Retry-After passthrough |
| Long sessions | history trim MAX12/TTL30m · instruction TTL24h · WS ping keepalive |
| Observability | `[PERF]` spans, `/api/metrics` p50/p95, `/api/prompt/effective`, redacted logs |

## 6) Latency Budget (measured targets, live mode)

| Stage | Target | Mechanism |
|---|---|---|
| Endpointing | 350–500ms | server VAD `silence_duration_ms` (console slider) |
| STT final after last word | ~100–300ms | `stream_type=fast` partials already visible |
| Brain first delta | ~300–800ms | Responses API streaming |
| First audible word | +150–400ms | sentence accumulator → warm TTS WS (`min_buffer_size:50`) |
| **Total time-to-first-audio** | **≈0.9–1.6s** | overlapping stages, not sequential sum |
