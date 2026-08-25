# 04 — Memory and Call Lifecycle

Working memory, call ledger, audio archive, post-call outcome, and SaaS compiled brain.

Aligned with **`memory implemenation.md`** (canonical) and **`MEMORY_CALL_ARCHIVE_PLAN.md`** (file layout).

**Target-state specification:** working memory, call APIs, server archive, outcome generation, and SaaS brain persistence are not implemented in the current repository.

---

## 1. Information architecture (three layers)

Normative detail: [12-brain-business-memory-spec.md](./12-brain-business-memory-spec.md) §17–28.

| Layer | Content | Live LLM? | Cached? |
|-------|---------|-----------|---------|
| **Stable compiled brain** | Platform rules + optimized business prompt + output rules | Yes (prefix) | Yes — OpenAI breakpoint |
| **Full internal memory (B)** | Structured slots + history + provenance + rolling_summary | **No** (full object) | No |
| **Live memory projection (C)** | Compact per-turn render from B | Yes (dynamic tail) | No |
| **Call ledger (A)** | Full transcript, timestamps, audio | **Never** | No |

**Rule ML-10:** Full ledger text is never injected into live brain context. Post-call and rolling summary read from ledger only.

**Rule ML-11:** Never send full internal memory wholesale to live LLM; only projection (+ optional separate rolling_summary block).

---

## 2. Working memory

Normative schemas, operations, merge rules, projection, budgets, and cache accounting: [12-brain-business-memory-spec.md](./12-brain-business-memory-spec.md).

### 2.1 Schema (summary — canonical field layout)

Target live projection size: **~80–250 tokens**; stored memory capped by `WORKING_MEMORY_MAX_CHARS` (default 2000).

```json
{
  "schema_version": 1,
  "memory_version": 0,
  "customer": {
    "name": { "current": null, "confidence": 0, "source": "model", "turn": 0, "confirmed": false, "history": [] },
    "phone": { "current": null, "confidence": 0, "source": "telephony", "turn": 0, "confirmed": false, "history": [] },
    "city": { "current": null, "confidence": 0, "source": "model", "turn": 0, "confirmed": false, "history": [] },
    "language_preference": { "current": "te-IN", "confidence": 1.0, "source": "system", "turn": 0, "confirmed": true, "history": [] }
  },
  "requirements": {
    "budget": { "current": [], "alternatives": [], "history": [] },
    "locations": { "current": [], "alternatives": [], "history": [] },
    "property_types": { "current": [], "alternatives": [], "history": [] },
    "timeline": { "current": null, "confidence": 0, "source": "model", "turn": 0, "confirmed": false, "history": [] }
  },
  "preferences": [],
  "objections": [],
  "decisions": [],
  "important_context": [],
  "rolling_summary": "",
  "turn_count": 0,
  "last_updated_turn": 0,
  "updated_at": "ISO8601"
}
```

Legacy flat slots (`customer.name` string) accepted during migration; normalize to scalar slots on first write.

### 2.2 Update mechanism

LLM memory-extraction returns **merge operations** (not full memory rewrite). Normative schema uses JSON Pointer `path` and `op`:

```json
{
  "memory_update": {
    "operations": [
      {
        "op": "set",
        "path": "/customer/name",
        "value": "రాము",
        "confidence": 0.92,
        "source_evidence": "నా పేరు రాము",
        "provenance": { "source": "user", "ledger_seq": 3, "confirmed": false }
      },
      {
        "op": "add",
        "path": "/requirements/property_types/current",
        "value": "2BHK",
        "group_id": "req-1",
        "atomic_group": false
      },
      {
        "op": "set",
        "path": "/rolling_summary",
        "value": "Customer Ramu asked about 2BHK in Hyderabad."
      }
    ]
  }
}
```

Supported `op` values: `add`, `set`, `remove`, `replace`. Legacy `action`/`field` aliases map during migration only.

Server applies via **`call/memory_manager.py`** only (orchestrator). Routes and brain service delegate; they do not merge directly.

- `add` — append to array/collection per schema
- `set` — set scalar `current` or establish value when allowed
- `remove` — deactivate; preserve history
- `replace` — replace `current` only when schema marks field replaceable and authority permits
- Invalid path → log warning, reject op (no crash)
- Every proposal → immutable event log entry (accepted or rejected)

### 2.3 Live context assembly (per turn)

Order in `instruction_builder.py` — matches `MEMORY_CALL_ARCHIVE_PLAN.md` §4.1 and OpenAI cache rules:

```
input[0]  role: developer   cached_brain_prompt (compiled brain)     ← prompt_cache_breakpoint (STABLE)
input[1]  role: user        [Working memory projection]\n{compact projection text}  ← dynamic (~80–250 tokens)
input[2]  role: user        [Rolling summary]\n{text}               ← only if distinct/non-empty; dynamic
input[3..]                  last BRAIN_CONTEXT_TURNS (truncated)     ← dynamic
input[N]  role: user        current transcript                       ← dynamic
```

**Naming in code** (from `memory implemenation.md` §23): use `cached_brain_prompt`, `live_memory_projection`, `rolling_summary`, `call_ledger` — not vague “dynamic cache” labels.

**Do not include:** full internal memory JSON, full ledger, raw business prompt (if compiled), prior call history (v1).

**Do not put** projection or rolling summary inside `input[0]` — that would bust the cache on every memory update.

### 2.4 Memory update timing (hybrid)

| Step | Path | Latency |
|------|------|---------|
| 1 | Stream `spoken_response` deltas → TTS | Hot — no wait for memory |
| 2 | On stream `done`, async memory merge call | Warm — 50–150 tokens structured |
| 3 | Apply operations to server-owned in-call state and append durable event | must remain off audio callback |
| 4 | Next turn reads updated memory | — |

Optional: rolling summary refresh every 4–6 turns via separate summarizer reading **ledger tail** (async).

### 2.5 Feature flag

```bash
ENABLE_WORKING_MEMORY=true
WORKING_MEMORY_MAX_CHARS=2000
MEMORY_PROJECTION_MAX_TOKENS=300
ROLLING_SUMMARY_MAX_TOKENS=150
ROLLING_SUMMARY_INTERVAL_TURNS=5
MEMORY_EXTRACTION_MAX_OUTPUT_TOKENS=400
```

Migration rule: `ENABLE_WORKING_MEMORY` is canonical. If it is unset, legacy `ENABLE_SESSION_SUMMARY=true` enables the new rolling-summary behavior with a deprecation warning; the existing string-join summarizer is never treated as production memory.

---

## 3. Call lifecycle

### 3.1 Entities

| Entity | ID | Lifetime |
|--------|-----|----------|
| `session_id` | Existing browser/server session | Until TTL / clear |
| `call_id` | New UUID per voice interaction | Start → end + archive |

One session may have multiple calls (reconnect). Each call has immutable config snapshot.

### 3.2 API endpoints

#### `POST /api/call/start`

Request:

```json
{
  "agent_id": "uuid",
  "session_id": "optional-existing",
  "channel": "browser",
  "caller_id": null,
  "tier": "medium",
  "stack_override": null
}
```

**Deprecated:** `customer_id` in request body — use `agent_id`. `tenant_id` comes from auth context.

| `channel` | Meaning |
|-----------|---------|
| `browser` | Mic/speaker SPA (default) |
| `pstn` | Plivo phone call — see [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md) |

For PSTN, `caller_id` is E.164 from Plivo START event; pre-seeds `working_memory.customer.phone`.

Response:

```json
{
  "call_id": "uuid",
  "session_id": "uuid",
  "resolved_stack": { ... },
  "compiled_brain_version": "v3",
  "started_at": "ISO8601"
}
```

Server actions:

- Resolve stack (tier / frontend selection)
- Lock `compiled_brain` text + version for call
- Initialize working memory empty JSON
- Create `data/calls/{call_id}/` directory
- Open `transcript.jsonl` append handle
- Start audio capture buffers (user PCM from STT path, agent from TTS path)

#### `POST /api/call/end`

Request:

```json
{
  "call_id": "uuid",
  "reason": "user_stop" | "timeout" | "error" | "transfer" | "hangup"
}
```

Aliases accepted: `user_hangup` → `user_stop`, `idle_timeout` → `timeout`.

Response: **202 Accepted** immediately; post-call work runs async (per archive plan).

Server actions (async job queue or background task):

1. Finalize `transcript.jsonl`
2. Finalize `audio/user.pcm`, `audio/agent.pcm` (or convenience WAV derivatives)
3. Mix stereo `mix.wav` (user=L, agent=R)
4. Run post-call LLM → `outcome.json`
5. Update call index (`calls_index.json` or DB row)
6. Clear in-RAM call state

#### `GET /api/call/{call_id}`

Returns metadata + outcome + transcript summary (not full audio inline).

#### `GET /api/calls`

List with filters: date range, disposition, tier, `agent_id`.

#### `GET /api/call/{call_id}/audio/mix`

Stream `mix.wav`.

### 3.3 Client integration

`app.js` on **Start**:

1. `POST /api/call/start` before opening STT WS
2. Pass `call_id` in brain SSE query/body
3. On stop/hangup: `POST /api/call/end`
4. Idle timeout (existing) triggers `call/end` with `idle_timeout`

`conversation_store.js` may sync server call list; localStorage becomes cache, not source of truth.

### 3.4 Auto-finalize

If client disconnects without `call/end`:

- Server finalizes after configurable `CALL_IDLE_TIMEOUT_SEC` (initial default 300 seconds, matching the source plan’s five-minute example; tune by channel after tests)
- Same post-call pipeline runs

---

## 4. Call ledger

### 4.1 Directory layout (canonical — `MEMORY_CALL_ARCHIVE_PLAN.md` §6.1)

```
data/calls/{call_id}/
  meta.json              # ids, channel, caller_id, stack, tier, versions, times
  transcript.jsonl       # append-only while call is live (untruncated)
  transcript.json        # pretty closed file after hang-up (CRM/human)
  audio/
    user.pcm             # 16 kHz s16le mono (browser mic or PSTN after transcode)
    agent.pcm            # TTS stream as played (24 kHz or muxed)
    mix.wav              # stereo after hang-up: L=user, R=agent
    user.wav             # optional convenience convert
    agent.wav
  outcome.json           # summary + disposition (after hang-up)
  working_memory.json    # final snapshot at call end
```

### 4.2 `transcript.jsonl` line schema

```json
{
  "t": "2026-08-25T06:41:28.112Z",
  "seq": 3,
  "speaker": "user",
  "text": "నమస్కారం",
  "t_start_ms": 1840,
  "t_end_ms": 3120,
  "interrupted": false,
  "stt_model": "saaras:v3-realtime",
  "stt_latency_ms": 120
}
```

Assistant lines add `llm_ttft_ms`, `tts_first_audio_ms`, `tts_speaker`, `chars`, `token_usage`.

### 4.3 Ledger writers

| Event | Writer |
|-------|--------|
| STT final | `call_ledger.append_user_turn()` |
| Brain done | `call_ledger.append_assistant_turn()` |
| Barge-in | Flush **partial** assistant text actually heard via TTS with `interrupted: true` — not full brain string |

Writes are append-only; no truncation in ledger (unlike `conversation_manager` char caps for live LLM).

---

## 5. Post-call outcome

### 5.1 Generation

- **Input:** full `transcript.jsonl` + final `working_memory.json` snapshot
- **Model:** same tier LLM or cheaper env `POST_CALL_LLM_MODEL`
- **Method:** Structured Outputs (JSON schema) — not streaming
- **store:** may be `true` for post-call (not live hot path)

### 5.2 `outcome.json` schema (aligned with source docs)

```json
{
  "call_id": "uuid",
  "outcome_status": "complete",
  "generated_at": "ISO8601",
  "duration_sec": 342,
  "summary_te": "తెలుగు సంక్షిప్త సారాంశం",
  "summary_en": "English summary for ops",
  "disposition": "can_convert",
  "disposition_confidence": 0.87,
  "disposition_detail": "Appointment booked for Saturday 10am",
  "intent": "property inquiry",
  "next_action": "schedule site visit",
  "callback_time": null,
  "objections": ["parking"],
  "sentiment": "positive",
  "talk_ratio_user_pct": 42,
  "extracted": {
    "name": "Ramu",
    "city": "Hyderabad",
    "phone": null,
    "product": "2BHK"
  },
  "working_memory_final": { ... }
}
```

| `outcome_status` | Meaning |
|------------------|---------|
| `complete` | Outcome LLM succeeded |
| `failed` | LLM error — retry job eligible |
| `pending` | Still processing after `call/end` |

Prompt rules: use transcript only; if unknown → `null` / `no_outcome`; do not invent phone numbers.

### 5.3 Disposition enum

See [02-requirements-reconciliation.md](./02-requirements-reconciliation.md) §4.

### 5.4 CRM hook (thin v1)

`POST /api/call/end` optionally fires webhook if `CRM_WEBHOOK_URL` set — payload = `outcome.json` + `call_id`. No retry queue in v1 (log failure).

---

## 6. SaaS compiled brain

### 6.1 Customer brain record

```json
{
  "agent_id": "agent_abc",
  "tenant_id": "tenant_xyz",
  "raw_business_prompt": "exact text customer entered",
  "optimized_business_prompt": "LLM-compressed instructions",
  "platform_brain_version": "1.2.0",
  "business_brain_version": 4,
  "compiled_brain": "full cached prefix text",
  "compiled_brain_version": "1.2.0+4",
  "updated_at": "ISO8601"
}
```

### 6.2 Onboarding flow

1. Customer saves raw prompt in UI (**Business** panel).
2. Server runs **optimizer** (one LLM call, structured) → `optimized_business_prompt`.
3. Server compiles:

   `compiled_brain = PLATFORM_BRAIN + optimized_business + STATIC_OUTPUT_RULES`

4. Increment `business_brain_version`; recompute `compiled_brain_version`.
5. UI shows raw text only; compiled text visible in dev mode via `/api/prompt/effective`.

### 6.3 Optimizer goals (from memory doc)

- Remove redundancy vs platform brain
- Preserve business facts, products, policies
- Target token budget (env `BUSINESS_BRAIN_MAX_TOKENS`)
- Never drop compliance / safety rules from platform layer

### 6.4 Version locking at call start

`call/start` copies `compiled_brain_version` into `meta.json`. In-flight calls unaffected by later brain edits.

### 6.5 Cache key

`prompt_cache_key = hash(compiled_brain_version + BRAIN_TOKEN_BUDGET)` — not sessionId (existing pattern preserved).

---

## 7. Prompt caching rules (must not break)

From current implementation + OpenAI guidance:

1. **Stable content first:** `compiled_brain` entire block before breakpoint.
2. **Dynamic content last:** working memory, recent turns, current utterance after breakpoint.
3. **Breakpoint:** on brain developer message when ≥1024 tokens and model supports caching.
4. **store: false** on all live turn requests.
5. **Regression test:** cache hit rate ≥85% on turn 2+ with working memory enabled.

---

## 8. Migration from current state

| Current | Target |
|---------|--------|
| `ENABLE_SESSION_SUMMARY=false` | `ENABLE_WORKING_MEMORY=true`; legacy flag accepted temporarily as described above |
| `compact_history_summary()` | `working_memory.rolling_summary` |
| `conversation_store.js` only | Server `GET /api/calls` primary |
| `instruction_store` per-session brain | Agent compiled brain when `agent_id` set |
| `conversation_manager` 8-msg window | Keep for live LLM; ledger separate |

---

## 9. Acceptance criteria

- [ ] After 10-turn call, agent recalls name from turn 2 without ledger in LLM input
- [ ] `transcript.jsonl` has full untruncated text
- [ ] `outcome.json` disposition matches golden test transcripts (≥80% on fixture set)
- [ ] `mix.wav` playable; user/agent channels correct
- [ ] Cache hit rate regression test passes with working memory
- [ ] `call/end` completes within 30s for 15-min call (async post-call)
- [ ] Auto-finalize on disconnect works
