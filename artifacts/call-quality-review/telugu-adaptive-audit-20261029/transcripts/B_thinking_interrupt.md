# B_thinking_interrupt

Review: **PASS; 9/10**. During actual thinking with zero queued speech, a correction changes split AC to window AC. The real cancel/merge/relaunch path replies with window AC ₹499 and remembers it next turn, without speaking the obsolete split-AC answer. This is text-level interruption evidence, not acoustic VAD evidence.

Call `d920d578-c9bc-4696-a1de-2eecbcee739f`; session `adaptive-ae0da4b3d58440adb61a75271078b919`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నాకు split AC service కావాలి. దాని ధర ఎంత?

Agent text queued to speech: Window AC servicing కి four hundred ninety nine rupees అవుతుంది. మీకు appointment కావాలా?

Final orchestrator text: Window AC servicing కి four hundred ninety nine rupees అవుతుంది. మీకు appointment కావాలా?

Elapsed: 1.546s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC service"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: నాకు ఇప్పుడు window AC service కావాలి అన్నది గుర్తుందా?

Agent text queued to speech: అవును, గుర్తుంది. Window AC servicing కి four hundred ninety nine rupees అవుతుంది. మీరు appointment book చేయమంటారా?

Final orchestrator text: అవును, గుర్తుంది. Window AC servicing కి four hundred ninety nine rupees అవుతుంది. మీరు appointment book చేయమంటారా?

Elapsed: 1.593s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC service"
  },
  "preferences": {
    "service_timing": "ఇప్పుడు"
  },
  "important_context": "",
  "summary": ""
}
```

## Turn 3

Caller: సరే, నా ప్రశ్నలు అయిపోయాయి. ధన్యవాదాలు.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.422s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC service"
  },
  "preferences": {
    "service_timing": "ఇప్పుడు"
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
            "key": "product",
            "value": "window AC service"
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
      "transcript": "నాకు split AC service కావాలి. దాని ధర ఎంత? ముందు చెప్పింది మార్చుతున్నాను. నాకు split AC కాదు, window AC service కావాలి. దాని ధర ఎంత?",
      "at": 104203.39
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "service_timing",
            "value": "ఇప్పుడు"
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
      "transcript": "నాకు ఇప్పుడు window AC service కావాలి అన్నది గుర్తుందా?",
      "at": 104205.015
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "సరే, నా ప్రశ్నలు అయిపోయాయి. ధన్యవాదాలు.",
        "memory_operations": [],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "సరే, నా ప్రశ్నలు అయిపోయాయి. ధన్యవాదాలు.",
      "at": 104206.359
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 3,
      "at": 104206.359
    }
  ],
  "carrier": [
    {
      "turn": 3,
      "at": 104207.421,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [
    {
      "kind": "caller_interrupt_while_thinking",
      "text": "ముందు చెప్పింది మార్చుతున్నాను. నాకు split AC కాదు, window AC service కావాలి. దాని ధర ఎంత?",
      "phase": "thinking",
      "queued_speech_before": 0
    }
  ],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_thinking_interrupt.json).
