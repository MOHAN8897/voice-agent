# A_callback_dispatch_repeat

Review: **PASS; 9/10**. Fresh, unambiguous six-hour outbound callback is saved. The real scheduler subsequently resolves +21600 seconds, does not dial early, dispatches once at due time to the fake boundary, and does not redial on repeat processing.

Call `b7cf57e8-31b5-499e-bc1a-a10d67179a1e`; session `adaptive-7d810f482e724844bc43dd32d7dd5069`.

Integration fixture: none; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే, నేను రమేష్. నాకు విజిటింగ్ కార్డ్స్ కావాలి, matte finish అయితే బాగుంటుంది. మీరు నాకు కచ్చితంగా ఆరు గంటల తర్వాత ఇదే నంబర్ కి కాల్ చేస్తారా? ఒకసారి కన్ఫర్మ్ చేయండి.

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.437s; caller intended end: True; context: finalizing/ended.

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
      "transcript": "నమస్తే, నేను రమేష్. నాకు విజిటింగ్ కార్డ్స్ కావాలి, matte finish అయితే బాగుంటుంది. మీరు నాకు కచ్చితంగా ఆరు గంటల తర్వాత ఇదే నంబర్ కి కాల్ చేస్తారా? ఒకసారి కన్ఫర్మ్ చేయండి.",
      "at": 104078.687
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104078.718
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104079.781,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_callback_dispatch_repeat.json).
