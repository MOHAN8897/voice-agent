# Scenario Transcript: SCEN_06 — Service Appointment Booking with Connected Calendar Integration
**Business:** B | **Agent:** Suresh | **Condition:** `connected`
**Caller Phone:** `+919876543220` | **Duration:** 15.68s | **Tokens:** 32188
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 8.42/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** నమస్కారం, మా ఇంట్లో స్ప్లిట్ ఏసీ సర్వీసింగ్ చేయించాలి. చార్జ్ ఎంత?
- **Caller (English translation):** Hello, need split AC servicing at home. How much charge?
- **Agent (Telugu response):** మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- *Metrics:* Latency: 1466 ms | Tokens: 4940 | End Call: `False`

### Turn 2
- **Caller (Telugu):** విండో ఏసీ అయితే ఎంత అవుతుంది?
- **Caller (English translation):** How much if it is a Window AC?
- **Agent (Telugu response):** మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- *Metrics:* Latency: 1216 ms | Tokens: 5045 | End Call: `False`

### Turn 3
- **Caller (Telugu):** ఫ్రిజ్ కూడా కూలింగ్ అవ్వడం లేదు, ఇన్‌స్పెక్షన్ చార్జ్ ఎంత?
- **Caller (English translation):** Fridge is also not cooling, how much inspection charge?
- **Agent (Telugu response):** మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- *Metrics:* Latency: 1408 ms | Tokens: 5134 | End Call: `False`

### Turn 4
- **Caller (Telugu):** మాధాపూర్‌లో మీ సర్వీస్ అందుబాటులో ఉందా?
- **Caller (English translation):** Is your service available in Madhapur?
- **Agent (Telugu response):** మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- *Metrics:* Latency: 1179 ms | Tokens: 5161 | End Call: `False`

### Turn 5
- **Caller (Telugu):** రేపు మధ్యాహ్నం 2 గంటలకు టెక్నీషియన్‌ని పంపగలరా? స్లాట్ ఉందా?
- **Caller (English translation):** Can you send a technician tomorrow at 2 PM? Is a slot available?
- **Agent (Telugu response):** మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- *Metrics:* Latency: 1231 ms | Tokens: 5916 | End Call: `False`

### Turn 6
- **Caller (Telugu):** నా పేరు కిరణ్, మాధాపూర్ మెయిన్ రోడ్. రేపు 2 గంటల స్లాట్ బుక్ చేయండి.
- **Caller (English translation):** My name is Kiran, Madhapur Main Road. Book tomorrow 2 PM slot.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 1378 ms | Tokens: 5992 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "5d8a9a68-5eed-4da1-b4ad-23dfb8f2bb59",
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
- ❌ FAIL: **turn_1_facts_fidelity** — Expected one of ['599', 'ఐదు వందల తొంబై తొమ్మిది'] in agent text
- ❌ FAIL: **turn_2_facts_fidelity** — Expected one of ['499', 'నాలుగు వందల తొంబై తొమ్మిది'] in agent text
- ❌ FAIL: **turn_3_facts_fidelity** — Expected one of ['250', 'రెండు వందల యాభై'] in agent text
- ❌ FAIL: **turn_4_facts_fidelity** — Expected one of ['మాధాపూర్', 'అవును'] in agent text
- ❌ FAIL: **turn_7_executed** — Turn not reached
- ❌ FAIL: **turn_8_executed** — Turn not reached