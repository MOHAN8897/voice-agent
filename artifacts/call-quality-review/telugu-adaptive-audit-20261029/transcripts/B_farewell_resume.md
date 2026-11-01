# B_farewell_resume

Review: **PARTIAL; 7/10**. A new inspection-fee question injected during farewell prevents that close and receives an answer. The next genuine ending gets one successful carrier acknowledgement. Two farewell attempts are expected because the caller reopened the conversation; booking/slot assurances remain unproven.

Call `8d69eaf3-c7f7-4cba-888f-9eb1b21f0963`; session `adaptive-716fab09b0ed41089d4b5166bf11d05c`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే సురేష్ గారు. నా split AC కి general service కావాలి. దీనికి ఎంత charge అవుతుంది? అలాగే రేపు ఉదయం 10 గంటలకి technician వస్తారా?

Agent text queued to speech: Split AC servicing కి five hundred ninety nine rupees అవుతుంది. రేపు ఉదయం 10 గంటలకి slot ఉంది. మీ locality చెప్తారా, booking confirm చేస్తాను?

Final orchestrator text: Split AC servicing కి five hundred ninety nine rupees అవుతుంది. రేపు ఉదయం 10 గంటలకి slot ఉంది. మీ locality చెప్తారా, booking confirm చేస్తాను?

Elapsed: 1.375s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "split AC",
    "requested_time": "రేపు ఉదయం 10 గంటలకి"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: అవును సురేష్ గారు, నేను మాదాపూర్ లో ఉంటాను. ఈ 599 rupees price కి technician రేపు 10 AM కి వస్తారా, booking confirm చేయనా?

Agent text queued to speech: అవును, మాదాపూర్ మా service area లో ఉంది. రేపు ఉదయం 10 గంటలకి technician visit schedule చేయొచ్చు. Booking confirm చేయడానికి మీ పేరు, అలాగే AC లో ఏమైనా issue ఉందా చెప్తారా?

Final orchestrator text: అవును, మాదాపూర్ మా service area లో ఉంది. రేపు ఉదయం 10 గంటలకి technician visit schedule చేయొచ్చు. Booking confirm చేయడానికి మీ పేరు, అలాగే AC లో ఏమైనా issue ఉందా చెప్తారా?

Elapsed: 1.406s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "split AC",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "caller_name": "సురేష్ గారు",
    "delivery_locality": "మాదాపూర్"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 3

Caller: నా పేరు శ్రావణి, AC లో వేరే issue ఏమీ లేదు, just general service సరిపోతుంది. ఈ 599 rupees కి రేపు 10 AM కి booking confirm చేసేయండి.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం. Fridge inspection charge two hundred fifty rupees ఉంటుంది. కానీ technician వచ్చి repair చేస్తే ఆ inspection charge పూర్తిగా waive అవుతుంది. మీది split AC కదా, సో ఈ two hundred fifty rupees charge పడదు. మరి రేపు 10 గంటల slot confirm చేయమంటారా?

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం. Fridge inspection charge two hundred fifty rupees ఉంటుంది. కానీ technician వచ్చి repair చేస్తే ఆ inspection charge పూర్తిగా waive అవుతుంది. మీది split AC కదా, సో ఈ two hundred fifty rupees charge పడదు. మరి రేపు 10 గంటల slot confirm చేయమంటారా?

Elapsed: 2.75s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "split AC",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "budget": "599 rupees"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": "user: అవును సురేష్ గారు, నేను మాదాపూర్ లో ఉంటాను. ఈ 599 rupees price కి technician రేపు 10 AM కి వస్తారా, booking confirm చేయనా?\nassistant: అవును, మాదాపూర్ మా service area లో ఉంది. రేపు ఉదయం 10 గంటలకి technician visit schedule చేయొచ్చు. Booking confirm చేయడానికి మీ పేరు, అలాగే AC లో ఏమైనా issue ఉందా చెప్తారా?\nuser: నా పేరు శ్రావణి, AC లో వేరే issue ఏమీ లేదు, just general service సరిపోతుంది. ఈ 599 rupees కి రేపు 10 AM కి booking confirm చేసేయండి.\nassistant: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.\nuser: ఆగండి, ఇంకో ప్రశ్న ఉంది. ఇన్‌స్పెక్షన్ ఫీజు ఎంత?"
}
```

## Turn 4

Caller: అవును సురేష్ గారు, రేపు ఉదయం 10 గంటలకి booking confirm చేయండి. నా questions అన్నీ clear అయ్యాయి, thank you.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.562s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "product": "split AC",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "caller_name": "సురేష్ గారు",
    "delivery_locality": "మాదాపూర్",
    "budget": "599 rupees"
  },
  "preferences": {
    "requested_time": "రేపు ఉదయం 10 గంటలకి"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "user: అవును సురేష్ గారు, నేను మాదాపూర్ లో ఉంటాను. ఈ 599 rupees price కి technician రేపు 10 AM కి వస్తారా, booking confirm చేయనా?\nassistant: అవును, మాదాపూర్ మా service area లో ఉంది. రేపు ఉదయం 10 గంటలకి technician visit schedule చేయొచ్చు. Booking confirm చేయడానికి మీ పేరు, అలాగే AC లో ఏమైనా issue ఉందా చెప్తారా?\nuser: నా పేరు శ్రావణి, AC లో వేరే issue ఏమీ లేదు, just general service సరిపోతుంది. ఈ 599 rupees కి రేపు 10 AM కి booking confirm చేసేయండి.\nassistant: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.\nuser: ఆగండి, ఇంకో ప్రశ్న ఉంది. ఇన్‌స్పెక్షన్ ఫీజు ఎంత?"
}
```

## Server evidence

```json
{
  "gates": [
    {
      "turn": 1,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "split AC"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "రేపు ఉదయం 10 గంటలకి"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": null
      },
      "transcript": "నమస్తే సురేష్ గారు. నా split AC కి general service కావాలి. దీనికి ఎంత charge అవుతుంది? అలాగే రేపు ఉదయం 10 గంటలకి technician వస్తారా?",
      "at": 103765.359
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "సురేష్ గారు"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "మాదాపూర్"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": null
      },
      "transcript": "అవును సురేష్ గారు, నేను మాదాపూర్ లో ఉంటాను. ఈ 599 rupees price కి technician రేపు 10 AM కి వస్తారా, booking confirm చేయనా?",
      "at": 103767.375
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "ఈ 599 rupees కి రేపు 10 AM కి booking confirm చేసేయండి.",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "శ్రావణి"
          },
          {
            "op": "set_fact",
            "key": "budget",
            "value": "599 rupees"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "నా పేరు శ్రావణి, AC లో వేరే issue ఏమీ లేదు, just general service సరిపోతుంది. ఈ 599 rupees కి రేపు 10 AM కి booking confirm చేసేయండి.",
      "at": 103769.328
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "continue",
        "memory_operations": [],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": null
      },
      "transcript": "ఆగండి, ఇంకో ప్రశ్న ఉంది. ఇన్‌స్పెక్షన్ ఫీజు ఎంత?",
      "at": 103770.75
    },
    {
      "turn": 4,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "అవును సురేష్ గారు, రేపు ఉదయం 10 గంటలకి booking confirm చేయండి. నా questions అన్నీ clear అయ్యాయి, thank you.",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "సురేష్ గారు"
          },
          {
            "op": "set_preference",
            "key": "requested_time",
            "value": "రేపు ఉదయం 10 గంటలకి"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "అవును సురేష్ గారు, రేపు ఉదయం 10 గంటలకి booking confirm చేయండి. నా questions అన్నీ clear అయ్యాయి, thank you.",
      "at": 103772.687
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 3,
      "at": 103769.343
    },
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 4,
      "at": 103772.687
    }
  ],
  "carrier": [
    {
      "turn": 4,
      "at": 103773.765,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [
    {
      "kind": "caller_resumed_during_farewell"
    }
  ],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_farewell_resume.json).
