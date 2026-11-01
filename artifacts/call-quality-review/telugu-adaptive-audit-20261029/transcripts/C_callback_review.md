# C_callback_review

Review: **PASS; 8/10**. The tomorrow-morning callback is captured for tenant review, not silently authorized for automatic dialing. Farewell follows persistence.

Call `1df75626-4728-4a87-ad6f-02b7632c2226`; session `adaptive-460af48966cf4e6e9e6e4c7eebaaa5b6`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. నాకు Python ఇంకా data training గురించి తెలుసుకోవాలి. నేను job చేస్తూ evenings లేదా weekends లో attend అవ్వగలను. దీని fees, placement details గురించి కొంచెం చెప్తారా?

Agent text queued to speech: కిరణ్ గారు, మా weekday batch రాత్రి eight PM నుంచి nine PM వరకు, weekend batch Saturday and Sunday ఉదయం ten AM నుంచి one PM వరకు ఉంటాయి. Total fee eight thousand nine hundred ninety nine rupees మాత్రమే.

Final orchestrator text: కిరణ్ గారు, మా weekday batch రాత్రి eight PM నుంచి nine PM వరకు, weekend batch Saturday and Sunday ఉదయం ten AM నుంచి one PM వరకు ఉంటాయి. Total fee eight thousand nine hundred ninety nine rupees మాత్రమే.

Elapsed: 1.844s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్",
    "product": "Python ఇంకా data training",
    "requested_time": "evenings లేదా weekends"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: సరే, ఎనిమిది వేల తొమ్మిది వందల తొంభై తొమ్మిది రూపాయలు అంటే కొంచెం ఎక్కువే అనిపిస్తోంది. నాకు రేపు ఉదయం ఒక callback arrange చేస్తారా? నా పేరు కిరణ్, team review తర్వాత నాకు call చేయమని చెప్పండి.

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.484s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్",
    "product": "Python ఇంకా data training",
    "requested_time": "evenings లేదా weekends"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
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
            "value": "కిరణ్"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "Python ఇంకా data training"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "evenings లేదా weekends"
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
      "transcript": "నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. నాకు Python ఇంకా data training గురించి తెలుసుకోవాలి. నేను job చేస్తూ evenings లేదా weekends లో attend అవ్వగలను. దీని fees, placement details గురించి కొంచెం చెప్తారా?",
      "at": 103664.39
    },
    {
      "turn": 2,
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
      "transcript": "సరే, ఎనిమిది వేల తొమ్మిది వందల తొంభై తొమ్మిది రూపాయలు అంటే కొంచెం ఎక్కువే అనిపిస్తోంది. నాకు రేపు ఉదయం ఒక callback arrange చేస్తారా? నా పేరు కిరణ్, team review తర్వాత నాకు call చేయమని చెప్పండి.",
      "at": 103665.609
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 2,
      "at": 103665.671
    }
  ],
  "carrier": [
    {
      "turn": 2,
      "at": 103666.734,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_callback_review.json).
