# A_memory_correction

Review: **PARTIAL; 7/10**. Name changes Ramesh→Ramana and quantity 100→200 are retained and later used. However, 'when will delivery happen?' is stored as delivery_time, and known identity is re-asked earlier. Successful recall can come from recent history even when the explicit memory projection is omitted.

Call `51d111c6-36bc-4293-b05d-051fcbf12fc8`; session `adaptive-f5ec9df3392e422fad6299ebd3892b1d`.

Integration fixture: success; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే. నేను రమేష్ మాట్లాడుతున్నాను, విజయవాడ నుంచి. నాకు 100 normal visiting cards కావాలి. దీని గురించి వివరాలు చెప్తారా?

Agent text queued to speech: సరే రమేష్ గారు, one hundred normal visiting cards కి two hundred rupees అవుతుంది. మీకు matte finish కావాలా లేక ఇదే order తో proceed అవుతారా?

Final orchestrator text: సరే రమేష్ గారు, one hundred normal visiting cards కి two hundred rupees అవుతుంది. మీకు matte finish కావాలా లేక ఇదే order తో proceed అవుతారా?

Elapsed: 1.438s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "delivery_locality": "విజయవాడ",
    "product": "normal visiting cards",
    "quantity": "100"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: నాకు matte finish కావాలి. మరి delivery ఎప్పటికి అవుతుంది? డిజైన్స్ నేను తర్వాత పంపిస్తాను.

Agent text queued to speech: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?

Final orchestrator text: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?

Elapsed: 1.5s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమేష్",
    "delivery_locality": "విజయవాడ",
    "product": "normal visiting cards",
    "quantity": "100",
    "delivery_time": "ఎప్పటికి అవుతుంది"
  },
  "preferences": {
    "finish": "matte finish"
  },
  "important_context": "",
  "summary": ""
}
```

## Turn 3

Caller: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?

Agent text queued to speech: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?

Final orchestrator text: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?

Elapsed: 1.828s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "delivery_locality": "విజయవాడ",
    "product": "matte visiting cards",
    "quantity": "200",
    "delivery_time": "ఎప్పటికి అవుతుంది"
  },
  "preferences": {
    "finish": "matte finish"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?\nuser: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?\nassistant: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?"
}
```

## Turn 4

Caller: త్రీ వర్కింగ్ డేస్ ఓకే, నేను తర్వాత డిజైన్స్ పంపిస్తాను. ఇప్పుడు మీ దగ్గర ఏయే పేర్లు, ప్రొడక్ట్స్, ఇంకా ఎంత క్వాంటిటీలో ఉన్నాయో చెప్తారా? నేను మళ్ళీ చెప్పను.

Agent text queued to speech: సరే రమణ గారు, మా దగ్గర visiting cards, wedding invitations, banners ఉన్నాయి. మీరు చెప్పింది note చేసుకున్నాను, మీరు మళ్ళీ చెప్పాల్సిన అవసరం లేదు. మీకు ఏ product గురించి ఇంకా details కావాలా?

Final orchestrator text: సరే రమణ గారు, మా దగ్గర visiting cards, wedding invitations, banners ఉన్నాయి. మీరు చెప్పింది note చేసుకున్నాను, మీరు మళ్ళీ చెప్పాల్సిన అవసరం లేదు. మీకు ఏ product గురించి ఇంకా details కావాలా?

Elapsed: 1.515s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "delivery_locality": "విజయవాడ",
    "product": "matte visiting cards",
    "quantity": "200",
    "delivery_time": "ఎప్పటికి అవుతుంది"
  },
  "preferences": {
    "finish": "matte finish",
    "delivery_time": "త్రీ వర్కింగ్ డేస్"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?\nuser: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?\nassistant: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?"
}
```

## Turn 5

Caller: విజిటింగ్ కార్డ్స్ కి సంబంధించిన వివరాలు చెప్పండి. నేను ఆర్డర్ request చేయాలనుకుంటున్నాను.

Agent text queued to speech: సరే రమణ గారు, విజిటింగ్ కార్డ్స్ కి minimum order one hundred cards ఉంటుంది. మీరు two hundred అడుగుతున్నారు కాబట్టి order proceed చేయవచ్చా? మరి మీ address చెప్తారా?

Final orchestrator text: సరే రమణ గారు, విజిటింగ్ కార్డ్స్ కి minimum order one hundred cards ఉంటుంది. మీరు two hundred అడుగుతున్నారు కాబట్టి order proceed చేయవచ్చా? మరి మీ address చెప్తారా?

Elapsed: 1.562s; caller intended end: True; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "delivery_locality": "విజయవాడ",
    "product": "విజిటింగ్ కార్డ్స్",
    "quantity": "200",
    "delivery_time": "ఎప్పటికి అవుతుంది"
  },
  "preferences": {
    "finish": "matte finish",
    "delivery_time": "త్రీ వర్కింగ్ డేస్"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?\nuser: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?\nassistant: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?"
}
```

## Turn 6

Caller: అవును, two hundred cards కి order proceed చేయండి. నా address విజయవాడ. దయచేసి order request ని internal గా process చేయండి, payment నేను తర్వాత చూసుకుంటాను. ఇంకేమైనా వివరాలు కావాలా?

Agent text queued to speech: సరే రమణ గారు, మీ enquiry save అయింది. మీరు designs పంపించాక, payment గురించి మాట్లాడదాం. ఇంకేమైనా వివరాలు కావాలా?

Final orchestrator text: సరే రమణ గారు, మీ enquiry save అయింది. మీరు designs పంపించాక, payment గురించి మాట్లాడదాం. ఇంకేమైనా వివరాలు కావాలా?

Elapsed: 1.531s; caller intended end: True; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "delivery_locality": "విజయవాడ",
    "product": "విజిటింగ్ కార్డ్స్",
    "quantity": "200",
    "delivery_time": "ఎప్పటికి అవుతుంది",
    "payment_method": "తర్వాత చూసుకుంటాను"
  },
  "preferences": {
    "finish": "matte finish",
    "delivery_time": "త్రీ వర్కింగ్ డేస్"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?\nuser: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?\nassistant: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?"
}
```

## Turn 7

Caller: లేదు, ఇంకేమీ అవసరం లేదు. మీరు internal order request process చేయండి. ధన్యవాదాలు, నేను ఫోన్ పెడుతున్నాను.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.562s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "రమణ",
    "delivery_locality": "విజయవాడ",
    "product": "విజిటింగ్ కార్డ్స్",
    "quantity": "200",
    "delivery_time": "ఎప్పటికి అవుతుంది",
    "payment_method": "తర్వాత చూసుకుంటాను"
  },
  "preferences": {
    "finish": "matte finish",
    "delivery_time": "త్రీ వర్కింగ్ డేస్"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards అయితే one hundred కి three hundred and fifty rupees అవుతుంది. Vijayawada లో artwork approval తర్వాత delivery కి 3 working days పడుతుంది. మీరు designs తర్వాత పంపిస్తాం అన్నారు కదా, మరి మీ పేరు confirm చేస్తారా?\nuser: అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?\nassistant: రమణ గారు, artwork approval తర్వాత Vijayawada లో delivery కి three working days పడుతుంది. Urgent గా కావాలంటే 24 hours కి extra one hundred fifty rupees అవుతుంది. మరి మీకు ఏది కావాలి?"
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
            "key": "delivery_locality",
            "value": "విజయవాడ"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "normal visiting cards"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "100"
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
      "transcript": "నమస్తే. నేను రమేష్ మాట్లాడుతున్నాను, విజయవాడ నుంచి. నాకు 100 normal visiting cards కావాలి. దీని గురించి వివరాలు చెప్తారా?",
      "at": 103673.031
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "finish",
            "value": "matte finish"
          },
          {
            "op": "set_fact",
            "key": "delivery_time",
            "value": "ఎప్పటికి అవుతుంది"
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
      "transcript": "నాకు matte finish కావాలి. మరి delivery ఎప్పటికి అవుతుంది? డిజైన్స్ నేను తర్వాత పంపిస్తాను.",
      "at": 103675.093
    },
    {
      "turn": 3,
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
            "value": "matte visiting cards"
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
      "transcript": "అవును, నా పేరు రమణ. 200 matte visiting cards కావాలి. మరి delivery ఎప్పటికి అవుతుంది?",
      "at": 103677.515
    },
    {
      "turn": 4,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "delivery_time",
            "value": "త్రీ వర్కింగ్ డేస్"
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
      "transcript": "త్రీ వర్కింగ్ డేస్ ఓకే, నేను తర్వాత డిజైన్స్ పంపిస్తాను. ఇప్పుడు మీ దగ్గర ఏయే పేర్లు, ప్రొడక్ట్స్, ఇంకా ఎంత క్వాంటిటీలో ఉన్నాయో చెప్తారా? నేను మళ్ళీ చెప్పను.",
      "at": 103679.812
    },
    {
      "turn": 5,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "విజిటింగ్ కార్డ్స్"
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
      "transcript": "విజిటింగ్ కార్డ్స్ కి సంబంధించిన వివరాలు చెప్పండి. నేను ఆర్డర్ request చేయాలనుకుంటున్నాను.",
      "at": 103681.89
    },
    {
      "turn": 6,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "payment_method",
            "value": "తర్వాత చూసుకుంటాను"
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
      "transcript": "అవును, two hundred cards కి order proceed చేయండి. నా address విజయవాడ. దయచేసి order request ని internal గా process చేయండి, payment నేను తర్వాత చూసుకుంటాను. ఇంకేమైనా వివరాలు కావాలా?",
      "at": 103684.078
    },
    {
      "turn": 7,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "లేదు, ఇంకేమీ అవసరం లేదు. మీరు internal order request process చేయండి. ధన్యవాదాలు, నేను ఫోన్ పెడుతున్నాను.",
        "memory_operations": [],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "లేదు, ఇంకేమీ అవసరం లేదు. మీరు internal order request process చేయండి. ధన్యవాదాలు, నేను ఫోన్ పెడుతున్నాను.",
      "at": 103686.218
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 7,
      "at": 103686.218
    }
  ],
  "carrier": [
    {
      "turn": 7,
      "at": 103687.281,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_memory_correction.json).
