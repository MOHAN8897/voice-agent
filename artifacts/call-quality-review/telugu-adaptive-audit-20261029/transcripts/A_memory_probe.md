# A_memory_probe

Review: **PASS; 8/10**. Explicit 'visiting cards only; wedding price is only a question' prevents the earlier product overwrite. The model correctly recalls Ramana, 200 matte visiting cards. This successful fresh contrast does not erase the original memory failure.

Call `0ec7baea-c013-4a8c-8f66-2a9965efb0ef`; session `adaptive-82a4c56c90b242fd87bf885c69b81cf9`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నా పేరు రమణ. నాకు 200 matte visiting cards కావాలి. ధర, delivery వివరాలు చెప్పండి.

Agent text queued to speech: సరే రమణ గారు, matte finish cards one hundred కి three hundred fifty rupees అవుతుంది, so two hundred cards కి seven hundred rupees అవుతుంది. Delivery Vijayawada లో artwork approval తర్వాత 3 working days పడుతుంది, urgent అయితే one hundred fifty rupees extra అవుతుంది. మీకు ఇది proceed అవ్వాలా?

Final orchestrator text: సరే రమణ గారు, matte finish cards one hundred కి three hundred fifty rupees అవుతుంది, so two hundred cards కి seven hundred rupees అవుతుంది. Delivery Vijayawada లో artwork approval తర్వాత 3 working days పడుతుంది, urgent అయితే one hundred fifty rupees extra అవుతుంది. మీకు ఇది proceed అవ్వాలా?

Elapsed: 1.578s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "product": "visiting cards",
    "quantity": "200"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 2

Caller: Visiting cards నే కావాలి. Wedding cards ధరలు ఎలా ఉంటాయో కేవలం తెలుసుకోవడానికి అడుగుతున్నాను. Wedding cards ఆర్డర్ చేయడం లేదు.

Agent text queued to speech: Wedding invitation cards అన్నీ customized కాబట్టి, design, paper sample, ఇంకా quantity బట్టి price మారుతుంది. ఫోన్లో fixed price చెప్పలేము. మీకు ఇంకా వేరే ఏమైనా details కావాలా?

Final orchestrator text: Wedding invitation cards అన్నీ customized కాబట్టి, design, paper sample, ఇంకా quantity బట్టి price మారుతుంది. ఫోన్లో fixed price చెప్పలేము. మీకు ఇంకా వేరే ఏమైనా details కావాలా?

Elapsed: 1.375s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "product": "visiting cards",
    "quantity": "200"
  },
  "preferences": {
    "product_interest": "wedding cards"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 3

Caller: ఇప్పటివరకు నా పేరు, నాకు కావాల్సిన product, quantity ఏం గుర్తు పెట్టుకున్నారు?

Agent text queued to speech: సరే రమణ గారు, మీ పేరు, two hundred matte visiting cards detail నేను note చేసుకున్నాను. Vijayawada లో delivery artwork approval తర్వాత three working days లో అవుతుంది. మీకు urgent గా కావాలంటే 24 hours delivery కి extra one hundred fifty rupees అవుతుంది.

Final orchestrator text: సరే రమణ గారు, మీ పేరు, two hundred matte visiting cards detail నేను note చేసుకున్నాను. Vijayawada లో delivery artwork approval తర్వాత three working days లో అవుతుంది. మీకు urgent గా కావాలంటే 24 hours delivery కి extra one hundred fifty rupees అవుతుంది.

Elapsed: 1.484s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "product": "visiting cards",
    "quantity": "200"
  },
  "preferences": {
    "product_interest": "wedding cards"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Wedding invitation cards అన్నీ customized కాబట్టి, design, paper sample, ఇంకా quantity బట్టి price మారుతుంది. ఫోన్లో fixed price చెప్పలేము. మీకు ఇంకా వేరే ఏమైనా details కావాలా?\nuser: ఇప్పటివరకు నా పేరు, నాకు కావాల్సిన product, quantity ఏం గుర్తు పెట్టుకున్నారు?\nassistant: సరే రమణ గారు, మీ పేరు, two hundred matte visiting cards detail నేను note చేసుకున్నాను. Vijayawada లో delivery artwork approval తర్వాత three working days లో అవుతుంది. మీకు urgent గా కావాలంటే 24 hours delivery కి extra one hundred fifty rupees అవుతుంది."
}
```

## Turn 4

Caller: సరే, ఇంతే చాలు. ధన్యవాదాలు, నమస్కారం.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.453s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "product": "visiting cards",
    "quantity": "200"
  },
  "preferences": {
    "product_interest": "wedding cards"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Wedding invitation cards అన్నీ customized కాబట్టి, design, paper sample, ఇంకా quantity బట్టి price మారుతుంది. ఫోన్లో fixed price చెప్పలేము. మీకు ఇంకా వేరే ఏమైనా details కావాలా?\nuser: ఇప్పటివరకు నా పేరు, నాకు కావాల్సిన product, quantity ఏం గుర్తు పెట్టుకున్నారు?\nassistant: సరే రమణ గారు, మీ పేరు, two hundred matte visiting cards detail నేను note చేసుకున్నాను. Vijayawada లో delivery artwork approval తర్వాత three working days లో అవుతుంది. మీకు urgent గా కావాలంటే 24 hours delivery కి extra one hundred fifty rupees అవుతుంది."
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
            "key": "caller_name",
            "value": "రమణ"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "visiting cards"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "200"
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
      "transcript": "నా పేరు రమణ. నాకు 200 matte visiting cards కావాలి. ధర, delivery వివరాలు చెప్పండి.",
      "at": 104173.484
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "close",
        "reason": "not_interested",
        "evidence": "Wedding cards ఆర్డర్ చేయడం లేదు.",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "product_interest",
            "value": "wedding cards"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": "user_asked_question"
      },
      "transcript": "Visiting cards నే కావాలి. Wedding cards ధరలు ఎలా ఉంటాయో కేవలం తెలుసుకోవడానికి అడుగుతున్నాను. Wedding cards ఆర్డర్ చేయడం లేదు.",
      "at": 104174.906
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
      "transcript": "ఇప్పటివరకు నా పేరు, నాకు కావాల్సిన product, quantity ఏం గుర్తు పెట్టుకున్నారు?",
      "at": 104176.406
    },
    {
      "turn": 4,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "సరే, ఇంతే చాలు. ధన్యవాదాలు, నమస్కారం.",
        "memory_operations": [],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "సరే, ఇంతే చాలు. ధన్యవాదాలు, నమస్కారం.",
      "at": 104177.781
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 4,
      "at": 104177.781
    }
  ],
  "carrier": [
    {
      "turn": 4,
      "at": 104178.828,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_memory_probe.json).
