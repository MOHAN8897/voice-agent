# A_budget_correction

Review: **PARTIAL; 7/10**. Corrected quantity 200, matte finish and budget 900 are recalled accurately. The model repeatedly pushes order progression during information questions. The final order request receives only farewell, without an explicit saved-request assurance or fulfilment distinction.

Call `45c39898-68e0-4ebc-9443-ade7d02568a4`; session `adaptive-44a0a237151e43beb2e87935c8de53e9`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నాకు 100 normal visiting cards కావాలి. నా budget 500 rupees వరకు ఉంటుంది.

Agent text queued to speech: Normal paper visiting cards one hundred కి two hundred rupees అవుతుంది. మీ budget five hundred rupees లోపు ఇది easily సరిపోతుంది. మరి మీ పేరు చెప్తారా? order process చేద్దాము.

Final orchestrator text: Normal paper visiting cards one hundred కి two hundred rupees అవుతుంది. మీ budget five hundred rupees లోపు ఇది easily సరిపోతుంది. మరి మీ పేరు చెప్తారా? order process చేద్దాము.

Elapsed: 1.468s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "normal visiting cards",
    "quantity": "100",
    "budget": "500 rupees"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?

Agent text queued to speech: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?

Final orchestrator text: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?

Elapsed: 1.5s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "visiting cards",
    "quantity": "200",
    "budget": "900 rupees",
    "latest_caller_correction": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 3

Caller: సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.

Agent text queued to speech: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?

Final orchestrator text: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?

Elapsed: 1.265s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "visiting cards",
    "quantity": "200",
    "budget": "900 rupees",
    "latest_caller_correction": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?"
  },
  "preferences": {},
  "important_context": "",
  "summary": "assistant: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?\nuser: సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.\nassistant: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?"
}
```

## Turn 4

Caller: నా పేరు రమేష్, email ramesh.audit@example.invalid. Payment ఎలా చేయాలి? నేను payment authorize చేయలేను.

Agent text queued to speech: రమేష్ గారు, thousand rupees పైన orders కి 50% advance payment చేయాలి. one thousand rupees లోపు అయితే cash on delivery ఉంటుంది. Phone లో online payment లేదా credit card తీసుకోము. మీరు artwork approve చేసి design confirm చేశాకే order process అవుతుంది. దీనిపై ముందుకు వెళ్దామా?

Final orchestrator text: రమేష్ గారు, thousand rupees పైన orders కి 50% advance payment చేయాలి. one thousand rupees లోపు అయితే cash on delivery ఉంటుంది. Phone లో online payment లేదా credit card తీసుకోము. మీరు artwork approve చేసి design confirm చేశాకే order process అవుతుంది. దీనిపై ముందుకు వెళ్దామా?

Elapsed: 1.516s; caller intended end: True; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "visiting cards",
    "quantity": "200",
    "budget": "900 rupees",
    "latest_caller_correction": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?",
    "caller_name": "రమేష్",
    "payment_method": "payment authorize చేయలేను",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?\nuser: సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.\nassistant: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?"
}
```

## Turn 5

Caller: నా budget 900 rupees లోపే ఉంది, సో advance payment లేకుండా cash on delivery option ఏమైనా ఉందా? నాకు payment authorize చేయడం కుదరదు.

Agent text queued to speech: అవును రమేష్ గారు, మీ order nine hundred rupees లోపు ఉంది కాబట్టి cash on delivery option ఉంది. మరి order process చేద్దామా?

Final orchestrator text: అవును రమేష్ గారు, మీ order nine hundred rupees లోపు ఉంది కాబట్టి cash on delivery option ఉంది. మరి order process చేద్దామా?

Elapsed: 1.234s; caller intended end: True; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "visiting cards",
    "quantity": "200",
    "budget": "900 rupees",
    "latest_caller_correction": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?",
    "caller_name": "రమేష్",
    "payment_method": "payment authorize చేయలేను",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?\nuser: సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.\nassistant: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?"
}
```

## Turn 6

Caller: సరే, cash on delivery అయితే okay. నేను order place చేస్తున్నాను, note చేసుకోండి.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.453s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "product": "visiting cards",
    "quantity": "200",
    "budget": "900 rupees",
    "latest_caller_correction": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?",
    "caller_name": "రమేష్",
    "payment_method": "payment authorize చేయలేను",
    "caller_email": "ramesh.audit@example.invalid"
  },
  "preferences": {
    "payment_method": "cash on delivery"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: Matte finish cards one hundred కి three hundred and fifty rupees అవుతుంది, సో two hundred cards కి seven hundred rupees అవుతుంది. ఇది మీ nine hundred rupees budget లో సరిపోతుంది. మరి order proceed చేద్దామా?\nuser: సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.\nassistant: మీరు two hundred matte finish visiting cards అడిగారు, మీ budget nine hundred rupees వరకు ఉంది. దీనిపై ముందుకు వెళ్దామా? మీ పేరు చెప్తారా?"
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
            "value": "normal visiting cards"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "100"
          },
          {
            "op": "set_fact",
            "key": "budget",
            "value": "500 rupees"
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
      "transcript": "నమస్తే, నాకు 100 normal visiting cards కావాలి. నా budget 500 rupees వరకు ఉంటుంది.",
      "at": 104826.515
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "visiting cards"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "200"
          },
          {
            "op": "set_fact",
            "key": "budget",
            "value": "900 rupees"
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
      "transcript": "Actually, నాకు 200 matte visiting cards కావాలి, నా budget 900 rupees వరకు ఉంటుంది. మీరు విన్నవి ఒకసారి మళ్ళీ చెప్తారా?",
      "at": 104828.625
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
      "transcript": "సరే, మీరు విన్నవి ఒకసారి మళ్ళీ confirm చేయండి. మీరు ఏ product, ఎన్ని quantity, ఇంకా ఎంత budget note చేసుకున్నారో చెప్పండి.",
      "at": 104830.453
    },
    {
      "turn": 4,
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
            "key": "payment_method",
            "value": "payment authorize చేయలేను"
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
      "transcript": "నా పేరు రమేష్, email ramesh.audit@example.invalid. Payment ఎలా చేయాలి? నేను payment authorize చేయలేను.",
      "at": 104832.5
    },
    {
      "turn": 5,
      "proposal": {
        "decision": "close",
        "reason": "not_interested",
        "evidence": "నా budget 900 rupees లోపే ఉంది, సో advance payment లేకుండా cash on delivery option ఏమైనా ఉందా? నాకు payment authorize చేయడం కుదరదు.",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "budget",
            "value": "900 rupees"
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
      "transcript": "నా budget 900 rupees లోపే ఉంది, సో advance payment లేకుండా cash on delivery option ఏమైనా ఉందా? నాకు payment authorize చేయడం కుదరదు.",
      "at": 104834.328
    },
    {
      "turn": 6,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "సరే, cash on delivery అయితే okay. నేను order place చేస్తున్నాను, note చేసుకోండి.",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "payment_method",
            "value": "cash on delivery"
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
      "transcript": "సరే, cash on delivery అయితే okay. నేను order place చేస్తున్నాను, note చేసుకోండి.",
      "at": 104836.203
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 6,
      "at": 104836.203
    }
  ],
  "carrier": [
    {
      "turn": 6,
      "at": 104837.281,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": [
    {
      "turn": 1,
      "start_s": 104825.125,
      "local_facts_present": false,
      "worker_start_s": 104825.125,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.23399999999674037,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 2,
      "start_s": 104827.156,
      "local_facts_present": true,
      "worker_start_s": 104827.156,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.23399999999674037,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 3,
      "start_s": 104829.203,
      "local_facts_present": true,
      "worker_start_s": 104829.203,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.2340000000112923,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 4,
      "start_s": 104831.015,
      "local_facts_present": true,
      "worker_start_s": 104831.015,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.21899999999732245,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 5,
      "start_s": 104833.125,
      "local_facts_present": true,
      "worker_start_s": 104833.125,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.21799999999348074,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 6,
      "start_s": 104834.906,
      "local_facts_present": true,
      "worker_start_s": 104834.906,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.23399999999674037,
      "projection_chars": 0,
      "rolling_chars": 0
    }
  ]
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_budget_correction.json).
