# Workflow simulation workflow-v5

Schema `sim_2cb746f475364808a0006d7cd020c74d`.

| Scenario | Pass | Failures |
|---|---|---|
| callback | 6/7 | callback_not_saved |
| dnd | 7/7 | - |
| end_no_dnd | 7/7 | - |

| Missed-call mode | DND | Jobs | Pass |
|---|---|---|---|

## Transcripts

### en-IN/callback/realestate PASS — disposition callback_required []
- opening: Hi, this is Ravi calling from Green Acres Realty. Do you have a moment?
- caller: I'm busy right now. Can you call me back tomorrow at 6 in the evening?
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. Thank you for your time. Goodbye.

### en-IN/dnd/realestate PASS — disposition not_interested []
- opening: Hi, this is Ravi calling from Green Acres Realty. Do you have a moment?
- caller: Please don't call this number ever again. Remove my number from your list.
- agent: (silent)
- farewell: Understood, we won't call this number again. Thank you for your time. Goodbye.

### en-IN/end_no_dnd/printing PASS — disposition interested []
- opening: Hi, this is Kavitha calling from Sri Krishna Digital Prints. How can I help you today?
- caller: What is the price of matte visiting cards?
- agent: Matte finish visiting cards cost 350 rupees per 100 cards. The minimum order is 100 cards.
- caller: Okay, that's all I needed. Thanks, bye.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### gu-IN/callback/academy PASS — disposition callback_required []
- opening: નમસ્તે! હું Teja Data Academy માંથી Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: હું અત્યારે busy છું. તમે મને કાલે સાંજે 6 વાગ્યે call કરી શકશો?
- agent: હું સમજી શકું છું કે તમે અત્યારે busy છો. મેં કાલે સાંજે 6 વાગ્યાની તમારી callback request નોંધી લીધી છે. અમારી team તમને ત્યારે call કરશે.
- caller: હા, આ જ number પર. મારું નામ Kiran છે.
- agent: ઠીક છે Kiran ભાઈ, મેં તમારો number અને કાલે સાંજે 6 વાગ્યાનો time નોંધી લીધો છે. અમારી team તમને ત્યારે જ call કરશે.
- caller: ઠીક છે, આભાર.
- agent: (silent)
- farewell: તમારી વિગતો અને ફરીથી કૉલ કરવાની વિનંતી નોંધી લીધી છે. તમારા સમય માટે આભાર. આવજો.

### gu-IN/dnd/printing PASS — disposition not_interested []
- opening: નમસ્તે! હું Sri Krishna Digital Prints માંથી Kavitha. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: પ્લીઝ હવે ક્યારેય આ number પર call ના કરતા. તમારા list માંથી મારો number કાઢી નાખજો.
- agent: (silent)
- farewell: ઠીક છે, આ નંબર પર હવે ફરી કૉલ નહીં કરીએ. તમારા સમય માટે આભાર. આવજો.

### gu-IN/end_no_dnd/academy PASS — disposition interested []
- opening: નમસ્તે! હું Teja Data Academy માંથી Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: Course fee કેટલી છે અને weekend batch છે ખરી?
- agent: Course ની fee ₹8,999 છે અને હા, weekend batch છે, જે સવારે 10 થી 1 વાગ્યા સુધી ચાલે છે.
- caller: ઠીક છે, મારે બસ આટલું જ જોઈતું હતું. આભાર, આવજો.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### hi-IN/callback/academy PASS — disposition callback_required []
- opening: नमस्ते! मैं Teja Data Academy से Madhavi। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मैं अभी busy हूँ। क्या आप मुझे कल शाम 6 बजे call कर सकते हो?
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/dnd/realestate PASS — disposition not_interested []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: प्लीज इस number पर दोबारा कभी call मत करना। अपनी list से मेरा number हटा दो।
- agent: (silent)
- farewell: ठीक है, इस नंबर पर अब दोबारा कॉल नहीं करेंगे। समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/end_no_dnd/academy PASS — disposition interested []
- opening: नमस्ते! मैं Teja Data Academy से Madhavi। बताइए, आज आपकी कैसे मदद करूँ?
- caller: Course fee कितनी है और क्या weekend batch है?
- agent: Course की fee ₹8,999 है और इसमें कोई instalment नहीं है। हाँ, weekend batch भी है, जो सुबह 10 बजे से दोपहर 1 बजे तक चलता है। क्या आप इसमें join करना चाहेंगे?
- caller: ठीक है, मुझे बस यही चाहिए था। Thanks, bye.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### kn-IN/callback/clinic FAIL — disposition callback_required ['callback_not_saved']
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾನು ಈಗ ಬ್ಯುಸಿ ಇದ್ದೀನಿ. ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡ್ತೀರಾ?
- agent: ಖಂಡಿತ, ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ callback ಮಾಡೋಕೆ ನಾನು note ಮಾಡ್ತೀನಿ. ಅಷ್ಟರಲ್ಲಿ, ನಿಮ್ಮ ಸಮಸ್ಯೆ ಏನು ಅಂತ ಹೇಳ್ತೀರಾ?
- caller: ಹೌದು, ಇದೇ number-ನಲ್ಲಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್.
- agent: ಸರಿ ಕಿರಣ್, ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ callback ಮಾಡೋಕೆ note ಮಾಡಿದ್ದೀನಿ. ನಿಮ್ಮ dental problem ಏನು ಅಂತ ಸ್ವಲ್ಪ ಹೇಳ್ತೀರಾ?
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ ಯು.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/dnd/appliance PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು SmartCare Appliance Services ಇಂದ Suresh. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ದಯವಿಟ್ಟು ಈ number-ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡ್ಬೇಡಿ. ನಿಮ್ಮ ಲಿಸ್ಟ್‌ನಿಂದ ನನ್ನ number ರಿಮೂವ್ ಮಾಡಿ.
- agent: (silent)
- farewell: ಸರಿ, ಈ ನಂಬರ್‌ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡಲ್ಲ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/end_no_dnd/clinic PASS — disposition interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ಕನ್ಸಲ್ಟೇಶನ್ ಫೀ ಎಷ್ಟು, ಮತ್ತೆ ನೀವು ಯಾವಾಗ ಓಪನ್ ಇರ್ತೀರಾ?
- agent: Consultation fee ₹300 ಇರುತ್ತೆ. ನಾವು Monday ಇಂದ Saturday ವರೆಗೆ, ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ ಸಂಜೆ 8 PM ವರೆಗೆ open ಇರ್ತೀವಿ. Appointment ಬೇಕಾ?
- caller: ಓಕೆ, ನನಗೆ ಇಷ್ಟೇ ಬೇಕಾಗಿದ್ದು. ಥ್ಯಾಂಕ್ಸ್, ಬೈ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### ml-IN/callback/appliance PASS — disposition callback_required []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: ഞാൻ ഇപ്പോ തിരക്കിലാണ്. നാളെ വൈകുന്നേരം 6 മണിക്ക് തിരിച്ചു വിളിക്കാമോ?
- agent: (silent)
- farewell: നിങ്ങളുടെ വിവരങ്ങളും തിരികെ വിളിക്കാനുള്ള അഭ്യർത്ഥനയും രേഖപ്പെടുത്തിയിട്ടുണ്ട്. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/dnd/appliance PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: ഈ number-ലേക്ക് ഇനി ഒരിക്കലും വിളിക്കരുത്. എന്റെ number നിങ്ങളുടെ ലിസ്റ്റിൽ നിന്ന് മാറ്റണം.
- agent: (silent)
- farewell: ശരി, ഈ നമ്പറിലേക്ക് ഇനി വിളിക്കില്ല. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/end_no_dnd/appliance PASS — disposition interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: split AC servicing-ന് എത്രയാകും?
- agent: സ്പ്ലിറ്റ് എസി സർവീസിങ്ങിന് ₹599 ആകും. നിങ്ങൾക്ക് ഒരു വിസിറ്റ് ആവശ്യമുണ്ടോ?
- caller: ശരി, എനിക്ക് ഇത്രയേ വേണ്ടിയിരുന്നുള്ളൂ. Thanks, bye.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ta-IN/callback/appliance PASS — disposition callback_required []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: நான் இப்போ busy-ஆ இருக்கேன். நாளைக்கு evening 6 மணிக்கு திரும்ப call பண்ண முடியுமா?
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/dnd/printing PASS — disposition not_interested []
- opening: வணக்கம்! நான் Sri Krishna Digital Prints-ல இருந்து Kavitha பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: தயவுசெஞ்சு இனிமே இந்த number-க்கு call பண்ணாதீங்க. என் number-அ உங்க list-ல இருந்து remove பண்ணிடுங்க.
- agent: (silent)
- farewell: சரி, இந்த எண்ணுக்கு இனி அழைக்க மாட்டோம். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/end_no_dnd/appliance PASS — disposition interested []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: Split AC servicing-க்கு எவ்வளவு charge பண்ணுவீங்க?
- agent: Split AC servicing-க்கு ₹599 charge பண்ணுவோம்.
- caller: Okay, எனக்கு இதுதான் வேணும். Thanks, bye.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### te-IN/callback/realestate PASS — disposition callback_required []
- opening: హలో, నేను Green Acres Realty నుండి Ravi. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను. రేపు సాయంత్రం 6 కి మళ్ళీ call చేయగలరా?
- agent: సరే, మీరు busy గా ఉన్నారని అర్థమైంది. రేపు సాయంత్రం 6 కి మళ్ళీ call చేయమని note చేస్తున్నాను.
- caller: అవును, ఈ same number కి. నా పేరు Kiran.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/dnd/appliance PASS — disposition not_interested []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: దయచేసి ఈ number కి మళ్ళీ ఎప్పుడూ call చేయకండి. నా number ని మీ list నుంచి తీసేయండి.
- agent: (silent)
- farewell: సరే, ఈ నంబర్‌కి మళ్లీ కాల్ చేయము. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/end_no_dnd/printing PASS — disposition interested []
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: Matte visiting cards price ఎంత?
- agent: Matte finish visiting cards 100 కి ₹350 అవుతుంది. మీకు ఎన్ని cards కావాలో చెప్తారా?
- caller: Okay, నాకు కావాల్సింది అంతే. Thanks, bye.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
