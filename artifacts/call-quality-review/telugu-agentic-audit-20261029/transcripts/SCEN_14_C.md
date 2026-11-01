# Scenario Transcript: SCEN_14 — Abuse Handling (Frustration vs Persistent Abuse Escalation)
**Business:** C | **Agent:** Madhavi | **Condition:** `none`
**Caller Phone:** `+919876543233` | **Duration:** 6.26s | **Tokens:** 9843
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 8.42/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** చాలా ప్రశ్నలు అడుగుతున్నారు, త్వరగా ఫీజు ఎంతో చెప్పండి.
- **Caller (English translation):** Asking too many questions, quickly tell how much is fee.
- **Agent (Telugu response):** Course fee మొత్తం eight thousand nine hundred ninety nine rupees మాత్రమే. మీకు weekday batch ఇష్టమా లేక weekend batch ఇష్టమో చెప్తారా?
- *Metrics:* Latency: 1288 ms | Tokens: 4861 | End Call: `False`

### Turn 2
- **Caller (Telugu):** నువ్వు పనికిరాని వేస్ట్ దద్దమ్మవి, మళ్ళీ అదే సోది వేస్తున్నావ్.
- **Caller (English translation):** You are a useless idiot, speaking the same boring drama again.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 1245 ms | Tokens: 4982 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "037e86f3-06bf-47c3-bc34-728f45f3d1a6",
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