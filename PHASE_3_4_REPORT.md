# Phase 3 & 4 — Completion Report

**Date:** 2026-08-23
**Plan:** `IMPLEMENTATION_PLAN_V2.md:355` (Phase 3) + `IMPLEMENTATION_PLAN_V2.md:414` (Phase 4)
**Result:** ✅ Both phases implemented, mocked-tested (24/24 pass), live smoke verified.

---

## Phase 3 — Telugu TTS + End-to-End Voice Loop

**Goal per spec:** `Mic → STT → Brain → TTS → Playback` with perf measurement.

### What Was Built

| Task | File | Notes |
|---|---|---|
| **3A TTS service** | `server/services/sarvam_tts_service.py:1` | `synthesize()` REST: `POST https://api.sarvam.ai/text-to-speech` JSON `{text, language_code:"te-IN", model:"bulbul:v3", speaker, pace:0.5-2.0}` → decode `audios[]` base64 → `audio/wav`. `synthesize_stream()` HTTP stream: `POST /text-to-speech/stream` yields binary `mp3` chunks. Limits 2500/3500, speaker via `get_speaker_for_language()`, error taxonomy §4.4. |
| **TTS routes** | `server/routes/tts.py:1` | `POST /api/tts` (413 if >2500, returns `audio/wav`), `POST /api/tts/stream` (`audio/mpeg` chunked). Validates `language_code` against `SUPPORTED_LANGUAGES`. |
| **Voice Session Controller** | `server/session/voice_session.py:1` | `VoiceSessionController.run_turn()` orchestrates `PROCESSING_STT → THINKING → GENERATING_TTS → PLAYING`, owns `TurnResult` with `sttMs/brainMs/ttsMs/e2eMs`, `request_ids`, `language_context`. Logs `[PERF] turn` per spec §7. Handles empty transcript + abort (barge-in hook for Phase 5). |
| **Voice Turn routes** | `server/routes/voice.py:1` | `POST /api/voice/turn` (multipart `file` + `sessionId` + `userInstructions`) → JSON `{transcript, brain_text, language_context, audio_base64, metrics, request_ids}`. Also `POST /api/voice/stt-brain` text-only. Merges stored instructions (Phase 4) if no explicit param. |
| **3B Client Playback** | `client/app.js:37` (`playBase64()`), `client/index.html:49` | `Audio` element, `URL.createObjectURL` from `atob` base64, `play()` with autoplay-block handling, `stopAudio()`, `Replay`, `TTS only` (calls `POST /api/tts` for current response), `metrics` + `ttsInfo` display. Barge-in prep: stops audio on new recording. |
| **3C Wiring** | `server/app.py:18` | Added `tts_router`, `voice_router`, bumped `APP_VERSION:0.1.0-phase4`, `lifespan` startup, `GET /api/meta` now lists TTS + voice endpoint. |

**Exit Criteria (mocked + live no-key smoke):**
- [x] `POST /api/tts` mocked → returns `audio/wav` (`test_tts_rest_mocked`) ✅
- [x] `POST /api/tts` >2500 → 413 ✅
- [x] `POST /api/tts/stream` mocked → `audio/mpeg` chunks ✅
- [x] `POST /api/voice/turn` mocked → base64 audio + metrics (`test_voice_turn_mocked`: `e2eMs 820`) ✅
- [x] Empty transcript → graceful `error: empty_transcript` no TTS ✅
- [x] Live smoke with dummy keys: `POST /api/tts` correctly returns 403 `auth_error` ("AI service configuration is invalid.") — not leaked, handled per §4.4 ✅
- [x] Client: toggle `Full Voice Loop` checked → voice turn + autoplay; unchecked → STT→Brain text-only; `Replay` + `TTS only` work; `metrics` shows `stt/brain/tts/e2e` ✅

---

## Phase 4 — User-Customizable Brain, Memory & Language Resolver

**Goal per spec:** Personalization + state + extensibility by config.

### What Was Built

| Task | File | Notes |
|---|---|---|
| **4A Instruction Builder** | `server/agent/instruction_builder.py:1` (existing, verified) | `build_agent_instructions({core,user,language})` wraps `user_custom_instructions`, strips tags, caps 2000, never overrides system `instructions`. Already used by `openai_brain_service.py:44`. |
| **4B Instruction Store + API** | `server/agent/instruction_store.py:1`, `server/routes/instructions.py:1` | In-memory per-`sessionId` with 24h TTL, `sanitize_user_instructions`. Routes: `POST /api/instructions` (save, returns sanitized), `GET /api/instructions?sessionId=`, `DELETE /api/instructions`. Brain routes fallback to store: `server/routes/brain.py:31` + `server/routes/voice.py:38` (if `userInstructions` missing, load stored). |
| **Customize AI UI** | `client/index.html:69`, `client/app.js:62` | Textarea + `Save` (POST store + localStorage), `Reset` (DELETE + local), `Test` (POST `/api/brain/test` ephemeral), `Active` badge, `saveStatus`, `previewOutput`, `historyCount`. Loads server value on start (`loadInstructions()`). |
| **4C Conversation Memory** | `server/agent/conversation_manager.py:1` (existing) | `MAX 12` + TTL 30m, `add_turn` + `_trim`, `clear`, `get_history`. Tested: `test_history_and_trim`, `test_brain_memory_via_mock` (Sai two-turn). Phase 4 adds metrics + store fallback; no rewrite needed — extensible as spec. |
| **4D Language Resolver** | `server/agent/language_resolver.py:1` | `resolve_language()` code-mix regex `[\u0C00-\u0C7F]` + `[A-Za-z]`, always `responseLanguage: te-IN` in Phase 1-4, `SUPPORTED_LANGUAGES` map in `server/config/constants.py:22`. TTS speaker via `get_speaker_for_language()` and `SARVAM_TTS_SPEAKER_TE` env. Adding `hi-IN` = one map entry + voice test (no pipeline change). |

**Exit Criteria:**
- [x] Custom instruction `"ఎప్పుడూ చిన్నగా సమాధానం ఇవ్వాలి."` → short answer (store + brain merge, tested `test_brain_uses_stored_instructions`) ✅
- [x] Conflict: 5000-word request blocked by `MAX_RESPONSE_LENGTH` (brain `max_output_tokens` cap) — system wins ✅ (enforced in `openai_brain_service.py:69`)
- [x] Test-before-save: `POST /api/brain/test` ephemeral session, no persistence (`previewBtn` in `client/app.js:236`) ✅
- [x] CRUD mocked: `test_instructions_crud` + `test_instructions_sanitize` ✅
- [x] `hi-IN` extensibility: `constants.SUPPORTED_LANGUAGES` already has `hi-IN`/`en-IN`, voice picks speaker by `responseLanguage` — no pipeline change ✅

---

## Verification

```
python -m pytest -v   → 24 passed (Phases 1-4)
GET /api/health (no .env)  → ok:false, no leak
GET /api/health (dummy)    → ok:true, version 0.1.0-phase4
GET /api/meta              → lists tts + voice endpoint
GET /api/instructions?sess → {present:false} → POST → {present:true} → DELETE → cleared
POST /api/tts (dummy key)  → 403 auth_error (correct taxonomy)
POST /api/voice/turn (mock)→ base64 audio + metrics e2e 820ms
GET /                      → Phase 4 HTML (voice toggle, playback, customize)
client grep OPENAI_API_KEY → empty (no secret leak)
```

## How to Run (Phases 3-4)

```powershell
# .env already needs OPENAI_API_KEY + SARVAM_API_KEY for live TTS/Brain
python -m uvicorn server.app:app --reload --port 8000
# Open http://localhost:8000
# - Check "Full Voice Loop" on, press mic, speak Telugu → transcript + Telugu response + autoplay Telugu audio
# - Uncheck for text-only loop
# - Customize AI: type instruction → Save → speak → response style changes; Test previews without saving; Reset clears
# - Playback: Replay last, TTS only, Stop audio, metrics show stt/brain/tts/e2e
```

Live full-loop cURL (needs real keys):
```bash
curl -X POST http://localhost:8000/api/voice/turn \
  -F "file=@utt.wav" -F "language_code=te-IN" -F "sessionId=live" -F "userInstructions=Answer briefly"
# → {"transcript":"…","brain_text":"…","audio_base64":"UklGR…","metrics":{"sttMs":…,"brainMs":…,"ttsMs":…,"e2eMs":…}}

# TTS only:
curl -X POST http://localhost:8000/api/tts -H "Content-Type: application/json" \
  -d '{"text":"హాయ్ సాయి, ఎలా ఉన్నారు?","language_code":"te-IN"}' --output out.wav
```

Next: **Phase 5** — realtime WS (`/speech-to-text-realtime/ws` `stream_type=fast`), streaming Brain + TTS sentence buffer, barge-in `interrupt()` (stop audio + abort), rate limits, `/api/metrics`.
