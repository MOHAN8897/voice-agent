# Memory, Ledger & Outcome Data Models

Objects **A**, **B**, **C**, and post-call outcome — the three-store pattern from industry practice (Pipecat, Vapi, AWS LCA).

**Normative spec:** [`prd/12-brain-business-memory-spec.md`](../prd/12-brain-business-memory-spec.md)

---

## 1. Three stores — one job each

```
DURING CALL (hot)
  STT → projection C → LLM → TTS
        ↑ reads B

APPEND-ONLY (warm, never blocks speech)
  A: transcript.jsonl + audio streams

AFTER HANG-UP (cold)
  outcome.json from full A + B snapshot
```

| Store | Job | Token cost |
|-------|-----|------------|
| **B + C** | Remember context during call | ~80–150 tokens/turn (C only to LLM) |
| **A** | Complete record for compliance/replay | Zero on hot path |
| **Outcome** | Disposition + summaries | One LLM call post-call |

---

## 2. Object A — Call ledger

**Owner:** `call/call_ledger.py`  
**Path:** `data/calls/{call_id}/transcript.jsonl`

### Line schema

```json
{
  "seq": 1,
  "role": "user",
  "text": "నా పేరు రవి",
  "ts": "2026-08-25T10:30:01.123Z",
  "stt_latency_ms": 145,
  "partial": false
}
```

```json
{
  "seq": 2,
  "role": "assistant",
  "text": "నమస్కారం రవి గారు...",
  "ts": "2026-08-25T10:30:03.456Z",
  "brain_latency_ms": 420,
  "tts_first_byte_ms": 180
}
```

### Rules

- Append-only; never truncated
- Never included in live LLM `input[]`
- `conversation_manager` holds truncated recent turns for live path only

### Audio refs (in `meta.json` or ledger events)

| File | Format |
|------|--------|
| `user.pcm` | 16 kHz mono Int16 |
| `agent.mp3` or `agent.pcm` | TTS stream capture |
| `mix.wav` | Stereo L=user R=agent (post-call) |

---

## 3. Object B — Full internal memory

**Owner:** `call/memory_manager.py`  
**Persisted:** `memory_events.jsonl` + `memory_snapshot.json`

### Default compact schema (MVP)

```json
{
  "facts": {
    "name": "Ravi",
    "city": "Hyderabad",
    "intent": "2BHK apartment"
  },
  "preferences": {
    "language": "te-en codemix"
  },
  "important_context": "Budget around 50L. Prefers Gachibowli area.",
  "summary": "Caller Ravi looking for 2BHK in Gachibowli, budget 50L."
}
```

### Event log entry

```json
{
  "turn_seq": 5,
  "ts": "ISO8601",
  "operations": [
    {"op": "set_fact", "key": "budget", "value": "50L"}
  ],
  "applied": true,
  "validation_errors": []
}
```

### Operation types

| Op | Target field |
|----|--------------|
| `set_fact` | `facts.{key}` |
| `set_preference` | `preferences.{key}` |
| `append_context` | `important_context` (bounded) |
| `update_summary` | `summary` (token-capped, ~100 tokens) |

**Cross-call memory:** Not in MVP. B destroyed or archived with call.

---

## 4. Object C — Live memory projection

**Owner:** `call/memory_projection.py`  
**Purpose:** Deterministic compact render of B for live LLM

### Example output

```text
[Facts]
name: Ravi | city: Hyderabad | intent: 2BHK apartment | budget: 50L
[Preferences]
language: te-en codemix
[Context]
Prefers Gachibowli area.
```

### Constraints

- Hard cap: ~150 tokens (configurable `MEMORY_PROJECTION_MAX_TOKENS`)
- Priority on truncation: facts > preferences > context > summary tail
- Never includes full transcript or event log

---

## 5. Live structured turn schema

Same LLM returns both fields (CD-016):

```json
{
  "spoken_response": "సరే రవి గారు, గచ్చిబౌలి ఏరియాలో ఏ రకమైన ఫ్లాట్ కావాలి?",
  "memory_update": {
    "operations": [
      {"op": "set_fact", "key": "area", "value": "Gachibowli"}
    ]
  }
}
```

---

## 6. Post-call outcome

**Owner:** `call/post_call_pipeline.py`  
**Path:** `data/calls/{call_id}/outcome.json`

```json
{
  "disposition": "qualified",
  "disposition_confidence": 0.89,
  "summary_te": "రవి గారు గచ్చిబౌలిలో 50 లక్షల బడ్జెట్‌తో 2BHK కోసం అడిగారు...",
  "summary_en": "Ravi inquired about a 2BHK in Gachibowli with a 50L budget...",
  "next_action": "schedule_site_visit",
  "extracted_fields": {
    "name": "Ravi",
    "budget": "50L",
    "location": "Gachibowli",
    "unit_type": "2BHK"
  },
  "objections": ["price sensitivity"],
  "model": "gpt-5.6-luna",
  "prompt_version": "outcome_v1",
  "generated_at": "2026-08-25T10:35:00Z"
}
```

### Disposition enum (locked)

| Value | Meaning |
|-------|---------|
| `new_lead` | First contact |
| `interested` | Positive engagement |
| `qualified` | Meets criteria |
| `site_visit_planned` | Appointment scheduled |
| `callback_required` | Follow-up needed |
| `not_interested` | Declined |
| `wrong_number` | Misdial |
| `converted` | Goal achieved |
| `no_outcome` | Too short / ambiguous |

---

## 7.5 Memory API paths (canonical — `prd/13` §6)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/call/{id}/memory` | B snapshot (role-redacted) |
| `GET /api/call/{id}/memory-events` | Event log |
| `GET /api/call/{id}/memory/projection?turn=N` | Per-turn projection debug |

No public write endpoint. Admin `manual_correction` → audited event only.

---

## 7. PostgreSQL call index (metadata only)

Full content in file store / bucket. DB holds index:

```sql
calls (
  call_id UUID PK,
  tenant_id UUID,
  agent_id UUID,
  channel TEXT,           -- browser | pstn
  disposition TEXT,       -- from outcome, nullable until complete
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_sec INT,
  compiled_brain_version TEXT,
  combination_id TEXT,
  finalization_status TEXT,
  storage_path TEXT
)
```

---

## 9. Token budget reference

| Layer | Tokens | Cached? |
|-------|--------|---------|
| Compiled brain (L2) | 800–2000+ | Yes (breakpoint) |
| Projection C | 80–150 | No |
| Rolling summary (if separate) | 80–120 | No |
| Recent 2 turns | 100–300 | No |
| Current utterance | 20–80 | No |

**Never** put C or summary inside the cached developer block.
