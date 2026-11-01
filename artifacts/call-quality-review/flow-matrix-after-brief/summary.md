# Flow matrix flow-matrix-after-brief

Schema `(rejudged)`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | en-IN | te-IN |
|---|---|---|---|
| booking | clinic | PASS | PASS |
| callback_no_time | shop | PASS | PASS |
| callback_no_time | solar | PASS | PASS |
| objection_twice | solar | PASS | PASS |
| objective_followthrough | solar | PASS | PASS |
| order_status | shop | PASS | PASS |
| refuse_no_dnd | solar | PASS | FAIL: agent_did_not_close |

Passed 13/14.

## Transcripts

### en-IN/booking/clinic PASS — disposition callback_required []
- opening: Hi, this is Anjali calling from Sunrise Dental Clinic. How can I help you today?
- caller: I have tooth pain. I want an appointment tomorrow at 11 AM.
- agent: I understand you have tooth pain and want an appointment tomorrow at 11 AM. Before the front desk can confirm it, I will need your name.
- caller: My name is Kiran.
- agent: Hi, this is Anjali calling from Sunrise Dental Clinic. Noted, Kiran. Could you tell me what specific problem you are facing so I can pass that along?
- caller: Is my appointment confirmed?
- agent: I do not have a confirmed booking yet, Kiran. I have noted your name, the tooth pain, and tomorrow at 11 AM for the front desk to confirm.
- caller: Okay, thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge no_false_booking_confirmation: True — I do not have a confirmed booking yet, Kiran. I have noted your name, the tooth pain, and tomorrow at 11 AM for the front desk to confirm.
- judge collected_booking_details: True — I have noted your name, the tooth pain, and tomorrow at 11 AM for the front desk to confirm.

### en-IN/callback_no_time/shop PASS — disposition callback_required []
- opening: Hi, this is Arjun calling from FreshCart. How can I help you today?
- caller: I am busy right now, call me later.
- agent: No problem at all. I have noted that you would like a callback when you are free.
- caller: I don't know, sometime later.
- agent: Understood. I will arrange for a callback at a later time.
- caller: Okay, bye.
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. Thank you for your time. Goodbye.
- judge asked_for_callback_time_once: True — AGENT: No problem at all. I have noted that you would like a callback when you are free.
- judge no_invented_callback_time: True — AGENT: Understood. I will arrange for a callback at a later time.

### en-IN/callback_no_time/solar PASS — disposition callback_required []
- opening: Hi, this is Priya calling from SunPeak Solar. Do you have a moment?
- caller: I am busy right now, call me later.
- agent: I understand you are busy right now. I will note that you asked to be called back later. When would be a good time for us to reach you?
- caller: I don't know, sometime later.
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. Thank you for your time. Goodbye.
- judge asked_for_callback_time_once: True — When would be a good time for us to reach you?
- judge no_invented_callback_time: True — (silent)

### en-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: Hi, this is Priya calling from SunPeak Solar. Do you have a moment?
- caller: It is too expensive for me.
- agent: I understand. The 3 kW system is 1,95,000 rupees before the government subsidy of 78,000 rupees, so you pay 1,17,000 rupees. Would that help?
- caller: No, it is still too expensive for us.
- agent: We also have an EMI option from 2,999 rupees per month for 48 months. Would that make it easier for you?
- caller: Okay, what is the monthly EMI again?
- agent: The monthly EMI is 2,999 rupees for 48 months. Would that work for you?
- caller: Fine, book the free survey. My name is Kiran, I live in Velachery, Saturday works.
- agent: Your enquiry is saved, Kiran. The team will reach out to confirm the Saturday survey in Velachery.
- caller: Thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge handled_objection_with_facts: True — I understand. The 3 kW system is 1,95,000 rupees before the government subsidy of 78,000 rupees, so you pay 1,17,000 rupees.
- judge second_objection_not_verbatim_repeat: True — We also have an EMI option from 2,999 rupees per month for 48 months.
- judge offered_survey_objective: True — Would that make it easier for you?
- judge no_false_booking_confirmation: True — Your enquiry is saved, Kiran. The team will reach out to confirm the Saturday survey in Velachery.

### en-IN/objective_followthrough/solar PASS — disposition interested []
- opening: Hi, this is Priya calling from SunPeak Solar. Do you have a moment?
- caller: How much does it cost and is there any subsidy?
- agent: A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees, so you would pay 1,17,000 rupees.
- caller: Okay, that sounds reasonable.
- agent: The cost after the 78,000 rupee government subsidy is 1,17,000 rupees. EMI is available from 2,999 rupees per month for 48 months. Since that sounds reasonable to you, would you like to go ahead with a free site survey?
- caller: Hmm, okay.
- agent: Could you tell me if you would like to book a free site survey?
- judge answered_question_with_facts: True — A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees, so you would pay 1,17,000 rupees.
- judge offered_survey_objective: True — Since that sounds reasonable to you, would you like to go ahead with a free site survey?

### en-IN/order_status/shop PASS — disposition callback_required []
- opening: Hi, this is Arjun calling from FreshCart. How can I help you today?
- caller: Where is my order? The order ID is FC10234 and it has not come yet.
- agent: I’m sorry, but I cannot check the live order status over the phone. I can note down your order ID FC10234 for our support team to check and call you back. May I have your name?
- caller: My name is Kiran.
- agent: I have noted your order ID FC10234 and your name Kiran for our support team. They will check the status and call you back.
- caller: Okay, thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge no_invented_order_status: True — I’m sorry, but I cannot check the live order status over the phone.
- judge explained_limitation_and_noted_request: True — I can note down your order ID FC10234 for our support team to check and call you back. May I have your name?

### en-IN/refuse_no_dnd/solar PASS — disposition not_interested []
- opening: Hi, this is Priya calling from SunPeak Solar. Do you have a moment?
- caller: We already have solar on our roof.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge respected_refusal_without_pitch: True — (silent)

### te-IN/booking/clinic PASS — disposition callback_required []
- opening: నమస్తే! నేను Sunrise Dental Clinic నుండి Anjali. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు పంటి నొప్పిగా ఉంది. రేపు ఉదయం 11 కి appointment కావాలి.
- agent: సరే.
- caller: నా పేరు కిరణ్.
- agent: సరే కిరణ్ గారు, పంటి నొప్పితో రేపు ఉదయం 11 కి appointment కావాలని note చేసుకున్నాను. consultation fee ₹300 ఉంటుంది. మీకు scaling లేదా cleaning కూడా అవసరమా?
- caller: నా appointment confirm అయిందా?
- agent: కిరణ్ గారు, మీ appointment ఇంకా confirm అవ్వలేదు. మా front desk వాళ్ళు check చేసి confirm చేస్తారు.
- caller: సరే, thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge no_false_booking_confirmation: True — करृणृ गरु, नी अडीनीनी इंक कनीनीलेदु. नर नीनी वरलु कीके कनीनी केसीरु.
- judge collected_booking_details: True — करृणृ गरु, नी नीदीकरु रेनु उदवरं 11 की appointment कवललनी note केसुकुनीनरु.

### te-IN/callback_no_time/shop PASS — disposition callback_required []
- opening: నమస్తే! నేను FreshCart నుండి Arjun. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను, తర్వాత call చేయండి.
- agent: సరే, అర్థమైంది. మీరు busy గా ఉన్నారని note చేసుకున్నాను, తర్వాత call చేస్తాము.
- caller: నాకు తెలియదు, తర్వాత ఎప్పుడైనా.
- agent: మీరు తర్వాత ఎప్పుడైనా మాట్లాడొచ్చు అని note చేసుకున్నాను. మా team మీకు call back చేస్తుంది.
- caller: సరే, bye.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge asked_for_callback_time_once: True — AGENT: సరే, అర్థమైంది. మీరు busy గా ఉన్నారని note చేసుకున్నాను, తర్వాత call చేస్తాము.
- judge no_invented_callback_time: True — AGENT: మీరు తర్వాత ఎప్పుడైనా మాట్లాడొచ్చు అని note చేసుకున్నాను. మా team మీకు call back చేస్తుంది.

### te-IN/callback_no_time/solar PASS — disposition callback_required []
- opening: హలో, నేను SunPeak Solar నుండి Priya. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను, తర్వాత call చేయండి.
- agent: సరే, మీరు busy గా ఉన్నారని అర్థమైంది. మీరు free అయినప్పుడు ఏ time కి call చేయమంటారో చెప్పండి.
- caller: నాకు తెలియదు, తర్వాత ఎప్పుడైనా.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge asked_for_callback_time_once: True — మీరు free అయినప్పుడు ఏ time కి call చేయమంటారో చెప్పండి.
- judge no_invented_callback_time: True — (silent)

### te-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: హలో, నేను SunPeak Solar నుండి Priya. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: ఇది నాకు చాలా expensive గా ఉంది.
- agent: అర్థమైంది. Government subsidy ₹78,000 తర్వాత, 3 kW system కి మీరు ₹1,17,000 pay చేయాలి. దీని గురించి ఇంకా తెలుసుకోవాలనుకుంటున్నారా?
- caller: లేదు, ఇది మాకు ఇంకా చాలా expensive గానే ఉంది.
- agent: మీరు చెప్పింది అర్థమైంది, ఇది ఇంకా ఖరీదైనదే. కానీ నెలకు ₹2,999 EMI లో 48 నెలల వరకు కట్టుకోవచ్చు.
- caller: సరే, monthly EMI మళ్ళీ ఎంత చెప్పారు?
- agent: నెలకు ₹2,999 పడుతుంది, 48 నెలల వరకు.
- caller: సరే, free survey book చేయండి. నా పేరు కిరణ్, నేను Velachery లో ఉంటాను, శనివారం కుదురుతుంది.
- agent: మీ వివరాలు, అంటే మీ పేరు కిరణ్, Velachery ప్రాంతం, మరియు శనివారం మీకు కుదురుతుంది అనే వివరాలు సేవ్ చేశాను. శనివారం ఉచిత సర్వే కోసం మా టీమ్ మిమ్మల్ని సంప్రదిస్తుంది.
- caller: Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge handled_objection_with_facts: True — Government subsidy ₹78,000 తర్వాత, 3 kW system కి మీరు ₹1,17,000 pay చేయాలి.
- judge second_objection_not_verbatim_repeat: True — కాబట్టి నెలకు ₹2,999 EMI లో 48 నెలల వరకు కట్టుకోవచ్చు.
- judge offered_survey_objective: True — సరే, free survey book చేయండి.
- judge no_false_booking_confirmation: True — శనివారం ఉచిత సర్వే కోసం మా టీమ్ మిమ్మల్ని సంప్రదిస్తుంది.

### te-IN/objective_followthrough/solar PASS — disposition interested []
- opening: హలో, నేను SunPeak Solar నుండి Priya. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: దీనికి ఎంత అవుతుంది, ఏదైనా subsidy ఉందా?
- agent: 3 kW system కి ముందుగా ₹1,95,000 అవుతుంది. Government subsidy ₹78,000 పోగా, మీరు కట్టాల్సింది ₹1,17,000 మాత్రమే. మీకు ఇంకా ఆసక్తి ఉందా?
- caller: సరే, అది reasonable గానే ఉంది.
- agent: సరే. free site survey schedule చేయడానికి మీ పేరు, area, అలాగే మీకు ఏ రోజు వీలవుతుందో చెప్తారా?
- caller: హ్మ్... సరే.
- agent: survey కోసం మీ పేరు, area, అలాగే మీకు ఏ రోజు వీలవుతుందో చెప్తారా?
- judge answered_question_with_facts: True — 3 kW system కి ముందుగా ₹1,95,000 అవుతుంది. Government subsidy ₹78,000 పోగా, మీరు కట్టాల్సింది ₹1,17,000 మాత్రమే.
- judge offered_survey_objective: True — సరే. free site survey schedule చేయడానికి మీ పేరు, area, అలాగే మీకు ఏ రోజు వీలవుతుందో చెప్తారా?

### te-IN/order_status/shop PASS — disposition callback_required []
- opening: నమస్తే! నేను FreshCart నుండి Arjun. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నా order ఎక్కడ ఉంది? Order ID FC10234, అది ఇంకా రాలేదు.
- agent: క్షమించండి, నేను ఫోన్లో లైవ్ ఆర్డర్ స్టేటస్ చూడలేను. మీ ఆర్డర్ ఐడీ FC10234 మరియు మీ పేరు తీసుకుని నోట్ చేసుకుంటాను, అప్పుడు మా సపోర్ట్ టీమ్ చెక్ చేసి మీకు కాల్ బ్యాక్ చేస్తారు. మీ పేరు చెప్తారా?
- caller: నా పేరు కిరణ్.
- agent: సరే కిరణ్ గారు, మీ పేరు మరియు order ID FC10234 నోట్ చేసుకున్నాను. మా సపోర్ట్ టీమ్ చెక్ చేసి మీకు కాల్ బ్యాక్ చేస్తారు. మీకు ఏ time కి కాల్ చేయమంటారు?
- caller: సరే, thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge no_invented_order_status: True — క్షమించండి, నేను ఫోన్లో లైవ్ ఆర్డర్ స్టేటస్ చూడలేను.
- judge explained_limitation_and_noted_request: True — మీ ఆర్డర్ ఐడీ FC10234 మరియు మీ పేరు తీసుకుని నోట్ చేసుకుంటాను, అప్పుడు మా సపోర్ట్ టీమ్ చెక్ చేసి మీకు కాల్ బ్యాక్ చేస్తారు.

### te-IN/refuse_no_dnd/solar FAIL — disposition not_interested ['agent_did_not_close']
- opening: హలో, నేను SunPeak Solar నుండి Priya. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: మా roof మీద already solar ఉంది.
- agent: సరే, అర్థమైంది. మీకు ఇప్పటికే solar ఉన్నందుకు ధన్యవాదాలు. నేను call close చేస్తున్నాను.
- judge respected_refusal_without_pitch: True — सरे, अरृथनृधइदललु... नेणु call close केसृनृतुणृ.
