# Voice Agent: Barge-in, Presets, and Safe Tuning

This document explains **why** changing TTS pace/temperature broke barge-in in your logs, **what** the root causes were, and **how** to run the agent safely without breaking token caching or the live voice pipeline.

---

## 1. What your logs showed (`fix.md`)

### Critical: `live-guards.js` returned 404

```
GET /live-guards.js HTTP/1.1" 404 Not Found
```

**Impact:** The barge-in guard module never loaded. Rules that prevent:
- false interrupts from TTS echo
- queued speech after a real interrupt
- think-cancel storms during playback

…were **not running** in the browser.

**Fix applied:** `server/app.py` serves all `client/*.{js,css,html}` at root via a catch-all route (no more per-file 404s). After deploy, hard-refresh (`Ctrl+Shift+R`) and confirm the network tab shows **200** for `live-guards.js`.

**Client fallback:** `app.js` includes a minimal inline guard if the file still fails to load.

---

### Secondary: free-form sliders changed coupled settings

You changed **TTS pace** and **temperature** independently. Those values do not affect barge-in directly, but they change:

| Setting | Side effect on live voice |
|--------|---------------------------|
| Faster pace (e.g. 1.1×) | Longer playback window → more time for STT to hear echo |
| Higher temperature (e.g. 0.8+) | More varied prosody → harder echo cancellation |
| Custom VAD silence | Endpointing too short → partials fire before you finish speaking |
| Custom barge thresholds | Too sensitive → agent stops; too weak → queue stuck |

Industry practice (Sarvam STT docs, voice-agent guides): **STT VAD, barge-in, and TTS pacing are tuned as one bundle**, not independent sliders.

---

### Symptom: input shows as "queued"

Correct live flow after interrupt:

```
USER SPEAKS (barge-in)
  → stop audio + cancel brain/TTS
  → busy = false
  → STT final
  → runTurn() immediately
```

Broken flow (what you saw):

```
USER SPEAKS while busy
  → transcript.final → enqueueFinal()
  → old turn still holds busy
  → UI shows "queued"
  → agent stops, never responds
```

This was fixed in `client/app.js` (`handleSttFinal`, `doBargeIn`, `turnGeneration`). Partial/think-cancel guards need `live-guards.js` (or the inline fallback in `app.js`). **VAD-start barge-in works even without the external file.**

---

## 2. Root causes (summary)

| # | Issue | Severity |
|---|--------|----------|
| 1 | `live-guards.js` not served → no barge-in guards | **Critical** |
| 2 | User tuned pace/temp/VAD separately → unstable interrupt timing | **High** |
| 3 | `busy` flag + queue used for interrupts instead of immediate `runTurn` | **High** (fixed in code) |
| 4 | Stale TTS chunks after interrupt | **Medium** (fixed via `_ttsOwnerGen`) |

**TTS pace/temperature did not break the brain or token cache.** Brain logs still show `CACHE_HIT` and `cache_key: telugu-voice:v5:cfg-...`. Prompt caching is unchanged.

---

## 3. New design: curated voice profiles (not free sliders)

Instead of exposing pace, temperature, VAD silence, and barge sliders, the **Voice Pipeline** tab now uses **four tested profiles**. Each profile sets all coupled values together.

### Default profile: **Natural** (recommended)

| Parameter | Value |
|-----------|-------|
| TTS pace | **1.0×** |
| TTS temperature | **0.80** |
| VAD silence | 500 ms |
| VAD threshold | 0.30 |
| Barge-in min words | 3 |
| Require VAD before barge | Yes |
| STT stream | fast |

### All four profiles

| Profile | Pace | Temp | VAD silence | Use case |
|---------|------|------|-------------|----------|
| **natural** (default) | 1.0 | 0.80 | 500 ms | Everyday Telugu voice — balanced |
| **fast** | 1.1 | 0.60 | 400 ms | Short back-and-forth |
| **calm** | 0.95 | 0.50 | 600 ms | Explanations, slower delivery |
| **expressive** | 1.0 | 0.90 | 500 ms | More vocal variety, still safe barge-in |

**Speaker** (shubh, ritu, etc.) remains user-selectable — it does not affect barge-in logic.

**Source of truth:** `server/prompts/voice_defaults.py` → `VOICE_PIPELINE_PRESETS`

---

## 4. What users should change (and what not to)

### Safe to change

- **Voice profile** (Natural / Fast / Calm / Expressive)
- **TTS speaker**
- **Brain model** (use "Apply recommended settings" on AI Brain tab)
- **Brain prompt** (Prompting tab — affects cache key only when content changes)

### Do not change manually (locked in profile)

- TTS pace, temperature
- STT VAD silence, threshold
- Barge-in min words, VAD requirement
- TTS min buffer / max chunk

**Enforced server-side:** POST `/api/settings/runtime` rejects individual pipeline keys unless `voicePresetId` is included. The UI only sends `voicePresetId` — the server expands the full bundle.

### AI Brain (model presets)

- Pick a model → recommended max tokens, prompt budget, and reasoning effort apply automatically
- Sliders for max tokens / prompt budget are removed — values come from `OPENAI_MODEL_PRESETS`

### Does not affect barge-in

- Brain prompt text (after save)
- OpenAI model / reasoning effort
- Token budget (1500–2500)
- CRM settings

---

## 5. Operational checklist

After any settings change:

1. Click **Save all settings**
2. **Hard refresh** the page (`Ctrl+Shift+R`)
3. Confirm `live-guards.js` → **200** in browser DevTools → Network
4. Start a **new** live session (mic button)
5. Test interrupt: speak over the agent → should see `⚡ interrupted — speak now…`, **not** `queued`

After changing voice profile:

- Settings auto-reconnect STT + TTS if a live session is running (no mic restart needed)

---

## 6. Token caching — unchanged

These changes **do not** modify:

- `cache_key` / `telugu-voice:v5:cfg-...`
- Brain prompt budget (1500–2500 tokens)
- `ENABLE_PROMPT_CACHING` in `.env`
- Composed prompt structure

Saving a voice profile only updates runtime TTS/STT fields. Brain cache remains tied to the **saved brain prompt** and config hash.

---

## 7. Environment defaults (`.env`)

```env
SARVAM_TTS_PACE=1.0
SARVAM_TTS_TEMPERATURE=0.80
```

Session overrides come from the selected **voice profile** after Save.

---

## 8. For developers

| File | Role |
|------|------|
| `client/live-guards.js` | Barge-in policy (must be served at `/live-guards.js`) |
| `client/app.js` | Live state machine, `handleSttFinal`, `doBargeIn` |
| `server/prompts/voice_defaults.py` | Profile definitions |
| `server/services/runtime_settings.py` | Expands `voicePresetId` → full patch |
| `server/app.py` | Catch-all static route for `client/*.{js,css,html}` |

**Tests:** `server/tests/test_live_barge_policy.py`, `server/tests/test_finetune_console.py`

**Note:** This project uses **vanilla JavaScript** (client) and **Python** (server). There is no TypeScript layer — type safety is enforced via Pydantic (`RuntimePatch`) and unit tests.

---

## 11. Architecture audit (reaudit)

**Verdict: Good architecture for a cascaded STT → Brain SSE → TTS WS pipeline.** Preset bundling is the right industry pattern. A few gaps remain — none block production if you follow the operational checklist.

### What is correct

| Area | Status | Notes |
|------|--------|-------|
| Barge-in cancel path | ✅ | `doBargeIn` stops playback → aborts brain → closes TTS WS → clears queue → `busy=false` |
| Stale turn invalidation | ✅ | `turnGeneration` + `_ttsOwnerGen` drop late SSE/TTS chunks |
| Post-barge STT final | ✅ | `handleSttFinal` calls `runTurn()` immediately when `bargeActive` or `awaitingUserAfterBarge` |
| Preset single source | ✅ | `voice_defaults.py` → catalog API → `runtime_settings` expansion |
| Server enforcement | ✅ | Bundled keys rejected unless `voicePresetId` is in the patch |
| Token cache isolation | ✅ | Voice presets do not touch brain prompt / `cache_key` |
| Thread safety (server) | ✅ | `RuntimeSettingsStore` uses `RLock` + rollback snapshot on validation failure |
| Industry alignment | ✅ | Client-first flush, VAD+min-words gate, cooldown, bundled tuning ([FutureAGI](https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/), [SyncSoft](https://www.syncsoft.ai/en/blog/voice-agent-barge-in-vad-tuning-2026)) |

### Issues found (by severity)

| # | Issue | Severity | Status |
|---|--------|----------|--------|
| 1 | `live-guards.js` 404 broke partial/think-cancel guards | Critical | **Fixed** — catch-all static route + inline fallback |
| 2 | Free sliders destabilized coupled pipeline | High | **Fixed** — 4 voice profiles + server rejection of loose keys |
| 3 | `busy` + queue on interrupt | High | **Fixed** — `handleSttFinal` / `doBargeIn` |
| 4 | Duplicate DOM ids (`ttsMinBuffer` / `ttsMaxChunk`) | High | **Fixed** — Advanced sliders removed |
| 5 | Pydantic `model_dump()` sent `null` for all fields → bypassed bundled-key guard | High | **Fixed** — filter `v is not None` in `post_runtime` |
| 6 | Partial validation left corrupt runtime state | Medium | **Fixed** — snapshot rollback in `runtime_settings.update` |
| 7 | STT WebSocket params frozen at session start | Medium | **Fixed** — hot reconnect on save while live |
| 8 | Triple guard maintenance (`live-guards.js`, `app.js` fallback, Python tests) | Medium | **Open** — keep in sync manually; tests mirror JS |
| 9 | `openaiTemperature` slider exposed | Low | **Fixed** — hidden; model presets only |
| 10 | No TypeScript | N/A | Vanilla JS — not a bug; Pydantic covers API |

### Race conditions reviewed

| Scenario | Risk | Mitigation in code |
|----------|------|-------------------|
| Barge during `runTurn` | Stale brain/TTS continues | `turnGeneration++` in `doBargeIn`; `isTurnStale(gen)` in SSE/TTS handlers |
| Two `transcript.final` while busy | Double turn | `runTurn` checks `busy && !bargeActive` → queue; barge path clears queue first |
| Settings save during live session | Stale VAD on STT WS | **Fixed** — `reconnectLivePipeline()` on `runtime-settings-saved` |
| `drainPendingFinal` loop | Infinite loop | `queueMicrotask` drains one item; only grows via explicit `enqueueFinal` |
| Concurrent runtime POSTs | Corrupt settings | Server `RLock` serializes updates per process |
| TTS chunk after interrupt | Ghost audio | `_ttsOwnerGen !== turnGeneration` → ignore stale events |

**No infinite loops found** in the live state machine.

### Import / module issues reviewed

| Check | Result |
|-------|--------|
| `runtime_settings.py` missing `constants` import | **Fixed** (was causing 500 on save) |
| Circular imports (`voice_defaults` ↔ `runtime_settings`) | ✅ None — one-way import |
| `ensureLiveGuards` before definition | ✅ Function hoisted; also called at end of `app.js` |
| Client script load order | ✅ `live-guards.js` before `app.js` in `index.html` |

### Architectural boundaries (do not mix)

```
┌─────────────────────────────────────────────────────────┐
│  Voice Pipeline presets (voicePresetId)                 │
│  → STT VAD, barge thresholds, TTS pace/temp/buffer      │
│  → Affects: live mic, TTS WS, barge-in guards           │
│  → Does NOT affect: brain cache_key, prompt composition │
├─────────────────────────────────────────────────────────┤
│  AI Brain presets (openaiModel + OPENAI_MODEL_PRESETS)  │
│  → reasoning effort, max tokens, prompt budget          │
│  → Affects: brain latency, cache eligibility            │
│  → Does NOT affect: barge-in timing                     │
├─────────────────────────────────────────────────────────┤
│  Brain prompt (Prompting tab)                           │
│  → cache_key changes only when saved content changes    │
└─────────────────────────────────────────────────────────┘
```

### Gaps vs industry best practice (addressed)

1. **Hot STT reconnect** — saving settings during a live session now reconnects `/ws/stt-realtime` and TTS WS without stopping the mic.
2. **Barge cooldown 250 ms** — matches industry post-flush guidance ([SyncSoft](https://www.syncsoft.ai/en/blog/voice-agent-barge-in-vad-tuning-2026)).
3. **Brain temperature** — removed from UI; GPT-5 family uses reasoning effort from model presets only.

### Remaining future improvements (not blockers)

1. **Dual-pass VAD** — Sarvam VAD + client min-words + RMS echo gate (no local WebRTC GMM pass).
2. **History truncation** — cancel generation but do not truncate assistant text to played-audio-ms (acceptable for short Telugu replies).

### Is this architecture good?

**Yes, for your stack** (Sarvam STT/TTS + OpenAI Responses + browser client):

- Presets prevent the exact failure mode from `fix.md` (user tuning pace/temp in isolation).
- Barge-in follows the client-first cancel pattern recommended for cascaded pipelines.
- Token caching stays on the brain path, untouched by voice tuning.
- Server-side validation is fail-closed (reject loose keys, rollback on partial failure).

**Not recommended:** re-exposing individual pace/VAD/barge sliders in the UI or bypassing `voicePresetId` in API clients.

---

## 9. References

- Sarvam STT: use `high_vad_sensitivity` and tune VAD as a unit ([best practices](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/best-practices))
- Voice agents: barge-in requires cancel brain + TTS + playback together; never queue the interrupt behind the old turn
- OpenAI voice: GPT-5 family uses **reasoning effort**, not temperature — use AI Brain presets, not TTS sliders

---

## 10. Quick recovery if voice breaks again

1. Voice Pipeline → select **Natural** → Save
2. Hard refresh
3. Check `live-guards.js` is not 404
4. Advanced → Reset defaults if needed
5. Do **not** tune pace/temperature sliders (removed from UI by design)

If problems persist, capture logs showing:
- `[VOICE][BARGE-IN]` in browser console
- `POST /api/session/interrupt`
- Whether UI says `queued` vs `speak now`
