# Scenario Transcript: SCEN_10 — Callback Request under Manual Policy (Requires Review)
**Business:** B | **Agent:** Suresh | **Condition:** `none`
**Caller Phone:** `+919876543224` | **Duration:** 5.23s | **Tokens:** 4907
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 7.75/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** ప్రస్తుతం బిజీగా ఉన్నాను, తర్వాత మాట్లాడతాను.
- **Caller (English translation):** Currently busy, will talk later.
- **Agent (Telugu response):** సరే, అర్థమైంది. మీకు వీలైనప్పుడు మళ్ళీ call చేయమని చెప్పండి, లేదా ఎప్పుడు మాట్లాడాలో ఆ time చెప్పండి.
- *Metrics:* Latency: 1220 ms | Tokens: 4907 | End Call: `False`

### Turn 2
- **Caller (Telugu):** ఈరోజు సాయంత్రం ఆరు గంటల తర్వాత కాల్ చేయండి.
- **Caller (English translation):** Call after 6 PM today.
- **Agent (Telugu response):** క్షమించండి, మీ కాల్‌బ్యాక్ అభ్యర్థనను సేవ్ చేయలేకపోయాను. దయచేసి వ్యాపార సంస్థను నేరుగా సంప్రదించండి. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 308 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "ebb6a131-5061-4445-b543-241c2ffcc0eb",
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
- ❌ FAIL: **callback_recorded_in_storage** — Callbacks: 0, Jobs: 0