# A_deep_enquiry

Review: **FAIL; 1/10**. At T3 'I will call later about wedding cards' is interpreted as THEM calling the customer. Two visiting-card delivery/rush questions remain open. The server persists an unwanted callback and disconnects after only three turns.

Call `6d04e658-9c39-4982-9375-53ece2bd5f43`; session `adaptive-7f81bd6591434596980041904102fe0a`.

Integration fixture: success; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే Kavitha, నేను విజయవాడ నుంచి రమేష్ ని మాట్లాడుతున్నా. నాకు visiting cards కావాలి, matte finish అయితే బాగుంటుంది. ముందుగా 100 cards కి standard pricing ఎలా ఉంటుంది, minimum quantity ఎంత పెట్టాలి? నా design ని తర్వాత పంపిస్తాను.

Agent text queued to speech: Matte finish cards one hundred కి three hundred fifty rupees అవుతుంది. Minimum order quantity కూడా one hundred cards ఏ ఉంటుంది. మీరు design తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు ఒకసారి చెప్తారా?

Final orchestrator text: Matte finish cards one hundred కి three hundred fifty rupees అవుతుంది. Minimum order quantity కూడా one hundred cards ఏ ఉంటుంది. మీరు design తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు ఒకసారి చెప్తారా?

Elapsed: 1.703s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "product": "visiting cards",
    "quantity": "100",
    "delivery_locality": "విజయవాడ"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: నా పేరు రమేష్, email ramesh.audit@example.invalid. 100 cards కి 350 rupees అంటే బాగుంది. మరి 200 cards కి ఏమైనా discount ఉంటుందా? అలాగే wedding cards price కూడా ఎలా ఉంటుందో ఒకసారి చెప్తారా?

Agent text queued to speech: two hundred cards కి discount details నాకు అందుబాటులో లేవు. Wedding invitation cards design, paper sample, ఇంకా quantity బట్టి మారుతాయి, కాబట్టి phone లో fixed price చెప్పలేము. మీకు ఈ visiting cards order తో ముందుకు వెళ్దామా?

Final orchestrator text: two hundred cards కి discount details నాకు అందుబాటులో లేవు. Wedding invitation cards design, paper sample, ఇంకా quantity బట్టి మారుతాయి, కాబట్టి phone లో fixed price చెప్పలేము. మీకు ఈ visiting cards order తో ముందుకు వెళ్దామా?

Elapsed: 1.532s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "product": "visiting cards",
    "quantity": "200",
    "delivery_locality": "విజయవాడ",
    "email": "ramesh.audit@example.invalid",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 3

Caller: సరే, discount details ఇప్పుడు లేకపోతే పర్లేదు. Wedding cards price కనుక్కోవడానికి నేను తర్వాత call చేస్తాను. ఈ 100 matte cards కి delivery ఎంత time పడుతుంది? అలాగే rush order ఏమైనా ఉంటే extra charges ఉంటాయా?

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.5s; caller intended end: False; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "product": "visiting cards",
    "quantity": "200",
    "delivery_locality": "విజయవాడ",
    "email": "ramesh.audit@example.invalid",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: two hundred cards కి discount details నాకు అందుబాటులో లేవు. Wedding invitation cards design, paper sample, ఇంకా quantity బట్టి మారుతాయి, కాబట్టి phone లో fixed price చెప్పలేము. మీకు ఈ visiting cards order తో ముందుకు వెళ్దామా?\nuser: సరే, discount details ఇప్పుడు లేకపోతే పర్లేదు. Wedding cards price కనుక్కోవడానికి నేను తర్వాత call చేస్తాను. ఈ 100 matte cards కి delivery ఎంత time పడుతుంది? అలాగే rush order ఏమైనా ఉంటే extra charges ఉంటాయా?\nassistant: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."
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
            "value": "రమేష్"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "visiting cards"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "100"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "విజయవాడ"
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
      "transcript": "నమస్తే Kavitha, నేను విజయవాడ నుంచి రమేష్ ని మాట్లాడుతున్నా. నాకు visiting cards కావాలి, matte finish అయితే బాగుంటుంది. ముందుగా 100 cards కి standard pricing ఎలా ఉంటుంది, minimum quantity ఎంత పెట్టాలి? నా design ని తర్వాత పంపిస్తాను.",
      "at": 103986.265
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "రమేష్"
          },
          {
            "op": "set_fact",
            "key": "email",
            "value": "ramesh.audit@example.invalid"
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
      "transcript": "నా పేరు రమేష్, email ramesh.audit@example.invalid. 100 cards కి 350 rupees అంటే బాగుంది. మరి 200 cards కి ఏమైనా discount ఉంటుందా? అలాగే wedding cards price కూడా ఎలా ఉంటుందో ఒకసారి చెప్తారా?",
      "at": 103988.531
    },
    {
      "turn": 3,
      "proposal": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నోట్ చేసుకున్నాను. ధన్యవాదాలు."
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "callback"
      },
      "transcript": "సరే, discount details ఇప్పుడు లేకపోతే పర్లేదు. Wedding cards price కనుక్కోవడానికి నేను తర్వాత call చేస్తాను. ఈ 100 matte cards కి delivery ఎంత time పడుతుంది? అలాగే rush order ఏమైనా ఉంటే extra charges ఉంటాయా?",
      "at": 103989.562
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 3,
      "at": 103989.656
    }
  ],
  "carrier": [
    {
      "turn": 3,
      "at": 103990.718,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_deep_enquiry.json).
