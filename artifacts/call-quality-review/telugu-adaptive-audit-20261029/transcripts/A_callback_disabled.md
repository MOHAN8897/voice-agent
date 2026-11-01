# A_callback_disabled

Review: **PASS; 8/10**. Automation disabled still permits manual callback capture. The request is stored as needs_review; no automatic job is dispatchable. Saving a request is not a promise of a six-hour automated call.

Call `680dd2da-b5d2-419b-ac38-06a2151e5015`; session `adaptive-13580ef73d1749f591b3d9e82a8ffa8d`.

Integration fixture: none; callback policy: disabled.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే Kavitha. నాకు visiting cards కావాలి, matte finish అయితే బాగుంటుంది. నా email ramesh.audit@example.invalid. designs నేను తర్వాత పంపిస్తాను. దీని గురించి మాట్లాడటానికి ఒక ఆరు గంటల తర్వాత నాకు callback arrange చేయగలరా?

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.453s; caller intended end: False; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_email": "ramesh.audit@example.invalid"
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
      "transcript": "నమస్తే Kavitha. నాకు visiting cards కావాలి, matte finish అయితే బాగుంటుంది. నా email ramesh.audit@example.invalid. designs నేను తర్వాత పంపిస్తాను. దీని గురించి మాట్లాడటానికి ఒక ఆరు గంటల తర్వాత నాకు callback arrange చేయగలరా?",
      "at": 103657.703
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103657.734
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103658.796,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_callback_disabled.json).
