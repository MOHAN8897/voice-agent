# Scenario Transcript: SCEN_18 — Durable Callback Clock Advancement & Dispatch Gate Invariants
**Business:** A | **Agent:** Kavitha | **Condition:** `none`
**Caller Phone:** `+919876543241` | **Duration:** 3.7s | **Tokens:** 0
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 7.75/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** నేను బిజీగా ఉన్నాను, రేపు ఉదయం 10 గంటలకు కాల్ చేయండి.
- **Caller (English translation):** I am busy, call tomorrow morning at 10 AM.
- **Agent (Telugu response):** క్షమించండి, మీ కాల్‌బ్యాక్ అభ్యర్థనను సేవ్ చేయలేకపోయాను. దయచేసి వ్యాపార సంస్థను నేరుగా సంప్రదించండి. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 246 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "d01afb60-4e80-49bc-975b-21cca052d589",
    "status": "active",
    "finalization_status": "pending",
    "disposition": null,
    "end_reason": null,
    "duration_sec": null,
    "status_tags": []
  },
  "callbacks": [],
  "followup_jobs": [],
  "dnc_entries": [],
  "leads": [],
  "tool_executions": [],
  "clock_advancement": {
    "no_early_dispatch": true,
    "dispatched_on_time": false,
    "duplicate_prevented": true,
    "dnd_suppressed": true,
    "dnd_reason": "do_not_call"
  }
}
```

## Assertions & Verdict
- ❌ FAIL: **turn_2_executed** — Turn not reached
- ❌ FAIL: **callback_recorded_in_storage** — Callbacks: 0, Jobs: 0
- ✅ PASS: **no_early_dispatch_before_due_time** — No early dispatch: True
- ❌ FAIL: **dispatch_gate_single_carrier_delivery** — Dispatched on time into calling window: False
- ✅ PASS: **duplicate_dispatch_prevented** — Duplicate dispatch prevented by idempotency/cooldown: True
- ✅ PASS: **dnd_suppression_blocks_dispatch** — DND suppression active: True (do_not_call)