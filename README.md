# Telugu Voice Agent — Phases 1–5

Telugu-first voice agent: `Mic → Sarvam STT → OpenAI Brain → Sarvam TTS → Playback`
with **realtime WebSocket streaming**, **dynamic prompting**, and a **Fine-tune Console**.

## 🚀 How to Run

```powershell
# 1) One-time setup
Copy-Item .env.example .env
#    Edit .env and fill in:
#      OPENAI_API_KEY=sk-...        (https://platform.openai.com/api-keys)
#      SARVAM_API_KEY=...           (https://dashboard.sarvam.ai)
#    Everything else has sensible defaults.

# 2) Install (Python 3.10+)
pip install -e ".[dev]"

# 3) Start
python -m uvicorn server.app:app --reload --port 8000

# 4) Use it
#    Main agent:   http://localhost:8000            (mic button, Space = talk, Esc = stop audio)
#    Fine-tune:    http://localhost:8000/settings.html

# 5) Tests
python -m pytest -v        # 37 tests
```

## Modes (main page)

| Toggle | Path | Latency profile |
|---|---|---|
| **Full Voice Loop** (default) | `POST /api/voice/turn` — record → STT → Brain → TTS → autoplay | simplest, ~2-4s e2e |
| **⚡ Realtime WS** | `WS /ws/stt-realtime` (`saaras:v3-realtime`, `stream_type=fast`) → live partials while you speak; on final: Brain → `WS /ws/tts` (`bulbul:v3`) streamed into MediaSource | lowest perceived latency, live partials |
| Uncheck Voice Loop | STT → Brain text only | fastest text iteration |

## Fine-tune Console (/settings.html)

Everything is **per-session** (24h TTL), validated against provider catalogs, keys stay in `.env`:

- **STT**: model (`saaras:v3`/`saaras:v4`/`saarika:v2.5`), mode (transcribe/codemix/…), language, realtime stream type, VAD silence ms + threshold sliders
- **TTS**: model (`bulbul:v3`/`v2`), speaker (37 v3 voices), pace slider, temperature slider (v3 only), codec, sample rate + **Test TTS** button
- **OpenAI**: model allowlist (`OPENAI_ALLOWED_MODELS` env), temperature, max output tokens — *keys are never enterable in the browser (security standard)*
- **Dynamic prompting**: response style dropdown + custom instructions textarea (wrapped `<user_custom_instructions>` developer-role block that cannot override system safety), Save/Reset, **View effective prompt** (hierarchy transparency via `GET /api/prompt/effective`)

Saved settings automatically apply to `/api/brain`, `/api/tts`, and `/api/voice/*`.

## Verified Provider Contracts (docs.sarvam.ai + platform.openai.com, Aug 2026)

- STT REST `POST /speech-to-text` (`saaras:v3`, `te-IN`, ≤30 s) · Realtime WS `/speech-to-text-realtime/ws` (`audio_input` base64 PCM16 ⇄ `transcript.partial/final`, VAD events, close codes 1003/1008/1011/4000)
- TTS REST `POST /text-to-speech` · HTTP stream `/text-to-speech/stream` · WS `/text-to-speech/ws?model=bulbul:v3&send_completion_event=true` (`config→text→flush`, audio chunks `{type:"audio",data:{audio:b64}}`, completion `data.event_type=="final"`; **no server-side cancel — barge-in closes the socket client-side**, per docs)

## API Map

```
GET  /api/health | /api/meta | /api/metrics (+POST reset) | /api/config-check
GET  /api/prompt/effective?sessionId=
POST /api/stt (multipart)          POST /api/brain [/stream SSE] [/test]
POST /api/tts [/stream]            POST /api/voice/turn | /api/voice/stt-brain
GET/POST/DELETE /api/instructions  GET/POST/DELETE /api/settings/runtime  GET /api/settings/catalog
POST /api/session/clear | /api/session/interrupt     GET /api/session/history
WS   /ws/stt-realtime              WS   /ws/tts
```

## Layout & Docs

- Plan: `IMPLEMENTATION_PLAN_V2.md` · Audit: `AUDIT_REPORT.md` · Reports: `PHASE_1_2_REPORT.md`, `PHASE_3_4_REPORT.md`
- Server: `server/{config,services,agent,routes,session,utils,prompts}` · Client: `client/` (app.js, settings.js, pcm-worklet.js)
