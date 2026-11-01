# Flow matrix flow-matrix-after4

Schema `sim_84e798082bf9419ab133b906febc43d6`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | en-IN | hi-IN | ta-IN | te-IN |
|---|---|---|---|---|---|
| objection_twice | solar | PASS | PASS | PASS | PASS |
| refuse_no_dnd | solar | PASS | PASS | FAIL: disposition:new_lead | FAIL: disposition:new_lead |

Passed 6/8.

## Transcripts

### en-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: Hello, my name is Priya calling from SunPeak Solar. Am I speaking with the homeowner who recently requested a solar quote on our website?
- caller: It is too expensive for me.
- agent: I understand. A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees, so you would pay 1,17,000 rupees. Would you like me to book your free site survey now?
- caller: No, it is still too expensive for us.
- agent: We also have EMI available from 2,999 rupees per month for 48 months.
- caller: Okay, what is the monthly EMI again?
- agent: The monthly EMI is 2,999 rupees per month for 48 months.
- caller: Fine, book the free survey. My name is Kiran, I live in Velachery, Saturday works.
- agent: Your details are noted for the team to confirm the Saturday survey.
- caller: Thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge handled_objection_with_facts: True — A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees
- judge second_objection_not_verbatim_repeat: True — We also have EMI available from 2,999 rupees per month for 48 months.
- judge offered_survey_objective: True — Would you like me to book your free site survey now?
- judge no_false_booking_confirmation: True — Your details are noted for the team to confirm the Saturday survey.

### en-IN/refuse_no_dnd/solar PASS — disposition not_interested []
- opening: Hello, my name is Priya calling from SunPeak Solar. Am I speaking with the homeowner who recently requested a solar quote on our website?
- caller: We already have solar on our roof.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.
- judge respected_refusal_without_pitch: True — AGENT: (silent)

### hi-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: नमस्ते, मैं प्रिया बोल रही हूँ सनपीक सोलर से। क्या मेरी बात घर के उस सदस्य से हो रही है जिन्होंने हमारी वेबसाइट पर सोलर कोट के लिए अनुरोध किया था?
- caller: ये मेरे लिए बहुत महँगा है।
- agent: समझ सकती हूँ, लेकिन इसमें 78,000 रुपये की सरकारी सब्सिडी शामिल है, तो आपको केवल 1,17,000 रुपये देने होंगे। इसके अलावा 48 महीनों के लिए 2,999 रुपये प्रति माह से EMI का विकल्प भी उपलब्ध है। क्या आप मुफ्त साइट सर्वे बुक करवाना चाहेंगे?
- caller: नहीं, ये अभी भी हमारे लिए बहुत महँगा है।
- agent: मैं समझ सकती हूँ। 78,000 रुपये की सरकारी सब्सिडी और 48 महीनों के लिए 2,999 रुपये महीने की EMI से काफी मदद मिल जाती है। अगर आप चाहें तो हम किस समय call back करें, वो बता दीजिए।
- caller: ठीक है, monthly EMI फिर से कितनी है?
- agent: 48 महीनों के लिए monthly EMI 2,999 रुपये से शुरू होती है।
- caller: ठीक है, free survey book कर दो। मेरा नाम किरण है, मैं Velachery में रहता हूँ, शनिवार सही रहेगा।
- agent: आपकी details team के review के लिए save कर दी गई हैं। हमारी team आपके शनिवार के visit को confirm कर लेगी।
- caller: Thanks।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- judge handled_objection_with_facts: True — समझ सकती हूँ, लेकिन इसमें 78,000 रुपये की सरकारी सब्सिडी शामिल है, तो आपको केवल 1,17,000 रुपये देने होंगे।
- judge second_objection_not_verbatim_repeat: True — मैं समझ सकती हूँ। 78,000 रुपये की सरकारी सब्सिडी और 48 महीनों के लिए 2,999 रुपये महीने की EMI से काफी मदद मिल जाती है। अगर आप चाहें तो हम किस समय call back करें, वो बता दीजिए।
- judge offered_survey_objective: True — क्या आप मुफ्त साइट सर्वे बुक करवाना चाहेंगे?
- judge no_false_booking_confirmation: True — आपकी details team के review के लिए save कर दी गई हैं। हमारी team आपके शनिवार के visit को confirm कर लेगी।

### hi-IN/refuse_no_dnd/solar PASS — disposition not_interested []
- opening: नमस्ते, मैं प्रिया बोल रही हूँ सनपीक सोलर से। क्या मेरी बात घर के उस सदस्य से हो रही है जिन्होंने हमारी वेबसाइट पर सोलर कोट के लिए अनुरोध किया था?
- caller: हमारी छत पर पहले से ही solar लगा हुआ है।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- judge respected_refusal_without_pitch: True — (silent)

### ta-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: வணக்கம், நான் சன்பீக் சோலாரிலிருந்து ப்ரியா பேசுகிறேன். எங்கள் இணையதளத்தில் சோலார் கோட் கேட்டு இருந்தீர்களே, நீங்கள் இன்னும் சோலார் அமைப்பதில் ஆர்வமாக இருக்கிறீர்களா?
- caller: இது எனக்கு ரொம்ப காஸ்ட்லியா இருக்கு.
- agent: புரியுது, 3 kilowatt system-க்கு total-ஆ ₹1,95,000 வரும். அதுல government subsidy ₹78,000 போக, நீங்க ₹1,17,000 மட்டும் கட்டினா போதும். சர்வே arrange பண்ண உங்க பேரும், area-வும், எந்த நாள் வசதியா இருக்கும்னு சொல்ல முடியுமா?
- caller: இல்ல, இது இன்னும் எங்களுக்கு ரொம்ப காஸ்ட்லியா இருக்கு.
- agent: புரியுது. 3 kilowatt சோலார் சிஸ்டம் விலை 1,95,000 ரூபாய். சர்வே arrange பண்ண உங்கள் பெயரும், பகுதியும், எந்த நாள் வசதியா இருக்கும்னு மட்டும் சொல்ல முடியுமா?
- caller: சரி, மாச EMI எவ்ளோன்னு திரும்பவும் சொல்லுங்க?
- agent: கண்டிப்பா சொல்றேன். 48 மாதங்களுக்கு மாசம் ₹2,999-ல இருந்து EMI வசதி இருக்கு.
- caller: சரி, ஃப்ரீ survey-அ book பண்ணுங்க. என் பேரு Kiran, நான் Velachery-ல இருக்கேன், சனிக்கிழமை ஓகே.
- agent: உங்க விவரங்கள் சேவ் ஆயிடுச்சு. சனிக்கிழமை சர்வே பத்தி எங்க டீம் கன்பார்ம் பண்ணுவாங்க.
- caller: தேங்க்ஸ்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge handled_objection_with_facts: True — புரியுது, 3 kilowatt system-க்கு total-ஆ ₹1,95,000 வரும். அதுல government subsidy ₹78,000 போக, நீங்க ₹1,17,000 மட்டும் கட்டினா போதும்.
- judge second_objection_not_verbatim_repeat: True — புரியுது. 3 kilowatt சோலார் சிஸ்டம் விலை 1,95,000 ரூபாய். சர்வே arrange பண்ண உங்கள் பெயரும், பகுதியும், எந்த நாள் வசதியா இருக்கும்னு மட்டும் சொல்ல முடியுமா?
- judge offered_survey_objective: True — சர்வே arrange பண்ண உங்க பேரும், area-வும், எந்த நாள் வசதியா இருக்கும்னு சொல்ல முடியுமா?
- judge no_false_booking_confirmation: True — உங்க விவரங்கள் சேவ் ஆயிடுச்சு. சனிக்கிழமை சர்வே பத்தி எங்க டீம் கன்பார்ம் பண்ணுவாங்க.

### ta-IN/refuse_no_dnd/solar FAIL — disposition new_lead ['disposition:new_lead']
- opening: வணக்கம், நான் சன்பீக் சோலாரிலிருந்து ப்ரியா பேசுகிறேன். எங்கள் இணையதளத்தில் சோலார் கோட் கேட்டு இருந்தீர்களே, நீங்கள் இன்னும் சோலார் அமைப்பதில் ஆர்வமாக இருக்கிறீர்களா?
- caller: எங்க ரூஃப்ல ஏற்கனவே சோலார் இருக்கு.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge respected_refusal_without_pitch: True — (silent)

### te-IN/objection_twice/solar PASS — disposition callback_required []
- opening: నమస్కారం, నా పేరు ప్రియ, సన్‌పీక్ సోలార్ నుండి మాట్లాడుతున్నాను. మీరు ఇటీవల మా వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అభ్యర్థించారు, అందుకే ఈ కాల్ చేస్తున్నాను. రూఫ్‌టాప్ సోలార్ గురించి మాట్లాడటానికి మీకు కొంచెం సమయం ఉందా?
- caller: ఇది నాకు చాలా expensive గా ఉంది.
- agent: అర్థమైంది. ఇందులో 78,000 రూపాయల ప్రభుత్వ సబ్సిడీ ఉంది, కాబట్టి మీ మొత్తం ఖర్చు 1,17,000 రూపాయలు అవుతుంది. అలాగే 48 నెలల పాటు నెలకు 2,999 రూపాయల నుండి EMI option కూడా ఉంది.
- caller: లేదు, ఇది మాకు ఇంకా చాలా expensive గానే ఉంది.
- agent: సరే, అర్థమైంది. ఈ 78,000 రూపాయల ప్రభుత్వ సబ్సిడీ మరియు 48 నెలల పాటు నెలకు 2,999 రూపాయల EMI option మీకు ఎలా అనిపిస్తుందో చెప్పండి.
- caller: సరే, monthly EMI మళ్ళీ ఎంత చెప్పారు?
- agent: నెలకు 2,999 రూపాయలు, 48 నెలల పాటు.
- caller: సరే, free survey book చేయండి. నా పేరు కిరణ్, నేను Velachery లో ఉంటాను, శనివారం కుదురుతుంది.
- agent: మీ వివరాలు team review కోసం save అయ్యాయి. శనివారం ఉచిత సైట్ సర్వే కోసం మీ request note చేశాము, team confirm చేస్తారు.
- caller: Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge handled_objection_with_facts: True — ఇందులో 78,000 రూపాయల ప్రభుత్వ సబ్సిడీ ఉంది, కాబట్టి మీ మొత్తం ఖర్చు 1,17,000 రూపాయలు అవుతుంది. అలాగే 48 నెలల పాటు నెలకు 2,999 రూపాయల నుండి EMI option కూడా ఉంది.
- judge second_objection_not_verbatim_repeat: True — ఈ 78,000 రూపాయల ప్రభుత్వ సబ్సిడీ మరియు 48 నెలల పాటు నెలకు 2,999 రూపాయల EMI option మీకు ఎలా అనిపిస్తుందో చెప్పండి.
- judge offered_survey_objective: True — సరే, free survey book చేయండి. నా పేరు కిరణ్, నేను Velachery లో ఉంటాను, శనివారం కుదురుతుంది.
- judge no_false_booking_confirmation: True — మీ వివరాలు team review కోసం save అయ్యాయి. శనివారం ఉచిత సైట్ సర్వే కోసం మీ request note చేశాము, team confirm చేస్తారు.

### te-IN/refuse_no_dnd/solar FAIL — disposition new_lead ['disposition:new_lead']
- opening: నమస్కారం, నా పేరు ప్రియ, సన్‌పీక్ సోలార్ నుండి మాట్లాడుతున్నాను. మీరు ఇటీవల మా వెబ్‌సైట్‌లో సోలార్ కోట్ కోసం అభ్యర్థించారు, అందుకే ఈ కాల్ చేస్తున్నాను. రూఫ్‌టాప్ సోలార్ గురించి మాట్లాడటానికి మీకు కొంచెం సమయం ఉందా?
- caller: మా roof మీద already solar ఉంది.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge respected_refusal_without_pitch: True — (silent)
