# A_carrier_failure

Review: **PASS; 8/10**. One farewell; first fake carrier acknowledgement fails and context stays active/closing. A harness-triggered second call to the real finish method gets one acknowledgement and finalizes. This proves safe failure/retry mechanics, NOT an autonomous carrier retry daemon.

Call `e8a965c4-6761-44cb-a8c0-2f2080331386`; session `adaptive-2b0b6b0221da42bf8759a2fecb29aacb`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే Kavitha, నాకు visiting cards కావాలి. Matte finish అయితే బాగుంటుంది. ముందుగా minimum order ఎంత ఉంటుందో చెప్పగలరా?

Agent text queued to speech: Matte finish cards కోసం minimum order one hundred cards ఉంటుంది. one hundred cards కి three hundred fifty rupees అవుతుంది. మీకు ఎన్ని cards కావాలో చెప్తారా?

Final orchestrator text: Matte finish cards కోసం minimum order one hundred cards ఉంటుంది. one hundred cards కి three hundred fifty rupees అవుతుంది. మీకు ఎన్ని cards కావాలో చెప్తారా?

Elapsed: 1.375s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "Kavitha",
    "product": "visiting cards",
    "finish": "Matte"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: ప్రస్తుతం నాకు 250 cards కావాలి. దీనికి ఏమైనా extra charges ఉంటాయా?

Agent text queued to speech: Extra charges గురించి నాకు సమాచారం లేదు. మీరు proceed అవ్వాలనుకుంటే, మీ పేరు చెప్తారా?

Final orchestrator text: Extra charges గురించి నాకు సమాచారం లేదు. మీరు proceed అవ్వాలనుకుంటే, మీ పేరు చెప్తారా?

Elapsed: 1.312s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "Kavitha",
    "product": "visiting cards",
    "finish": "Matte",
    "quantity": "250"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 3

Caller: సరే, నా పేరు రమేష్. నేను నా email ID ramesh.audit@example.invalid ద్వారా designs తర్వాత పంపిస్తాను, ప్రస్తుతానికి ఇంతే చాలు, goodbye.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.078s; caller intended end: True; context: active/closing.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "product": "visiting cards",
    "finish": "Matte",
    "quantity": "250",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards కోసం minimum order one hundred cards ఉంటుంది. one hundred cards కి three hundred fifty rupees అవుతుంది. మీకు ఎన్ని cards కావాలో చెప్తారా?\nuser: ప్రస్తుతం నాకు 250 cards కావాలి. దీనికి ఏమైనా extra charges ఉంటాయా?\nassistant: Extra charges గురించి నాకు సమాచారం లేదు. మీరు proceed అవ్వాలనుకుంటే, మీ పేరు చెప్తారా?\nuser: సరే, నా పేరు రమేష్. నేను నా email ID ramesh.audit@example.invalid ద్వారా designs తర్వాత పంపిస్తాను, ప్రస్తుతానికి ఇంతే చాలు, goodbye.\nassistant: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."
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
            "value": "Kavitha"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "visiting cards"
          },
          {
            "op": "set_fact",
            "key": "finish",
            "value": "Matte"
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
      "transcript": "నమస్తే Kavitha, నాకు visiting cards కావాలి. Matte finish అయితే బాగుంటుంది. ముందుగా minimum order ఎంత ఉంటుందో చెప్పగలరా?",
      "at": 103754.453
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "250"
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
      "transcript": "ప్రస్తుతం నాకు 250 cards కావాలి. దీనికి ఏమైనా extra charges ఉంటాయా?",
      "at": 103756.312
    },
    {
      "turn": 3,
      "proposal": {
        "should_end": true,
        "reason": "goodbye",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."
      },
      "result": {
        "should_end": true,
        "reason": "goodbye",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "సరే, నా పేరు రమేష్. నేను నా email ID ramesh.audit@example.invalid ద్వారా designs తర్వాత పంపిస్తాను, ప్రస్తుతానికి ఇంతే చాలు, goodbye.",
      "at": 103757.0
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 3,
      "at": 103757.031
    }
  ],
  "carrier": [
    {
      "turn": 3,
      "at": 103758.078,
      "playback_active": false,
      "pending": false,
      "acknowledged": false
    },
    {
      "turn": 3,
      "at": 103759.125,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [
    {
      "kind": "state_after_failed_ack",
      "status": "active",
      "phase": "closing"
    }
  ],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_carrier_failure.json).
