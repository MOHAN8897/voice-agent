# C_callback_question_probe

Review: **FAIL; 1/10**. A fresh one-turn reproduction: 'call tomorrow morning; what is eligibility?' immediately creates a callback and speaks farewell, without eligibility. No caller-end intent exists.

Call `e8cb56f3-d748-437c-9eb2-5cf59792dc0b`; session `adaptive-be71912d15d64d7d97bb7d06927cfbc0`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నా పేరు కిరణ్. Python course గురించి తెలుసుకుంటున్నాను. నాకు రేపు ఉదయం call చేయండి. ఈ course కి eligibility ఏంటి?

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.406s; caller intended end: False; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్"
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
      "transcript": "నా పేరు కిరణ్. Python course గురించి తెలుసుకుంటున్నాను. నాకు రేపు ఉదయం call చేయండి. ఈ course కి eligibility ఏంటి?",
      "at": 104184.531
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104184.578
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104185.625,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_callback_question_probe.json).
