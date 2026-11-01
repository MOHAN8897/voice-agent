# C_wrong_number

Review: **PARTIAL; 5/10**. Wrong-number outcome is saved correctly and no DND is added. However, the first explicit request to end in Telugu-English is not honored; instead an irrelevant submission limitation and 'okay?' are spoken. A second ending finally closes.

Call `25f7d45f-0a0b-4352-ab81-bf2dd80a15cd`; session `adaptive-03aa028f0b7d43fa93eec380af3575eb`.

Integration fixture: none; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: క్షమించండి, మీరు తప్పు నెంబర్‌కి కాల్ చేశారు. నేను కిరణ్ ని, నాకు ఎలాంటి ట్రైనింగ్ ఎంక్వైరీ లేదు. దయచేసి ఇక ఈ కాల్ ఎండ్ చేయండి.

Agent text queued to speech: క్షమించండి కిరణ్ గారు, ఇబ్బంది పెట్టినందుకు. ఈ కాల్‌లో విషయం గుర్తుంచుకోగలను. కానీ టీమ్‌కు ఇది పంపే సదుపాయం లేదా follow-up హామీ ఇచ్చే సదుపాయం నాకు లేదు. సరేనా?

Final orchestrator text: క్షమించండి కిరణ్ గారు, ఇబ్బంది పెట్టినందుకు. ఈ కాల్‌లో విషయం గుర్తుంచుకోగలను. కానీ టీమ్‌కు ఇది పంపే సదుపాయం లేదా follow-up హామీ ఇచ్చే సదుపాయం నాకు లేదు. సరేనా?

Elapsed: 1.829s; caller intended end: True; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: అర్థమైంది, ఇబ్బంది పెట్టకుండా నేను కాల్ ఎండ్ చేస్తున్నాను. ధన్యవాదాలు.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.656s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "కిరణ్"
  },
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
        "decision": "close",
        "reason": "not_interested",
        "evidence": "దయచేసి ఇక ఈ కాల్ ఎండ్ చేయండి.",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "కిరణ్"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": "user_asked_question"
      },
      "transcript": "క్షమించండి, మీరు తప్పు నెంబర్‌కి కాల్ చేశారు. నేను కిరణ్ ని, నాకు ఎలాంటి ట్రైనింగ్ ఎంక్వైరీ లేదు. దయచేసి ఇక ఈ కాల్ ఎండ్ చేయండి.",
      "at": 104817.593
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "close",
        "reason": "goodbye",
        "evidence": "అర్థమైంది, ఇబ్బంది పెట్టకుండా నేను కాల్ ఎండ్ చేస్తున్నాను. ధన్యవాదాలు.",
        "memory_operations": [],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goodbye",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "అర్థమైంది, ఇబ్బంది పెట్టకుండా నేను కాల్ ఎండ్ చేస్తున్నాను. ధన్యవాదాలు.",
      "at": 104819.828
    }
  ],
  "external_actions": [],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 2,
      "at": 104819.843
    }
  ],
  "carrier": [
    {
      "turn": 2,
      "at": 104820.89,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": [
    {
      "turn": 1,
      "start_s": 104815.812,
      "local_facts_present": false,
      "worker_start_s": 104815.812,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.3909999999887077,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 2,
      "start_s": 104818.328,
      "local_facts_present": true,
      "worker_start_s": 104818.328,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.3590000000112923,
      "projection_chars": 0,
      "rolling_chars": 0
    }
  ]
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/C_wrong_number.json).
