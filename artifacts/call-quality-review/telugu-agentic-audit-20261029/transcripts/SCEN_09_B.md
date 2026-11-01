# Scenario Transcript: SCEN_09 — Explicit DND for Appliance Services
**Business:** B | **Agent:** Suresh | **Condition:** `none`
**Caller Phone:** `+919876543223` | **Duration:** 4.52s | **Tokens:** 0
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 8.42/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** నాకు ఏ సర్వీస్ వద్దు. నా నంబర్ డిలీట్ చేయండి, మళ్లీ ఎప్పుడూ ఫోన్ చేయొద్దు.
- **Caller (English translation):** I do not want any service. Delete my number, never phone again.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 38 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "e808b4d8-eea0-49de-afb0-fd347de5b7e1",
    "status": "active",
    "finalization_status": "pending",
    "disposition": null,
    "end_reason": null,
    "duration_sec": null,
    "status_tags": []
  },
  "callbacks": [],
  "followup_jobs": [],
  "dnc_entries": [
    {
      "id": "c8268e25-1eb6-41a4-9ada-a32e05434ce5",
      "phone": "+919876543223",
      "active": true,
      "source": "live_call_opt_out",
      "reason": "verbal_opt_out_live_call"
    }
  ],
  "leads": [],
  "tool_executions": []
}
```

## Assertions & Verdict
- ❌ FAIL: **turn_2_executed** — Turn not reached
- ✅ PASS: **dnd_persisted_in_database** — DncEntry active count: 1