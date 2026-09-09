# PSTN Voice Architecture — Technical Audit (living)

**Status:** Post-fix audit. Original snapshot was 2026-09-08 (read-only). This file is updated to match **current code** after the `VOICE_AGENT_PRESETS.md` P0–P2 playbook.  
**Living invariants:** prefer `VOICE_AGENT_PRESETS.md` for barge/playback rules.  
**Scope:** Dial → prewarm → answer → media WS → STT → LLM/Realtime → streaming TTS → provider audio → barge → hangup.

---

## Executive summary

The shared `PstnVoiceLoop` + provider media adapters + Realtime streaming + sentence TTS design is in place and **mostly deterministic** after P0–P2.

### Already fixed (do not re-implement)

| Former risk | Status | Where |
|-------------|--------|--------|
| TTS `_flush_audio_tail` after barge | **RESOLVED** | `pstn_turn_tts.py` — skip flush when interrupted / `emission_blocked` |
| Exotel/Plivo no `is_agent_audio_active` | **RESOLVED** (estimate) | `EstimatedPlaybackTracker` wired in both bridges |
| Misleading “echo-tail drops STT frames” comment | **RESOLVED** | STT stays ON; dual-rail echo on transcripts |
| Barge “disabled” comment vs `True` | **RESOLVED** | Comment: barge is ON |
| Realtime cancel on barge critical path | **RESOLVED** | `interrupt_tts` → `create_task(cancel)` |
| `_turn_busy` held through memory merge | **RESOLVED** | stream path `create_task(_after_assistant)` |
| Unbounded archive `create_task` | **RESOLVED** | `PstnArchiveWriter` |
| Soft `note_spoken` only | **RESOLVED** | retry ×2 + priming fallback |
| Telnyx invalid gens never pruned | **RESOLVED** | prune at >16 |

### Remaining open risks (current)

1. **MEDIUM — Exotel/Plivo playback is estimate-only** (no provider ACK drain); post-send hold (~150 ms) biases “still playing.”
2. **MEDIUM — Media-flow / `tts_first_audio_ms` still Telnyx-centric** in ledger traces.
3. **LOW–MEDIUM — Cartesia on 8 kHz bridges** now forces μ-law conversion when codec is mulaw; still watch non-Cartesia L16 paths.
4. **LOW — Competing Realtime + PSTN layers** — OK if only `_run_turn` starts Realtime turns.

**Principle:** measure p50/p95 stage latencies before retuning barge/VAD constants (P3).

---

## 1. Current architecture

### 1.1 Layers

```
Dial / registry metadata
        │
        ▼
pstn_prewarm (Realtime + greeting frames) ──TTL 90s──┐
        │                                             │
Answer / provider media WebSocket                     │
        │                                             │
call_lifecycle_service.start ◄── adopt prewarm ───────┘
        │
        ▼
PstnVoiceLoop  (FSM + barge + STT + TTS)
        │
        ├── STT WS (always on; echo rails on text)
        ├── live_turn_orchestrator → RealtimeTextSession / HTTP LLM
        ├── PstnTurnTtsSession (one TTS WS per reply; no flush on interrupt)
        ├── PlaybackController (Telnyx queue | Exotel/Plivo estimate)
        └── Provider bridge (codec, framing, clear)
```

### 1.2 Core files

| Role | Path |
|------|------|
| Shared voice loop | `server/services/pstn_voice_core.py` |
| Turn TTS session | `server/services/pstn_turn_tts.py` |
| Playback controllers | `server/services/pstn_playback.py` |
| Archive single-writer | `server/services/pstn_archive_writer.py` |
| Echo dual-rail | `server/services/echo_guard.py` |
| Sentence chunker | `server/services/pstn_text_chunker.py` |
| Prewarm | `server/services/pstn_prewarm.py` |
| Orchestrator | `server/call/live_turn_orchestrator.py` |
| Realtime | `server/realtime/text_session.py`, `manager.py` |
| Exotel / Telnyx / Plivo | `server/services/*_pstn_bridge.py` |
| Fix playbook | `VOICE_AGENT_PRESETS.md` |

### 1.3 Behavior → implementation

| Behavior | Implementation | Verdict |
|----------|----------------|---------|
| Shared `PstnVoiceLoop` | All bridges | **Correct** |
| Prewarm Realtime + greeting | `pstn_prewarm` TTL 90s; adopt ~3s | **Correct** |
| Intro barge off + queue | `PHASE_INTRO` / `_intro_queue` | **Correct** |
| `note_spoken` + retry/prime | `_note_opening_spoken` | **Correct** |
| `_tts_active` whole turn | `_set_tts_active` | **Correct** |
| Endpointing ≠ barge | finals vs partials | **Correct** |
| Barge 3 / 0.7s / 0.2s / 0.8s | constants + `_should_commit_barge` | **Correct** |
| Dual-rail echo | barge 0.55 / final-tail 0.65 / listening 0.80 / barge-final 0.85 | **Correct** |
| STT always on | intentional; echo on text rails | **Correct** |
| Telnyx clear + drain + gen drop | `TelnyxQueuePlayback` + `_invalid_generations` | **Correct** |
| Exotel/Plivo active tracking | `EstimatedPlaybackTracker` + clear | **Correct (estimate)** |
| Pending / barge-final | `_awaiting_barge_final` window 1.5s | **Correct** |
| Empty cancelled archive skip | orchestrator | **Correct** |
| One turn at a time | `_turn_busy` + coordinator + lock | **Correct** |
| Think-cancel | while `PHASE_THINKING`, ≥3 words / 0.2s | **Correct** |
| Media-flow all providers | mainly Telnyx | **Gap** |

---

## 2. Call lifecycle (traced)

### 2.1 Dial → prewarm → answer

Unchanged: dial stores meta → `schedule_prewarm` → media WS → `call_lifecycle_service.start` (adopt or cold Realtime) → build `PstnVoiceLoop` + playback → `start_call`.

### 2.2 Intro

1. `PHASE_INTRO`; barge off; finals → `_intro_queue`.
2. Parallel: `open_stt` + prewarm frames or `speak(greeting)` + `_note_opening_spoken`.
3. `_end_intro_phase` → `PHASE_LISTENING`; optional `_launch_turn(queue)`.

### 2.3 Normal turn

1. Final (idle) → `_launch_turn` → `PHASE_THINKING` → stream LLM → `PHASE_SPEAKING` on TTS.
2. Sentence drain → `_send_tts_text` (`prepare_spoken_reply`) → wire via playback.
3. `finally`: voice free → `PHASE_LISTENING` (or stay `INTERRUPTING` for barge-final); launch pending.
4. Memory/archive: background `_after_assistant` (does not hold voice busy).

### 2.4 Barge (fast path)

```
BARGE_COMMIT
  → _interrupted_generation = old_gen; invalidate(old_gen)
  → note_barge(heard_sentences)
  → provider clear (_on_barge)
  → interrupt_tts (no flush; clear playback; cancel TTS)
  → Realtime cancel via create_task (not awaited)
  → PHASE_INTERRUPTING; await barge final ≤1.5s
```

### 2.5 Hangup

Agent hangup gated → lifecycle end + provider hangup. Remote stop → `voice.close()` → archive drain → `end(pstn_hangup)`.

---

## 3. Audio pipeline

| Provider | In | STT rate | Out | Playback truth |
|----------|----|----------|-----|----------------|
| **Exotel** | PCM@8k (assumed) | 8000 | μ-law media; **one `turn-end` mark per TTS end** | `EstimatedPlaybackTracker` |
| **Telnyx** | L16@16k / G.711 | 16000 | 20 ms paced `_out_queue` | `TelnyxQueuePlayback` |
| **Plivo** | μ-law → PCM | 8000 | `playAudio` μ-law | `EstimatedPlaybackTracker` |

**TTS path:** chunks → optional μ-law@8k (including Cartesia when bridge is mulaw) → frames → `_emit_agent_wire` (gen / interrupt guards) → bridge.

**Open audio risks:** Exotel inbound codec not asserted; estimate ≠ true buffer; media-flow sparse on 8 kHz bridges.

---

## 4. FSM (actual)

```
INTRO → LISTENING → THINKING → SPEAKING → INTERRUPTING → LISTENING
                                         ↘ CLEANING → ENDED
```

| Phase | Allowed |
|-------|---------|
| INTRO | finals → intro queue; barge OFF |
| LISTENING | final → THINKING |
| THINKING | think-cancel on partial ≥3 words / 0.2s; barge N/A until audio |
| SPEAKING | barge → INTERRUPTING |
| INTERRUPTING | no new LLM; barge-final window |
| ENDED | ignore |

**Playback truth:** `provider_playing = playback.is_active() OR _tts_active OR echo_tail` — never `_tts_active` alone.

---

## 5. Async task map

| Task | Owner |
|------|-------|
| Prewarm builder / TTL | `pstn_prewarm` |
| Media WS + Telnyx `_out_worker` | bridge |
| `_stt_reader` / ping | voice loop |
| `_run_turn` (tracked) | voice loop |
| TTS reader / ping | `PstnTurnTtsSession` |
| Archive writer | `PstnArchiveWriter` |
| `_after_assistant` | orchestrator (background) |
| Realtime cancel | fire-and-forget from barge |

---

## 6. PlaybackController

```text
PlaybackController
  is_active() / queued_ms() / clear()
  invalidate_generation / set_current_generation / is_generation_valid
```

| Impl | Providers |
|------|-----------|
| `TelnyxQueuePlayback` | Telnyx — queue depth + in-flight send |
| `EstimatedPlaybackTracker` | Exotel/Plivo — frames sent − time decay + ~150 ms hold |

---

## 7. Findings catalog (updated)

| ID | Topic | Status |
|----|-------|--------|
| F1 | Barge flag comment | **RESOLVED** |
| F2 | STT always fed | **RESOLVED** as policy (dual-rail echo) |
| F3 | Exotel/Plivo `is_active` | **RESOLVED** (estimate; still not ACK-based) |
| F4 | Flush after interrupt | **RESOLVED** |
| F5 | Swallow `CancelledError` | **RESOLVED** — cleanup then re-raise |
| F6 | Realtime cancel on critical path | **RESOLVED** |
| F7 | Busy through memory | **RESOLVED** |
| F8 | Exotel mark every send | **RESOLVED** — mark once on TTS end |
| F9 | Media-flow / `tts_first_audio_ms` | **OPEN** |
| F10 | Archive task storm | **RESOLVED** |
| F11 | Double `prepare_spoken_reply` | **LOW / open** (idempotent) |
| F12 | Invalid gens prune | **RESOLVED** |
| F13 | Echo guard | **IMPROVED** — dual + listening threshold; tune from data |
| F14 | Finals while provider playing | **MITIGATED** — hold when `_agent_audio_playing()` |
| F15 | Rapid finals merge | **IMPROVED** — barge-final prefer latest ≥2 words |
| F16 | Competing SMs | **ACCEPTABLE** if single `_run_turn` entry |
| F17 | `note_spoken` soft fail | **RESOLVED** |

---

## 8. Race conditions

| Race | Status |
|------|--------|
| R1 clear then flush | **MITIGATED** |
| R2 cancelled turn still emitting | **MITIGATED** (gen + emission_blocked; Telnyx strongest) |
| R3 busy false while provider playing | **PARTIALLY** (estimate + hold + final gate) |
| R4 pending vs hangup | OK if pending cleared |
| R5 archive after close | **MITIGATED** (`PstnArchiveWriter.close`) |
| R6 intro fail still ends intro | **ACCEPTABLE** (enable barge; log greeting.failed) |

---

## 9. Barge state machine (precise)

```
PARTIAL:
  IF intro → reject
  IF not _agent_audio_playing → reject
  IF debounce / min_after_speak / words<3 / hold / barge_echo(0.55) → reject
  ELSE COMMIT (see §2.4)

THINKING partial (≥3 words, hold 0.2s):
  → THINK_CANCEL (cancel LLM; wait for final)

FINAL:
  IF intro → queue
  IF barge_final window → prefer ≥2 words; drop only if overlap ≥0.85
  ELIF busy / thinking / speaking / interrupting / provider_playing → pending
  ELSE launch (skip if within barge-final debounce)
```

Logs: `BARGE_CHECK` (reason/result/`provider_queued_ms`), `BARGE_TRIGGER`, `BARGE_AUDIO_STOP_MS`, `PROVIDER_CLEAR`, `DROP_STALE_GEN`.

---

## 10–12. Endpointing / TTS / Realtime

- Silence default **400 ms**; barge vs endpointing remain separate (correct).
- TTS: early open, first flush ~18 chars, live cap 150; **no flush on interrupt**.
- Realtime: prewarm adopt, cancel async, empty cancelled archive skip, `note_spoken` hardened.

---

## 13. Latency bottlenecks (measure, don’t guess)

1. Prewarm adopt (≤~3s) / cold Realtime  
2. STT silence (~400 ms)  
3. Memory blocks before stream (read path)  
4. First sentence buffer → TTS open  
5. Telnyx queue pace / full spin  
6. Barge → queue empty (`BARGE_AUDIO_STOP_MS`)  

**Do not retune silence/barge thresholds until histograms exist (P3).**

---

## 14–15. Observability & measurement

Desired events (many already logged via `log_pstn`):  
`INTRO_*`, `TURN_*`, `BARGE_*`, `TTS_*`, `PROVIDER_CLEAR`, `QUEUE_DRAIN`, `DROP_STALE_GEN`, `THINK_CANCEL`, `CLEANUP`.

**Still thin:** Exotel/Plivo `pstn_media_flow` rows; orchestrator `tts_first_audio_ms` often `None`.

Measure p50/p95 of: stop→final, final→LLM token, token→TTS audio, audio→provider send, barge→queue empty.

---

## 16. Target guarantees (acceptance)

1. Single turn owner: `_run_turn` only.  
2. PlaybackController per provider with `is_active` + `clear`.  
3. Interrupt: gen death → clear → no flush → async Realtime cancel → one next turn.  
4. History matches heard (`note_barge` + heard sentences).  
5. Echo does not invent turns; barge still works.  
6. Hangup drains archive and stops emitters.

---

## 17. Fix priority (remaining)

| Priority | Item | Notes |
|----------|------|-------|
| **P2** | Media-flow + `tts_first_audio_ms` for all providers | Observability |
| **P2** | Optional ACK-based drain for Exotel marks | Improves R3 |
| **P3** | Threshold tune from p50/p95 | One knob at a time |
| **Done** | P0 flush / playback / echo / gen / fast barge / FSM / barge-final / archive / memory split / think-cancel / mark-once / CancelledError / Cartesia→μ-law on 8k | See `VOICE_AGENT_PRESETS.md` |

---

## 18. Change checklist (status)

| PR | Intent | Status |
|----|--------|--------|
| PR-A | No flush + interrupt flag | **Done** |
| PR-B | Playback `is_active` Exotel/Plivo | **Done** (estimate) |
| PR-C | Echo feed policy + dual rails | **Done** |
| PR-D | Barge condition logs + stages | **Mostly done**; media-flow gap |
| PR-E | Docs / barge flag | **Done** (this file + presets) |

---

## Appendix A — Key constants (code)

| Name | Value |
|------|-------|
| `ENABLE_PSTN_BARGE_IN` | `True` |
| `PSTN_BARGE_MIN_WORDS` | `3` |
| `PSTN_BARGE_HOLD_S` | `0.2` |
| `PSTN_BARGE_MIN_AFTER_SPEAK_S` | `0.7` |
| `PSTN_BARGE_DEBOUNCE_S` | `0.8` |
| `PSTN_BARGE_FINAL_WINDOW_S` | `1.5` |
| `PSTN_BARGE_FINAL_DEBOUNCE_S` | `0.3` |
| `PSTN_THINK_CANCEL_MIN_WORDS` | `3` |
| `PSTN_THINK_CANCEL_HOLD_S` | `0.2` |
| `PSTN_ECHO_TAIL_S` | `0.35` |
| `BARGE_ECHO_OVERLAP` | `0.55` |
| `FINAL_ECHO_OVERLAP` (tail) | `0.65` |
| `LISTENING_FINAL_ECHO_OVERLAP` | `0.80` |
| `BARGE_FINAL_ECHO_OVERLAP` | `0.85` |
| Default STT silence | `400` ms |
| Intro queue max | `4` |
| Pending merge cap | `500` chars |
| Prewarm TTL / adopt | `90` s / `~3` s |
| Live reply max | `150` chars |
| Telnyx max queue frames | `20` (~400 ms) |
| Estimate post-send hold | `~150` ms |

---

## Appendix B — Method notes

- Prefer **code behavior** over older prose when they conflict.  
- Original audit did not modify production code; this revision documents post-playbook reality and remaining gaps.  
- Companion: `VOICE_AGENT_PRESETS.md` (invariants + change order).

---

*End of audit.*
