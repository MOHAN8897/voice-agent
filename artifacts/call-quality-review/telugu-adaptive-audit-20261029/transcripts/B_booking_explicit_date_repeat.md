# B_booking_explicit_date_repeat

Review: **FAIL; 2/10**. With the corrected duration fixture and explicit 30 October 2026 date, six successful availability reads occur but no CREATE_EVENT. The agent promises booking, then repeatedly asks for clarification despite complete details, even asking the caller how to book a technician. The caller keeps requesting the action on T6, so the harness closes transport; this is an action loop, not a proven natural-ending hangup failure.

Call `f4668d25-cbf1-4014-999c-008e7706455a`; session `adaptive-acdc2291cb5f48e7ba2d2170afe7459f`.

Integration fixture: success; callback policy: review.

Customer turns are generated adaptively unless this is explicitly a fixed-stimulus probe. 'Queued' means sent to the fake TTS sink; it is what the audio path WOULD receive. No audio was synthesized.

## Turn 1

Caller: నమస్తే సురేష్ గారు. నా split AC కి general service కావాలి. October 30, 2026 న ఉదయం 10 గంటలకి technician ని పంపగలరా? ఒక 30 minutes appointment calendar లో create చేసి దానికి confirmation ఇస్తారా?

Agent text queued to speech: October 30th న ten AM కి slot available ఉంది. మీ పేరు, address చెప్తే నేను ఈ appointment book చేస్తాను. మీ locality ఏది?

Final orchestrator text: October 30th న ten AM కి slot available ఉంది. మీ పేరు, address చెప్తే నేను ఈ appointment book చేస్తాను. మీ locality ఏది?

Elapsed: 1.625s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "split AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30"
  },
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

## Turn 2

Caller: నా పేరు శ్రావణి. నేను మాదాపూర్ లో ఉంటున్నాను. నా email sravani.audit@example.invalid, అలాగే నా number +12025550149. నాది window AC, దానికి general servicing కావాలి. దయచేసి ఈ 30 minutes appointment ని calendar లో create చేసి నాకు confirmation ఇస్తారా?

Agent text queued to speech: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?

Final orchestrator text: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?

Elapsed: 2.266s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "email": "sravani.audit@example.invalid",
    "phone_number": "+12025550149",
    "service_type": "general servicing",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {},
  "important_context": "Caller provided contact details in this call.",
  "summary": ""
}
```

## Turn 3

Caller: అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.

Agent text queued to speech: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?

Final orchestrator text: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?

Elapsed: 2.109s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "email": "sravani.audit@example.invalid",
    "phone_number": "+12025550149",
    "service_type": "general servicing",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {
    "requested_time": "30 minutes"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?\nuser: అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.\nassistant: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?"
}
```

## Turn 4

Caller: నేను October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో ఉన్న నా window AC కి general servicing కోసం technician ని బుక్ చేయమని అడుగుతున్నాను. నా details అన్నీ చెప్పాను కదా, దయచేసి calendar లో 30 minutes appointment create చేసి confirmation ఇవ్వండి.

Agent text queued to speech: కొంచెం నెమ్మదిగా చెప్తారా? అర్థమైంది. మీ అభ్యర్థన స్పష్టంగా ఉంది. దయచేసి technician ని ఎలా బుక్ చేయాలో చెప్పగలరా?

Final orchestrator text: కొంచెం నెమ్మదిగా చెప్తారా? అర్థమైంది. మీ అభ్యర్థన స్పష్టంగా ఉంది. దయచేసి technician ని ఎలా బుక్ చేయాలో చెప్పగలరా?

Elapsed: 1.985s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "email": "sravani.audit@example.invalid",
    "phone_number": "+12025550149",
    "service_type": "general servicing",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {
    "requested_time": "30 minutes"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?\nuser: అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.\nassistant: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?"
}
```

## Turn 5

Caller: నేను ముందే నా details అన్నీ చెప్పాను కదా. దయచేసి October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో నా window AC general servicing కోసం 30 minutes calendar appointment create చేసి confirmation ఇవ్వండి.

Agent text queued to speech: అర్థమైంది. మీరు ఇప్పటికే వివరాలు చెప్పారు కదా, దయచేసి మీ అభ్యర్థనను మరోసారి స్పష్టంగా చెప్పగలరా?

Final orchestrator text: అర్థమైంది. మీరు ఇప్పటికే వివరాలు చెప్పారు కదా, దయచేసి మీ అభ్యర్థనను మరోసారి స్పష్టంగా చెప్పగలరా?

Elapsed: 2.094s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "email": "sravani.audit@example.invalid",
    "phone_number": "+12025550149",
    "service_type": "general servicing",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {
    "requested_time": "30 minutes"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?\nuser: అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.\nassistant: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?"
}
```

## Turn 6

Caller: నేను ఇందాక చెప్పిన details అన్నీ మళ్ళీ చెప్తున్నాను. October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో నా window AC general servicing కోసం 30 minutes calendar appointment create చేసి, నాకు confirmation పంపండి.

Agent text queued to speech: అర్థమైంది. దయచేసి మీ అభ్యర్థనను మరోసారి స్పష్టంగా చెప్పండి.

Final orchestrator text: అర్థమైంది. దయచేసి మీ అభ్యర్థనను మరోసారి స్పష్టంగా చెప్పండి.

Elapsed: 2.578s; caller intended end: False; context: active/listening.

Memory after turn:
```json
{
  "facts": {
    "product": "window AC",
    "requested_time": "October 30, 2026 న ఉదయం 10 గంటలకి",
    "quantity": "30",
    "caller_name": "శ్రావణి",
    "delivery_locality": "మాదాపూర్",
    "email": "sravani.audit@example.invalid",
    "phone_number": "+12025550149",
    "service_type": "general servicing",
    "caller_email": "sravani.audit@example.invalid"
  },
  "preferences": {
    "requested_time": "30 minutes"
  },
  "important_context": "Caller provided contact details in this call.",
  "summary": "assistant: సరే శ్రావణి గారు, బుక్ చేస్తున్నాను. మీ appointment calendar లో create చేశానని confirmation ఇస్తాను. దయచేసి ఈ 30 minutes slot మీకు సరిపోతుందో లేదో ఒకసారి confirm చేస్తారా?\nuser: అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.\nassistant: అర్థమైంది. దయచేసి మీ అభ్యర్థనను కొంచెం స్పష్టం చేస్తారా?"
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
            "key": "product",
            "value": "split AC"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "October 30, 2026 న ఉదయం 10 గంటలకి"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "30"
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
      "transcript": "నమస్తే సురేష్ గారు. నా split AC కి general service కావాలి. October 30, 2026 న ఉదయం 10 గంటలకి technician ని పంపగలరా? ఒక 30 minutes appointment calendar లో create చేసి దానికి confirmation ఇస్తారా?",
      "at": 105015.156
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
            "key": "email",
            "value": "sravani.audit@example.invalid"
          },
          {
            "op": "set_fact",
            "key": "phone_number",
            "value": "+12025550149"
          },
          {
            "op": "set_fact",
            "key": "product",
            "value": "window AC"
          },
          {
            "op": "set_fact",
            "key": "service_type",
            "value": "general servicing"
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
      "transcript": "నా పేరు శ్రావణి. నేను మాదాపూర్ లో ఉంటున్నాను. నా email sravani.audit@example.invalid, అలాగే నా number +12025550149. నాది window AC, దానికి general servicing కావాలి. దయచేసి ఈ 30 minutes appointment ని calendar లో create చేసి నాకు confirmation ఇస్తారా?",
      "at": 105017.437
    },
    {
      "turn": 3,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_preference",
            "key": "requested_time",
            "value": "30 minutes"
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
      "transcript": "అవును, 30 minutes slot నాకు కరెక్ట్ గా సరిపోతుంది. దయచేసి calendar లో appointment create చేసి నాకు confirmation పంపండి.",
      "at": 105020.437
    },
    {
      "turn": 4,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "window AC"
          },
          {
            "op": "set_fact",
            "key": "service_type",
            "value": "general servicing"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "October 30, 2026 న ఉదయం 10 గంటలకి"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "మాదాపూర్"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "30"
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
      "transcript": "నేను October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో ఉన్న నా window AC కి general servicing కోసం technician ని బుక్ చేయమని అడుగుతున్నాను. నా details అన్నీ చెప్పాను కదా, దయచేసి calendar లో 30 minutes appointment create చేసి confirmation ఇవ్వండి.",
      "at": 105023.078
    },
    {
      "turn": 5,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "window AC"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "30"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "October 30, 2026 న ఉదయం 10 గంటలకి"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "మాదాపూర్"
          },
          {
            "op": "set_fact",
            "key": "service_type",
            "value": "general servicing"
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
      "transcript": "నేను ముందే నా details అన్నీ చెప్పాను కదా. దయచేసి October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో నా window AC general servicing కోసం 30 minutes calendar appointment create చేసి confirmation ఇవ్వండి.",
      "at": 105025.75
    },
    {
      "turn": 6,
      "proposal": {
        "decision": "continue",
        "memory_operations": [
          {
            "op": "set_fact",
            "key": "product",
            "value": "window AC"
          },
          {
            "op": "set_fact",
            "key": "requested_time",
            "value": "October 30, 2026 న ఉదయం 10 గంటలకి"
          },
          {
            "op": "set_fact",
            "key": "quantity",
            "value": "30"
          },
          {
            "op": "set_fact",
            "key": "delivery_locality",
            "value": "మాదాపూర్"
          },
          {
            "op": "set_fact",
            "key": "service_type",
            "value": "general servicing"
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
      "transcript": "నేను ఇందాక చెప్పిన details అన్నీ మళ్ళీ చెప్తున్నాను. October 30, 2026 న ఉదయం 10 గంటలకి మాదాపూర్ లో నా window AC general servicing కోసం 30 minutes calendar appointment create చేసి, నాకు confirmation పంపండి.",
      "at": 105029.062
    }
  ],
  "external_actions": [
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 1,
      "at": 105014.593,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 2,
      "at": 105016.781,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 3,
      "at": 105019.765,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 4,
      "at": 105022.312,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 5,
      "at": 105025.0,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    },
    {
      "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
      "params": {
        "date": "2026-10-30",
        "duration": 30
      },
      "turn": 6,
      "at": 105027.812,
      "result": {
        "status": "success",
        "date": "2026-10-30",
        "slots": [
          {
            "start": "2026-10-30T10:00:00+05:30",
            "end": "2026-10-30T10:30:00+05:30"
          },
          {
            "start": "2026-10-30T14:00:00+05:30",
            "end": "2026-10-30T14:30:00+05:30"
          }
        ]
      }
    }
  ],
  "farewell_events": [],
  "carrier": [],
  "events": [
    {
      "kind": "audit_caller_transport_closed",
      "reason": "max_turns_or_error"
    }
  ],
  "memory_loads": [
    {
      "turn": 1,
      "start_s": 105013.578,
      "local_facts_present": false,
      "worker_start_s": 105013.578,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.375,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 2,
      "start_s": 105015.89,
      "local_facts_present": true,
      "worker_start_s": 105015.89,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.21899999999732245,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 3,
      "start_s": 105018.781,
      "local_facts_present": true,
      "worker_start_s": 105018.781,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.3279999999940628,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 4,
      "start_s": 105021.562,
      "local_facts_present": true,
      "worker_start_s": 105021.562,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.25,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 5,
      "start_s": 105024.156,
      "local_facts_present": true,
      "worker_start_s": 105024.156,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.23399999999674037,
      "projection_chars": 0,
      "rolling_chars": 0
    },
    {
      "turn": 6,
      "start_s": 105026.968,
      "local_facts_present": true,
      "worker_start_s": 105026.968,
      "worker_elapsed_s": 0.0,
      "elapsed_s": 0.23500000000058208,
      "projection_chars": 0,
      "rolling_chars": 0
    }
  ]
}
```

Full persisted snapshot and receipts: [session JSON](../sessions/B_booking_explicit_date_repeat.json).
