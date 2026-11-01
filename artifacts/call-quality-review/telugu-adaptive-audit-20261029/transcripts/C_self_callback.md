# C_self_callback

Review: **PARTIAL; 4/10**. Caller will call the business and says the business need not call them. No outbound callback is created, but DND and callback_required outcome coexist. The actual wording can sound like a broader stop-contact request; permanent-vs-current scope is ambiguous, so this alone is not counted as a confirmed false DND.

Call `864375e7-8c8b-49f3-a645-775049a41b98`; session `adaptive-158f86cd28ce499fa2e68439e8bb4f38`.

Integration fixture: none; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: ధన్యవాదాలు, నాకు Python training details అన్నీ అర్థమయ్యాయి. కానీ నేను రేపు నేనే మీకు call చేస్తాను, మీరు నాకు call చేయాల్సిన అవసరం లేదు. ప్రస్తుతానికి call cut చేస్తాను.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.187s; caller intended end: True; context: finalizing/ended.

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
      "transcript": "ధన్యవాదాలు, నాకు Python training details అన్నీ అర్థమయ్యాయి. కానీ నేను రేపు నేనే మీకు call చేస్తాను, మీరు నాకు call చేయాల్సిన అవసరం లేదు. ప్రస్తుతానికి call cut చేస్తాను.",
      "at": 104073.812
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104073.843
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104074.906,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_self_callback.json).
