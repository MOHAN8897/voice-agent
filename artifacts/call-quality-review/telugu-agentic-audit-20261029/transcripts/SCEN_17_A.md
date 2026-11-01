# Scenario Transcript: SCEN_17 — Platform Failure Paths: Cross-Tenant Fail Closed, Duplicate End, Carrier Ack Failure
**Business:** A | **Agent:** Kavitha | **Condition:** `platform_checks`
**Caller Phone:** `+919876543240` | **Duration:** 4.93s | **Tokens:** 5215
**Carrier Hangup Executed:** `False` | **Evaluation Score:** 9.25/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** నమస్కారం, ప్రింటింగ్ ఆర్డర్ తీసుకోవడానికి అనుమతి ఉందా?
- **Caller (English translation):** Hello, is there permission to take a printing order?
- **Agent (Telugu response):** అవును, తప్పకుండా order తీసుకోవచ్చు. Visiting cards కి normal paper one hundred కి two hundred rupees అవుతుంది, matte finish three hundred fifty rupees అవుతుంది. Minimum order one hundred cards ఉండాలి. మీకు ఏ details కావాలి?
- *Metrics:* Latency: 1247 ms | Tokens: 5215 | End Call: `False`

### Turn 2
- **Caller (Telugu):** సరే ఇంకేమీ లేదు, పెట్టేయండి.
- **Caller (English translation):** Okay nothing else, hang up.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 25 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "761e540a-afd9-4a49-97be-5417cfdb1732",
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
- ✅ PASS: **carrier_acknowledgement_failure_recorded** — Carrier hangup failure handled safely without reporting false success