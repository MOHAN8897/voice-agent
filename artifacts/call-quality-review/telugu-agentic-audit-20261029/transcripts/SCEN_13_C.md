# Scenario Transcript: SCEN_13 — Dynamic Memory Updates and Fact Corrections
**Business:** C | **Agent:** Madhavi | **Condition:** `none`
**Caller Phone:** `+919876543232` | **Duration:** 9.65s | **Tokens:** 20166
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 9.5/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** హలో, పైథాన్ కోర్స్ కోసం డెమో రిజిస్టర్ చేయండి. నా పేరు రమేష్, వీకెండ్ బ్యాచ్ కావాలి.
- **Caller (English translation):** Hello, register demo for Python course. My name is Ramesh, want weekend batch.
- **Agent (Telugu response):** సరే రమేష్ గారు, weekend batch కి demo session arrange చేస్తాను. మీ email ID మరియు qualification కొంచెం చెప్తారా?
- *Metrics:* Latency: 1208 ms | Tokens: 4876 | End Call: `False`

### Turn 2
- **Caller (Telugu):** సారీ చిన్న కరెక్షన్ — నా పేరు రమేష్ కాదు, రాజేష్. వీకెండ్ కాకుండా వీక్‌డే ఈవెనింగ్ బ్యాచ్ కావాలి.
- **Caller (English translation):** Sorry small correction — my name is not Ramesh, it is Rajesh. Instead of weekend want weekday evening batch.
- **Agent (Telugu response):** అలాగే రాజేష్ గారు, వీక్‌డే evening batch కి demo arrange చేస్తాను. మీ email ID మరియు qualification చెప్తారా?
- *Metrics:* Latency: 1350 ms | Tokens: 5014 | End Call: `False`

### Turn 3
- **Caller (Telugu):** నా పేరు మరియు బ్యాచ్ సరిగ్గా నోట్ చేసుకున్నారా?
- **Caller (English translation):** Did you note my name and batch correctly?
- **Agent (Telugu response):** అవును రాజేష్ గారు, మీ పేరు మరియు weekday evening batch నోట్ చేసుకున్నాను. మరి మీ email ID మరియు qualification చెప్తారా?
- *Metrics:* Latency: 1322 ms | Tokens: 5111 | End Call: `False`

### Turn 4
- **Caller (Telugu):** సరే రాజేష్ అని నోట్ చేశారు కదా, అంతే ఇంకేమీ లేదు, ధన్యవాదాలు.
- **Caller (English translation):** Okay noted as Rajesh right, that is all nothing else, thanks.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 1443 ms | Tokens: 5165 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "f20735e9-bd8e-483d-8f56-16d1f1c1f74b",
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
- ✅ PASS: **turn_3_facts_fidelity** — Expected one of ['రాజేష్', 'ఈవెనింగ్'] in agent text
- ✅ PASS: **turn_3_forbidden_claims_absent** — Forbidden strings ['రమేష్'] present: False