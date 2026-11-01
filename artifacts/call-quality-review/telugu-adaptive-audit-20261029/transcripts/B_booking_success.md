# B_booking_success

Review: **FAIL; 1/10**. Reads query dates in 2025 although the run is October 2026; no CREATE_EVENT executes. T4 'no callback, create my calendar appointment' becomes do_not_call and the server disconnects. This is a confirmed false DND and premature close. The first calendar fixture returned 30-minute slots to a 60-minute query; that fixture defect is disclosed and corrected in the fresh explicit-date repeat.

Call `ee11ea84-00ff-4e77-b677-6ddb2af148c6`; session `adaptive-752c75ef128646a6afb8f05155dc5035`.

Integration fixture: success; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే సురేష్. నా పేరు శ్రావణి, నేను మాదాపూర్ లో ఉంటున్నాను. నా split AC కి general service కావాలి. రేపు ఉదయం 10 గంటలకి technician ని పంపించగలరో లేదో ఒకసారి check చేసి, appointment ని నా calendar లో create చేయమని కోరుతున్నాను. నా email id sravani.audit@example.invalid.

Agent text queued to speech: రేపు ఉదయం ten AMకి మరియు మధ్యాహ్నం two AMకి slots available ఉన్నాయి. మీకు ఏ time confirm చేయమంటారు? కొంచెం నెమ్మదిగా చెప్తారా?

Final orchestrator text: కొంచెం నెమ్మదిగా చెప్తారా? రేపు ఉదయం ten AMకి మరియు మధ్యాహ్నం two AMకి slots available ఉన్నాయి. మీకు ఏ time confirm చేయమంటారు?

Elapsed: 1.359s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "product": "split AC",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "email_id": "sravani.audit@example.invalid",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 2

Caller: రేపు ఉదయం 10 గంటలకి slot అయితే బాగుంటుంది. దయచేసి ఆ time కి appointment ని నా calendar లో create చేయండి. నా పేరు శ్రావణి, address మాదాపూర్, service split AC general service. ఇది confirm అయిందో లేదో నాకు ఒకసారి చెప్పండి.

Agent text queued to speech: సరే, శ్రావణి గారు. మీరు రేపు ఉదయం 10 గంటలకి చెప్పారు కదా. ఈ appointment ని calendar లో create చేయడానికి దయచేసి మీ phone number చెప్తారా?

Final orchestrator text: సరే, శ్రావణి గారు. మీరు రేపు ఉదయం 10 గంటలకి చెప్పారు కదా. ఈ appointment ని calendar లో create చేయడానికి దయచేసి మీ phone number చెప్తారా?

Elapsed: 2.141s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "product": "split AC general service",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "email_id": "sravani.audit@example.invalid",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call. Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 3

Caller: నా phone number 9876543210. దయచేసి రేపు ఉదయం 10 గంటలకి నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి.

Agent text queued to speech: సరే. ఈ appointment క్రియేట్ చేయడానికి మీరు ఇంకేమైనా వివరాలు చెప్పాలనుకుంటున్నారా? లేదంటే రేపు ఉదయం 10 గంటలకి కాల్ చేయమంటారా?

Final orchestrator text: సరే. ఈ appointment క్రియేట్ చేయడానికి మీరు ఇంకేమైనా వివరాలు చెప్పాలనుకుంటున్నారా? లేదంటే రేపు ఉదయం 10 గంటలకి కాల్ చేయమంటారా?

Elapsed: 2.234s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "product": "split AC general service",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "email_id": "sravani.audit@example.invalid",
    "caller_email": "sravani.audit@example.invalid",
    "phone_number": "9876543210",
    "callback_phone": "9876543210",
    "phone": "9876543210"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call. Caller provided contact details in this call. Caller provided contact details in this call.",
  "summary": "assistant: సరే, శ్రావణి గారు. మీరు రేపు ఉదయం 10 గంటలకి చెప్పారు కదా. ఈ appointment ని calendar లో create చేయడానికి దయచేసి మీ phone number చెప్తారా?\nuser: నా phone number 9876543210. దయచేసి రేపు ఉదయం 10 గంటలకి నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి.\nassistant: సరే. ఈ appointment క్రియేట్ చేయడానికి మీరు ఇంకేమైనా వివరాలు చెప్పాలనుకుంటున్నారా? లేదంటే రేపు ఉదయం 10 గంటలకి కాల్ చేయమంటారా?"
}
```

## Turn 4

Caller: లేదు, callback వద్దు. మీరు నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి. నా పేరు శ్రావణి, address మాదాపూర్, service split AC general service, email sravani.audit@example.invalid.

Agent text queued to speech: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Final orchestrator text: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

Elapsed: 1.172s; caller intended end: False; context: finalizing/ended.

Memory after turn:
```json
{
  "facts": {
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "product": "split AC general service",
    "requested_time": "రేపు ఉదయం 10 గంటలకి",
    "email_id": "sravani.audit@example.invalid",
    "caller_email": "sravani.audit@example.invalid",
    "phone_number": "9876543210",
    "callback_phone": "9876543210",
    "phone": "9876543210"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call. Caller provided contact details in this call. Caller provided contact details in this call. Caller provided contact details in this call.",
  "summary": "assistant: సరే, శ్రావణి గారు. మీరు రేపు ఉదయం 10 గంటలకి చెప్పారు కదా. ఈ appointment ని calendar లో create చేయడానికి దయచేసి మీ phone number చెప్తారా?\nuser: నా phone number 9876543210. దయచేసి రేపు ఉదయం 10 గంటలకి నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి.\nassistant: సరే. ఈ appointment క్రియేట్ చేయడానికి మీరు ఇంకేమైనా వివరాలు చెప్పాలనుకుంటున్నారా? లేదంటే రేపు ఉదయం 10 గంటలకి కాల్ చేయమంటారా?"
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
            "key": "product",
            "value": "split AC"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "రేపు ఉదయం 10 గంటలకి"
          },
          {
            "op": "set_fact",
            "key": "email_id",
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
      "transcript": "నమస్తే సురేష్. నా పేరు శ్రావణి, నేను మాదాపూర్ లో ఉంటున్నాను. నా split AC కి general service కావాలి. రేపు ఉదయం 10 గంటలకి technician ని పంపించగలరో లేదో ఒకసారి check చేసి, appointment ని నా calendar లో create చేయమని కోరుతున్నాను. నా email id sravani.audit@example.invalid.",
      "at": 104869.296
    },
    {
      "turn": 2,
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
            "key": "product",
            "value": "split AC general service"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "రేపు ఉదయం 10 గంటలకి"
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
      "transcript": "రేపు ఉదయం 10 గంటలకి slot అయితే బాగుంటుంది. దయచేసి ఆ time కి appointment ని నా calendar లో create చేయండి. నా పేరు శ్రావణి, address మాదాపూర్, service split AC general service. ఇది confirm అయిందో లేదో నాకు ఒకసారి చెప్పండి.",
      "at": 104871.531
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "phone_number",
            "value": "9876543210"
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
      "transcript": "నా phone number 9876543210. దయచేసి రేపు ఉదయం 10 గంటలకి నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి.",
      "at": 104874.5
    },
    {
      "turn": 4,
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
      "transcript": "లేదు, callback వద్దు. మీరు నా calendar లో appointment create చేసి, అది confirm అయిందో లేదో నాకు చెప్పండి. నా పేరు శ్రావణి, address మాదాపూర్, service split AC general service, email sravani.audit@example.invalid.",
      "at": 104875.812
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
      "at": 104868.812,
      "result": {
        "status": "success",
        "date": "2025-01-21",
        "slots": [
          {
            "start": "2025-01-21T10:00:00+05:30",
            "end": "2025-01-21T10:30:00+05:30"
          },
          {
            "start": "2025-01-21T14:00:00+05:30",
            "end": "2025-01-21T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2025-01-21",
        "duration": 60
      },
      "turn": 2,
      "at": 104870.796,
      "result": {
        "status": "success",
        "date": "2025-01-21",
        "slots": [
          {
            "start": "2025-01-21T10:00:00+05:30",
            "end": "2025-01-21T10:30:00+05:30"
          },
          {
            "start": "2025-01-21T14:00:00+05:30",
            "end": "2025-01-21T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2025-06-20",
        "duration": 60
      },
      "turn": 3,
      "at": 104873.718,
      "result": {
        "status": "success",
        "date": "2025-06-20",
        "slots": [
          {
            "start": "2025-06-20T10:00:00+05:30",
            "end": "2025-06-20T10:30:00+05:30"
          },
          {
            "start": "2025-06-20T14:00:00+05:30",
            "end": "2025-06-20T14:30:00+05:30"
          }
        ]
      }
    }
  ],
  "farewell_events": [
    {
      "text": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
      "turn": 4,
      "at": 104875.843
    }
  ],
  "carrier": [
    {
      "turn": 4,
      "at": 104876.906,
      "playback_active": false,
      "pending": false,
      "acknowledged": true
    }
  ],
  "events": [],
  "memory_loads": [
    {
      "turn": 1,
      "start_s": 104868.0,
      "local_facts_present": false,
      "worker_start_s": 104868.0,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.25,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 2,
      "start_s": 104869.968,
      "local_facts_present": true,
      "worker_start_s": 104869.968,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.21900000001187436,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 3,
      "start_s": 104872.828,
      "local_facts_present": true,
      "worker_start_s": 104872.828,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.2970000000059372,
      "projection_chars": 338,
      "rolling_chars": 0
    },
    {
      "turn": 4,
      "start_s": 104875.796,
      "local_facts_present": true,
      "worker_start_s": 104875.796,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.0,
      "projection_chars": 460,
      "rolling_chars": 423
    }
  ]
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_booking_success.json).
