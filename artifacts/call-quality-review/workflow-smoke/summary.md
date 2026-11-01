# Workflow simulation workflow-smoke

Schema `sim_61dcf7e600d144e9af0910a0b740f4ca`.

| Scenario | Pass | Failures |
|---|---|---|
| callback | 0/1 | disposition:no_outcome |
| dnd | 1/1 | - |
| order | 0/1 | disposition:no_outcome, speech:too_many_sentences:4 |

| Missed-call mode | DND | Jobs | Pass |
|---|---|---|---|
| off | False | [] | True |
| review | False | [('missed', 'needs_review', 'approval_required')] | True |
| automatic | False | [('missed', 'scheduled', 'missed_call')] | True |
| automatic | True | [('missed', 'scheduled', 'missed_call')] | False |

## Transcripts

### te-IN/callback/realestate FAIL — disposition no_outcome ['disposition:no_outcome']
- opening: హలో, నేను Green Acres Realty నుండి Ravi. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను. రేపు సాయంత్రం 6 కి మళ్ళీ call చేయగలరా?
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/dnd/appliance PASS — disposition not_interested []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: దయచేసి ఈ number కి మళ్ళీ ఎప్పుడూ call చేయకండి. నా number ని మీ list నుంచి తీసేయండి.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order/printing FAIL — disposition no_outcome ['disposition:no_outcome', 'speech:too_many_sentences:4', 'speech:too_many_sentences:4']
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు 200 matte visiting cards కావాలి.
- agent: సరే, 200 matte finish visiting cards కి మొత్తం ₹700 అవుతుంది. Minimum order 100 cards కాబట్టి ఇది కుదురుతుంది. మీ పేరు, delivery address చెప్తారా? Order confirm చేస్తాను.
- caller: నా పేరు Ravi Kumar. Vijayawada లోని 12 MG Road కి deliver చేయండి.
- agent: మీ order confirm అయింది. 200 matte finish visiting cards, delivery address 12 MG Road, Vijayawada. Artwork approval తర్వాత 3 working days లో delivery అవుతుంది. Cash on delivery ఉంటుంది.
- caller: అవును, order confirm చేయండి.
- agent: మీ order confirm అయింది. ఇంకేమైనా సహాయం కావాలా?
- caller: Thanks, అంతే.
- agent: సరే, మీ order already confirm అయింది. ఇంకేమైనా వివరాలు కావాలా? లేదంటే ఇక్కడితో ముగిద్దామా?
