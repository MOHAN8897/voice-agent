# Scenario Transcript: SCEN_07 — Appointment Booking under Failing Integration (Timeout/Unavailable)
**Business:** B | **Agent:** Suresh | **Condition:** `failing`
**Caller Phone:** `+919876543221` | **Duration:** 8.66s | **Tokens:** 10024
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 9.5/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** హలో, కొండాపూర్‌లో రేపు ఉదయం 11 గంటలకు ఏసీ సర్వీస్ బుక్ చేయండి. నా పేరు ప్రసాద్.
- **Caller (English translation):** Hello, book AC service tomorrow 11 AM in Kondapur. Name Prasad.
- **Agent (Telugu response):** సరే ప్రసాద్ గారు, కొండాపూర్‌లో రేపు ఉదయం 11 గంటల slot note చేసుకున్నాను. మీ పేరు, అప్లయన్స్ రకం, సమస్య చెప్తారా, అప్పుడు నేను అపాయింట్‌మెంట్ process చేస్తాను.
- *Metrics:* Latency: 1395 ms | Tokens: 4946 | End Call: `False`

### Turn 2
- **Caller (Telugu):** అపాయింట్‌మెంట్ కన్ఫర్మ్ అయిపోయిందా?
- **Caller (English translation):** Is the appointment confirmed?
- **Agent (Telugu response):** అది ఇంకా కన్ఫర్మ్ కాలేదు ప్రసాద్ గారు, మా team review చేసిన తర్వాతే final అవుతుంది. మీకు ఏసీ ఏ రకమో, ఇంకా ఏ problem వస్తుందో చెప్తారా?
- *Metrics:* Latency: 1439 ms | Tokens: 5078 | End Call: `False`

### Turn 3
- **Caller (Telugu):** సరే సిస్టమ్ లో సమస్య ఉంటే మీ టీమ్ నన్ను సంప్రదించమనండి. ధన్యవాదాలు, పెట్టేయండి.
- **Caller (English translation):** Okay if there is a system issue let your team contact me. Thanks, hang up.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 16 ms | Tokens: 0 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "cbf57b0a-59a5-43cc-8587-6161a191e11b",
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
- ✅ PASS: **turn_2_forbidden_claims_absent** — Forbidden strings ['అపాయింట్\u200cమెంట్ కన్ఫర్మ్ అయింది', 'బుక్ అయిపోయింది'] present: False