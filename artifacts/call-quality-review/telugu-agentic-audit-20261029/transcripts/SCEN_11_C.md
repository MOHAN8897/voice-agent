# Scenario Transcript: SCEN_11 — Course Enquiry & Demo Booking with Connected CRM Integration
**Business:** C | **Agent:** Madhavi | **Condition:** `connected`
**Caller Phone:** `+919876543230` | **Duration:** 17.11s | **Tokens:** 36230
**Carrier Hangup Executed:** `True` | **Evaluation Score:** 8.42/10

## Conversation Transcript

### Turn 1
- **Caller (Telugu):** నమస్కారం మేడమ్, మీ పైథాన్ డేటా అనలిటిక్స్ కోర్స్ గురించి వివరాలు కావాలి.
- **Caller (English translation):** Hello madam, need details about your Python Data Analytics course.
- **Agent (Telugu response):** నమస్కారం, నేను Madhavi, Teja Data Academy నుంచి మాట్లాడుతున్నాను. తప్పకుండా చెప్తాను, మన Python with Data Analytics course 8 weeks online live classes మరియు hands-on projects తో ఉంటుంది. మీకు ఏ details కావాలి?
- *Metrics:* Latency: 1617 ms | Tokens: 4894 | End Call: `False`

### Turn 2
- **Caller (Telugu):** కోర్స్ ఎన్ని వారాలు ఉంటుంది? క్లాస్ టైమింగ్స్ ఏమిటి?
- **Caller (English translation):** How many weeks is the course? What are the class timings?
- **Agent (Telugu response):** ఈ course 8 weeks online live classes తో పాటు hands-on projects ఉంటాయి. Weekday batch రాత్రి eight PM నుంచి nine PM వరకు, weekend batch ఉదయం ten AM నుంచి మధ్యాహ్నం one PM వరకు నడుస్తుంది. మీకు ఏ batch బాగా set అవుతుంది?
- *Metrics:* Latency: 1468 ms | Tokens: 5040 | End Call: `False`

### Turn 3
- **Caller (Telugu):** కోర్స్ ఫీజు ఎంతండి? పాత బ్రోచర్‌లో 12000 అని ఉంది.
- **Caller (English translation):** What is the course fee? Old brochure says 12000.
- **Agent (Telugu response):** ఆ పాత బ్రోచర్ లో ఉన్న prices ఇప్పుడు లేవు. ప్రస్తుతానికి course fee మొత్తం eight thousand nine hundred ninety nine rupees మాత్రమే. మీకు ఏ batch వీలవుతుందో చెప్తారా? Weekday ఆ లేక weekend ఆ?
- *Metrics:* Latency: 1437 ms | Tokens: 5075 | End Call: `False`

### Turn 4
- **Caller (Telugu):** డిగ్రీ చదివిన వాళ్ళు ఎలిజిబుల్ లేక కోడింగ్ బ్యాక్‌గ్రౌండ్ ఉండాలా?
- **Caller (English translation):** Are degree graduates eligible or is a coding background required?
- **Agent (Telugu response):** ఏ graduate అయినా లేదా final year college student అయినా eligible. Basic computer knowledge ఉంటే చాలు, prior coding అవసరం లేదు. మీకు ఏ batch set అవుతుందో చెప్తారా?
- *Metrics:* Latency: 1390 ms | Tokens: 5124 | End Call: `False`

### Turn 5
- **Caller (Telugu):** కోర్స్ అయ్యాక జాబ్ గ్యారెంటీ ఇస్తారా?
- **Caller (English translation):** Do you give a job guarantee after the course?
- **Agent (Telugu response):** Strictly job guarantee ఏమీ ఉండదు, కానీ one hundred% placement assistance మాత్రం ఇస్తాము. ఇందులో resume building, interview preparation, job referrals ఉంటాయి. మీకు ఈ course గురించి ఇంకేమైనా details కావాలా?
- *Metrics:* Latency: 1545 ms | Tokens: 5180 | End Call: `False`

### Turn 6
- **Caller (Telugu):** ఉచిత డెమో క్లాస్ ఉందా? నేను అటెండ్ అవ్వవచ్చా?
- **Caller (English translation):** Is there a free demo class? Can I attend?
- **Agent (Telugu response):** అవును, free demo session ఉంది. మీరు తప్పకుండా attend అవ్వొచ్చు. మీ పేరు, email, qualification మరియు మీకు ఏ batch కావాలో చెప్తారా?
- *Metrics:* Latency: 1332 ms | Tokens: 5224 | End Call: `False`

### Turn 7
- **Caller (Telugu):** నా పేరు శ్రీనివాస్, ఈమెయిల్ srinivas.audit@example.com. ఈవెనింగ్ బ్యాచ్ డెమో రిజిస్టర్ చేయండి.
- **Caller (English translation):** My name Srinivas, email srinivas.audit@example.com. Register evening batch demo.
- **Agent (Telugu response):** సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- *Metrics:* Latency: 1274 ms | Tokens: 5693 | End Call: `True`

## Persisted Database Evidence
```json
{
  "call": {
    "call_id": "f2dca063-4f59-44c3-b682-9434f340ebbe",
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
- ✅ PASS: **turn_2_facts_fidelity** — Expected one of ['8', 'ఎనిమిది వారాలు', '8:00'] in agent text
- ❌ FAIL: **turn_3_facts_fidelity** — Expected one of ['8,999', '8999', 'ఎనిమిది వేల'] in agent text
- ❌ FAIL: **turn_4_facts_fidelity** — Expected one of ['గ్రాడ్యుయేట్', 'డిగ్రీ'] in agent text
- ❌ FAIL: **turn_5_facts_fidelity** — Expected one of ['అసిస్టెన్స్', 'గ్యారెంటీ లేదు'] in agent text
- ❌ FAIL: **turn_8_executed** — Turn not reached
- ❌ FAIL: **turn_9_executed** — Turn not reached