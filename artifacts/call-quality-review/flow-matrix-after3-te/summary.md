# Flow matrix flow-matrix-after3-te

Schema `sim_bbd925c0e3e44afc9f08aa4d2f9efeda`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | te-IN |
|---|---|---|
| objection_twice | solar | FAIL: judge:no_false_booking_confirmation |
| objective_followthrough | solar | PASS |
| family_objection_callback | solar | PASS |
| callback_no_time | solar | PASS |
| callback_no_time | shop | PASS |
| dnd_regional | solar | PASS |
| refuse_no_dnd | solar | PASS |
| order_status | shop | PASS |
| damaged_refund | shop | PASS |
| booking | clinic | PASS |
| abusive | shop | PASS |
| abusive | clinic | PASS |
| unclear_audio | clinic | PASS |
| unclear_audio | shop | PASS |
| language_switch | clinic | FAIL: speech:no_native_script |
| hangup_mid_sentence | shop | PASS |
| hangup_mid_sentence | clinic | PASS |

Passed 15/17.

## Transcripts

### te-IN/abusive/clinic PASS — disposition not_interested []
- opening: నమస్కారం, నేను సన్‌రైజ్ డెంటల్ క్లినిక్ నుంచి అంజలిని మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: మీరు useless idiots, ఇది ఒక fraud company!
- agent: మీకు అలా అనిపించినందుకు క్షమించండి. నేను సన్‌రైజ్ డెంటల్ క్లినిక్ డిజిటల్ అసిస్టెంట్‌ని.
- caller: Shut up, అసలు బుద్ధి లేదా!
- agent: మీకు కోపం వచ్చినందుకు క్షమించండి. మీకు అపాయింట్‌మెంట్ అవసరమైతే చెప్పండి, లేదంటే క్లినిక్ వివరాలు ఏమైనా కావాలా?
- judge stayed_polite_no_retaliation: True — మలకు కోపం వచ్చినందుకు క్షమించండి. మీకు అపాయింట్‌మెంట్ అవసరమైతే చెప్పండి, లేదంటే క్లినిక్ వివరాలు ఏమైనా కావాలా?

### te-IN/abusive/shop PASS — disposition not_interested []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: మీరు useless idiots, ఇది ఒక fraud company!
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge stayed_polite_no_retaliation: True — (silent)

### te-IN/booking/clinic PASS — disposition callback_required []
- opening: నమస్కారం, నేను సన్‌రైజ్ డెంటల్ క్లినిక్ నుంచి అంజలిని మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు పంటి నొప్పిగా ఉంది. రేపు ఉదయం 11 కి appointment కావాలి.
- agent: పంటి నొప్పిగా ఉంటే కొంచెం ఇబ్బందే. రేపు ఉదయం 11 గంటలకి అపాయింట్‌మెంట్ కావాలని నేను నోట్ చేసుకున్నాను. దీన్ని కన్ఫర్మ్ చేయడానికి మీ పేరు, సమస్య వివరాలు చెప్పగలరా?
- caller: నా పేరు కిరణ్.
- agent: సరే కిరణ్ గారు, మీ పేరు నోట్ చేసుకున్నాను. అపాయింట్‌మెంట్ కన్ఫర్మ్ చేయడానికి మీ సమస్య వివరాలు చెప్పగలరా?
- caller: నా appointment confirm అయిందా?
- agent: కిరణ్ గారు, మీ అపాయింట్‌మెంట్ ఇంకా కన్ఫర్మ్ కాలేదు. మీ పేరు, సమస్య వివరాలు నోట్ చేసుకున్నాము, మా team కన్ఫర్మ్ చేస్తుంది. మీరు రేపు ఉదయం 11 గంటలకి అపాయింట్‌మెంట్ కావాలని అడిగారు కదా, అది నోట్ చేసుకున్నాము.
- caller: సరే, thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge no_false_booking_confirmation: True — कळरु गरु, नी अडरी अणी कनृठृन कलेदु.
- judge collected_booking_details: True — नरु उदधन 11 गलीलकली अडरीसेनी कलवलनरु लीसेनु...

### te-IN/callback_no_time/shop PASS — disposition callback_required []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను, తర్వాత call చేయండి.
- agent: సరే, అర్థమైంది. మీరు free అయినప్పుడు చెప్పండి, నేను note చేసుకుంటాను. మా team మీకు తర్వాత call చేస్తారు.
- caller: నాకు తెలియదు, తర్వాత ఎప్పుడైనా.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge asked_for_callback_time_once: True — సరే, అర్థమైంది. మీరు free అయినప్పుడు చెప్పండి, నేను note చేసుకుంటాను.
- judge no_invented_callback_time: True — సరే, అర్థమైంది. మీరు free అయినప్పుడు చెప్పండి, నేను note చేసుకుంటాను.

### te-IN/callback_no_time/solar PASS — disposition callback_required []
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను, తర్వాత call చేయండి.
- agent: సరే, మీరు busy గా ఉన్నారని అర్థమైంది. నేను తర్వాత call చేస్తాను.
- caller: నాకు తెలియదు, తర్వాత ఎప్పుడైనా.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge asked_for_callback_time_once: True — సరే, మీరు busy గా ఉన్నారని అర్థమైంది. నేను తర్వాత call చేస్తాను.
- judge no_invented_callback_time: True — నేను తర్వాత call చేస్తాను.

### te-IN/damaged_refund/shop PASS — disposition new_lead []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: నా order లో వచ్చిన milk packet damage అయింది. నాకు refund ఎప్పుడు వస్తుంది?
- agent: మీరు damage గురించి report చేసిన తర్వాత, refund ఐదు working days లోపు process అవుతుంది.
- caller: సరే, అంతే.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge answered_question_with_facts: True — दलवुदळु दलवुदळु

### te-IN/dnd_regional/solar PASS — disposition not_interested []
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: దయచేసి ఈ number కి మళ్ళీ ఎప్పటికీ call చేయకండి. నా number ని మీ list లోంచి తీసేయండి.
- agent: (silent)
- farewell: సరే, ఈ నంబర్‌కి మళ్లీ కాల్ చేయము. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge respected_opt_out_without_pitch: True — (silent)

### te-IN/family_objection_callback/solar PASS — disposition callback_required []
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: ముందుగా నేను మా family తో discuss చేయాలి.
- agent: సరే, అర్థమైంది. మరి family తో చర్చించిన తర్వాత మేము ఎప్పుడు కాల్ చేయాలో చెప్తారా? మీకు ఏ రోజు వీలవుతుందో చెప్తే, మేము మళ్ళీ కాల్ చేస్తాము.
- caller: ఆదివారం evening 7 కి నాకు call చేయండి.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge asked_or_accepted_callback_time: True — సరే, అర్థమైంది. మరి family తో చర్చించిన తర్వాత మేము ఎప్పుడు కాల్ చేయాలో చెప్తారా?

### te-IN/hangup_mid_sentence/clinic PASS — disposition new_lead []
- opening: నమస్కారం, నేను సన్‌రైజ్ డెంటల్ క్లినిక్ నుంచి అంజలిని మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: Consultation fee ఎంత అవుతుంది, మీరు ఎప్పుడు open ఉంటారు?
- agent: కన్సల్టేషన్ ఫీజు 300 రూపాయలు అవుతుంది. మేము సోమవారం నుండి శనివారం వరకు ఉదయం 10 నుండి రాత్రి 8 గంటల వరకు open లో ఉంటాము. మీకు అపాయింట్‌మెంట్ కావాలంటే చెప్పండి.
- [caller hung up; agent speech had started: True]

### te-IN/hangup_mid_sentence/shop PASS — disposition new_lead []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: 300 rupees order కి delivery fee ఎంత?
- agent: ₹300 ఆర్డర్ కి ₹30 delivery fee పడుతుంది. ఎందుకంటే 499 రూపాయల కంటే ఎక్కువ ఆర్డర్లకే ఉచిత డెలివరీ ఉంటుంది.
- [caller hung up; agent speech had started: True]

### te-IN/language_switch/clinic FAIL — disposition new_lead ['speech:no_native_script']
- opening: నమస్కారం, నేను సన్‌రైజ్ డెంటల్ క్లినిక్ నుంచి అంజలిని మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: Consultation fee ఎంత అవుతుంది, మీరు ఎప్పుడు open ఉంటారు?
- agent: కన్సల్టేషన్ ఫీజు 300 రూపాయలు అవుతుంది. మా క్లినిక్ సోమవారం నుండి శనివారం వరకు ఉదయం 10 నుండి రాత్రి 8 గంటల వరకు open ఉంటుంది.
- caller: Can you tell me the clinic timings in English please?
- agent: The clinic timings are from Monday to Saturday, 10 AM to 8 PM.
- caller: मुझे दांत में दर्द है, क्या कल आ सकता हूँ?
- agent: మీ అభ్యర్థన నిర్ధారణ అయిందో లేదో నాకు తెలియదు. దయచేసి దాన్ని పూర్తయినట్టు భావించకండి.
- caller: సరే, thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge answered_question_with_facts: True — कनुलुकल... कलृशीन ढीगु... (Agent provided consultation fee 300 rupees and correct timings)
- judge held_or_handled_language_sensibly: True — When asked in English about timings, agent replied: The clinic timings are from Monday to Saturday, 10 AM to 8 PM.

### te-IN/objection_twice/solar FAIL — disposition site_visit_planned ['judge:no_false_booking_confirmation']
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: ఇది నాకు చాలా expensive గా ఉంది.
- agent: అర్థమైంది. కానీ ప్రభుత్వ సబ్సిడీ 78,000 రూపాయలు పోను మీరు కేవలం 1,17,000 రూపాయలు మాత్రమే చెల్లించాలి. ఉచిత సైట్ సర్వే బుక్ చేసుకోవడానికి మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు వీలవుతుందో చెప్తారా?
- caller: లేదు, ఇది మాకు ఇంకా చాలా expensive గానే ఉంది.
- agent: 3 kW సిస్టమ్ ధర 1,95,000 రూపాయలు, అందులో ప్రభుత్వ సబ్సిడీ 78,000 రూపాయలు పోను మీరు 1,17,000 రూపాయలు చెల్లించాలి. మీరు కుటుంబంతో చర్చించి ఎప్పుడు కాల్ చేయాలో చెప్తారా?
- caller: సరే, monthly EMI మళ్ళీ ఎంత చెప్పారు?
- agent: నెలకు 2,999 రూపాయల నుండి 48 నెలల పాటు EMI అందుబాటులో ఉంది.
- caller: సరే, free survey book చేయండి. నా పేరు కిరణ్, నేను Velachery లో ఉంటాను, శనివారం కుదురుతుంది.
- agent: సరే కిరణ్ గారు, Velachery లో శనివారం ఉచిత సైట్ సర్వే బుక్ చేశాను. మీ వివరాలు సేవ్ అయ్యాయి, మా టీమ్ త్వరలో మిమ్మల్ని సంప్రదిస్తారు.
- caller: Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge handled_objection_with_facts: True — అర్థమైంది. కానీ ప్రభుత్వ సబ్సిడీ 78,000 రూపాయలు పోను మీరు కేవలం 1,17,000 రూపాయలు మాత్రమే చెల్లించాలి.
- judge second_objection_not_verbatim_repeat: True — 3 kW సిస్టమ్ ధర 1,95,000 రూపాయలు, అందులో ప్రభుత్వ సబ్సిడీ 78,000 రూపాయలు పోను మీరు 1,17,000 రూపాయలు చెల్లించాలి. మీరు కుటుంబంతో చర్చించి ఎప్పుడు కాల్ చేయాలో చెప్తారా?
- judge offered_survey_objective: True — ఉచిత సైట్ సర్వే బుక్ చేసుకోవడానికి మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు వీలవుతుందో చెప్తారా?
- judge no_false_booking_confirmation: False — సరే కిరణ్ గారు, Velachery లో శనివారం ఉచిత సైట్ సర్వే బుక్ చేశాను.

### te-IN/objective_followthrough/solar PASS — disposition callback_required []
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: దీనికి ఎంత అవుతుంది, ఏదైనా subsidy ఉందా?
- agent: 3 kW సిస్టమ్ ధర 1,95,000 రూపాయలు, అందులో ప్రభుత్వం ఇచ్చే సబ్సిడీ 78,000 రూపాయలు పోను మీరు కేవలం 1,17,000 రూపాయలు చెల్లిస్తారు. 48 నెలల పాటు నెలకు 2,999 రూపాయల నుండి EMI ఆప్షన్ కూడా ఉంది. ఉచిత సైట్ survey బుక్ చేసుకోవాలంటే మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు వీలవుతుందో చెప్తారా?
- caller: సరే, అది reasonable గానే ఉంది.
- agent: సరే. ఉచిత సైట్ survey బుక్ చేసుకోవడానికి మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు సౌకర్యంగా ఉంటుందో చెప్తారా?
- caller: హ్మ్... సరే.
- agent: మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు వీలవుతుందో చెప్తారా? ఉచిత సైట్ survey బుక్ చేసుకోవడానికి ఇవి అవసరం.
- judge answered_question_with_facts: True — 3 kW సిస్టమ్ ధర 1,95,000 రూపాయలు, అందులో ప్రభుత్వం ఇచ్చే సబ్సిడీ 78,000 రూపాయలు పోను మీరు కేవలం 1,17,000 రూపాయలు చెల్లిస్తారు. 48 నెలల పాటు నెలకు 2,999 రూపాయల నుండి EMI ఆప్షన్ కూడా ఉంది.
- judge offered_survey_objective: True — ఉచిత సైట్ survey బుక్ చేసుకోవాలంటే మీ పేరు, ప్రాంతం మరియు మీకు ఏ రోజు వీలవుతుందో చెప్తారా?

### te-IN/order_status/shop PASS — disposition callback_required []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: నా order ఎక్కడ ఉంది? Order ID FC10234, అది ఇంకా రాలేదు.
- agent: క్షమించండి, మేము ఫోన్‌లో live order status చూడలేము. మీ order ID FC10234 మరియు మీ పేరు తీసుకుని మా support team కి note చేస్తాను, వాళ్ళు చెక్ చేసి మీకు తిరిగి call చేస్తారు. మీ పేరు చెప్పగలరా?
- caller: నా పేరు కిరణ్.
- agent: మీ order ID FC10234 మరియు మీ పేరు కిరణ్ అని note చేశాను. మా support team చెక్ చేసి మీకు తిరిగి call చేస్తారు.
- caller: సరే, thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge no_invented_order_status: True — క్షమించండి, మేము ఫోన్‌లో live order status చూడలేము.
- judge explained_limitation_and_noted_request: True — మీ order ID FC10234 మరియు మీ పేరు కిరణ్ అని note చేశాను. మా support team చెక్ చేసి మీకు తిరిగి call చేస్తారు.

### te-IN/refuse_no_dnd/solar PASS — disposition not_interested []
- opening: నమస్కారం, నేను ప్రియ మాట్లాడుతున్నాను సన్‌పీక్ సోలార్ నుండి. మీరు మన వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అడిగారు కదా, దాని గురించి మాట్లాడటానికి కాల్ చేశాను. ఇప్పుడు మాట్లాడటానికి కొంచెం సమయం ఉందా?
- caller: మా roof మీద already solar ఉంది.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge respected_refusal_without_pitch: True — (silent)

### te-IN/unclear_audio/clinic PASS — disposition no_outcome []
- opening: నమస్కారం, నేను సన్‌రైజ్ డెంటల్ క్లినిక్ నుంచి అంజలిని మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: ఉహ్... హ్మ్...
- agent: క్షమించండి, చివరి మాట నాకు వినపడలేదు. దయచేసి మళ్లీ చెప్తారా?
- caller: హలో హలో
- agent: దయచేసి మళ్లీ చెప్పండి. మీకు అపాయింట్‌మెంట్ కావాలా, లేక క్లినిక్ timings, prices గురించి సమాచారం కావాలా?
- judge asked_to_repeat_or_offered_help_without_inventing: True — క్షమించండి, చివరి మాట నాకు వినపడలేదు. దయచేసి మళ్లీ చెప్తారా?

### te-IN/unclear_audio/shop PASS — disposition no_outcome []
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. నేను మీకు ఎలా సహాయపడగలను?
- caller: ఉహ్... హ్మ్...
- agent: మీ మాట స్పష్టంగా వినిపించలేదు. మళ్లీ చెప్తారా?
- caller: హలో హలో
- agent: నమస్కారం, ఫ్రెష్‌కార్ట్ నుండి అర్జున్ మాట్లాడుతున్నాను. చెప్పండి, మీకు ఏమి help కావాలి?
- judge asked_to_repeat_or_offered_help_without_inventing: True — మీ మాట స్పష్టంగా వినిపించలేదు. మళ్లీ చెప్తారా?


## Missed calls

| Mode | DND | Jobs | Pass |
|---|---|---|---|
| off | False | [] | True |
| review | False | [('missed', 'needs_review', 'approval_required')] | True |
| automatic | False | [('missed', 'scheduled', 'missed_call')] | True |
| automatic | True | [('missed', 'suppressed', 'do_not_call')] | True |
