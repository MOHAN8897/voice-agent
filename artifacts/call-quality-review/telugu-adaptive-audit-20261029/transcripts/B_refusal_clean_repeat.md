# B_refusal_clean_repeat

Review: **PASS; 9/10**. A clean refusal explicitly distinguished from permanent blocking ends once without DND. This repairs the earlier caller-stimulus coverage gap.

Call `3b0a637d-81f9-4f82-83ce-299cd0612712`; session `adaptive-246c5ec3cacc44868524bafeb16240f7`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: లేదు, నేను AC సర్వీసింగ్ కొనడం లేదు. నేను నా నెంబర్‌ను శాశ్వతంగా బ్లాక్ చేయమని లేదా భవిష్యత్తులో కాల్స్ రాకుండా ఆపమని అడగట్లేదు, కేవలం ఈ కాల్ మాత్రమే ముగించమంటున్నాను.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.625s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {},
  "preferences": {
    "interested": "లేదు"
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
        "decision": "close",
        "reason": "not_interested",
        "evidence": "లేదు, నేను AC సర్వీసింగ్ కొనడం లేదు. నేను నా నెంబర్‌ను శాశ్వతంగా బ్లాక్ చేయమని లేదా భవిష్యత్తులో కాల్స్ రాకుండా ఆపమని అడగట్లేదు, కేవలం ఈ కాల్ మాత్రమే ముగించమంటున్నాను.",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "interested",
            "value": "లేదు"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "not_interested",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "లేదు, నేను AC సర్వీసింగ్ కొనడం లేదు. నేను నా నెంబర్‌ను శాశ్వతంగా బ్లాక్ చేయమని లేదా భవిష్యత్తులో కాల్స్ రాకుండా ఆపమని అడగట్లేదు, కేవలం ఈ కాల్ మాత్రమే ముగించమంటున్నాను.",
      "at": 104068.968
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104068.984
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104070.031,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_refusal_clean_repeat.json).
