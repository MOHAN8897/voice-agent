# 18 — Outbound Campaigns and Dialing

Normative for outbound calling, campaign management, and telephony automation.  
Product decision source: [`17-product-decisions.md`](./17-product-decisions.md) §7–8.

**Priority:** Outbound over inbound for product value. Plivo is transport — see [09-plivo-telephony-integration.md](./09-plivo-telephony-integration.md).

---

## 1. Goals

- Let business owners run **outbound campaigns** with the same voice agent stack as inbound/browser tests.
- Enforce **consent, DNC, and calling windows** before dial.
- Support **retry, timeout, and engagement** rules when callee does not answer or disconnects early.
- Record campaign metrics separately from ad-hoc inbound calls.

---

## 2. Entities

| Entity | Description |
|--------|-------------|
| `campaign` | Scheduled outbound program bound to `agent_id`, number pool, and audience |
| `campaign_contact` | One callee row (phone, consent state, DNC flags, attempt count) |
| `campaign_run` | Execution instance (scheduled or manual start) |
| `dial_attempt` | One outbound attempt → creates `call_id` on connect |

---

## 3. Campaign configuration

```json
{
  "campaign_id": "uuid",
  "agent_id": "uuid",
  "tenant_id": "uuid",
  "environment": "staging|production",
  "name": "Q1 outbound",
  "from_number_id": "uuid",
  "status": "draft|scheduled|running|paused|completed|cancelled",
  "schedule": {
    "start_at": "ISO8601",
    "end_at": "ISO8601",
    "timezone": "Asia/Kolkata",
    "calling_windows": [
      { "days": ["mon","tue","wed","thu","fri"], "start": "09:00", "end": "19:00" }
    ]
  },
  "retry_policy": {
    "max_attempts": 3,
    "retry_delay_minutes": [15, 60, 1440],
    "retry_on": ["no_answer", "busy", "failed", "short_engagement"]
  },
  "engagement_rules": {
    "min_duration_sec_to_count_connect": 5,
    "short_call_sec": 10,
    "mark_short_as": "short_engagement"
  },
  "consent_policy": {
    "require_consent_record": true,
    "consent_source_field": "campaign_contact.consent_status"
  },
  "dnc_policy": {
    "respect_global_dnc": true,
    "respect_campaign_dnc": true
  },
  "compiled_brain_version": "locked at campaign start",
  "resolved_stack": { "stt", "llm", "tts", "tier" }
}
```

---

## 4. Dial flow

```text
Worker polls scheduled campaigns
  → filter contacts (consent, DNC, window, max attempts)
  → Plivo outbound API initiate call
  → on answer: POST /api/call/start { channel: pstn, direction: outbound, campaign_id, ... }
  → same live_turn_orchestrator path as inbound
  → on end: disposition + campaign_contact state update + retry scheduling
```

| Event | System action |
|-------|----------------|
| No answer | Increment attempts; schedule retry per policy |
| Busy | Same as no answer |
| Short engagement (&lt; threshold) | Optional retry; metric `short_engagement` |
| Callee hangup early | Record partial ledger; disposition if possible |
| Agent completed goal | `converted` or campaign-specific disposition |
| DNC hit | Skip; log `dnc_blocked` |
| Outside window | Queue for next window |

---

## 5. APIs (normative)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/campaigns` | List campaigns |
| `POST` | `/api/campaigns` | Create draft |
| `GET` | `/api/campaigns/{id}` | Detail + stats |
| `PATCH` | `/api/campaigns/{id}` | Update draft |
| `POST` | `/api/campaigns/{id}/contacts/import` | CSV/API import |
| `POST` | `/api/campaigns/{id}/start` | Start or schedule |
| `POST` | `/api/campaigns/{id}/pause` | Pause running |
| `POST` | `/api/campaigns/{id}/cancel` | Cancel |
| `GET` | `/api/campaigns/{id}/analytics` | Attempts, connects, dispositions, cost |
| `GET` | `/api/dnc` | Tenant DNC list |
| `POST` | `/api/dnc` | Add number to DNC |

Worker processes: `campaign_dial_queue` via Redis (see `06` §16).

---

## 6. Consent and compliance

| Rule | Detail |
|------|--------|
| Production outbound | Contact must have `consent_status=granted` or equivalent proof field |
| Calling windows | Enforce tenant timezone windows server-side |
| DNC | Global tenant DNC + per-contact flags; never dial blocked numbers |
| Recording | Follow `17` §7 — production consent before recorded PSTN |
| Opt-out mid-call | Callee opt-out → add DNC + end call |

---

## 7. Analytics

Per campaign and fleet:

- attempts, connects, connect rate
- average talk time, short-call rate
- disposition breakdown
- retry exhaustion count
- provider fallback rate
- cost estimate (Plivo + STT/LLM/TTS)

---

## 8. MVP acceptance criteria

- [ ] Create campaign bound to agent + outbound number
- [ ] Import contacts with consent flag
- [ ] Schedule within calling window; block outside window
- [ ] Outbound dial creates `call_id` and full ledger
- [ ] Retry on no-answer per policy
- [ ] DNC blocks dial
- [ ] Campaign pause stops new dials
- [ ] Analytics page shows attempt/connect/disposition counts
