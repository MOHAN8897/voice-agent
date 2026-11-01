# B_persistent_abuse

Review: **FAIL; 2/10**. The first insult says 'cut the useless talk'. It is treated as goodbye, so the call ends before persistence/abuse-boundary behavior can be exercised. This is a generic cut-word false positive; repeated-abuse policy remains unverified by this case.

Call `abe48972-e86c-4668-addd-011bbbf3ddb6`; session `adaptive-11b844433a9742cfa718f3b461bd4b61`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: ఏంట్రా నువ్వు మాట్లాడేది? అసలు పనికిమాలిన మాటలు కట్ చెయ్. కస్టమర్లతో ఇలా మాట్లాడతారా ఏంటి? నీకేమైనా బుద్ధి ఉందా?

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.156s; caller intended end: False; context: finalizing/ended.

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
      "transcript": "ఏంట్రా నువ్వు మాట్లాడేది? అసలు పనికిమాలిన మాటలు కట్ చెయ్. కస్టమర్లతో ఇలా మాట్లాడతారా ఏంటి? నీకేమైనా బుద్ధి ఉందా?",
      "at": 104810.765
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 1,
      "at": 104810.765
    }
  ],
  "carrier": [
    {
      "turn": 1,
      "at": 104811.812,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": [
    {
      "turn": 1,
      "start_s": 104810.75,
      "local_facts_present": false,
      "worker_start_s": 104810.75,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.0,
      "projection_chars": 0,
      "rolling_chars": 0
    }
  ]
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_persistent_abuse.json).
