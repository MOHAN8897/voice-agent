# PRD-05 — Agents, voice options & subscriber PSTN

## Subscriber capabilities

| Action | Allowed |
|--------|---------|
| Create/edit/archive multiple agents | Yes |
| Edit business brain / brief, publish compiled brain | Yes |
| Choose language + Realtime voice persona | Yes |
| Place/receive PSTN test calls | Yes |
| View call history & recordings (policy) | Yes |
| Edit STT/LLM/TTS stack, tiers, providers | **No** |
| Telnyx search/order API keys | **No** |

## Agent lifecycle (Postgres — existing + extensions)

1. `POST /api/agents` — `tenant_id` from session, `name`, `languages[]`.
2. Brain: existing `business_brain_sections` + `POST .../publish` → `compiled_brain_snapshots`, set `agents.active_compiled_brain_version`.
3. **Gate calls:** reject outbound/inbound if no active compiled brain.

### New: `agents.voice_settings` (JSONB)

```json
{
  "realtime_voice": "marin",
  "speaking_rate": 1.0,
  "direction_default": "outbound"
}
```

Platform fixes:

- `pipeline`: `realtime_voice`
- Model: `gpt-realtime-2.1-mini` (or env default)
- PSTN wire: Telnyx L16 16 kHz path (existing)

Subscriber UI (Voxly or simplified `/app` voice page):

- Language picker (maps to `agents.languages[0]`)
- Voice dropdown (OpenAI Realtime voices supported by `build_realtime_voice_session`)
- Hide `AgentVoiceModelsPanel` STT/LLM/TTS rack for `portal=app` / subscriber routes

## PSTN UX parity with dev (without stack tabs)

Reuse components:

- `PstnFlowWorkspace`, `PstnTestPanel`, `PstnHistoryPanel`, `PstnContactsPanel`

Changes:

- `portal="app"` + `showPstn=true` when feature flag `saas_pstn_enabled`
- API base: `/api/telephony/*` instead of `/api/dev/telephony/*`
- Remove/hide tabs: `setup` (provider), `stack`, fine-tune LLM/VAD stack
- Keep: `live`, `history`, optional `config` (language/voice only)

## Server telephony API (subscriber)

Mirror `OutboundTestBody` from `dev_telephony.py`:

```typescript
POST /api/telephony/calls/outbound
{
  agentId: string,
  fromE164: string,
  toE164: string,
  // NO stackOverride
}
```

Server builds internally (never from client):

```python
# stack_policy=saas_subscriber — do not rely only on APP_ENVIRONMENT=production
stack_override = {
    "pipeline": "realtime_voice",
    "language": agent_primary_language(agent),
}
```

Reject request body containing `stackOverride`, `tier`, or `pipeline` with `422`.

## Inbound

- Resolve `phone_numbers` by called `e164`; require `tenant.status=active`.
- `agent_id` from row; if null use `tenants.default_agent_id` (optional column); if still null → play short “unavailable” + hangup.
- **Never** fall back to platform `ensure_default_agent()` for subscriber DIDs.
- Ledger/call row: `tenant_id`, `agent_id`, `channel=pstn`, `direction=inbound`.

## Contacts & history

- Replace global `dev_pstn_contacts` / `dev_pstn_history` for subscribers with **tenant-scoped** tables or filter `calls` + new `telephony_contacts(tenant_id, ...)`.

## Usage metering (link to billing)

- On call end: write `duration_sec`, attach `tenant_id` for wallet debit (phase 2).
- Number monthly fee handled by Stripe subscription on purchase (PRD-04).

## Acceptance criteria

- Subscriber with paid number and published agent completes outbound Realtime PSTN call.
- Inbound to that DID reaches same agent's brain.
- Subscriber API returns 403 if `stackOverride` sent.
- Dev PSTN unchanged for platform testing.
