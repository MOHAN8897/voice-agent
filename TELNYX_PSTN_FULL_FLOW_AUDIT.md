# Telnyx PSTN Full-Flow Deep Audit

> **Auditor**: Antigravity Code Audit  
> **Date**: 2026-09-08  
> **Remediation pass 1**: 2026-09-08 (Cursor)  
> **Remediation pass 2 (deep re-verify)**: 2026-09-08 — closed partials, races, regressions  
> **Scope**: End-to-end PSTN call flow via Telnyx — ring → stream → STT → brain → TTS → hangup

---

## Executive Summary

Deep re-verification found several items previously marked ✅ FIXED that were **partial or regressed**. Pass 2 closed them:

- Removed harmful listening silence-VAD (was blocking STT end-of-utterance)
- Staged idempotent cleanup (shield cancel no longer leaks)
- Atomic admission lock for concurrent call limit
- Coalesce epoch (no double-launch race)
- Smarter pending-transcript merge + full turn text
- Production fail-closed webhook verify
- Redis-backed call registry when `REDIS_URL` set
- Stale prewarm brain-version reject
- Indic-aware reply clamp + web/server limit sync (180)

---

## Status legend

| Mark | Meaning |
|------|---------|
| ✅ FIXED | Fully implemented and wired in current code |
| ✅ VERIFIED OK | Original finding incorrect / already correct by design |
| ⬜ BY DESIGN | Intentionally unchanged (documented) |

---

## 1. Webhook & Call Setup

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 1.1 | No webhook signature verification | 🔴 | ✅ FIXED | `parse_verified_webhook_json` on webhook; Ed25519; **fail-closed** when `APP_ENVIRONMENT` is production/staging without `TELNYX_PUBLIC_KEY` |
| 1.2 | `call.answered` duplicate race | 🟡 | ✅ FIXED | `atomic_check_and_set("answered_handled")` — process lock + Redis `SET NX` claim when `REDIS_URL` set |
| 1.3 | No retry on `start_streaming` | 🟡 | ✅ FIXED | 3 attempts + exponential backoff; serialized by answered claim |
| 1.4 | In-memory-only registry | 🟡 | ✅ FIXED | Process memory + Redis mirror (`voice:telnyx:call:`) + distributed claim keys; TTL prune |
| 1.5 | `stream_url` scheme validation | 🟠 | ✅ FIXED | `build_stream_ws_url` rejects non-http(s) |

---

## 2. WebSocket Bridge & Audio Framing

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 2.1 | Duplicate `_outbound_pcm8k_buf` | 🟠 | ✅ FIXED | Single init |
| 2.2 | Clock drift in 20ms pacer | 🔴 | ✅ FIXED | Monotonic `next_send_at` |
| 2.3 | Assertion kills outbound worker | 🔴 | ✅ FIXED | Log + drop frame |
| 2.4 | Busy-wait queue backpressure | 🟡 | ✅ FIXED | `await queue.put` + timeout |
| 2.5 | Non-deterministic set prune | 🟠 | ✅ FIXED | FIFO `_invalid_generation_order` |
| 2.6 | Undocumented `clear` event | 🟡 | ✅ VERIFIED OK | Telnyx Clear Frame is documented |
| 2.7 | No WS health check | 🟡 | ✅ FIXED | 35s idle timeout on `receive()` |
| 2.8 | Orphan voice loop task | 🟡 | ✅ FIXED | `_voice_loop_task` cancelled in staged cleanup |

---

## 3. STT Pipeline

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 3.1 | STT during TTS / no AEC | 🔴 | ✅ FIXED | Soft AEC + barge hysteresis (2 loud frames open / 8 quiet close); floor RMS 320 |
| 3.2 | STT reader swallows errors | 🟡 | ✅ FIXED | `_stt_supervisor` + `_reopen_stt_socket` (max 3) |
| 3.3 | 20s STT ping | 🟠 | ✅ FIXED | 12s ping |
| 3.4 | No VAD pre-filter | 🟡 | ✅ FIXED | **Corrected approach**: do not drop silence while listening (STT needs silence to finalize). Soft AEC covers TTS echo. Provider VAD handles endpointer. |
| 3.5 | `"fast"` STT undocumented | 🟠 | ⬜ BY DESIGN | Runtime `sttStreamType` already configurable; ops note below |

---

## 4. Barge-In

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 4.1 | Order-blind bag-of-words echo | 🔴 | ✅ FIXED | 0.35 unigram + 0.65 bigram intersection |
| 4.2 | Min words uses `split()` | 🟡 | ✅ FIXED | `effective_word_count` |
| 4.3 | Hold timer reset on not_speaking | 🟡 | ✅ FIXED | Timer preserved across gaps |
| 4.4 | 0.8s debounce too aggressive | 🟡 | ✅ FIXED | `0.45s` |
| 4.5 | `_awaiting_barge_final` no timeout | 🟡 | ✅ FIXED | 4s timeout clears flag |
| 4.6 | No clear ACK | 🟡 | ✅ FIXED | Handle Telnyx `mark` events after clear |

---

## 5. LLM / Brain Turn

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 5.1 | No LLM response timeout | 🔴 | ✅ FIXED | `REALTIME_TURN_TIMEOUT_SEC=18` |
| 5.2 | Empty reply → dead air | 🟡 | ✅ FIXED | `UNCLEAR_FALLBACK` after empty retry |
| 5.3 | Untracked fire-and-forget turn | 🟡 | ✅ FIXED | `turn_coordinator.track` / orphan done-callback |
| 5.4 | Pending merge loses corrections | 🟡 | ✅ FIXED | Correction-aware merge (keep “no/not/wait…” + refinements) |
| 5.5 | Re-raise `CancelledError` loses state | 🟡 | ✅ FIXED | Pending preserved in `finally`; no re-raise after cleanup |
| 5.6 | 160 tok / 150 char too tight | 🟡 | ✅ FIXED | 220 tokens / 180 chars (server + web `types.ts`) |

---

## 6. TTS Pipeline

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 6.1 | 120s finish timeout | 🔴 | ✅ FIXED | 12s + `_done.set()` |
| 6.2 | No TTS connect timeout | 🟡 | ✅ FIXED | 8s `wait_for` on `__aenter__` |
| 6.3 | Double `_first_chunk` check | 🟠 | ⬜ BY DESIGN | Logging only; no functional bug |
| 6.4 | Force flush mid-word | 🟡 | ✅ FIXED | Word boundary; no-space flushes whole buffer |
| 6.5 | No TTS error fallback | 🟡 | ✅ FIXED | `_had_error` on reader/timeout; speak fallback on zero audio or turn exception |
| 6.6 | μ-law padding clicks | 🟠 | ✅ VERIFIED OK | `\xff` is correct G.711 silence |

---

## 7. Audio Transcoding

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 7.1 | `audioop` removed in 3.13 | 🔴 | ✅ FIXED | `audioop-lts` + all hot paths use `audio_transcode` (no raw bridge `import audioop`) |
| 7.2 | One-shot inbound resample | 🟡 | ✅ FIXED | Stateful `StreamingPcmResampler` on L16 inbound |
| 7.3 | μ-law silence padding | 🟠 | ✅ VERIFIED OK | Correct |
| 7.4 | Full decode for dBFS | 🟠 | ⬜ BY DESIGN | Low-cost; skip unless CPU-bound |

---

## 8. Turn-Taking & FSM

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 8.1 | Coalesce cancel race | 🟡 | ✅ FIXED | Epoch token; stale fire ignored |
| 8.2 | 0.22s coalesce too short | 🟡 | ✅ FIXED | 0.32s + 0.15s grace |
| 8.3 | Phase transitions not atomic | 🟡 | ✅ FIXED | `PHASE_ENDED` terminal; `_set_phase_async` on hangup/close; asyncio single-thread assign |
| 8.4 | ENDED doesn’t stop STT | 🟠 | ✅ FIXED | Reader breaks on `PHASE_ENDED` |
| 8.5 | Intro queue last-4 drops speech | 🟠 | ✅ FIXED | Keep last **8** |

---

## 9. Greeting & Prewarm

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 9.1 | Stale prewarm after brain edit | 🟡 | ✅ FIXED | Bundle stores `compiled_brain_version`; adopt rejects mismatch |
| 9.2 | English-biased opening regex | 🟡 | ✅ FIXED | `opening_line_te` + policy junk filter |
| 9.3 | Generic Telugu default greeting | 🟠 | ✅ FIXED | Extractor + `note_spoken` do-not-repeat marker |
| 9.4 | note_spoken only 2 retries | 🟠 | ✅ FIXED | 5 attempts + backoff + session priming |

---

## 10. Call End / Hangup

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 10.1 | Lifecycle end blocks cleanup | 🟡 | ✅ FIXED | 5s `wait_for` |
| 10.2 | Hangup before farewell | 🟡 | ✅ FIXED | `drain_outbound(2.5s)` before provider hangup |
| 10.3 | Drop queued farewell frames | 🟡 | ✅ FIXED | Same drain path |

---

## 11. Memory & Context

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 11.1 | Clear conversation on every call | 🟡 | ⬜ BY DESIGN | Fresh PSTN legs; callback memory is separate |
| 11.2 | Turn transcript is trigger-only | 🟠 | ✅ FIXED | Launch merges pending barge/correction into `_current_turn_transcript` |

---

## 12. Concurrency & Resources

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 12.1 | No concurrent call limit | 🟡 | ✅ FIXED | `TELNYX_MAX_CONCURRENT_CALLS` + **`_admission_lock`** (check+insert atomic) |
| 12.2 | `_ws_send_lock` serializes WS | 🟡 | ⬜ BY DESIGN | Required for WebSocket frame integrity |
| 12.3 | Cleanup not shielded / leaky | 🟠 | ✅ FIXED | `asyncio.shield` + **staged idempotent cleanup** (safe re-entry) |

---

## 13. Prompt & Brain

| # | Issue | Severity | Status | Evidence |
|---|-------|----------|--------|----------|
| 13.1 | English-biased char limits | 🟡 | ✅ FIXED | 180 char / 220 token; web synced |
| 13.2 | Clamp cuts Telugu mid-thought | 🟡 | ✅ FIXED | Avoid cutting on Indic combining marks / virama |
| 13.3 | PHONE_SPEAK_BAN vs capture | 🟠 | ✅ FIXED | Speak-vs-capture + `CALLER_DETAIL_CAPTURE` |

---

## Pass-2 gap log (what was wrong before)

| Gap | Why prior “FIXED” was incomplete | Fix |
|-----|----------------------------------|-----|
| 3.4 silence VAD while listening | Dropped silence → STT never finalized | Removed listening silence gate |
| 3.1 soft AEC mute | Single RMS threshold muted quiet barge | Hysteresis (2 loud open / 8 quiet close) + lower floor 320 |
| 12.3 cleanup | `_closed=True` then early-return on retry leaked resources | Staged flags; re-entrant |
| 12.1 admission | Check then insert race under load | `asyncio.Lock` |
| 8.1 coalesce | Cancelled fire cleared new transcript / double launch | Epoch |
| 5.4 / 5.5 / 11.2 | Corrections lost; CancelledError wiped pending | Merge + no re-raise |
| 1.1 prod | Missing key skipped verify in production | Fail-closed staging/prod |
| 1.4 | Memory-only / multi-worker claim race | Redis mirror + **SET NX** claim keys for `answered_handled` |
| 9.1 | TTL only | Brain version check on adopt |
| 6.5 | Fallback only mid-finish path | Reader/timeout set `_had_error`; zero-audio fallback; turn exception speech |
| 7.1 raw `import audioop` | Bridge/TTS bypassed `audio_transcode` shim | Route μ-law via `pcm16_to_mulaw` |
| 8.3 dead `_set_phase_async` | Never called | Used on hangup/close `PHASE_ENDED` |

---

## Ops checklist

1. Set **`TELNYX_PUBLIC_KEY`** (required in staging/production).
2. Set **`REDIS_URL`** for multi-worker call-registry durability.
3. Tune **`TELNYX_MAX_CONCURRENT_CALLS`** (default 50).
4. Python ≥3.13: ensure **`audioop-lts`** installed.
5. STT: prefer `sttStreamType=accurate` for Telugu quality if latency allows (3.5).

---

## Summary

All audit items are either **fully fixed**, **verified OK**, or **explicitly by design**. No critical/partial items remain open from this checklist. Regression suite for PSTN/webhook/hangup/limits/prewarm: green after pass 2.
