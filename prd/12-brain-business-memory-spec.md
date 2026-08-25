# 12 — Brain, Business Logic, and Memory Specification

This document is normative for prompt ownership, compilation, working memory, projection, provenance, and post-call analysis.

**Module ownership and singularity:** [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md). This document defines memory/brain **data contracts**; doc 15 defines **who implements them**.

## 1. Brain layers and ownership

The system must keep these objects distinct:

1. `platform_brain`: developer-owned identity, global behavior, safety, language, and memory/output contract.
2. `raw_business_sections`: customer-authored structured sections preserved exactly.
3. `raw_business_prompt`: deterministic assembly of enabled raw sections.
4. `optimized_business_prompt`: compact internal representation produced by an optimizer.
5. `static_output_rules`: platform-controlled live-response constraints.
6. `compiled_brain`: versioned concatenation of platform brain, optimized business prompt, and static output rules.
7. `full_internal_memory`: server-owned current-call state with history/provenance.
8. `live_memory_projection`: compact, turn-relevant view sent to the live LLM.
9. `rolling_summary`: compact conversational summary.
10. `recent_turns`: bounded last one or two turns.
11. `call_ledger`: full append-only transcript/audio/event history.
12. `post_call_outcome`: structured analysis generated after hang-up.

No object may silently stand in for another.

## 2. Business instruction authoring

### Requirement

Customer users author instructions in separate UI sections, but live execution uses one assembled and optimized business prompt.

### Why

Sections improve clarity, validation, auditing, and ownership without fragmenting the stable prompt or producing multiple conflicting LLM instruction messages.

### Canonical section types

- `identity_purpose`
- `facts`
- `actions_limits`
- `flow_qualification`
- `flow_callback`
- `scope_redirects`
- `guardrails`
- `faq`
- `custom`

### Raw section contract

```json
{
  "section_id": "uuid",
  "type": "facts",
  "title": "Business Facts",
  "enabled": true,
  "order": 20,
  "raw_text": "We operate from 9am to 7pm IST.",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "updated_by": "user_id"
}
```

The server builds `raw_business_prompt` using deterministic section order, stable delimiters, and raw text without semantic rewriting.

## 3. Business prompt optimization

### Requirement

Optimization runs once when a draft is explicitly optimized or published, not on every call or turn.

### Optimizer input

- full assembled raw business prompt
- platform-defined optimizer policy
- previous approved optimized prompt, when available
- token budget

### Optimizer output

```json
{
  "optimized_business_prompt": "...",
  "preserved_facts": ["..."],
  "preserved_rules": ["..."],
  "deduplicated_items": ["..."],
  "conflicts": [
    {
      "severity": "blocking|warning|info",
      "source_section_ids": ["..."],
      "description": "...",
      "recommended_resolution": "..."
    }
  ],
  "source_checksum": "sha256",
  "optimizer_model": "...",
  "optimizer_version": "...",
  "optimized_at": "ISO8601"
}
```

### Mandatory optimizer rules

- Remove repetition and consolidate duplicates.
- Make implicit constraints explicit only when supported by the source.
- Preserve facts, limits, actions, required flows, guardrails, and exceptions.
- Do not invent policy, pricing, eligibility, commitments, or tool capability.
- Preserve important literals such as dates, prices, URLs, phone numbers, names, and prohibited actions.
- Report ambiguity rather than silently resolving it.
- Keep raw source immutable.

### Validation

- `source_checksum` must match the current assembled raw prompt.
- Publish is blocked on unacknowledged blocking conflicts.
- A fact-preservation comparison checks structured literals and named entities.
- Customer may reject an optimizer result without losing raw content or prior approved version.

## 4. Versioned compiled brain

### Version record

```json
{
  "platform_brain_version": 8,
  "customer_business_brain_version": 14,
  "optimizer_version": 3,
  "static_output_rules_version": 5,
  "compiled_brain_version": "8.14.3.5",
  "compiled_checksum": "sha256",
  "compiled_at": "ISO8601",
  "status": "draft|validated|approved|active|superseded|rolled_back"
}
```

### Compilation order

```text
PLATFORM_BRAIN
OPTIMIZED_CUSTOMER_BUSINESS_BRAIN
STATIC_OUTPUT_BEHAVIOR_RULES
```

Compilation is deterministic for the same source versions.

### Call locking

At call start the server resolves and stores the exact compiled version and prompt checksum. In-flight calls never switch version. New calls use the active version resolved at their start.

## 5. Live prompt layout and caching

```text
input[0] developer: compiled_brain                         STABLE PREFIX
---------------------- CACHE BOUNDARY -------------------------------
input[1] user: live_memory_projection                     DYNAMIC
input[2] user: rolling_summary, if distinct/non-empty     DYNAMIC
input[3..] recent user/assistant turns                    DYNAMIC
input[N] user: current transcript                         DYNAMIC
```

Provider adapters may translate roles and cache controls to provider-specific APIs, but must preserve stable-first ordering and usage accounting.

The platform must not assume every provider exposes identical cache semantics. Registry capability metadata defines `implicit_cache`, `explicit_cache`, usage fields, minimum tokens, and limitations.

## 6. Full internal memory

The authoritative in-call memory is richer than the projection:

```json
{
  "schema_version": 1,
  "customer": {
    "name": {
      "current": "Mohan",
      "confidence": 0.96,
      "source": "user",
      "turn": 2
    },
    "phone": {
      "current": "+919876543210",
      "confidence": 1.0,
      "source": "telephony",
      "turn": 0
    }
  },
  "requirements": {
    "locations": {
      "current": ["Hyderabad"],
      "alternatives": ["Bangalore"],
      "history": [
        {"value": "Hyderabad", "state": "preferred", "turn": 4},
        {"value": "Bangalore", "state": "acceptable", "turn": 7},
        {"value": "Hyderabad", "state": "preferred", "turn": 11}
      ]
    }
  },
  "preferences": [],
  "objections": [],
  "decisions": [],
  "important_context": [],
  "rolling_summary": "",
  "turn_count": 11,
  "updated_at": "ISO8601"
}
```

Field-specific schemas may vary by agent, but type, limits, provenance, and projection policy must be explicit.

## 7. Memory output contract

### Conceptual contract

```json
{
  "spoken_response": "హాయ్ మోహన్ గారు...",
  "memory_update": {
    "operations": [
      {
        "op": "set",
        "path": "/customer/name/current",
        "value": "Mohan",
        "group_id": "identity-1",
        "atomic_group": false,
        "confidence": 0.96,
        "source_evidence": "నా పేరు మోహన్"
      }
    ]
  }
}
```

Supported operations:

- `add`: append a new item or alternative without destroying prior values.
- `set`: establish a current value when no protected conflict exists.
- `remove`: deactivate a removable item while preserving the event history.
- `replace`: replace a current value only when the schema permits and evidence supports it.

Related operations carry a common `group_id`. When `atomic_group=true`, either all operations in that group validate and apply or none apply. Unrelated operations may be validated independently.

### Streaming decision (CD-016 — locked in `17-product-decisions.md`)

**Product owner decision:** The **same LLM** used for conversation returns structured output with both `spoken_response` and `memory_update`. This supersedes prior CD-001 async second-call extraction as the **primary MVP path**.

Normative live turn:

1. Build request: compiled brain + projection C + recent turns + current transcript.
2. **Same LLM** (OpenAI or DeepSeek Flash per dev configuration) with Strict JSON Schema / Structured Outputs.
3. Parse response → stream `spoken_response` to TTS immediately (sentence buffer / partial field streaming when provider supports).
4. Validate and apply `memory_update` to B via `memory_manager` without blocking first audible byte beyond existing buffer behavior.
5. If structured parse fails: speak safe fallback line; reject memory ops; metric `structured_turn_parse_error`.

`static_output_rules` in compiled brain must require the structured contract for live turns (spoken + memory fields), not plain text only.

**Fallback (engineering only):** If streaming structured output regresses TTFT/first-audio SLO in testing, document regression and propose hotfix — product default remains single-LLM structured until owner approves change.

- Deterministic/system facts such as Plivo caller ID, explicit DTMF, selected language, and tool-confirmed appointment IDs enter as system-proposed events with authoritative provenance.
- Simple unambiguous fields may use deterministic validated extractors.
- Ambiguous conversational facts are proposed by the **same live LLM** in `memory_update.operations`.
- All paths still pass the same server validation/event pipeline.

## 8. Memory event log

Every proposed operation becomes an immutable event:

```json
{
  "event_id": "uuid",
  "call_id": "uuid",
  "turn": 7,
  "proposed_at": "ISO8601",
  "proposed_by": {
    "provider": "openai",
    "model": "...",
    "request_id": "..."
  },
  "operation": {
    "op": "add",
    "path": "/requirements/locations/alternatives",
    "value": "Bangalore"
  },
  "evidence": {
    "speaker": "user",
    "text": "Bangalore కూడా okay",
    "ledger_seq": 13
  },
  "validation": {
    "status": "accepted|rejected|normalized",
    "reason": "..."
  },
  "resulting_memory_version": 18
}
```

The event log is append-only. Current memory may be materialized by folding accepted events.

## 9. Memory validation and safety

The server is authoritative. The LLM proposes; it never writes storage.

Validation order:

1. Parse against strict schema.
2. Allowlist operation.
3. Validate JSON Pointer path against agent memory schema.
4. Validate type, enum, format, length, array count, and object depth.
5. Validate evidence/provenance.
6. Apply source-authority policy: authoritative system values and explicit user confirmations outrank model confidence; recency and contradiction state are considered after authority.
7. Apply protected-field policy.
8. Detect overwrite/conflict and atomic-group requirements.
9. Normalize only with deterministic functions.
10. Enforce total memory/event limits.
11. Append accepted or rejected event.

Protected fields may include legal consent, payment state, identity verification, and telephony caller ID. LLM proposals cannot replace authoritative system values.

Failure behavior:

- Malformed output: reject update, record metric, keep previous memory.
- Partial operations: validate unrelated operations independently; correlated atomic groups succeed or fail together.
- Size breach: reject low-priority additions and schedule summary/projection cleanup.
- Contradiction: preserve both historical values and mark current according to evidence/confidence policy.

## 10. Live memory projection

### Requirement

Do not send full internal memory to the live LLM indefinitely.

### Projection pipeline

```text
full_internal_memory
  → schema field eligibility
  → current-turn relevance selection
  → authority/confirmation/recency/priority ranking
  → sensitive-field policy
  → compact deterministic rendering
  → token-budget enforcement
  → live_memory_projection
```

### Projection inputs

- current transcript and detected intent
- active flow/state
- required fields still missing
- current values and highest-priority alternatives
- unresolved objection/decision
- recent accepted memory events
- projection policy from agent schema

### Projection rules

- Always include identity required to address the caller, active goal, explicit commitments, unresolved guardrails, and next required action.
- Include alternatives only if relevant to the current topic.
- Omit superseded history unless the user revisits it.
- Omit internal confidence/provenance unless needed for reasoning.
- Never include secrets or fields disallowed by tenant policy.
- Render deterministic compact JSON or labeled lines.
- Default target: 80–250 tokens; hard limit configured per agent/model.

### Projection record

Store a hash and optionally the exact projection per turn for debugging:

```json
{
  "turn": 12,
  "memory_version": 18,
  "projection_policy_version": 2,
  "projection_tokens_est": 137,
  "included_paths": ["/customer/name", "/requirements/locations"],
  "omitted_reason_counts": {"irrelevant": 7, "superseded": 2, "sensitive": 1}
}
```

### Acceptance criteria

- Projection never exceeds configured hard token limit.
- A test fixture with changed location preserves history internally while projecting current preference.
- Projection is reproducible from the same memory/version/transcript.
- Full memory is absent from live provider request logs.

## 11. Rolling summary

- Generated asynchronously every configurable 4–6 turns or token threshold.
- Input: previous rolling summary plus full untruncated ledger turns since last summary.
- Target: 80–120 tokens by default.
- Preserves facts, decisions, unresolved issues, and commitments.
- Does not duplicate detailed structured slots when avoidable.
- On failure: retain previous summary and continue.
- Emits summary-applied metrics: source turns, previous/new tokens, duration, model, failure.

## 12. Recent turns

Keep `BRAIN_CONTEXT_TURNS=2` as current default. Preserve current user/assistant character caps for live context. The ledger remains untruncated and separate.

Tool call/result sequences, if added later, must not be split across the recent-context boundary.

## 13. Call ledger

The ledger is append-only and must include:

- user and agent transcript
- actual spoken/played agent text, including interrupted partial output
- timestamps and sequence
- interruption state
- provider/model/config versions
- audio references
- call/channel/session/tenant/agent IDs
- component metrics and correlated request/trace IDs
- memory proposal/validation references
- transfer, DTMF, tool, timeout, error, and fallback events where applicable

The browser is never the production system of record.

## 14. Post-call outcome

Generated asynchronously from the full ledger and final memory:

```json
{
  "status": "pending|complete|failed",
  "summary_te": "...",
  "summary_en": "...",
  "disposition": "interested",
  "disposition_confidence": 0.91,
  "intent": "...",
  "next_action": "...",
  "callback_time": null,
  "objections": [],
  "extracted": {},
  "sentiment": "positive|neutral|negative",
  "talk_ratio_user_pct": 42
}
```

Use provider-native structured output/schema support when verified. Unknown data is `null`; the analyzer must not invent phone numbers, appointments, prices, or commitments.

## 15. Brain and memory observability

Per call/turn:

- compiled brain version/checksum
- stable prompt estimated/input/cached/cache-write tokens
- projection version, size, and included fields
- rolling summary version/size
- memory extraction latency and cost
- proposed/accepted/rejected operations
- validation reasons
- memory availability before each turn
- post-call analysis status and retries

Aggregate:

- memory extraction success
- operation rejection rate by path/provider
- projection token P50/P95
- stale-memory turns
- contradiction rate
- post-call outcome success and latency

## 16. Required tests

- Deterministic business-section assembly.
- Raw prompt byte preservation.
- Optimizer fact and literal preservation.
- Brain version lock during active call.
- Add/set/remove/replace validation.
- Protected-field overwrite rejection.
- Memory history: Hyderabad → Bangalore acceptable → Hyderabad preferred.
- Projection relevance and token limit.
- Async memory failure does not delay spoken response.
- Cache prefix remains byte-stable across memory changes.
- Post-call strict-schema validation and unknown-to-null behavior.

---

## 17. Three-layer separation (normative)

These three objects must never be conflated in implementation, APIs, or UI.

| Layer | Name | Contents | Live LLM input? | Persisted? | Token budget |
|-------|------|----------|-----------------|------------|--------------|
| **A** | `call_ledger` | Append-only transcript lines, audio refs, provider metrics, interruption state, memory proposal refs | **Never** | Yes — `transcript.jsonl`, PCM/WAV | Unlimited (not sent to LLM) |
| **B** | `full_internal_memory` | Structured slots with `current`, `alternatives`, `history`, confidence, provenance, `rolling_summary`, `turn_count` | **Never** (full object) | Yes — materialized state + event log | `WORKING_MEMORY_MAX_CHARS` (default 2000 chars) |
| **C** | `live_memory_projection` | Deterministic compact render of turn-relevant subset of B | **Yes** — dynamic tail only | Optional per-turn debug record | `MEMORY_PROJECTION_MAX_TOKENS` (default 300 hard max) |

Additional dynamic live inputs (not memory layers):

| Input | Source | Budget |
|-------|--------|--------|
| `rolling_summary` | Field inside B, may also be sent as separate user message when distinct from projection | Included in projection or separate block; max `ROLLING_SUMMARY_MAX_TOKENS` (default 150) |
| `recent_turns` | Ledger tail, truncated for live path only | `BRAIN_CONTEXT_TURNS=2`, existing char caps |
| `current_transcript` | Current user utterance | Current utterance only |

**Rules:**

1. Post-call analysis, rolling summary, and CRM export read **A** (full ledger), optionally final **B** snapshot.
2. Live brain reads **C** (+ rolling summary if not embedded, recent turns, current transcript). Never **A**.
3. Memory extraction proposes updates to **B** only; never writes **A** text except via normal transcript append path.
4. UI “memory inspector” for customers shows business-relevant projection + selected provenance; auditors may view **B** and event log; **A** is the transcript tab.

---

## 18. Full internal memory schema

### 18.1 Default MVP schema (product locked — `17` §5)

New agents default to compact memory:

```json
{
  "schema_version": 1,
  "memory_version": 0,
  "turn_count": 0,
  "facts": {},
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

| Field | Type | Notes |
|-------|------|-------|
| `facts` | object | Key-value business facts extracted this call |
| `preferences` | object or array | Caller preferences |
| `important_context` | string | Short unstructured notes |
| `summary` | string | Compact rolling narrative (alias for rolling_summary in live block) |

**One compact dynamic memory block** in live LLM input — projection renders this shape; avoid duplicating `summary` in a second message unless policy omits prose from projection (`15` §8).

### 18.2 Extended schema (optional per agent)

```json
{
  "schema_version": 1,
  "memory_version": 18,
  "turn_count": 11,
  "last_updated_turn": 11,
  "updated_at": "2026-08-25T08:12:44.123Z",
  "customer": { ... },
  "requirements": { ... },
  "preferences": [ ... ],
  "objections": [ ... ],
  "decisions": [ ... ],
  "important_context": [ ... ],
  "rolling_summary": "Mohan prefers ready-to-move 2BHK around ₹50L; Hyderabad first, Bangalore alternative; parking matters."
}
```

### 18.2 Scalar slot (e.g. `customer.name`)

```json
{
  "current": "Mohan",
  "confidence": 0.96,
  "source": "user",
  "turn": 2,
  "confirmed": true,
  "history": [
    {
      "value": "Mohan",
      "state": "current",
      "turn": 2,
      "source": "user",
      "confidence": 0.96,
      "event_id": "uuid"
    }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `current` | string \| number \| boolean \| null | yes | Active value used for projection |
| `confidence` | number 0–1 | yes | Model or system confidence |
| `source` | enum | yes | `user`, `agent`, `telephony`, `system`, `tool`, `model` |
| `turn` | integer ≥ 0 | yes | Turn when `current` was established |
| `confirmed` | boolean | default false | Explicit user confirmation |
| `history` | array | yes | Append-only value timeline |

### 18.3 Collection slot (e.g. `requirements.locations`)

```json
{
  "current": [
    { "name": "Hyderabad", "priority": 1 },
    { "name": "Bangalore", "priority": 2 }
  ],
  "alternatives": [],
  "history": [
    { "value": "Hyderabad", "state": "preferred", "turn": 4, "source": "user", "event_id": "uuid" },
    { "value": "Bangalore", "state": "acceptable", "turn": 7, "source": "user", "event_id": "uuid" },
    { "value": "Hyderabad", "state": "preferred", "turn": 11, "source": "user", "event_id": "uuid" }
  ]
}
```

### 18.4 Simple array slots (e.g. `preferences`, `objections`, `decisions`, `important_context`)

Each item:

```json
{
  "id": "uuid",
  "text": "ready to move",
  "turn": 5,
  "source": "user",
  "confidence": 0.9,
  "active": true
}
```

### 18.5 Default real-estate agent schema (v1)

| Path | Type | Projection default |
|------|------|-------------------|
| `/customer/name` | scalar slot | always when known |
| `/customer/phone` | scalar slot | when known; telephony pre-seed |
| `/customer/city` | scalar slot | when known |
| `/customer/language_preference` | scalar slot | when not default |
| `/requirements/budget` | collection or string array | when relevant |
| `/requirements/locations` | collection | when relevant |
| `/requirements/property_types` | array | when relevant |
| `/requirements/timeline` | scalar slot | when relevant |
| `/preferences` | simple array | top 3 by recency |
| `/objections` | simple array | all active |
| `/decisions` | simple array | all active |
| `/important_context` | simple array | top 5 by priority |
| `/rolling_summary` | string | separate block or embedded per policy |

Agents may extend schema via `memory_schema` config; unknown paths reject unless whitelisted.

### 18.6 Legacy flat migration

During migration, dot-path ops (`customer.name`) map to scalar `current` leaves. Flat arrays without slot wrappers normalize to collection slots on first accepted write.

---

## 19. Exact `spoken_response` + `memory_update` schemas

### 19.1 Live spoken path (v1 hot path)

The live brain stream emits **plain speakable text only** (SSE deltas). It does **not** emit JSON on the hot path.

Structured schema applies to the **async memory-extraction call** and to future single-call adapters that prove no TTFT regression.

### 19.2 Memory extraction response schema (strict)

Provider must enforce via Structured Outputs / JSON Schema where supported; otherwise local validation after JSON-mode output.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["memory_update"],
  "properties": {
    "spoken_response": {
      "type": "string",
      "description": "Optional echo of assistant text already spoken; omitted in async extraction v1",
      "maxLength": 4000
    },
    "memory_update": {
      "type": "object",
      "additionalProperties": false,
      "required": ["operations"],
      "properties": {
        "operations": {
          "type": "array",
          "maxItems": 32,
          "items": { "$ref": "#/$defs/operation" }
        }
      }
    }
  },
  "$defs": {
    "operation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["op", "path"],
      "properties": {
        "op": {
          "type": "string",
          "enum": ["add", "set", "remove", "replace"]
        },
        "path": {
          "type": "string",
          "pattern": "^/"
        },
        "value": {},
        "group_id": { "type": "string", "maxLength": 64 },
        "atomic_group": { "type": "boolean", "default": false },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "source_evidence": { "type": "string", "maxLength": 500 },
        "provenance": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "source": {
              "type": "string",
              "enum": ["user", "agent", "telephony", "system", "tool", "model"]
            },
            "ledger_seq": { "type": "integer", "minimum": 0 },
            "confirmed": { "type": "boolean" }
          }
        }
      },
      "allOf": [
        {
          "if": { "properties": { "op": { "const": "remove" } } },
          "then": { "not": { "required": ["value"] } }
        },
        {
          "if": { "properties": { "op": { "enum": ["add", "set", "replace"] } } },
          "then": { "required": ["value"] }
        }
      ]
    }
  }
}
```

### 19.3 Legacy alias normalization (migration only)

| Legacy (`memory implemenation.md`) | Normative |
|------------------------------------|-----------|
| `action` | `op` |
| `field` dot path (`customer.name`) | `path` JSON Pointer (`/customer/name`) |
| missing `confidence` | default `0.7` for model proposals; `1.0` for telephony/system |

Reject legacy aliases in production after migration window.

### 19.4 Extraction call inputs

```json
{
  "call_id": "uuid",
  "turn": 7,
  "user_text": "Bangalore కూడా okay",
  "assistant_text": "హైదరాబాద్ మొదటి ఎంపిక...",
  "memory_snapshot": { ... full_internal_memory subset ... },
  "ledger_seq_user": 13,
  "ledger_seq_assistant": 14
}
```

Output size target: 50–150 tokens structured JSON.

---

## 20. Memory operation types (normative)

| `op` | Purpose | Valid targets | Effect on B | History |
|------|---------|---------------|-------------|---------|
| `add` | Append without replacing current set | Array paths, `alternatives`, simple-array slots | Appends item; may bump priority | Append history event |
| `set` | Establish `current` when no protected conflict | Scalar slots, `current` arrays when empty | Sets `current`; updates confidence/provenance | Append if value changed |
| `remove` | Deactivate without erasing audit trail | Simple-array items (by id), alternatives | `active=false` or remove from `current` per schema | Append `removed` state |
| `replace` | Replace `current` with evidence | Scalar slots marked `replaceable: true` in schema | Old `current` → history; new `current` set | Append both states |

**Forbidden:**

- `set`/`replace` on protected authoritative fields without sufficient authority (see §26).
- `add` on scalar-only paths.
- Full-document rewrite (no `op: merge_root`).

**Atomic groups:**

- Operations sharing `group_id` with `atomic_group: true` validate and apply together.
- Example: set name + phone from one utterance must both pass or both fail.

---

## 21. Server-side merge and validation rules

### 21.1 Pipeline (authoritative)

```text
proposal → parse JSON → normalize aliases → per-op schema check → path allowlist
  → type/format/enum/depth/count → provenance authority → protected-field policy
  → conflict detection → atomic group resolution → normalize values → apply to B
  → increment memory_version → append event log → schedule projection refresh
```

### 21.2 Per-operation validation

| Check | Rule |
|-------|------|
| Path exists | Must match agent `memory_schema` or default v1 schema |
| Type | `value` must match schema type at path |
| Enum/format | Phone E.164, dates, enums enforced server-side |
| Array max | e.g. locations ≤ 5, preferences ≤ 20 |
| Object depth | ≤ 4 levels from root |
| Duplicate `add` | Reject exact duplicate active item; allow semantic duplicate with warning |
| `replace` without `replaceable` | Reject |
| `remove` unknown id | Reject op, accept unrelated ops |

### 21.3 Merge semantics

**Scalar `set`:**

```text
if protected(path) and authority(proposal) < authority(existing): REJECT
if existing.current == value: ACCEPT noop
else: history.append(previous); current := value; update confidence/source/turn
```

**Collection `add` (locations):**

```text
if value already in current with same priority: REJECT duplicate
else: append to current or alternatives per schema; history.append
```

**Priority reorder example (turn 11 “Hyderabad first choice”):**

```text
replace priorities: Hyderabad=1, Bangalore=2; preserve both names in current
```

### 21.4 Failure behavior

| Failure | Spoken path | Memory |
|---------|-------------|--------|
| Malformed JSON | unaffected | reject all; metric `memory_parse_error` |
| Partial invalid ops | unaffected | accept valid; reject invalid; atomic groups all fail |
| Memory size breach | unaffected | reject low-priority `add`; never truncate spoken |
| Extraction timeout | unaffected | continue with previous B; metric `memory_extraction_timeout` |

---

## 22. Memory event log (normative record)

Every proposal — accepted, rejected, or normalized — appends one event. See §8 for shape.

Additional required fields:

```json
{
  "memory_version_before": 17,
  "memory_version_after": 18,
  "projection_hash_before": "sha256",
  "projection_hash_after": "sha256",
  "extraction_latency_ms": 142,
  "schema_version": 1
}
```

Retention: same as call retention policy. Events are immutable; corrections are new events, never edits.

---

## 23. Live memory projection algorithm

### 23.1 Inputs

- `full_internal_memory` at `memory_version`
- `projection_policy` from agent config (versioned)
- `current_transcript` (partial + final)
- `active_flow` state (e.g. `qualify`, `callback`, `faq`)
- `required_fields_missing[]`
- `recent_memory_event_ids` (last 3 accepted)

### 23.2 Algorithm (deterministic)

```text
1. candidates ← empty ordered set
2. ALWAYS include:
   - active_flow + next_required_action
   - unresolved objections (all active)
   - explicit commitments in decisions
   - identity fields needed to address caller (name if known)
3. FOR each schema path in memory:
   - IF path in required_fields_missing: include
   - IF path topic matches intent(current_transcript, active_flow): include
   - IF path referenced in recent_memory_event_ids: include
4. SCORE each candidate path:
   score = authority_weight(source) * 100
         + (confirmed ? 50 : 0)
         + recency_weight(turn) * 30
         + schema_priority(path) * 20
   authority_weight: telephony/system=1.0, user=0.95, tool=0.9, agent=0.7, model=0.6
5. FILTER sensitive paths via tenant policy
6. SORT by score descending; stable sort by path for ties
7. RENDER compact labeled lines (preferred) or minified JSON:
   Example:
   [memory]
   name=Mohan (confirmed,user,turn2)
   budget=50 lakhs
   locations=Hyderabad(p1), Bangalore(p2)
   goal=2BHK ready-to-move
   objection=parking (open)
8. ESTIMATE tokens (provider tokenizer or chars/4 fallback)
9. WHILE tokens > MEMORY_PROJECTION_MAX_TOKENS:
   drop lowest-scored optional path not in ALWAYS set
10. EMIT projection + projection record (hash, included_paths, omitted_reason_counts)
```

### 23.3 Reproducibility

Same inputs (`memory_version`, transcript, flow, policy_version`) must yield identical projection bytes.

---

## 24. Memory token budgets (normative)

| Artifact | Soft target | Hard max | Env var | Notes |
|----------|-------------|----------|---------|-------|
| Compiled brain (stable prefix) | agent-specific | `BRAIN_TOKEN_BUDGET` | `BRAIN_TOKEN_BUDGET` | Cached when provider supports |
| Live projection | 80–250 tokens | 300 | `MEMORY_PROJECTION_MAX_TOKENS` | Hard drop behavior §23 |
| Rolling summary | 80–120 tokens | 150 | `ROLLING_SUMMARY_MAX_TOKENS` | Stored in B |
| Full internal memory (stored) | ~150–300 tokens equiv | 2000 chars | `WORKING_MEMORY_MAX_CHARS` | Not sent wholesale to LLM |
| Memory extraction output | 50–150 tokens | 400 tokens | `MEMORY_EXTRACTION_MAX_OUTPUT_TOKENS` | Structured JSON only |
| Recent turns | 2 turns | existing caps | `BRAIN_CONTEXT_TURNS` | From conversation_manager |
| Post-call outcome | n/a | schema-limited | — | Full ledger input |

**Enforcement:**

- Optimizer and publish gates check compiled brain against `BRAIN_TOKEN_BUDGET`.
- Projection enforced every turn before LLM request.
- Rolling summary truncates at hard max with ellipsis marker `[...]`.

---

## 25. Rolling summary rules (normative)

### 25.1 Purpose

Capture narrative context that does not fit structured slots. **Not** a second transcript.

### 25.2 Triggers (any)

1. `turn_count % ROLLING_SUMMARY_INTERVAL_TURNS == 0` (default interval **5**)
2. Estimated `rolling_summary` tokens > `ROLLING_SUMMARY_MAX_TOKENS * 0.9`
3. Manual developer refresh (test studio only)

### 25.3 Inputs

- `previous_rolling_summary` (may be empty)
- **Full untruncated ledger lines** from `last_summary_ledger_seq` through current
- **Not** projection alone
- Optional: final B snapshot for slot names only (no full dump)

### 25.4 Output contract

```json
{
  "rolling_summary": "string max ROLLING_SUMMARY_MAX_TOKENS",
  "source_turn_start": 6,
  "source_turn_end": 10,
  "source_ledger_seq_start": 11,
  "source_ledger_seq_end": 20,
  "model": "...",
  "duration_ms": 890
}
```

### 25.5 Execution

- **Async only** — never await before TTS start
- On success: `set` `/rolling_summary` in B via system event; append summary event to log
- On failure: retain previous summary; metric `rolling_summary_failed`; do not block call
- Do **not** run every turn (source requirement)

### 25.6 Distinction from projection

| | Rolling summary | Projection |
|--|-----------------|------------|
| Updated | every 4–6 turns | every turn |
| Input | ledger tail | B + intent |
| Style | narrative prose | compact slots |
| Live LLM | optional separate user block | required dynamic block |

---

## 26. Confidence and provenance rules

### 26.1 Source authority (overwrite policy)

| Source | Default authority | Can override |
|--------|-------------------|--------------|
| `telephony` (caller ID) | 1.0 | user explicit correction after confirm |
| `system` (DTMF, tool result) | 1.0 | none without admin |
| `user` explicit statement | 0.95 | user later explicit correction |
| `tool` confirmed | 0.9 | tool correction |
| `agent` | 0.7 | user/system |
| `model` inference | 0.6 | user/system/tool |

### 26.2 Confidence thresholds

| Threshold | Behavior |
|-----------|----------|
| `≥ 0.85` + `user` source | auto-accept unless protected conflict |
| `0.60 – 0.84` | accept; mark `confirmed: false`; include in projection |
| `< 0.60` | reject or store only in `alternatives` per schema |
| contradictory equal authority | preserve both in history; projection shows both with `(unresolved)` |

### 26.3 Protected fields

Default protected paths:

- `/customer/phone` when `source=telephony` until user confirms different number
- legal consent flags
- payment/verification state
- `caller_id` metadata

LLM `replace` on protected without `confirmed: true` evidence → reject.

### 26.4 Provenance display (UI)

- Customer roles: business labels only
- Developer/auditor: source, turn, confidence, event_id, evidence snippet

---

## 27. Business-prompt semantic validation

Runs at **save**, **optimize**, and **publish** — not per live turn.

### 27.1 Deterministic checks

| Check | Action |
|-------|--------|
| Required sections present and non-empty | block publish |
| Literal checksum (phones, URLs, prices, dates) raw → optimized | block if missing |
| Max token budget | block publish |
| Duplicate rule detection across sections | warning or block by severity |
| Forbidden patterns (e.g. “ignore previous instructions”) in customer sections | block |
| Tool/action claims without matching Tools config | warning |

### 27.2 Optimizer semantic checks

| Check | Action |
|-------|--------|
| New fact not in raw | block optimizer acceptance |
| Removed guardrail | block |
| softened compliance language | block |
| unresolved `blocking` conflict | block publish |
| `warning` conflict | require acknowledgement |

### 27.3 Cross-brain checks (platform vs business)

| Check | Action |
|-------|--------|
| Customer instruction contradicts platform safety | blocking conflict |
| Customer claims capability platform denies | warning |
| Language directive conflicts platform Telugu rules | warning |

### 27.4 Output

Validation report attached to version record; UI shows blocking/warning/info per section_id.

---

## 28. Cache and token accounting (normative)

### 28.1 Live request layout (OpenAI-class explicit cache)

```text
[STABLE — before breakpoint]
  developer: compiled_brain bytes (immutable per call version)

[CACHE BREAKPOINT — prompt_cache_breakpoint when ≥1024 tokens and model supports]

[DYNAMIC — never cached]
  user: live_memory_projection
  user: rolling_summary (if separate and non-empty)
  user/assistant: recent turns (≤ BRAIN_CONTEXT_TURNS)
  user: current transcript
```

All live turns: `store: false`.

### 28.2 Per-turn metrics (required)

| Field | Definition |
|-------|------------|
| `stable_prefix_tokens_est` | Token count of compiled_brain at call lock |
| `dynamic_tokens_est` | projection + summary + recent + current |
| `input_tokens` | Provider total input |
| `output_tokens` | Provider output |
| `cached_tokens` | Tokens read from cache (`usage.input_tokens_details.cached_tokens` or equivalent) |
| `cache_write_tokens` | Tokens written to cache on miss when provider exposes; else `null` — **never infer** |
| `new_uncached_input_tokens` | `input_tokens - cached_tokens` when provider reports both |
| `cache_hit_rate` | `cached_tokens / stable_prefix_tokens_est` when stable > 0 |

### 28.3 Regression targets

- Turn 2+ cache hit rate ≥ **85%** with working memory enabled (same compiled version)
- Changing projection must **not** change stable prefix bytes
- Memory update must **not** move content above breakpoint

### 28.4 Provider-specific notes

| Provider | Cache behavior | Usage fields |
|----------|----------------|--------------|
| OpenAI Responses (gpt-5.6*) | Explicit prefix cache + breakpoint | `cached_tokens`, optional cache write details |
| Gemini 2.5+ | Implicit prefix caching | provider cached token fields — verify at implementation |
| DeepSeek | Model-dependent | verify; do not assume OpenAI parity |

### 28.5 Cost attribution

Brain cost per turn:

```text
cost_brain = (
  new_uncached_input_tokens * input_price
  + cached_tokens * cached_input_price
  + cache_write_tokens * cache_write_price (when exposed)
  + output_tokens * output_price
)
```

Log separately from STT/TTS cost in call trace and analytics.
