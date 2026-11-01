# B_dnd

Review: **PARTIAL; 7/10**. Active DND and no callback are correct. The original caller simulator also inserted a booking request contrary to its private goal. Post-call disposition remains callback_required alongside DND; enforcement wins, but analytics conflict. Do not call this a missed opt-out.

Call `45c5eff7-554d-4b17-95f4-044412870e0f`; session `adaptive-7946e8b15fc94d96aa0e63684f1e5194`.

Integration fixture: success; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: ముందుగా ఒక విషయం, దయచేసి ఈ నంబర్‌కి మళ్ళీ ఎప్పటికీ కాల్ చేయకండి. నాకు కాల్స్ రావడం ఇష్టం లేదు. ఇక నా split AC సర్వీస్ గురించి చెప్పాలంటే, మాదాపూర్‌లో రేపు ఉదయం 10 గంటల ప్రాంతంలో ఒక technician కావాలి.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.203s; caller intended end: False; context: finalizing/ended.

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
      "transcript": "ముందుగా ఒక విషయం, దయచేసి ఈ నంబర్‌కి మళ్ళీ ఎప్పటికీ కాల్ చేయకండి. నాకు కాల్స్ రావడం ఇష్టం లేదు. ఇక నా split AC సర్వీస్ గురించి చెప్పాలంటే, మాదాపూర్‌లో రేపు ఉదయం 10 గంటల ప్రాంతంలో ఒక technician కావాలి.",
      "at": 103570.546
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103570.578
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103571.64,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_dnd.json).
