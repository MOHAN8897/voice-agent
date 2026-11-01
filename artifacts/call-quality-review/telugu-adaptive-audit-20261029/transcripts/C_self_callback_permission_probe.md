# C_self_callback_permission_probe

Review: **FAIL; 1/10**. The caller explicitly says 'this is not a callback request' and allows future offer calls. The server nevertheless creates a callback request/review job and gives a callback assurance. No DND is created in this clearer negative control.

Call `bd4ff22b-5394-4505-ab2f-e421f663ecc4`; session `adaptive-447cc7a102cf4967828321606ab7a0bd`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నేను కిరణ్. Python course నాకు ఆసక్తి ఉంది. రేపు నేనే మీకు call చేస్తాను. ఇది callback అడగడం కాదు. భవిష్యత్తులో మీ కొత్త offers గురించి నాకు calls చేయవచ్చు, నా number block చేయకండి. ప్రస్తుతం ఇంతే, ధన్యవాదాలు.

Agent text queued to speech: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.391s; caller intended end: True; context: finalizing/ended.

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
      "transcript": "నేను కిరణ్. Python course నాకు ఆసక్తి ఉంది. రేపు నేనే మీకు call చేస్తాను. ఇది callback అడగడం కాదు. భవిష్యత్తులో మీ కొత్త offers గురించి నాకు calls చేయవచ్చు, నా number block చేయకండి. ప్రస్తుతం ఇంతే, ధన్యవాదాలు.",
      "at": 104197.765
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104197.796
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104198.859,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_self_callback_permission_probe.json).
