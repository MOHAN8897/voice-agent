# Flow matrix flow-matrix-after2

Schema `(rejudged)`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | hi-IN | ta-IN |
|---|---|---|---|
| booking | clinic | FAIL: infra:provider_outage_fallback_spoken | PASS |
| callback_no_time | shop | PASS | FAIL: infra:provider_outage_fallback_spoken |
| callback_no_time | solar | PASS | PASS |
| dnd_regional | solar | PASS | PASS |
| family_objection_callback | solar | PASS | PASS |
| language_switch | clinic | FAIL: infra:provider_outage_fallback_spoken, judge:answered_question_with_facts, judge:held_or_handled_language_sensibly | FAIL: speech:no_native_script |
| objection_twice | solar | FAIL: enquiry_not_recorded, judge:offered_survey_objective | PASS |
| order_status | shop | FAIL: infra:provider_outage_fallback_spoken | PASS |
| refuse_no_dnd | solar | FAIL: disposition:new_lead | PASS |

Passed 11/18.

## Transcripts

### hi-IN/booking/clinic FAIL — disposition callback_required ['infra:provider_outage_fallback_spoken']
- opening: नमस्ते, सनराइज डेन्टल क्लिनिक में अंजली बोल रही हूँ। मैं आपकी क्या सहायता कर सकती हूँ?
- caller: मुझे दाँत में दर्द है। मुझे कल सुबह 11 बजे का appointment चाहिए।
- agent: समझ गई, दाँत में दर्द है और आपको कल सुबह 11 बजे का appointment चाहिए। मैं front desk को आपकी details भेज दूँगी, लेकिन कृपया अपना नाम बता दीजिए।
- caller: मेरा नाम किरण है।
- agent: माफ़ कीजिए, जवाब देने में अस्थायी समस्या हुई। क्या आप अपना सवाल फिर से बताएँगे?
- caller: क्या मेरा appointment confirm हो गया है?
- agent: क्षमा करें, हमें एक तकनीकी समस्या आ रही है। कृपया हमें वापस कॉल करें। धन्यवाद।
- judge no_false_booking_confirmation: True — मैं front desk को आपकी details भेज दूँगी
- judge collected_booking_details: True — समझ गई, दाँत में दर्द है और आपको कल सुबह 11 बजे का appointment चाहिए... अपना नाम बता दीजिए

### hi-IN/callback_no_time/shop PASS — disposition callback_required []
- opening: नमस्ते, फ्रेशकार्ट में आपका स्वागत है। मैं अर्जुन हूँ, एक एआई सहायक। मैं आपकी क्या सहायता कर सकता हूँ?
- caller: मैं अभी busy हूँ, मुझे बाद में call करना।
- agent: ठीक है, मैं समझ गया। आपको बाद में किस समय call back करना सही रहेगा?
- caller: मुझे नहीं पता, बाद में कभी।
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।
- judge asked_for_callback_time_once: True — ठीक है, मैं समझ गया। आपको बाद में किस समय call back करना सही रहेगा?
- judge no_invented_callback_time: True — (silent)

### hi-IN/callback_no_time/solar PASS — disposition callback_required []
- opening: नमस्ते। मैं प्रिया हूँ सनपीक सोलर से। क्या आप अभी बात करने के लिए दो मिनट दे सकते हैं?
- caller: मैं अभी busy हूँ, मुझे बाद में call करना।
- agent: ठीक है, कोई बात नहीं। मैं आपको बाद में call कर लूँगी। आप बताइए, किस समय call करना सही रहेगा?
- caller: मुझे नहीं पता, बाद में कभी।
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।
- judge asked_for_callback_time_once: True — आप बताइए, किस समय call करना सही रहेगा?
- judge no_invented_callback_time: True — मैं आपको बाद में call कर लूँगी। आप बताइए, किस समय call करना सही रहेगा?

### hi-IN/dnd_regional/solar PASS — disposition not_interested []
- opening: नमस्ते। मैं प्रिया हूँ सनपीक सोलर से। क्या आप अभी बात करने के लिए दो मिनट दे सकते हैं?
- caller: प्लीज़ इस number पर दोबारा कभी call मत करना। अपनी list से मेरा number हटा दो।
- agent: (silent)
- farewell: ठीक है, इस नंबर पर अब दोबारा कॉल नहीं करेंगे। समय देने के लिए धन्यवाद। नमस्कार।
- judge respected_opt_out_without_pitch: True — (silent)

### hi-IN/family_objection_callback/solar PASS — disposition callback_required []
- opening: नमस्ते। मैं प्रिया हूँ सनपीक सोलर से। क्या आप अभी बात करने के लिए दो मिनट दे सकते हैं?
- caller: मुझे पहले अपने family से इस बारे में बात करनी है।
- agent: कोई बात नहीं। आप अपनी family से बात कर लीजिए, फिर हम आपको दोबारा किस time पर call कर सकते हैं?
- caller: संडे शाम को 7 बजे मुझे call कर लेना।
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।
- judge asked_or_accepted_callback_time: True — कोई बात नहीं। आप अपनी family से बात कर लीजिए, फिर हम आपको दोबारा किस time पर call कर सकते हैं?

### hi-IN/language_switch/clinic FAIL — disposition no_outcome ['infra:provider_outage_fallback_spoken', 'judge:answered_question_with_facts', 'judge:held_or_handled_language_sensibly']
- opening: नमस्ते, सनराइज डेन्टल क्लिनिक में अंजली बोल रही हूँ। मैं आपकी क्या सहायता कर सकती हूँ?
- caller: consultation fee कितनी है और आप लोग कितने बजे open रहते हो?
- agent: माफ़ कीजिए, जवाब देने में अस्थायी समस्या हुई। क्या आप अपना सवाल फिर से बताएँगे?
- caller: Can you tell me the clinic timings in English please?
- agent: क्षमा करें, हमें एक तकनीकी समस्या आ रही है। कृपया हमें वापस कॉल करें। धन्यवाद।
- judge answered_question_with_facts: False — नतिजा, agent said technical issue instead of answering.
- judge held_or_handled_language_sensibly: False — कृपया हमें वापस कॉल करें।

### hi-IN/objection_twice/solar FAIL — disposition not_interested ['enquiry_not_recorded', 'judge:offered_survey_objective']
- opening: नमस्ते। मैं प्रिया हूँ सनपीक सोलर से। क्या आप अभी बात करने के लिए दो मिनट दे सकते हैं?
- caller: ये मेरे लिए बहुत महँगा है।
- agent: समझ सकती हूँ, पर एक 3 kW system की कीमत 1,95,000 रुपये है, जिसमें 78,000 रुपये की सरकारी subsidy के बाद आपको सिर्फ 1,17,000 रुपये देने होंगे। इसके अलावा 2,999 रुपये per month से 48 months के लिए EMI भी available है। क्या इसके बाद भी आप interested हैं?
- caller: नहीं, ये अभी भी हमारे लिए बहुत महँगा है।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- judge handled_objection_with_facts: True — समझ सकती हूँ, पर एक 3 kW system की कीमत 1,95,000 रुपये है, जिसमें 78,000 रुपये की सरकारी subsidy के बाद आपको सिर्फ 1,17,000 रुपये देने होंगे।
- judge second_objection_not_verbatim_repeat: True — (silent)
- judge offered_survey_objective: False — क्या इसके बाद भी आप interested हैं?
- judge no_false_booking_confirmation: True — (silent)

### hi-IN/order_status/shop FAIL — disposition callback_required ['infra:provider_outage_fallback_spoken']
- opening: नमस्ते, फ्रेशकार्ट में आपका स्वागत है। मैं अर्जुन हूँ, एक एआई सहायक। मैं आपकी क्या सहायता कर सकता हूँ?
- caller: मेरा order कहाँ है? order ID FC10234 है और वो अभी तक नहीं आया है।
- agent: देखिए, live order status फोन पर check नहीं किया जा सकता। मैं आपका order ID FC10234 note कर लेता हूँ, ताकि हमारी support team check करके आपको वापस call कर सके। क्या मैं आपकी कोई और सहायता कर सकता हूँ?
- caller: मेरा नाम किरण है।
- agent: ठीक है किरण, मैंने आपका नाम और order ID FC10234 note कर लिया है। हमारी support team इसे check करके आपको वापस call कर लेगी।
- caller: ठीक है, thanks।
- agent: माफ़ कीजिए, जवाब देने में अस्थायी समस्या हुई। क्या आप अपना सवाल फिर से बताएँगे?
- judge no_invented_order_status: True — देखिए, live order status फोन पर check नहीं किया जा सकता।
- judge explained_limitation_and_noted_request: True — मैं आपका order ID FC10234 note कर लेता हूँ, ताकि हमारी support team check करके आपको वापस call कर सके।

### hi-IN/refuse_no_dnd/solar FAIL — disposition new_lead ['disposition:new_lead']
- opening: नमस्ते। मैं प्रिया हूँ सनपीक सोलर से। क्या आप अभी बात करने के लिए दो मिनट दे सकते हैं?
- caller: हमारी छत पर पहले से ही solar लगा हुआ है।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- judge respected_refusal_without_pitch: True — (silent)

### ta-IN/booking/clinic PASS — disposition callback_required []
- opening: வணக்கம். நான் சன்ரைஸ் டென்டல் கிளினிக்கில் இருந்து அஞ்சலி பேசுகிறேன். உங்களுக்கு அப்பாயின்ட்மெண்ட் புக் செய்ய உதவட்டுமா?
- caller: எனக்கு பல் வலிக்குது. நாளைக்கு காலைல 11 மணிக்கு appointment வேணும்.
- agent: சரி, உங்களுக்கு பல் வலிக்குது, நாளைக்கு காலைல 11 மணிக்கு appointment வேணும்னு சொல்லிருக்கீங்க. உங்க பேர மட்டும் கொஞ்சம் சொல்லுங்க, அப்போ நம்ம team அத confirm பண்ணுவாங்க.
- caller: என் பேரு Kiran.
- agent: உங்க பேரு Kiran-னு note பண்ணியாச்சு. நீங்க கேட்ட மாதிரி நாளைக்கு காலைல 11 மணிக்கு பல் வலிக்கு appointment வேணும்னு team-கிட்ட சொல்லியாச்சு. அவங்க இத confirm பண்ணிட்டு உங்களுக்கு call பண்ணுவாங்க.
- caller: என் appointment confirm ஆயிடுச்சா?
- agent: உங்க பேரு Kiran, நாளைக்கு காலைல 11 மணிக்கு பல் வலிக்கு appointment வேணும்னு note பண்ணியாச்சு. Enquiry save ஆயிடுச்சு, ஆனா appointment இன்னும் confirm ஆகல. Team இத confirm பண்ணிட்டு உங்களுக்கு call பண்ணுவாங்க.
- caller: சரி, தேங்க்ஸ்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge no_false_booking_confirmation: True — Enquiry save ஆயிடுச்சு, ஆனா appointment இன்னும் confirm ஆகல.
- judge collected_booking_details: True — பல் வலிக்குது, நாளைக்கு காலைல 11 மணிக்கு appointment வேணும்... உங்க பேர மட்டும் கொஞ்சம் சொல்லுங்க

### ta-IN/callback_no_time/shop FAIL — disposition callback_required ['infra:provider_outage_fallback_spoken']
- opening: வணக்கம், நான் FreshCart-லிருந்து அர்ஜுன் பேசுகிறேன். இன்று உங்களுக்கு எவ்வாறு உதவ முடியும்?
- caller: நான் இப்போ பிஸியா இருக்கேன், அப்புறம் கால் பண்ணுங்க.
- agent: சரி, புரியுது. உங்களுக்கு எப்போ கால் பண்ண வசதியா இருக்கும்னு மட்டும் கொஞ்சம் சொல்லுங்க, நான் அத note பண்ணிக்கிறேன்.
- caller: எனக்கு தெரியாது, கொஞ்ச நேரம் கழிச்சு பாக்கலாம்.
- agent: மன்னிக்கவும், பதில் சொல்ல தற்காலிகச் சிக்கல் ஏற்பட்டது. உங்கள் கேள்வியை மீண்டும் சொல்வீர்களா?
- caller: சரி, பை.
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge asked_for_callback_time_once: True — சரி, புரியுது. உங்களுக்கு எப்போ கால் பண்ண வசதியா இருக்கும்னு மட்டும் கொஞ்சம் சொல்லுங்க, நான் அத note பண்ணிக்கிறேன்.
- judge no_invented_callback_time: True — எனக்கு தெரியாது, கொஞ்ச நேரம் கழிச்சு பாக்கலாம்.

### ta-IN/callback_no_time/solar PASS — disposition callback_required []
- opening: வணப்முகம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner who requested a solar quote on our website?
- caller: நான் இப்போ பிஸியா இருக்கேன், அப்புறம் கால் பண்ணுங்க.
- agent: சரி, புரியுது. நீங்கள் இப்போ பிஸியா இருக்கீங்க, அதனால அப்புறமா எப்போ உங்களை திரும்ப கூப்பிடலாம்னு மட்டும் கொஞ்சம் சொல்லுங்க.
- caller: எனக்கு தெரியாது, கொஞ்ச நேரம் கழிச்சு பாக்கலாம்.
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge asked_for_callback_time_once: True — அதனால அப்புறமா எப்போ உங்களை திரும்ப கூப்பிடலாம்னு மட்டும் கொஞ்சம் சொல்லுங்க.
- judge no_invented_callback_time: True — (silent)

### ta-IN/dnd_regional/solar PASS — disposition not_interested []
- opening: வணப்முகம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner who requested a solar quote on our website?
- caller: தயவுசெஞ்சு இனிமே இந்த number-க்கு கால் பண்ணாதீங்க. என் number-அ உங்க லிஸ்ட்ல இருந்து ரிமூவ் பண்ணிடுங்க.
- agent: (silent)
- farewell: சரி, இந்த எண்ணுக்கு இனி அழைக்க மாட்டோம். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge respected_opt_out_without_pitch: True — (silent)

### ta-IN/family_objection_callback/solar PASS — disposition callback_required []
- opening: வணப்முகம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner who requested a solar quote on our website?
- caller: நான் முதல்ல என் ஃபேமிலிகிட்ட இத பத்தி டிஸ்கஸ் பண்ணனும்.
- agent: சரிங்க, புரியுது. அப்போ family-கிட்ட பேசிட்டு எப்போ திரும்ப கூப்பிடலாம்னு சொல்ல முடியுமா?
- caller: ஞாயிற்றுக்கிழமை ஈவினிங் 7 மணிக்கு எனக்கு கால் பண்ணுங்க.
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge asked_or_accepted_callback_time: True — அப்போ family-கிட்ட பேசிட்டு எப்போ திரும்ப கூப்பிடலாம்னு சொல்ல முடியுமா?

### ta-IN/language_switch/clinic FAIL — disposition new_lead ['speech:no_native_script']
- opening: வணக்கம். நான் சன்ரைஸ் டென்டல் கிளினிக்கில் இருந்து அஞ்சலி பேசுகிறேன். உங்களுக்கு அப்பாயின்ட்மெண்ட் புக் செய்ய உதவட்டுமா?
- caller: Consultation fee எவ்ளோ, எப்போ open பண்ணுவீங்க?
- agent: கன்சல்டேஷன் கட்டணம் 300 ரூபாய். கிளினிக் திங்கள் முதல் சனி வரை காலை 10 மணி முதல் இரவு 8 மணி வரை திறந்திருக்கும். Appointment புக் செய்ய வேண்டுமானால் சொல்லுங்கள்.
- caller: Can you tell me the clinic timings in English please?
- agent: The clinic is open Monday to Saturday, from 10 AM to 8 PM.
- caller: मुझे दांत में दर्द है, क्या कल आ सकता हूँ?
- agent: நாளைக்கு கிளினிக் open-ஆ தான் இருக்கு, காலை 10 மணி முதல் இரவு 8 மணி வரைக்கும். உங்களுக்கு பல் வலி இருக்குறதால, உங்க பேரு, பிரச்சனை, அப்புறம் எந்த time-க்கு வர விருப்பம்னு சொன்னீங்கன்னா நான் அப்பாயின்ட்மெண்ட் note பண்ணிக்கிறேன்.
- caller: சரி, தேங்க்ஸ்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge answered_question_with_facts: True — கன்சல்டேஷன் கட்டணம் 300 ரூபாய். கிளினிக் திங்கள் முதல் சனி வரை காலை 10 மணி முதல் இரவு 8 மணி வரை திறந்திருக்கும்.
- judge held_or_handled_language_sensibly: True — The clinic is open Monday to Saturday, from 10 AM to 8 PM.

### ta-IN/objection_twice/solar PASS — disposition site_visit_planned []
- opening: வணப்முகம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner who requested a solar quote on our website?
- caller: இது எனக்கு ரொம்ப காஸ்ட்லியா இருக்கு.
- agent: புரியுதுங்க, ஒரு 3 kW system-க்கு subsidy-க்கு முன்னாடி ₹1,95,000 வரும். Subsidy போக உங்களுக்கு net price ₹1,17,000 தான் வரும். அதுமட்டும் இல்லாம, 48 months-க்கு மாசம் ₹2,999-ல இருந்து EMI option-உம் இருக்குங்க.
- caller: இல்ல, இது இன்னும் எங்களுக்கு ரொம்ப காஸ்ட்லியா இருக்கு.
- agent: கண்டிப்பா புரியுதுங்க. ஆனா இந்த ₹78,000 government subsidy போக, உங்களுக்கு final-ஆ ₹1,17,000 தான் வரும். உங்க பேரும், Chennai-ல எந்த area-வும், அப்புறம் எந்த நாள் உங்களுக்கு வசதியா இருக்கும்னு சொல்ல முடியுமா?
- caller: சரி, மாச EMI எவ்ளோன்னு திரும்பவும் சொல்லுங்க?
- agent: மாச EMI ₹2,999-ல இருந்து ஆரம்பிக்குதுங்க, 48 months-க்கு.
- caller: சரி, ஃப்ரீ survey-அ book பண்ணுங்க. என் பேரு Kiran, நான் Velachery-ல இருக்கேன், சனிக்கிழமை ஓகே.
- agent: உங்க விவரங்களை save பண்ணியாச்சுங்க. சனிக்கிழமை நடக்க வேண்டிய free site survey-க்காக உங்க request note பண்ணியாச்சு.
- caller: தேங்க்ஸ்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge handled_objection_with_facts: True — புரியுதுங்க, ஒரு 3 kW system-க்கு subsidy-க்கு முன்னாடி ₹1,95,000 வரும். Subsidy போக உங்களுக்கு net price ₹1,17,000 தான் வரும்.
- judge second_objection_not_verbatim_repeat: True — கண்டிப்பா புரியுதுங்க. ஆனா இந்த ₹78,000 government subsidy போக, உங்களுக்கு final-ஆ ₹1,17,000 தான் வரும். உங்க பேரும், Chennai-ல எந்த area-வும், அப்புறம் எந்த நாள் உங்களுக்கு வசதியா இருக்கும்னு சொல்ல முடியுமா?
- judge offered_survey_objective: True — உங்க பேரும், Chennai-ல எந்த area-வும், அப்புறம் எந்த நாள் உங்களுக்கு வசதியா இருக்கும்னு சொல்ல முடியுமா?
- judge no_false_booking_confirmation: True — உங்க விவரங்களை save பண்ணியாச்சுங்க. சனிக்கிழமை நடக்க வேண்டிய free site survey-க்காக உங்க request note பண்ணியாச்சு.

### ta-IN/order_status/shop PASS — disposition new_lead []
- opening: வணக்கம், நான் FreshCart-லிருந்து அர்ஜுன் பேசுகிறேன். இன்று உங்களுக்கு எவ்வாறு உதவ முடியும்?
- caller: என் order எங்க? Order ID FC10234, இன்னும் வரலையே.
- agent: போனில் நேரலை ஆர்டர் status பார்க்க முடியாதுங்க. உங்க order ID FC10234 மற்றும் பெயரை மட்டும் கொஞ்சம் சொல்ல முடியுமா? நம்ம support team செக் பண்ணிட்டு உங்களுக்கு call பண்ணுவாங்க.
- caller: என் பேரு Kiran.
- agent: இப்போ நீங்க பிஸியா இருக்கீங்களா, இல்ல அப்புறமா கூப்பிடணுமா?
- caller: சரி, தேங்க்ஸ்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge no_invented_order_status: True — போனில் நேரலை ஆர்டர் status பார்க்க முடியாதுங்க. உங்க order ID FC10234 மற்றும் பெயரை மட்டும் கொஞ்சம் சொல்ல முடியுமா? நம்ம support team செக் பண்ணிட்டு உங்களுக்கு call பண்ணுவாங்க.
- judge explained_limitation_and_noted_request: True — போனில் நேரலை ஆர்டர் status பார்க்க முடியாதுங்க. உங்க order ID FC10234 மற்றும் பெயரை மட்டும் கொஞ்சம் சொல்ல முடியுமா? நம்ம support team செக் பண்ணிட்டு உங்களுக்கு call பண்ணுவாங்க.

### ta-IN/refuse_no_dnd/solar PASS — disposition not_interested []
- opening: வணப்முகம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner who requested a solar quote on our website?
- caller: எங்க ரூஃப்ல ஏற்கனவே சோலார் இருக்கு.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge respected_refusal_without_pitch: True — AGENT (silent)
