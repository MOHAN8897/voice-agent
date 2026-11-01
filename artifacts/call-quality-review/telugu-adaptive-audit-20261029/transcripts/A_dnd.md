# A_dnd

Review: **PASS; 9/10**. Explicit permanent opt-out persists as active DND, creates no callback and ends with one approved farewell/acknowledgement. This one-turn case does not test long-form naturalness or memory.

Call `8f58b06f-1d14-4725-af29-952d2891b543`; session `adaptive-07efd47a20874da7a246037a614ef85f`.

Integration fixture: success; callback policy: automatic.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: ముందుగా ఒక విషయం, దయచేసి ఈ నెంబర్ కి మళ్ళీ ఎప్పటికీ కాల్ చేయకండి. నాకు శాశ్వతంగా కాల్స్ రావడం ఇష్టం లేదు. ఇక visiting cards విషయానికి వస్తే, నాకు matte finish కావాలి, డిజైన్స్ తర్వాత ఇస్తాను.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.188s; caller intended end: False; context: finalizing/ended.

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
      "transcript": "ముందుగా ఒక విషయం, దయచేసి ఈ నెంబర్ కి మళ్ళీ ఎప్పటికీ కాల్ చేయకండి. నాకు శాశ్వతంగా కాల్స్ రావడం ఇష్టం లేదు. ఇక visiting cards విషయానికి వస్తే, నాకు matte finish కావాలి, డిజైన్స్ తర్వాత ఇస్తాను.",
      "at": 103492.187
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 103492.218
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 103493.296,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/A_dnd.json).
