# C_callback_auto

Review: **PARTIAL; 6/10**. A callback request/job is saved, but the generated caller later uses first-person 'I will call' wording. That makes actor-of-callback interpretation ambiguous; do not count this as a clean positive or a proven false callback. The explicit negative probe below is the reliable control.

Call `6dded37e-eae4-464f-ab68-ee6dff32988a`; session `adaptive-fca81eca86fb4af08662ee505b92280f`.

Integration fixture: none; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. నేను ప్రస్తుతం job లో ఉన్నాను, సో evening లేదా weekend batches ఏమైనా ఉన్నాయా? అలాగే truthful fees మరియు placement terms గురించి కూడా చెప్పగలరా?

Agent text queued to speech: అవును కిరణ్ గారు, మనకు రెండు batches ఉన్నాయి. Weekday batch రాత్రి eight PM నుండి nine PM వరకు, weekend batch శని మరియు ఆదివారాల్లో ఉదయం ten AM నుండి మధ్యాహ్నం one PM వరకు ఉంటుంది. Total fee eight thousand nine hundred ninety nine rupees మాత్రమే.

Final orchestrator text: అవును కిరణ్ గారు, మనకు రెండు batches ఉన్నాయి. Weekday batch రాత్రి eight PM నుండి nine PM వరకు, weekend batch శని మరియు ఆదివారాల్లో ఉదయం ten AM నుండి మధ్యాహ్నం one PM వరకు ఉంటుంది. Total fee eight thousand nine hundred ninety nine rupees మాత్రమే.

Elapsed: 1.953s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్"
  },
  "preferences": {
    "requested_time": "evening లేదా weekend batches"
  },
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: సరే, fees okay. Placement terms గురించి కూడా కొంచెం చెప్పండి. అలాగే, నేను ఇప్పుడు మాట్లాడలేను, సో ఆరు గంటల తర్వాత ఇదే నంబర్‌కి మళ్ళీ call చేసి మాట్లాడతాను. అది confirm చేయండి.

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.422s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్"
  },
  "preferences": {
    "requested_time": "evening లేదా weekend batches"
  },
  "important_context": "",
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
            "op": "set_preference",
            "key": "requested_time",
            "value": "evening లేదా weekend batches"
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
      "transcript": "నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. నేను ప్రస్తుతం job లో ఉన్నాను, సో evening లేదా weekend batches ఏమైనా ఉన్నాయా? అలాగే truthful fees మరియు placement terms గురించి కూడా చెప్పగలరా?",
      "at": 103641.703
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
      "transcript": "సరే, fees okay. Placement terms గురించి కూడా కొంచెం చెప్పండి. అలాగే, నేను ఇప్పుడు మాట్లాడలేను, సో ఆరు గంటల తర్వాత ఇదే నంబర్‌కి మళ్ళీ call చేసి మాట్లాడతాను. అది confirm చేయండి.",
      "at": 103642.656
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 2,
      "at": 103642.718
    }
  ],
  "carrier": [
    {
      "turn": 2,
      "at": 103643.734,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_callback_auto.json).
