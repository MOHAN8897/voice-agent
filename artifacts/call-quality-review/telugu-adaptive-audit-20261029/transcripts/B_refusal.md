# B_refusal

Review: **PARTIAL; 8/10**. The caller actually said not to call again, despite the scenario asking for ordinary refusal. DND is correct for the executed wording. This is a caller-stimulus mismatch, not evidence of a false DND; use the clean repeat.

Call `c8e83589-48c1-4c90-9865-c512650504d5`; session `adaptive-03e2854b26284917a77e0323eb0ef0e9`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే సురేష్. నాకు ఇప్పుడే AC సర్వీస్ అవసరం లేదు, అందుకే నేను ఈ సర్వీస్ తీసుకోలేను. దయచేసి ఇకపై కాల్స్ చేయకండి. ధన్యవాదాలు.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.156s; caller intended end: True; context: finalizing/ended.

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
      "transcript": "నమస్తే సురేష్. నాకు ఇప్పుడే AC సర్వీస్ అవసరం లేదు, అందుకే నేను ఈ సర్వీస్ తీసుకోలేను. దయచేసి ఇకపై కాల్స్ చేయకండి. ధన్యవాదాలు.",
      "at": 103576.578
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103576.593
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103577.656,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_refusal.json).
