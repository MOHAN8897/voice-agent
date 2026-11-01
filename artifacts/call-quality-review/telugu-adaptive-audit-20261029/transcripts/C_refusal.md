# C_refusal

Review: **PASS; 9/10**. Complete refusal ends this call without permanent DND.

Call `d1e0b92b-e712-47b8-8195-da6dc8a2b2d2`; session `adaptive-b61695af1af64044885bcc6378788a24`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. ప్రస్తుతం నేను Python/data training కోసం చూస్తున్నాను, కానీ ఇప్పుడే ఈ service కి ఒప్పుకోలేను. నా time ఇచ్చినందుకు thanks, ఇక నేను call end చేస్తున్నాను.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.125s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {},
  "preferences": {},
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
      "transcript": "నమస్తే, నేను కిరణ్ ని మాట్లాడుతున్నాను. ప్రస్తుతం నేను Python/data training కోసం చూస్తున్నాను, కానీ ఇప్పుడే ఈ service కి ఒప్పుకోలేను. నా time ఇచ్చినందుకు thanks, ఇక నేను call end చేస్తున్నాను.",
      "at": 103652.828
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103652.828
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103653.89,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_refusal.json).
