# C_dnd

Review: **PASS; 9/10**. Explicit permanent opt-out is saved and closes once; no callback is created.

Call `d4535232-534c-47b3-81b3-bb6257d2a8b7`; session `adaptive-d55a680f29bc4cb88792cf81e3f99e7d`.

Integration fixture: success; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: ముందుగా ఒక విషయం, దయచేసి ఈ నంబర్‌కి మళ్ళీ ఎప్పుడూ కాల్ చేయకండి. ఇది పర్మినెంట్, మళ్ళీ ఎప్పటికీ కాల్ చేయకూడదు.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.172s; caller intended end: True; context: finalizing/ended.

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
        "reason": "firm_refusal",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."
      },
      "result": {
        "should_end": true,
        "reason": "firm_refusal",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "do_not_call"
      },
      "transcript": "ముందుగా ఒక విషయం, దయచేసి ఈ నంబర్‌కి మళ్ళీ ఎప్పుడూ కాల్ చేయకండి. ఇది పర్మినెంట్, మళ్ళీ ఎప్పటికీ కాల్ చేయకూడదు.",
      "at": 103648.828
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103648.859
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103649.921,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_dnd.json).
