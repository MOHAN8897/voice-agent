# Memory, Call Summary, Disposition & Archive Plan

**Telugu Voice Agent** — how to remember the whole call, stay cheap on tokens, stay fast, and save audio + transcript for later.

**Date:** 25 Aug 2026  
**Status:** design only (not implemented yet)  
**Stack today:** Sarvam STT/TTS streaming + OpenAI Responses API (`gpt-5.6-luna`) + `store: false` + explicit prompt cache

This document is the recommended industry pattern mapped onto *this* codebase. It is written so you can implement in phases without breaking the token-saving work already shipped.

---

## 1. What you asked for

| Need | Meaning |
|------|---------|
| Memory until the call ends | Agent still knows the caller’s name, city, intent, and earlier facts on turn 20, not only the last two replies |
| Summary of the entire call | After hang-up, a readable recap (Telugu + optional English) |
| Status assigned by the AI | Structured outcome: interested / not interested / can convert / callback / etc. |
| Token-saving architecture | Do **not** dump the full transcript into the live brain every turn |
| Save streaming for the future | Persist **user audio**, **agent audio**, and **aligned transcript** as files + JSON, not browser `localStorage` |

These are three different jobs. Mixing them into the live spoken reply is the usual way teams ruin latency and cost. Industry practice (Pipecat, LiveKit, Vapi/Retell end-of-call reports, AWS Live Call Analytics) splits them.

---

## 2. Industry standard (2026) in one picture

```
 DURING THE CALL (hot path — must stay streaming and small)
 ┌─────────────────────────────────────────────────────────────┐
 │  STT final  →  tiny working memory  →  Luna stream  →  TTS  │
 │                 last 2 turns                                │
 │                 + entity slots (~80 tokens)                 │
 │                 + rolling summary (~100 tokens)             │
 │                 brain prompt stays CACHED and UNCHANGED     │
 └─────────────────────────────────────────────────────────────┘
        │ append-only (never blocks speech)
        ▼
 CALL LEDGER (cold — never sent to the live brain)
 ┌─────────────────────────────────────────────────────────────┐
 │  Full untruncated turns JSONL                               │
 │  User PCM stream  +  Agent TTS stream  →  stereo WAV        │
 └─────────────────────────────────────────────────────────────┘

 AFTER HANG-UP (async — user already gone)
 ┌─────────────────────────────────────────────────────────────┐
 │  One structured Luna call on the FULL transcript            │
 │  → summary + disposition + next_action + extracted fields   │
 └─────────────────────────────────────────────────────────────┘
```

That split is the standard because:

1. **Pipecat** auto-summarises older messages in the background and keeps recent turns raw. Summarisation must **not** sit on the spoken LLM path (`docs.pipecat.ai` context summarization). Default trigger is large (~8k tokens or ~20 messages). For a short voice call you trigger earlier, but still **off the hot path**.
2. **Vapi / Retell** inject long-term memory **once at call start**, then write the transcript **once at call end**. They do not retrieve vectors on every turn (that adds 100–400 ms).
3. **AWS Live Call Analytics** writes stereo audio (caller one channel, agent the other) and runs transcript summarisation **when the call ends**.
4. **Contact-centre / Future AGI logging (2026)** stores two audio files (or stereo), turn-level transcript with timestamps, and metadata in a DB. Audio lives in object storage; the DB only stores paths.
5. **OpenAI prompt cache (2026)** only hits if the **prefix is byte-stable**. Anything that changes every turn (summary, slots, history) must sit **after** the cache breakpoint. Cached input is 0.1×; a cache miss on a 1,100-token brain prompt is expensive and slower (TTFT).

You already follow the cache rule. Memory work must not undo it.

---

## 3. What this project already has (audit)

### 3.1 Token-saving — already good, keep it

| Mechanism | Where | Verdict |
|-----------|--------|---------|
| One composed brain prompt, no duplicate `instructions` | `brain_prompt_composer.py`, `openai_brain_service.py` | Keep |
| Explicit `prompt_cache_breakpoint` + `prompt_cache_key` + 30m TTL | `instruction_builder.py`, `prompt_cache_key.py` | Keep |
| `store: false` | `openai_brain_service.py` | Keep — do **not** switch live turns to `previous_response_id` or Conversations API |
| Live brain sees only last **2** turns | `BRAIN_CONTEXT_TURNS=2`, `get_context_for_brain()` | Keep for the hot path |
| History char caps (user 300, assistant 120) | `conversation_manager.py` | Keep **only** for what is sent to the live brain |
| `reasoning.effort: none` for voice | `openai_model_params.py` | Keep |
| Streaming brain SSE → sentence buffer → TTS WS | `app.js`, `routes/ws.py` | Keep |

Measured (your cost probe, 24 Aug 2026): ~90% cache hit after turn 1, brain **₹0.09 / talking minute**. Do not inflate live input.

### 3.2 Memory — exists, but is not real call memory

| Piece | What it actually does | Gap |
|-------|----------------------|-----|
| `ENABLE_SESSION_SUMMARY` | **Default `false` in `.env`** | Feature is off. Live agent only knows last 2 turns. |
| `session_memory.py` | In-RAM string, **400 char cap**, 30 min TTL, lost on restart | Not durable, not a call record |
| `compact_history_summary()` | Joins last **6 user lines** from the **already truncated** store. **No LLM.** | Not a summary. Drops agent facts. Drops anything older than the trim window. |
| `conversation_manager` | In-RAM, max **8 messages**, truncates every turn, TTL 30 min | Cannot be the source of truth for “the whole call” |
| `GET /api/session/history` | Returns that truncated RAM store | Fine for debug, not for archive |
| No `POST /api/call/end` | Interrupt exists; **call end does not** | Nowhere to hang summary + status + flush audio |

So today: **the model is token-cheap because it is forgetful.** Turning on the current summariser without a full ledger will still forget early turns.

### 3.3 Transcript / audio save — client-only, not production

| Piece | What it actually does | Gap |
|-------|----------------------|-----|
| `client/conversation_store.js` | `localStorage` JSON of turns | Lost if user clears site data; not shared with CRM; not your server |
| `appendTurn` in `app.js` | Saves **last TTS clip as base64** with the turn | User speech is **not** saved. Base64 in `localStorage` will blow the 5 MB quota on a real call. Streaming chunks are not appended. |
| Export TXT / JSON / WAV buttons | Manual download from the browser | Not an archive. Not aligned to a `call_id`. |

Industry rule: **browser is a preview; server is the system of record.**

---

## 4. Target architecture (map onto this repo)

Keep three stores. Never use one store for all three jobs.

```
┌─ 1. WORKING MEMORY (hot, tiny, sent to Luna each turn) ──────────────┐
│  slots.json          name, city, intent, when, budget, objection     │
│  rolling_summary     80–120 tokens, facts only, Telugu or bilingual  │
│  last 2 turns        already truncated (today’s get_context_for_brain)│
│  NEVER the full transcript                                           │
└──────────────────────────────────────────────────────────────────────┘

┌─ 2. CALL LEDGER (complete, NOT sent to live Luna) ───────────────────┐
│  data/calls/{call_id}/transcript.jsonl   one line per utterance      │
│  data/calls/{call_id}/user.pcm           16 kHz mono as STT frames   │
│  data/calls/{call_id}/agent.mp3|pcm      TTS stream as it plays      │
│  After hang-up: mix.wav (L=user, R=agent) + transcript.json          │
└──────────────────────────────────────────────────────────────────────┘

┌─ 3. CALL OUTCOME (written once, after hang-up) ──────────────────────┐
│  summary_te / summary_en                                             │
│  disposition enum + confidence                                       │
│  next_action, extracted fields, objections                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.1 Live OpenAI request shape (token-saving + cache-safe)

Do **not** put slots or summary inside the cached developer prompt. That would bust the cache every time memory updates.

Keep exactly this order (you already have the first and last parts):

```
input[0]  developer  brain prompt          ← prompt_cache_breakpoint  (STABLE)
input[1]  user       [Working memory]      ← slots + rolling summary   (~80–150 tokens)
input[2..]           last 2 turns          ← truncated, as today
input[N]  user       current transcript
```

`prompt_cache_key` stays `sha256(brain_prompt + budget)` — **not** `sessionId`, **not** the summary.

Rough live input after turn 10:

| Layer | Tokens | Cached? |
|-------|--------|---------|
| Brain prompt | ~1,100 | Yes (0.1×) |
| Working memory | ~80–150 | No |
| Last 2 turns | ~80–150 | No |
| Current transcript | ~10–40 | No |
| **Billed uncached** | **~170–340** | — |

That is still far cheaper than sending a 3,000-token growing transcript every turn, and the agent still “remembers” the call via slots + summary.

### 4.2 Entity slots — highest value, lowest tokens

A 10-minute call does not need RAG. It needs a **form the model fills**.

```json
{
  "caller_name": "సాయి",
  "city": "హైదరాబాద్",
  "intent": "appointment",
  "product": null,
  "when": "tomorrow evening",
  "budget": null,
  "objections": [],
  "commitment": null,
  "language": "te-IN"
}
```

Rules:

- Merge, never replace blindly (do not wipe `caller_name` because this turn did not repeat it).
- Update **after** the spoken reply has started (async). Never block TTS.
- Send slots to the live brain as 5–12 short lines, not the whole ledger.

This is why the agent can say “సాయి, హైదరాబాద్ నుంచి…” on turn 15 even though those words fell out of the 2-turn window.

### 4.3 Rolling in-call summary — not the end-of-call summary

Two summaries, two jobs:

| | In-call rolling | End-of-call |
|--|-----------------|-------------|
| When | Every 4–6 turns, **async** | Once, on hang-up |
| Input | Previous rolling + last 4 **full** ledger turns | **Entire** JSONL transcript |
| Size | 80–120 tokens | 150–400 tokens, readable for humans |
| Consumer | Live brain (working memory block) | CRM, dashboard, you |
| Model | Luna, short, `store: false` | Luna or Terra; **structured JSON** |
| On failure | Keep previous rolling summary | Mark `outcome_status=failed`, retry |

Replace `compact_history_summary()` (string join). It is not a summary.

Pipecat’s rule applies here: use a **dedicated** summariser call that **bypasses** the live stream so the user never waits for it.

### 4.4 What not to do (latency / cost traps)

| Trap | Why it hurts this agent |
|------|-------------------------|
| Send full transcript every turn | Destroys the ₹0.09/min brain cost; TTFT climbs |
| Put summary inside the cached brain prompt | Cache miss every 4 turns; first-token latency jumps (you already saw ~2–4 s on cache write) |
| `previous_response_id` chaining for live voice | OpenAI then owns a growing thread; you lose trim + cache control. Keep `store: false`. |
| Structured JSON as the **spoken** reply | JSON is not speakable; TTS will read braces. Disposition is a **second** call after hang-up. |
| Tool call every turn to “save memory” | Extra round-trip before speech. Write memory in your process after `add_turn`. |
| Vector search mid-turn | Fine **between** calls at start; too slow **during** a turn. |
| Mid-call LLM summary on the hot path | Same as Pipecat anti-pattern: user waits while you compress history. |
| `localStorage` + base64 audio | Quota, no CRM, no stereo, no user channel. |

---

## 5. Call lifecycle (new, required)

Today a “session” is a UUID that never officially ends. Add a **call**.

```
POST /api/call/start     { sessionId, channel: "browser"|"pstn", callerId? }
  → { callId, startedAt }

  … existing STT / brain / TTS loop, each turn tagged with callId …

POST /api/call/end       { callId, reason: "user_stop"|"timeout"|"error"|"transfer" }
  → 202 Accepted immediately
  → background: mux audio, write transcript.json, run outcome LLM, save disposition
GET  /api/call/{callId}  metadata + summary + status + file URLs
```

Client: on Live start → `call/start`. On mic stop / tab close / `beforeunload` / PSTN hangup → `call/end` (beacon).

Server: if `call/end` never arrives, TTL (e.g. 5 min idle) auto-finalises so audio is not left as open PCM files.

Keep `sessionId` for Fine-tune console settings. **`callId` is the archive key.** One session can have many calls.

---

## 6. Saving the stream “in a neat way”

### 6.1 Folder layout (one call = one folder)

```
data/calls/{call_id}/
  meta.json              ids, times, models, language, disposition (filled at end)
  transcript.jsonl       append-only while the call is live
  transcript.json        pretty, closed file after hang-up
  audio/
    user.pcm             16 kHz s16le mono (same frames you already send to Sarvam)
    agent.pcm            24 kHz s16le or muxed mp3 chunks from TTS WS
    mix.wav              stereo after hang-up: L = user resampled, R = agent
    user.wav             optional convenience convert
    agent.wav
  outcome.json           summary + status (after hang-up)
```

Later, swap `data/calls/` for S3 / R2 / GCS. Same keys. DB stores only URLs.

### 6.2 `transcript.jsonl` line format (append on every utterance)

Write **untruncated** text. This file is never sent to the live brain.

```json
{"t":"2026-08-25T06:41:28.112Z","seq":1,"speaker":"user","text":"నా పేరు సాయి.","t_start_ms":1840,"t_end_ms":3120,"interrupted":false,"stt_model":"saaras:v3"}
{"t":"2026-08-25T06:41:31.440Z","seq":2,"speaker":"agent","text":"హాయ్ సాయి…","t_start_ms":3320,"t_end_ms":5100,"interrupted":false,"tts_speaker":"ritu","chars":62}
```

On barge-in: flush a partial agent line with `"interrupted": true` and the text actually spoken (what TTS already sent), not the full brain string. Pipecat’s reason: the ledger must match what the human heard.

### 6.3 How to capture audio without extra latency

You already have both streams in the proxy. Do **not** add a second recording pipeline on the client.

| Stream | Hook | Write |
|--------|------|-------|
| User | `routes/ws.py` STT WS — each PCM frame you already forward to Sarvam | `audio/user.pcm` append |
| Agent | TTS WS — each audio chunk you already forward to the browser | `audio/agent.pcm` or `.mp3` append |

Rules:

- Disk append is fire-and-forget (thread/async queue). Never await `write()` on the audio callback.
- Do not buffer the whole call in RAM.
- Do not put audio on the brain request.
- After `call/end`, mix to stereo WAV (industry default: **caller left, agent right**) so you can re-transcribe channels separately later.
- Keep raw PCM until mix succeeds, then you may delete PCM to save space (keep `mix.wav` + jsonl).

Do **not** keep using `conversation_store.js` base64 for production. Optionally keep a **text-only** client preview that reads `GET /api/call/{id}/transcript`.

### 6.4 Closed `transcript.json` (human / CRM)

```json
{
  "call_id": "c_8f3a…",
  "session_id": "453e3908-…",
  "started_at": "…",
  "ended_at": "…",
  "duration_ms": 184000,
  "language": "te-IN",
  "models": { "stt": "saaras:v3", "brain": "gpt-5.6-luna", "tts": "bulbul:v3" },
  "turns": [ { "seq": 1, "speaker": "user", "text": "…", "t_start_ms": 1840 } ],
  "audio": {
    "mix": "audio/mix.wav",
    "user": "audio/user.wav",
    "agent": "audio/agent.wav"
  },
  "outcome": { "$ref": "outcome.json" }
}
```

---

## 7. End-of-call summary + status (AI assigned)

Run **after** `call/end`, on the **full ledger**, with **Structured Outputs** (`text.format` json_schema, strict). This must not be the spoken model output.

Suggested schema (Telugu sales / inbound; change labels to match your business):

```json
{
  "summary_te": "string",
  "summary_en": "string",
  "disposition": "interested | highly_interested | can_convert | not_interested | callback | wrong_number | completed | no_outcome",
  "disposition_confidence": 0.0,
  "intent": "string",
  "next_action": "string",
  "callback_time": "string|null",
  "objections": ["string"],
  "extracted": {
    "name": "string|null",
    "city": "string|null",
    "phone": "string|null",
    "product": "string|null"
  },
  "sentiment": "positive | neutral | negative",
  "talk_ratio_user_pct": 0
}
```

Prompt rules for that job:

- Use only the transcript. If unknown, `null` / `no_outcome`. Do not invent a phone number.
- Prefer **not_interested** over **can_convert** when the user only said “చూస్తాను” with no time.
- `can_convert` = clear next step (appointment, payment, callback time).
- Keep `summary_te` 4–8 spoken-style sentences for a human supervisor.

Cost: one extra Luna call per call, ~2–4k input tokens of transcript. At your rates that is **well under ₹0.50 per call**, not per minute. Do not run this every turn.

Optional later: a cheaper mid-call **soft status** in slots (`leaning: interested`) for the agent’s wording only. The official status is still the hang-up job.

---

## 8. Working memory vs archive — code split

| Concern | Live (keep small) | Archive (keep complete) |
|---------|-------------------|-------------------------|
| Module | `session_memory.py` evolved → `working_memory.py` | new `call_ledger.py` + `call_audio.py` |
| Turns | last 2, truncated | all turns, full text |
| Summary | rolling, 120 tokens | final outcome, 400 tokens |
| Audio | none | PCM + mix.wav |
| TTL | end of call (then drop RAM) | weeks/months on disk |
| Sent to Luna during call | yes, tiny | **never** |

`conversation_manager` stays as the **live window**. Stop treating it as the archive.

`_after_turn_memory()` today runs on the request path and uses truncated history. Change it to:

1. `ledger.append(user_full, agent_full)` (untruncated)
2. `slots.merge_from_turn(...)` (cheap / rules first)
3. If `turn % N == 0`: **enqueue** rolling-summary job (do not await)
4. Return immediately so TTS is unaffected

---

## 9. Implementation steps (do in this order)

### Phase A — Call object + full text ledger (no extra LLM)

**Goal:** never lose a word, still no extra latency.

1. Add `call_id` on Live start; pass it on STT/brain/TTS.
2. `CallLedger.append()` writes JSONL with full user + full assistant text (from brain `done`, not the 120-char store).
3. Keep `conversation_manager` as the live 2-turn window.
4. `POST /api/call/end` closes the JSONL and writes `transcript.json`.
5. Tests: 12 turns → ledger has 24 utterances; brain request still only last 2 turns + cached prompt.

**Done when:** you can download a full Telugu transcript after a live session without using `localStorage`.

### Phase B — Stream audio to disk

1. STT WS proxy: append user PCM to `audio/user.pcm`.
2. TTS WS proxy: append agent chunks to `audio/agent.*`.
3. On `call/end`: resample/mux to `mix.wav` (L=user, R=agent).
4. `meta.json` gets file sizes + duration.
5. Tests: 30 s call → mix.wav duration ≈ 30 s; barge-in still <150 ms locally (audio write is async).

**Done when:** you can replay the call with user on the left and agent on the right.

### Phase C — Slots + rolling summary (real in-call memory)

1. `WorkingMemory.slots` merge after each turn (start with rule-based: name/city patterns + last intent line).
2. Enable a **new** rolling summariser (LLM) every 4 turns, **async**, input = previous summary + last 4 **ledger** turns (full text).
3. Inject `[Working memory]` as `input[1]` **after** the cache breakpoint (`instruction_builder.py` already has a `session_summary` slot — reuse it, but send `slots + summary`, not the old string-join).
4. Confirm `[BRAIN] CACHE_HIT` still fires on turns 2+ after a summary refresh (critical regression).
5. Leave `ENABLE_SESSION_SUMMARY` as the feature flag, but **replace** `compact_history_summary`.

**Done when:** turn 1 says name+city, turn 12 still uses them, cache hit rate stays ~90%, TTFT on turn 2+ stays in your current band (~0.8–1.8 s).

### Phase D — Hang-up summary + disposition

1. Background worker on `call/end`: load `transcript.jsonl` → structured Luna call → `outcome.json`.
2. `GET /api/call/{id}` returns summary + disposition + audio URLs.
3. Fine-tune / ops UI: list calls, filter by `disposition`, play mix.wav, read transcript.
4. Tests: fixture transcripts for interested / not_interested / can_convert / callback; schema always valid.

**Done when:** ending a call produces a status without another spoken sentence.

### Phase E — Polish (only if needed)

- Move `data/calls/` to object storage.
- Consent banner + retention days (India DPDP / TRAI if PSTN).
- Cross-call memory: on `call/start`, inject last outcome for this `callerId` (Vapi pattern — **once**, not per turn).
- Soft mid-call `leaning` slot for wording only.

---

## 10. Token budget after this work (expected)

Same 1 talking minute, 6 turns, factory prompt cached:

| Item | Now | After memory (live) |
|------|-----|---------------------|
| Cached brain | ~1,085 tok × 0.1× | same |
| Uncached live extra | ~100–180 | ~180–320 (slots+summary) |
| Brain ₹ / min | ~₹0.09 | ~₹0.12–0.18 |
| Rolling summary LLM | ₹0 | ~₹0.05–0.10 per **call** (every 4 turns, tiny) |
| End-of-call outcome LLM | ₹0 | ~₹0.10–0.40 per **call** |
| STT / TTS | ₹0.50 + ₹1.12 | unchanged (audio save is disk, not API) |

Memory should add **paise per minute** on the live path, not rupees. If live brain cost jumps toward ₹1/min, the full transcript is leaking into the request — that is a bug.

---

## 11. Latency budget (do not break)

| Stage | Keep |
|-------|------|
| VAD / STT final | unchanged |
| Brain TTFT | cache must stay on; working memory after breakpoint |
| First audio | still sentence-stream into TTS WS |
| Barge-in | still client-stop + abort; ledger marks `interrupted` |
| Summary / mix / disposition | **after** speech, or parallel after hang-up |

Acceptance: Phase C+D must not add more than **~20 ms** p50 to time-to-first-audio (disk queue + tiny extra tokens). If you see +300 ms, something is awaiting the summariser.

---

## 12. Files to add or change (when you implement)

| File | Change |
|------|--------|
| `server/agent/call_ledger.py` | **New.** Full JSONL turns |
| `server/agent/call_audio.py` | **New.** PCM append + mix |
| `server/agent/working_memory.py` | **New.** Slots + rolling summary (replace thin `session_memory`) |
| `server/services/call_outcome.py` | **New.** Structured hang-up LLM |
| `server/routes/calls.py` | **New.** start / end / get |
| `server/agent/instruction_builder.py` | Working-memory user block after cache breakpoint |
| `server/services/openai_brain_service.py` | Stop using truncated history for “summary”; enqueue async job |
| `server/routes/ws.py` | Append user/agent audio; stamp `call_id` |
| `client/app.js` | `call/start` + `call/end`; stop relying on base64 `localStorage` for archive |
| `server/tests/test_call_ledger.py` | Ledger completeness vs brain window |
| `server/tests/test_cache_with_memory.py` | Cache hit after summary update |

Do not rewrite the streaming pipeline. Memory and archive **wrap** it.

---

## 13. Suggested first week (if you say “build it”)

| Day | Output |
|-----|--------|
| 1 | `call/start` + JSONL ledger + `call/end` writes `transcript.json` |
| 2 | User + agent PCM append + mix.wav |
| 3 | Slots + working-memory block; cache-hit test |
| 4 | Async rolling summary from ledger |
| 5 | Structured `outcome.json` + simple calls list in the UI |

---

## 14. Short answers to the design choices

**“Can we just raise `BRAIN_CONTEXT_TURNS` to 20?”**  
No. That is the expensive, slow way. Use slots + rolling summary + last 2 raw turns.

**“Can OpenAI remember the call for us?”**  
You already chose `store: false` for cost and control. Keep it. You remember in *your* ledger; Luna only sees the compact working set.

**“Should disposition be a tool the model calls when it thinks the user is done?”**  
Optional later. Tools mid-call add delay and the user often never “closes” cleanly. Hang-up job is more reliable.

**“Should we save browser MediaRecorder instead of server PCM?”**  
Worse. Echo, mixed speakers, no stereo, codec drift. Save the same PCM you send to Sarvam and the same TTS you send to the speaker.

---

## 15. Bottom line

You already have the **token-saving live brain**. What you do not have is:

1. a **full untruncated ledger** (so memory and summary have a source of truth),
2. **working memory** (slots + small rolling summary **after** the cache breakpoint),
3. a **call end** hook that writes **summary + status**,
4. **server-side streaming audio** (user + agent) mixed to stereo.

That is the industry pattern used by Pipecat, Vapi/Retell, and AWS call analytics, fitted to this repo so cache hits and streaming TTS stay intact.

This file is the spec. Implementation starts when you want Phase A built in the codebase.
