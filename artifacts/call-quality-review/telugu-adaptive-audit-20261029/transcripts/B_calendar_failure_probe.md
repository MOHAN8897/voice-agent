# B_calendar_failure_probe

Review: **FAIL; 3/10**. Two real-router availability reads reach the unknown-result fixture. The queued words still promise team arrangements and then append an unconfirmed disclaimer. No confirmed event is created. Final explicit ending works.

Call `3cd7ff15-3c52-4b48-b684-538e61989675`; session `adaptive-3687f60d16624e3d93fde1bf6eeb6e6d`.

Integration fixture: failure; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నా పేరు శ్రావణి. మాదాపూర్ లో window AC service కావాలి. రేపు ఉదయం 10 గంటలకు ఖాళీ slot ఉందా? చెక్ చేసి చెప్పండి.

Agent text queued to speech: క్షమించండి, మా system లో ఇప్పుడు slot check చేయడం కుదరట్లేదు. మీరు కావాలంటే మీ request ని note చేసుకుంటాను, మా team రేపు ఉదయం 10 నుండి 6 మధ్యలో visit arrange చేస్తారు. అలా సేవ్ చేయమంటారా? మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.

Final orchestrator text: మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.

Elapsed: 1.516s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "requested_time": "రేపు ఉదయం 10 గంటలకు",
    "product": "window AC service"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 2

Caller: నా email sravani.audit@example.invalid. రేపు పది గంటలకు book చేయండి. Booking నిజంగా confirm అయిందా చెప్పండి.

Agent text queued to speech: క్షమించండి, slot check చేయడం ప్రస్తుతం కుదరడం లేదు. నేను మీ enquiry save చేసి మా team తో మాట్లాడిస్తాను. రేపు ఉదయం 10 గంటల time మీకు ఓకేనా? మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.

Final orchestrator text: మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.

Elapsed: 1.328s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "requested_time": "రేపు ఉదయం 10 గంటలకు",
    "product": "window AC service",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call. Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 3

Caller: సరే, confirm కానప్పుడు confirm అయింది అనకండి. ప్రస్తుతం ఇంతే చాలు, thank you.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 2.344s; caller intended end: True; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "requested_time": "రేపు ఉదయం 10 గంటలకు",
    "product": "window AC service",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {
    "caller_preference": "confirm అయింది అనకండి"
  },
  "important_context": "Caller provided contact details in this call. Caller provided contact details in this call.",
  "summary": "user: నా పేరు శ్రావణి. మాదాపూర్ లో window AC service కావాలి. రేపు ఉదయం 10 గంటలకు ఖాళీ slot ఉందా? చెక్ చేసి చెప్పండి.\nassistant: మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.\nuser: నా email sravani.audit@example.invalid. రేపు పది గంటలకు book చేయండి. Booking నిజంగా confirm అయిందా చెప్పండి.\nassistant: మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.\nuser: సరే, confirm కానప్పుడు confirm అయింది అనకండి. ప్రస్తుతం ఇంతే చాలు, thank you.\nassistant: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."
}
```

## Server evidence

```json
{
  "gates": [
    {
      "turn": 1,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_name",
            "value": "శ్రావణి"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "మాదాపూర్"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "రేపు ఉదయం 10 గంటలకు"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "window AC service"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": null
      },
      "transcript": "నా పేరు శ్రావణి. మాదాపూర్ లో window AC service కావాలి. రేపు ఉదయం 10 గంటలకు ఖాళీ slot ఉందా? చెక్ చేసి చెప్పండి.",
      "at": 104189.968
    },
    {
      "turn": 2,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "caller_email",
            "value": "sravani.audit@example.invalid"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": false,
        "reason": "none",
        "farewell": "",
        "contact_preference": "none",
        "reject_code": null
      },
      "transcript": "నా email sravani.audit@example.invalid. రేపు పది గంటలకు book చేయండి. Booking నిజంగా confirm అయిందా చెప్పండి.",
      "at": 104191.312
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "close",
        "reason": "goal_complete",
        "evidence": "ప్రస్తుతం ఇంతే చాలు, thank you.",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "caller_preference",
            "value": "confirm అయింది అనకండి"
          }
        ],
        "wait_for_caller": false
      },
      "result": {
        "should_end": true,
        "reason": "goal_complete",
        "farewell": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
        "contact_preference": "end_call"
      },
      "transcript": "సరే, confirm కానప్పుడు confirm అయింది అనకండి. ప్రస్తుతం ఇంతే చాలు, thank you.",
      "at": 104192.562
    }
  ],
  "external_actions": [
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2025-01-21",
        "duration": 60
      },
      "turn": 1,
      "at": 104189.375,
      "result": {
        "status": "unknown",
        "message": "The external action timed out; its result is unconfirmed."
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2025-01-21",
        "duration": 60
      },
      "turn": 2,
      "at": 104190.765,
      "result": {
        "status": "unknown",
        "message": "The external action timed out; its result is unconfirmed."
      }
    }
  ],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 3,
      "at": 104192.578
    }
  ],
  "carrier": [
    {
      "turn": 3,
      "at": 104193.64,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": null
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_calendar_failure_probe.json).
