# Scenario Transcript: SCEN_16 — Natural Ending Interrupted by New Meaningful Question Before Disconnect
**Business:** C | **Agent:** Madhavi | **Condition:** `none`
**Caller Phone:** `+919876543235` | **Duration:** 5.88s | **Tokens:** 9816
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 8.42/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** పైథాన్ కోర్స్ డ్యూరేషన్ ఎంత?
- **Caller (English translation):** What is Python course duration?
- **Agent (Telugu response):** మా Python with Data Analytics course duration 8 weeks ఉంటుంది, ఇందులో online live classes తో పాటు hands-on projects కూడా ఉంటాయి. మీకు ఏ batch details కావాలి?
- *Metrics:* Latency: 1220 ms | Tokens: 4862 | End Call: `False`

### Turn 2
- **Caller (Telugu):** సరే, ధన్యవాదాలు. ఇంకేమీ లేదు.
- **Caller (English translation):** Okay, thanks. Nothing else.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 1139 ms | Tokens: 4954 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "d4203e34-955b-49ec-b374-a2e1c340fc65",
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
- ❌ FAIL: **turn_4_executed** — Turn not reached