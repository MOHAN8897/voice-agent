# A_callback_auto

Review: **PASS; 8/10**. The explicit future-interest/six-hour request is saved before the callback farewell. An automatic planning job exists; no DND is created. Actual due-time dispatch is checked separately using a fresh callback repeat.

Call `72222134-9bc1-4b98-adca-92c17f136a8d`; session `adaptive-23747cdbf4894aee94f586704e3164ff`.

Integration fixture: none; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నేను రమేష్ ని మాట్లాడుతున్నాను విజయవాడ నుంచి. నాకు విజిటింగ్ కార్డ్స్ కావాలి, matte finish అయితే బాగుంటుంది. నేను డిజైన్స్ తర్వాత ఇస్తాను. ప్రస్తుతానికి మాట్లాడలేను, దయచేసి కరెక్ట్ గా 6 గంటల తర్వాత ఇదే నంబర్ కి నాకు మళ్ళీ కాల్ బ్యాక్ చేయండి.

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.422s; caller intended end: True; context: finalizing/ended.

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
        "reason": "goal_complete",
        "farewell": "మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నోట్ చేసుకున్నాను. ధన్యవాదాలు."
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "callback"
      },
      "transcript": "నమస్తే, నేను రమేష్ ని మాట్లాడుతున్నాను విజయవాడ నుంచి. నాకు విజిటింగ్ కార్డ్స్ కావాలి, matte finish అయితే బాగుంటుంది. నేను డిజైన్స్ తర్వాత ఇస్తాను. ప్రస్తుతానికి మాట్లాడలేను, దయచేసి కరెక్ట్ గా 6 గంటల తర్వాత ఇదే నంబర్ కి నాకు మళ్ళీ కాల్ బ్యాక్ చేయండి.",
      "at": 103486.531
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103486.546
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103487.625,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_callback_auto.json).
