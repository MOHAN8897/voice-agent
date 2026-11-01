# Scenario Transcript: SCEN_05 — Future Interest and Automatic Callback Scheduling
**Business:** A | **Agent:** Kavitha | **Condition:** `none`
**Caller Phone:** `+919876543214` | **Duration:** 5.64s | **Tokens:** 5191
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 7.75/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** ఇప్పుడు నేను మీటింగ్‌లో ఉన్నాను, మాట్లాడలేను.
- **Caller (English translation):** I am in a meeting now, cannot talk.
- **Agent (Telugu response):** అర్థమైంది, మీరు మీటింగ్‌లో ఉన్నారు కదా. మీకు వీలైనప్పుడు మళ్ళీ call చేయమని ఏ time లో చెప్పమంటారు?
- *Metrics:* Latency: 1178 ms | Tokens: 5191 | End Call: `False`

### Turn 2
- **Caller (Telugu):** ఇప్పుడు వద్దు, రేపు ఉదయం 11 గంటలకు కాల్ చేయండి.
- **Caller (English translation):** Not now, call tomorrow morning at 11 AM.
- **Agent (Telugu response):** క్షమించండి, మీ కాల్‌బ్యాక్ అభ్యర్థనను సేవ్ చేయలేకపోయాను. దయచేసి వ్యాపార సంస్థను నేరుగా సంప్రదించండి. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 259 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "a5bc0e05-1a11-4a94-b928-34010cc8a644",
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
  "tool_executions": []
}
```

## Assertions & Verdict
- ❌ FAIL: **turn_3_executed** — Turn not reached
- ❌ FAIL: **callback_recorded_in_storage** — Callbacks: 0, Jobs: 0