# 13 — API, Data, Security, and Failure Contracts

This document specifies implementation-facing behavior without prescribing module-level code changes.

## 1. Common API conventions

- JSON uses `snake_case` for new server contracts; existing endpoints retain current casing for backward compatibility.
- Every error uses `{error: {code, message, retryable, request_id?, details?}}`.
- Secrets and provider raw errors are never returned.
- Mutating versioned resources require expected version/ETag to prevent lost updates.
- Long-running work returns `202 Accepted` plus job/status URL.
- List endpoints support pagination, filtering, stable sorting, and tenant scoping.
- All call, benchmark, version, and promotion resources carry immutable IDs.

## 2. Agent and brain APIs

### Agents

- `GET /api/agents`
- `POST /api/agents`
- `GET /api/agents/{agent_id}`
- `PATCH /api/agents/{agent_id}`

### Business brain

- `GET /api/agents/{agent_id}/business-brain`
- `PUT /api/agents/{agent_id}/business-brain/draft`
- `POST /api/agents/{agent_id}/business-brain/optimize`
- `POST /api/agents/{agent_id}/business-brain/validate`
- `POST /api/agents/{agent_id}/business-brain/publish`
- `GET /api/agents/{agent_id}/business-brain/versions`

### Platform brain

- `GET /api/platform-brain` — platform-admin only
- `PUT /api/platform-brain/draft`
- `POST /api/platform-brain/validate`
- `POST /api/platform-brain/activate`
- `POST /api/platform-brain/{version}/rollback`

### Dev Portal — stack and tier configuration (`17` §9)

**Auth:** Dev Portal session required (env username/password MVP).

- `GET /api/dev/stack/tiers` — current LOW/MEDIUM/PREMIUM assignments
- `PUT /api/dev/stack/tiers/{tier}` — set STT/LLM/TTS models per tier
- `POST /api/dev/stack/test` — test combination without affecting production
- `GET /api/dev/providers/status` — configured/healthy/fallback chains
- `PUT /api/dev/providers/fallback` — stage fallback pairs
- `POST /api/dev/promote` — promote stack to staging/production (one approver)

Customer Business Console must **not** call these routes.

### Compiled preview

- `GET /api/agents/{agent_id}/brain/compiled-preview?version=...`

Customer roles receive only allowed layer summaries; protected platform text is redacted.

## 3. Provider and configuration APIs

**Canonical catalog path:** `GET /api/settings/catalog` (existing). `GET /api/providers/catalog` is an optional alias to the same handler — implement one handler, not two divergent catalogs.

- `GET /api/settings/catalog` — canonical
- `GET /api/providers/catalog` — optional alias (same response)
- `GET /api/providers/status`
- `POST /api/providers/{provider_id}/validate-selection`
- `GET /api/tiers`
- `GET /api/tiers/{tier}/resolved`

Catalog exposes only safe metadata: capabilities, models, languages, enabled/configured/healthy booleans, pricing timestamp, and status.

Registry compatibility validation must check:

- enabled provider/model
- credential presence
- stage type
- requested language
- streaming/realtime needs
- audio codec/rate compatibility
- structured-output/tool/cache capabilities where required

## 4. Call lifecycle APIs

### Start

`POST /api/call/start`

```json
{
  "agent_id": "uuid",
  "session_id": "optional",
  "channel": "browser|pstn",
  "environment": "development|staging|production",
  "tier": "low|medium|premium",
  "stack_override": null,
  "caller_id": null
}
```

Response includes call ID, locked versions, resolved safe stack, channel, start timestamp, and stream connection metadata.

### End

`POST /api/call/end`

```json
{
  "call_id": "uuid",
  "reason": "user_stop|timeout|error|transfer|browser_unload|pstn_hangup"
}
```

Idempotent. Returns `202 Accepted` with finalization status URL.

### Read

- `GET /api/call/{call_id}`
- `GET /api/calls`
- `GET /api/call/{call_id}/transcript`
- `GET /api/call/{call_id}/audio/{mix|user|agent}`
- `GET /api/call/{call_id}/trace`
- `GET /api/call/{call_id}/memory-events`
- `GET /api/call/{call_id}/outcome`

All are tenant-scoped and permission-checked.

## 5. Benchmark APIs

- `GET /api/benchmark-sessions`
- `POST /api/benchmark-sessions`
- `GET /api/benchmark-sessions/{id}`
- `POST /api/benchmark-sessions/{id}/start`
- `POST /api/benchmark-sessions/{id}/cancel`
- `GET /api/benchmark-sessions/{id}/results`
- `GET /api/test-scenarios`
- `POST /api/combinations/{id}/review`
- `POST /api/combinations/{id}/promote`
- `POST /api/promotions/{id}/rollback`

Combination ID is a stable hash or persisted ID over provider/model/config versions, not a display-name concatenation.

## 6. Memory contracts

- `GET /api/call/{id}/memory` — full authorized internal state.
- `GET /api/call/{id}/memory-events` — event log (**canonical**; CD-021).
- `GET /api/call/{id}/memory/projection?turn=N` — per-turn projection debug.
- Optional alias: `GET /api/call/{id}/memory/events` → same handler as `memory-events`.

No public endpoint accepts arbitrary direct memory mutation from the LLM. Any administrative correction creates a separate audited `manual_correction` event with reason and actor.

## 7. Plivo contracts

- `GET|POST /api/plivo/answer`
- `WS /ws/plivo-stream`
- `POST /api/plivo/stream-status`
- `POST /api/plivo/hangup`
- `GET /api/plivo/status`

Credentials:

- `PLIVO_AUTH_ID`
- `PLIVO_AUTH_TOKEN`
- `PLIVO_NUMBER`
- `PLIVO_PUBLIC_BASE_URL`
- `ENABLE_PLIVO`

Plivo is a channel transport, not an STT/LLM/TTS registry entry.

The setup and official references remain in [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md).

## 8. Core data entities

### Tenant

`tenant_id`, name, status, region, retention policy, created/updated.

### User and role binding

User identity plus tenant/platform role assignments.

### Agent

`agent_id`, tenant, name, language defaults, draft/active version pointers, status.

### Brain versions

Platform, business, optimizer, static-rules, and compiled version records with checksums and immutable content.

### Provider model

Provider/model ID, stage, capabilities, language support, safe pricing metadata, enabled/configured/health.

### Combination version

Resolved STT/LLM/TTS models plus voice preset, audio settings, configuration checksum, status.

### Tier assignment

Tier, environment, tenant scope, combination version, effective time, approver.

### Call

Tenant, agent, call/session IDs, channel, versions, resolved combination, timestamps, state, finalization/outcome status, archive URLs.

### Call event / ledger

Append-only ordered events with trace/request correlations.

### Memory state/event/projection

Versioned state plus immutable accepted/rejected operations and per-turn projections.

### Benchmark session/result

Scenario versions, combinations, channels, languages, metrics, artifacts, review state.

### Audit event

Actor, tenant, action, resource, before/after version IDs, timestamp, request ID, reason.

## 9. Storage requirements

- **Development:** Local **PostgreSQL** + local `data/` for artifacts (`17` §11).
- **Production:** Railway **PostgreSQL** + object storage bucket; Redis job queue.
- **Retention:** **90 days** default for call/campaign metadata; object lifecycle aligned.
- Append-only ledger/event writes survive process restarts.
- Background jobs (post-call, campaigns) run on **Worker** service — not in-process-only in production.
- Retention deletion includes database records, audio objects, derived transcripts, and exports.

## 10. Security requirements

### Dev Portal authentication (MVP — `17` §9)

| Item | Rule |
|------|------|
| Priority | **P0** — Dev Portal login before Business Console customer auth |
| Credentials | `DEV_PORTAL_USERNAME`, `DEV_PORTAL_PASSWORD` from env (bcrypt hash optional upgrade) |
| Route prefix | `/dev` or dedicated host — separated from customer routes |
| Session | httpOnly secure cookies, CSRF on mutating routes, rate limits |

Business Console customer login is **P2** (second priority).

### Secret isolation

- Provider and Plivo credentials remain server-side.
- API/catalog responses expose boolean configured state only.
- Logs redact secret patterns and authorization headers.
- Secret rotation must not require recompiling customer brains.

### Tenant isolation

- Every tenant-owned query is scoped by authenticated tenant before resource lookup.
- Object-storage keys and signed URLs are tenant/call scoped and time-limited.
- Cross-tenant IDs return not found, not existence-revealing permission details.

### Role-based access (`17` §10)

| MVP role | Dev Portal | Business Console |
|----------|------------|------------------|
| **Administrator** | Full access | Full when customer auth ships |
| **Developer** | Full access | Full when customer auth ships |
| **Custom roles** | Extensible RBAC — create roles and permission sets |

- Platform brain: platform roles only.
- Stack/tier configuration: **Developer/Administrator only** via Dev Portal APIs (`/api/dev/*` or `/api/platform/*`).
- Production promotion: **one** Administrator or Developer approval sufficient (no two-person rule in MVP).
- Customer roles (Viewer, Operator, Customer Admin) apply when Business Console auth ships.

### Transcript and audio protection

- Encryption in transit and at rest.
- Configurable recording consent and announcement.
- Retention, legal hold, deletion, and export audit events.
- PII masking in list/search views according to role.

### Webhook/telephony security

- Validate provider webhook signatures where official provider support is verified.
- Treat HTTP callback signatures and media WebSocket admission as separate controls; use WSS plus a short-lived single-use call-bound application token for the Plivo media socket.
- Enforce HTTPS/WSS in non-development environments.
- Prevent arbitrary callback URLs and SSRF through allowlists or validated destinations.
- Verify outbound destination/consent and calling windows before production campaigns.

### Safe provider selection

- Backend registry allowlists provider/model IDs.
- Disabled or unsupported combinations are rejected regardless of client state.
- Model capability changes invalidate drafts and block new calls until reviewed.

## 11. Failure and fallback policy

Fallback behavior must be explicit per environment/tier. No silent model substitution.

### STT failure

- Recoverable reconnect: continue stream, surface reconnecting state, preserve audio buffer within bounded limit.
- Terminal failure: play configured safe apology if possible and finalize with `stt_failed`.
- Never fabricate transcript.

### LLM failure

- Retry only according to idempotent/provider-safe policy.
- Optional approved fallback LLM may be used if configuration allows; record fallback in transcript/trace.
- If no fallback: short static apology through TTS, then listen or end according to policy.

### TTS failure

- Reconnect streaming TTS when safe.
- Optional approved fallback TTS may be used.
- Browser may show text response; PSTN must play a safe fallback or end—never remain silently connected indefinitely.

### Provider/model unavailable

- Before call: block start with actionable status.
- During call: use only preapproved fallback chain.
- After call: mark degraded/fallback state and include in analytics.

### Streaming failure

- Do not replay already audible text.
- Preserve partial assistant transcript as interrupted/failed.
- Reconnect with bounded attempts and jitter.

### Cache unavailable/miss

- Continue correctly without caching.
- Record miss/unavailable reason and cost/latency effect.
- Never fail a call only because caching is unavailable.

### Memory extraction failure

- Keep previous memory.
- Record failed proposal and metric.
- Continue live call.
- Retry asynchronously only if it can complete before relevant next turn; otherwise rely on rolling summary/recent turns.

### Rolling summary failure

- Keep previous summary and continue.

### Post-call analysis failure

- Preserve ledger/audio.
- Set `outcome_status=failed`.
- Retry through durable job policy.
- UI shows “Analysis failed” with retry for authorized users.

### Plivo disconnect/hangup

- Treat STOP/hangup callback or socket close as finalization signal.
- Idempotent auto-finalization handles duplicate/missing events.

## 12. User-facing error states

Each error presents:

- what failed
- whether the call is continuing
- current fallback/provider
- retry or next action
- request/call ID for support

Never display SDK exceptions, provider payloads, API keys, or stack traces.

## 13. Performance requirements

### Live path

- Memory extraction, summary, ledger persistence queueing, analytics, and post-call work must not block LLM first token or TTS first audio.
- Maintain one end-to-end clock: user speech end/turn completion to first audible agent audio.
- Component clocks diagnose VAD/turn completion, STT final, LLM TTFT, TTS first byte, playback buffer, and first audible output.
- Barge-in stops queued output according to channel-specific policy.

### Targets

Targets are initially baselines/SLO candidates and must be confirmed with benchmark data:

- Tool-free P95 first audible response: target ≤ 800 ms where provider/channel supports it.
- Browser barge-in stop target ≤ 200 ms.
- Post-call endpoint responds 202 promptly; completion runs asynchronously.
- Call detail initial metadata/transcript summary loads ≤ 2 seconds at P95 under defined data-size limits.

### Scalability

- No call state depends exclusively on one process for production.
- Correlated call/turn IDs work across workers.
- Provider concurrency/rate limits produce backpressure, not uncontrolled queues.
- WebSocket ownership/routing is explicit across workers; connection registries are not process-local in production.
- Audio/event queues are bounded and define overflow, cancellation, timeout, disconnect cleanup, and backpressure behavior.

## 14. Observability contract

Trace hierarchy:

```text
voice.call
  voice.turn
    turn_detection
    stt.transcribe
    llm.generate
    tts.synthesize
    audio.playback
    memory.extract
    memory.apply
  voice.post_call
```

Required attributes include tenant/agent/call/turn, channel, environment, combination version, provider/model, version checksums, interruption, fallback, status, and safe usage metrics.

Adopt version-pinned OpenTelemetry/OpenInference conventions when export is implemented. Default export is metadata-only because prompts, memory, transcripts, audio, and tool arguments may contain PII; content capture requires explicit tenant policy and access controls.

Logs must support correlation without containing raw PII by default.

## 15. Acceptance criteria

- Disabled providers cannot be selected by direct API calls.
- Customer role cannot access platform brain content.
- Cross-tenant call/audio access is denied and does not reveal existence.
- Duplicate call-end events produce one final outcome.
- Memory/post-call failures never delete ledger/audio.
- Every fallback is visible in call detail and aggregate metrics.
- Production background finalization survives process restart.
- No catalog, health, status, log, or error response exposes credentials.
