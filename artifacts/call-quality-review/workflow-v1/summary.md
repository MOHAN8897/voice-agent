# Workflow simulation workflow-v1

Schema `sim_a2700d0a1dd142dcb3bf941e3557d400`.

| Scenario | Pass | Failures |
|---|---|---|
| enquiry | 7/7 | - |
| callback | 6/7 | agent_did_not_close |
| dnd | 7/7 | - |
| end_no_dnd | 7/7 | - |
| negated_block | 7/7 | - |
| order | 1/7 | disposition:interested, order_not_recorded, speech:too_many_sentences:4, speech:too_many_sentences:5 |
| order_unavailable | 5/7 | speech:too_many_sentences:4 |
| refusal | 7/7 | - |

| Missed-call mode | DND | Jobs | Pass |
|---|---|---|---|
| off | False | [] | True |
| review | False | [('missed', 'needs_review', 'approval_required')] | True |
| automatic | False | [('missed', 'scheduled', 'missed_call')] | True |
| automatic | True | [('missed', 'suppressed', 'do_not_call')] | True |

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
- farewell: Thank you for your time. Goodbye.

### en-IN/end_no_dnd/printing PASS — disposition interested []
- opening: Hi, this is Kavitha calling from Sri Krishna Digital Prints. How can I help you today?
- caller: What is the price of matte visiting cards?
- agent: Matte finish visiting cards cost 350 rupees per 100 cards. What quantity were you looking at?
- caller: Okay, that's all I needed. Thanks, bye.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/enquiry/appliance PASS — disposition interested []
- opening: Hi, this is Suresh calling from SmartCare Appliance Services. How can I help you today?
- caller: How much is split AC servicing?
- agent: Split AC servicing costs 599 rupees.
- caller: Okay, please note my enquiry. My name is Kiran and I am interested.
- agent: Noted, Kiran. I have your name and that you are interested. To save your enquiry, I also need to know which appliance you need help with and the issue you are facing.
- caller: That's all for now, thank you.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/negated_block/realestate PASS — disposition callback_required []
- opening: Hi, this is Ravi calling from Green Acres Realty. Do you have a moment?
- caller: I'm driving now. Don't block my number, I am interested. Call me next Monday morning.
- agent: Noted. I’ll call you next Monday morning.
- caller: Yes, same number. My name is Kiran.
- agent: (silent)
- caller: Thanks.
- agent: Noted, Kiran. I’ll reach you next Monday morning on the same number.

### en-IN/order/printing FAIL — disposition converted ['speech:too_many_sentences:4']
- opening: Hi, this is Kavitha calling from Sri Krishna Digital Prints. How can I help you today?
- caller: I want 200 matte visiting cards.
- agent: Matte visiting cards are 350 rupees per 100 cards, so 200 cards will be 700 rupees. That meets our 100-card minimum. To place the order, I will need your name and delivery address.
- caller: My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.
- agent: Your order for 200 matte visiting cards is confirmed, Ravi Kumar. Delivery to 12 MG Road, Vijayawada will take 3 working days after artwork approval, and payment is cash on delivery.
- caller: Yes, please confirm the order.
- agent: The order is confirmed, Ravi Kumar. Your 200 matte visiting cards to 12 MG Road, Vijayawada are all set, and delivery will take 3 working days after artwork approval. Payment is cash on delivery. Just let me know if you need anything else.
- caller: Thanks, that's all.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/order_unavailable/appliance FAIL — disposition not_interested ['speech:too_many_sentences:4', 'speech:too_many_sentences:4']
- opening: Hi, this is Suresh calling from SmartCare Appliance Services. How can I help you today?
- caller: Book it for tomorrow 11 AM and confirm the booking right now.
- agent: I can help you book a visit, but I need a few details first. To confirm the booking right now, please tell me your name, which appliance needs servicing, the issue, your locality, and I have noted tomorrow at 11 AM.
- caller: Is it confirmed? Give me the booking number.
- agent: No, it is not confirmed yet. I still need your name, the appliance, the issue, and your locality to confirm the booking. I have noted your preferred slot as tomorrow at 11 AM. What is your name?
- caller: Okay, thanks.
- agent: No, it is not confirmed yet. I still need your name, the appliance, the issue, and your locality to confirm the booking. I have noted your preferred slot as tomorrow at 11 AM. What is your name?

### en-IN/refusal/academy PASS — disposition not_interested []
- opening: Hi, this is Madhavi calling from Teja Data Academy. How can I help you today?
- caller: No, I'm not interested. Thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### gu-IN/callback/academy PASS — disposition callback_required []
- opening: નમસ્તે! હું Teja Data Academy માંથી Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: I'm busy right now. Can you call me back tomorrow at 6 in the evening?
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. તમારા સમય માટે આભાર. આવજો.

### gu-IN/dnd/printing PASS — disposition not_interested []
- opening: નમસ્તે! હું Sri Krishna Digital Prints માંથી Kavitha. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: Please don't call this number ever again. Remove my number from your list.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/end_no_dnd/academy PASS — disposition interested []
- opening: નમસ્તે! હું Teja Data Academy માંથી Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: What is the course fee and is there a weekend batch?
- agent: Course ની fee ₹8,999 છે અને તેમાં કોઈ instalments નથી. હા, weekend batch પણ છે, જે સવારે 10 AM થી બપોરે 1 PM સુધી ચાલે છે. શું તમે free demo class માટે તમારું નામ, qualification અને preferred batch જણાવશો?
- caller: Okay, that's all I needed. Thanks, bye.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/enquiry/clinic PASS — disposition interested []
- opening: નમસ્તે! હું Sunrise Dental Clinic માંથી Anjali. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: How much is the consultation fee and when are you open?
- agent: Consultation fee ₹300 છે અને અમે Monday થી Saturday, સવારે 10 થી સાંજે 8 સુધી open રહીએ છીએ. બીજું કઈ જાણવું છે?
- caller: Okay, please note my enquiry. My name is Kiran and I am interested.
- agent: ઠીક છે, કિરણ. મેં તમારી enquiry નોંધી લીધી છે. તમે શેના વિશે વધુ માહિતી મેળવવા માંગો છો?
- caller: That's all for now, thank you.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/negated_block/realestate PASS — disposition callback_required []
- opening: નમસ્તે, હું Green Acres Realty માંથી Ravi. એક મિનિટ વાત થઈ શકે?
- caller: I'm driving now. Don't block my number, I am interested. Call me next Monday morning.
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. તમારા સમય માટે આભાર. આવજો.

### gu-IN/order/printing PASS — disposition converted []
- opening: નમસ્તે! હું Sri Krishna Digital Prints માંથી Kavitha. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: I want 200 matte visiting cards.
- agent: સારું. Matte visiting cards ના 200 cards ના ₹700 થશે. Order place કરવા માટે તમારું નામ અને Vijayawada નું delivery address કહેશો?
- caller: My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.
- agent: તમારો order confirm થઈ ગયો છે. 200 matte visiting cards નું delivery artwork approval પછી 3 working days માં 12 MG Road, Vijayawada પર પહોંચી જશે. Payment cash on delivery રહેશે.
- caller: Yes, please confirm the order.
- agent: હા, તમારો order confirm થઈ ગયો છે. 200 matte visiting cards નું delivery artwork approval પછી 3 working days માં 12 MG Road, Vijayawada પર પહોંચી જશે. Payment cash on delivery રહેશે.
- caller: Thanks, that's all.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/order_unavailable/clinic PASS — disposition not_interested []
- opening: નમસ્તે! હું Sunrise Dental Clinic માંથી Anjali. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: Book it for tomorrow 11 AM and confirm the booking right now.
- agent: હું અત્યારે જ બુકિંગ કન્ફર્મ કરી શકતી નથી. એપોઇન્ટમેન્ટ માટે મારે તમારું નામ અને શું તકલીફ છે એ જાણવું પડશે, જેથી ફ્રન્ટ ડેસ્ક આવતીકાલે સવારે 11 વાગ્યાની એપોઇન્ટમેન્ટ કન્ફર્મ કરી શકે. તમારું નામ શું છે?
- caller: Is it confirmed? Give me the booking number.
- agent: ના, હજી એપોઇન્ટમેન્ટ કન્ફર્મ નથી થયું, એટલે કોઈ booking number જનરેટ થયો નથી. ફ્રન્ટ ડેસ્ક વિગતો ચેક ન કરે ત્યાં સુધી એ કન્ફર્મ નહીં થાય. તમારું નામ જણાવશો?
- caller: Okay, thanks.
- agent: ના, હજી એપોઇન્ટમેન્ટ કન્ફર્મ નથી થયું, એટલે કોઈ booking number જનરેટ થયો નથી. ફ્રન્ટ ડેસ્ક વિગતો ચેક ન કરે ત્યાં સુધી એ કન્ફર્મ નહીં થાય. તમારું નામ જણાવશો?

### gu-IN/refusal/realestate PASS — disposition not_interested []
- opening: નમસ્તે, હું Green Acres Realty માંથી Ravi. એક મિનિટ વાત થઈ શકે?
- caller: No, I'm not interested. Thanks.
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
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/end_no_dnd/academy PASS — disposition interested []
- opening: नमस्ते! मैं Teja Data Academy से Madhavi। बताइए, आज आपकी कैसे मदद करूँ?
- caller: Course fee कितनी है और क्या weekend batch है?
- agent: Course की fee ₹8,999 है और इसमें कोई instalment नहीं है। हाँ, weekend batch available है, जो सुबह 10 AM से 1 PM तक चलता है। क्या आप free demo class लेना चाहेंगे?
- caller: ठीक है, मुझे बस यही चाहिए था। Thanks, bye.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/enquiry/clinic PASS — disposition interested []
- opening: नमस्ते! मैं Sunrise Dental Clinic से Anjali। बताइए, आज आपकी कैसे मदद करूँ?
- caller: Consultation fee कितनी है और आप कब खुलते हो?
- agent: Consultation fee ₹300 है, और हम Monday से Saturday, सुबह 10 AM से रात 8 PM तक खुले रहते हैं।
- caller: ठीक है, मेरी enquiry note कर लीजिए। मेरा नाम किरण है और मुझे interest है।
- agent: ठीक है किरण जी, आपकी enquiry नोट कर ली है। आप किस समस्या के लिए अपॉइंटमेंट लेना चाहते हैं और किस दिन और समय पर आना पसंद करेंगे?
- caller: अभी के लिए बस इतना ही, thank you.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/negated_block/realestate PASS — disposition callback_required []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: मैं अभी drive कर रहा हूँ। मेरा number block मत करना, मुझे interest है। मुझे अगले सोमवार सुबह call करना।
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order/printing FAIL — disposition interested ['order_not_recorded', 'disposition:interested', 'speech:too_many_sentences:4']
- opening: नमस्ते! मैं Sri Krishna Digital Prints से Kavitha। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मुझे 200 matte visiting cards चाहिए।
- agent: ठीक है। Matte finish cards का rate ₹350 per 100 cards है, तो 200 cards का total ₹700 होगा। Minimum order 100 cards का ही होता है। बताइए, order confirm कर दूँ?
- caller: मेरा नाम रवि कुमार है। Vijayawada में 12 MG Road पर deliver कर देना।
- agent: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order_unavailable/clinic PASS — disposition callback_required []
- opening: नमस्ते! मैं Sunrise Dental Clinic से Anjali। बताइए, आज आपकी कैसे मदद करूँ?
- caller: इसे कल सुबह 11 बजे के लिए बुक करो और अभी booking confirm कर दो।
- agent: ठीक है, कल सुबह 11 बजे की appointment के लिए मुझे आपका नाम और क्या problem है, ये बता दीजिए ताकि front desk इसे confirm कर सके।
- caller: क्या ये confirm हो गया? मुझे booking number दो।
- agent: अभी तक booking confirm नहीं हुई है, इसलिए कोई booking number नहीं दिया जा सकता। अभी तक आपका नाम और problem details नहीं मिली हैं, जो front desk को booking confirm करने के लिए चाहिए। अपना नाम और problem बता दीजिए।
- caller: ठीक है, thanks.
- agent: अभी तक booking confirm नहीं हुई है, इसलिए कोई booking number नहीं दिया जा सकता। अभी तक आपका नाम और problem details नहीं मिली हैं, जो front desk को booking confirm करने के लिए चाहिए। अपना नाम और problem बता दीजिए।

### hi-IN/refusal/realestate PASS — disposition not_interested []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: नहीं, मुझे interest नहीं है। Thanks.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### kn-IN/callback/clinic FAIL — disposition callback_required ['agent_did_not_close']
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾನು ಈಗ ಬ್ಯುಸಿ ಇದ್ದೀನಿ. ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡ್ತೀರಾ?
- agent: ಕ್ಷಮಿಸಿ, ಈಗ ಕಾಲ್ ಬ್ಯಾಕ್ ಮಾಡಲು ನನಗೆ ಅನುಮತಿ ಇಲ್ಲ. ನಾನು ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡಬಹುದೇ ಎಂದು ಪರಿಶೀಲಿಸಬಹುದು, ಆದರೆ ಅದನ್ನು ಈಗಲೇ ಖಚಿತಪಡಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ನಿಮಗೆ ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕಿದ್ದರೆ ತಿಳಿಸಿ.
- caller: ಹೌದು, ಇದೇ number-ನಲ್ಲಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್.
- agent: ಕ್ಷಮಿಸಿ, ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡುವುದನ್ನು ಈಗಲೇ ಖಚಿತಪಡಿಸಲು ನನಗೆ ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. ನಾನು ಪರಿಶೀಲಿಸಬಹುದು, ಆದರೆ ಅದನ್ನು ಈಗಲೇ ಖಚಿತಪಡಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ನಿಮಗೆ ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕಿದ್ದರೆ ತಿಳಿಸಿ.
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ ಯು.
- agent: ಸರಿ, ಕಿರಣ್ ಅವರೇ. ನಿಮಗೆ ಬೇರೆ ಏನಾದರೂ ಮಾಹಿತಿ ಬೇಕಿದ್ದರೆ ಹೇಳಿ.

### kn-IN/dnd/appliance PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು SmartCare Appliance Services ಇಂದ Suresh. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ದಯವಿಟ್ಟು ಈ number-ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡ್ಬೇಡಿ. ನಿಮ್ಮ ಲಿಸ್ಟ್‌ನಿಂದ ನನ್ನ number ರಿಮೂವ್ ಮಾಡಿ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/end_no_dnd/clinic PASS — disposition interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ಕನ್ಸಲ್ಟೇಶನ್ ಫೀ ಎಷ್ಟು, ಮತ್ತೆ ನೀವು ಯಾವಾಗ ಓಪನ್ ಇರ್ತೀರಾ?
- agent: Consultation fee ₹300 ಇರುತ್ತೆ. ನಾವು Monday ಇಂದ Saturday ವರೆಗೆ, ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ ರಾತ್ರಿ 8 PM ವರೆಗೆ open ಇರ್ತೀವಿ.
- caller: ಓಕೆ, ನನಗೆ ಇಷ್ಟೇ ಬೇಕಾಗಿದ್ದು. ಥ್ಯಾಂಕ್ಸ್, ಬೈ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/enquiry/printing PASS — disposition interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sri Krishna Digital Prints ಇಂದ Kavitha. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: matte ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಪ್ರೈಸ್ ಎಷ್ಟು?
- agent: Matte finish visiting cards ಬೆಲೆ 100 cards-ಗೆ ₹350 ಆಗುತ್ತೆ. Minimum order 100 cards ಇರುತ್ತೆ. ನಿಮಗೆ ಎಷ್ಟು quantity ಬೇಕಿತ್ತು?
- caller: ಓಕೆ, ದಯವಿಟ್ಟು ನನ್ನ enquiry ನೋಟ್ ಮಾಡಿಕೊಳ್ಳಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇದೆ.
- agent: ಸರಿ ಕಿರಣ್, ನಿಮ್ಮ enquiry ನೋಟ್ ಮಾಡ್ಕೊಂಡೆ. ನಿಮಗೆ matte finish visiting cards ಎಷ್ಟು quantity ಬೇಕಿತ್ತು ಅಂತ ಸ್ವಲ್ಪ ಹೇಳ್ತೀರಾ?
- caller: ಸದ್ಯಕ್ಕೆ ಅಷ್ಟೇ, ಥ್ಯಾಂಕ್ ಯು.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/negated_block/realestate PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ, ನಾನು Green Acres Realty ಇಂದ Ravi. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- caller: ನಾನು ಈಗ ಡ್ರೈವ್ ಮಾಡ್ತಿದ್ದೀನಿ. ನನ್ನ number ಬ್ಲಾಕ್ ಮಾಡ್ಬೇಡಿ, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇದೆ. ಮುಂದಿನ ಸೋಮವಾರ ಬೆಳಿಗ್ಗೆ ಕಾಲ್ ಮಾಡಿ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ವಿವರಗಳನ್ನು ಮತ್ತು ಮತ್ತೆ ಕರೆ ಮಾಡುವ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order/printing FAIL — disposition converted ['speech:too_many_sentences:4', 'speech:too_many_sentences:4']
- opening: ನಮಸ್ಕಾರ! ನಾನು Sri Krishna Digital Prints ಇಂದ Kavitha. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನನಗೆ 200 matte ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಬೇಕು.
- agent: (silent)
- caller: ನನ್ನ ಹೆಸರು ರವಿ ಕುಮಾರ್. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ ಡೆಲಿವರಿ ಮಾಡಿ.
- agent: ಸರಿ ರವಿ ಕುಮಾರ್ ಅವರೇ. 200 matte finish cards-ಗೆ ₹700 ಆಗುತ್ತೆ. ವಿಜಯವಾಡದಲ್ಲಿ artwork approve ಆದ ಮೇಲೆ 3 working days-ನಲ್ಲಿ delivery ಆಗುತ್ತೆ. ನಿಮ್ಮ delivery address 12 MG Road, ವಿಜಯವಾಡ ಅಂತ confirm ಮಾಡಿದ್ದೀರಾ, ಸರಿನಾ?
- caller: ಹೌದು, ದಯವಿಟ್ಟು order ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ಸರಿ ರವಿ ಕುಮಾರ್ ಅವರೇ. ನಿಮ್ಮ order confirm ಆಗಿದೆ: 200 matte finish visiting cards, delivery address 12 MG Road, ವಿಜಯವಾಡ. Artwork approve ಆದ ಮೇಲೆ 3 working days-ನಲ್ಲಿ delivery ಆಗುತ್ತೆ. Payment cash on delivery ಇರುತ್ತೆ.
- caller: ಥ್ಯಾಂಕ್ಸ್, ಅಷ್ಟೇ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order_unavailable/clinic PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾಳೆಗೆ 11 AM-ಗೆ ಬುಕ್ ಮಾಡಿ, ಈಗಲೇ ಬುಕ್ಕಿಂಗ್ ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ನಾಳೆಗೆ, ಅಂದ್ರೆ October 31st ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ appointment ಬುಕ್ ಮಾಡಬೇಕಲ್ವಾ? ಈಗಲೇ ಅದನ್ನು confirm ಮಾಡಲು ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ತಿಳಿಸುತ್ತೀರಾ?
- caller: ಕನ್ಫರ್ಮ್ ಆಯ್ತಾ? ನನಗೆ ಬುಕ್ಕಿಂಗ್ number ಕೊಡಿ.
- agent: ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ details ಇನ್ನು save ಆಗಿಲ್ಲ, ಹಾಗಾಗಿ ಈಗಲೇ booking number ಕೊಡೋಕೆ ಆಗಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ಹೇಳಿದ್ರೆ, ನಾನು note ಮಾಡ್ಕೊಳ್ತೀನಿ, ಆಮೇಲೆ front desk ಕಡೆಯಿಂದ confirm ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ಸ್.
- agent: ಕ್ಷಮಿಸಿ, front desk ಕಡೆಯಿಂದ confirm ಆಗುವವರೆಗೂ booking number ಇರೋದಿಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ಹೇಳಿದ್ರೆ, ನಾನು note ಮಾಡ್ಕೊಳ್ತೀನಿ, ಆಮೇಲೆ front desk ಕಡೆಯಿಂದ confirm ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ ಹೆಸರು ಏನು?

### kn-IN/refusal/realestate PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ, ನಾನು Green Acres Realty ಇಂದ Ravi. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- caller: ಇಲ್ಲ, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇಲ್ಲ. ಥ್ಯಾಂಕ್ಸ್.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### ml-IN/callback/appliance PASS — disposition callback_required []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: I'm busy right now. Can you call me back tomorrow at 6 in the evening?
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/dnd/appliance PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: Please don't call this number ever again. Remove my number from your list.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/end_no_dnd/appliance PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: How much is split AC servicing?
- agent: സ്പ്ലിറ്റ് എസി സർവീസിംഗിന് ₹599 ആണ് വരുന്നത്. ഇതിനെക്കുറിച്ച് കൂടുതൽ അറിയണോ?
- caller: Okay, that's all I needed. Thanks, bye.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/enquiry/academy PASS — disposition interested []
- opening: നമസ്കാരം! ഞാൻ Teja Data Academy-ൽ നിന്ന് Madhavi. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: What is the course fee and is there a weekend batch?
- agent: കോഴ്സ് ഫീ ₹8,999 ആണ്, ഇതിന് instalments ഒന്നുമില്ല. Weekend batch 10 AM മുതൽ 1 PM വരെയാണ്. ഇതിൽ താല്പര്യമുണ്ടോ?
- caller: Okay, please note my enquiry. My name is Kiran and I am interested.
- agent: ശരി കിരൺ, നിങ്ങളുടെ ആവശ്യം ഞാൻ ഇവിടെ രേഖപ്പെടുത്തിയിട്ടുണ്ട്. കോഴ്സ് ഫീ ₹8,999 ആണ്, ഇതിന് instalments ഒന്നുമില്ല. ഏത് ബാച്ചിലാണ് താല്പര്യം എന്ന് പറയാമോ?
- caller: That's all for now, thank you.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/negated_block/realestate PASS — disposition callback_required []
- opening: നമസ്കാരം, ഞാൻ Green Acres Realty-ൽ നിന്ന് Ravi. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- caller: I'm driving now. Don't block my number, I am interested. Call me next Monday morning.
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order/printing FAIL — disposition converted ['speech:too_many_sentences:5', 'speech:too_many_sentences:4']
- opening: നമസ്കാരം! ഞാൻ Kavitha. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: I want 200 matte visiting cards.
- agent: ശരി. Matte finish visiting cards-ന് 100 എണ്ണത്തിന് ₹350 ആണ് rate. അപ്പൊ 200 എണ്ണത്തിന് ₹700 ആകും. Minimum order 100 cards ആണ്. Order place ചെയ്യാൻ നിങ്ങളുടെ പേരും delivery address-ഉം ഒന്ന് പറയാമോ?
- caller: My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.
- agent: Draft-ൽ പറഞ്ഞിരിക്കുന്ന total cost (₹700) മാത്രമേ ഉറപ്പിക്കാൻ കഴിയൂ. Matte visiting cards-ന് 100 എണ്ണത്തിന് ₹350 ആണ് rate, അപ്പൊ 200 എണ്ണത്തിന് ₹700 ആകും. Minimum order 100 cards ആണ്.
- caller: Yes, please confirm the order.
- agent: Order confirm ആയിട്ടുണ്ട്. 200 matte visiting cards-ന് ₹700 ആണ് total amount. Delivery address 12 MG Road, Vijayawada ആണ്. Payment method cash on delivery ആണ്.
- caller: Thanks, that's all.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order_unavailable/appliance PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: Book it for tomorrow 11 AM and confirm the booking right now.
- agent: ക്ഷമിക്കണം, ബുക്കിംഗ് ഇപ്പോൾ സ്ഥിരീകരിക്കാൻ കഴിയില്ല. ഒരു visit ബുക്ക് ചെയ്യുന്നതിന് മുൻപ്, ഏത് appliance ആണ് service ചെയ്യേണ്ടത് എന്നും ഏത് area-യിലാണ് ഉള്ളത് എന്നും ഒന്ന് പറയാമോ? ഞങ്ങളുടെ service വരുന്നത് Madhapur, Gachibowli, Kondapur, Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമാണ്.
- caller: Is it confirmed? Give me the booking number.
- agent: ഇല്ല, ഇതുവരെ ഒന്നും confirm ആയിട്ടില്ല. ബുക്കിംഗ് number ഇപ്പോൾ തരാൻ കഴിയില്ല.
- caller: Okay, thanks.
- agent: ഇല്ല, ഇതുവരെ ഒന്നും confirm ആയിട്ടില്ല, ബുക്കിംഗ് number ഇപ്പോൾ തരാൻ കഴിയില്ല. ഒരു visit ബുക്ക് ചെയ്യുന്നതിന് മുൻപ്, ഏത് appliance ആണ് service ചെയ്യേണ്ടത് എന്നും ഏത് area-യിലാണ് ഉള്ളത് എന്നും ഒന്ന് പറയാമോ?

### ml-IN/refusal/academy PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ Teja Data Academy-ൽ നിന്ന് Madhavi. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: No, I'm not interested. Thanks.
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
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/end_no_dnd/appliance PASS — disposition interested []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: Split AC servicing-க்கு எவ்வளவு charge பண்ணுவீங்க?
- agent: Split AC servicing-க்கு ₹599 charge பண்ணுவோம்.
- caller: Okay, எனக்கு இதுதான் வேணும். Thanks, bye.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/enquiry/academy PASS — disposition interested []
- opening: வணக்கம்! நான் Teja Data Academy-ல இருந்து Madhavi பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: Course fee எவ்ளோ, weekend batch இருக்கா?
- agent: Course fee ₹8,999 வரும், அதுல எந்த instalment option-உம் கிடையாது. Weekend batch காலைல 10 AM-ல இருந்து 1 PM வரைக்கும் இருக்கு. உங்களுக்கு இதுல சேர விருப்பம் இருக்கா?
- caller: Okay, என் enquiry-அ note பண்ணிக்கோங்க. என் பேரு Kiran, எனக்கு interest இருக்கு.
- agent: சரி கிரன், உங்க enquiry-அ note பண்ணியாச்சு. இப்போ உங்களுக்கு எந்த qualification இருக்கு, அப்புறம் எந்த batch-ல சேர விருப்பம்னு சொல்ல முடியுமா?
- caller: இப்போதைக்கு அவ்வளவுதான், thank you.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/negated_block/realestate PASS — disposition callback_required []
- opening: வணக்கம், நான் Green Acres Realty-ல இருந்து Ravi. ஒரு நிமிஷம் பேசலாமா?
- caller: நான் இப்போ drive பண்றேன். என்னோட number-அ block பண்ணாதீங்க, எனக்கு interest இருக்கு. அடுத்த Monday morning call பண்ணுங்க.
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order/printing FAIL — disposition converted ['speech:too_many_sentences:5', 'speech:too_many_sentences:4', 'speech:too_many_sentences:4']
- opening: வணக்கம்! நான் Sri Krishna Digital Prints-ல இருந்து Kavitha பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: எனக்கு 200 matte visiting cards வேணும்.
- agent: சரி, matte finish visiting cards ஒரு 100-க்கு ₹350 வரும். நீங்க 200 cards கேட்டிருக்கறதால, total ₹700 வரும். Minimum order 100 cards தான். உங்க பேரும் delivery address-உம் சொல்ல முடியுமா? அப்போ தான் order confirm பண்ண முடியும்.
- caller: என் பேரு Ravi Kumar. Vijayawada-ல இருக்குற 12 MG Road-க்கு deliver பண்ணுங்க.
- agent: உங்க order confirm ஆயிடுச்சு. 200 matte visiting cards, Ravi Kumar பேர்ல, 12 MG Road, Vijayawada-க்கு. Artwork approve ஆனதும் 3 working days-ல delivery வந்துடும். Payment cash on delivery தான்.
- caller: ஆமா, order-அ confirm பண்ணுங்க.
- agent: ஆமா, order confirm ஆயிடுச்சு. 200 matte visiting cards, Ravi Kumar பேர்ல, 12 MG Road, Vijayawada-க்கு. Artwork approve ஆனதும் 3 working days-ல delivery வந்துடும். Payment cash on delivery தான்.
- caller: Thanks, அவ்வளவுதான்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order_unavailable/appliance PASS — disposition not_interested []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: நாளைக்கு 11 AM-க்கு book பண்ணி, இப்பவே booking-அ confirm பண்ணுங்க.
- agent: நாளைக்கு 11 AM-க்கு visit வேணும்னு நான் note பண்ணி வைக்கிறேன், ஆனா இப்பவே என்னால booking-அ confirm பண்ண முடியாது. visit-அ confirm பண்ண உங்க பேரும், எந்த area-ல இருந்து கூப்பிடுறீங்கன்னு சொல்ல முடியுமா?
- caller: Confirm ஆயிடுச்சா? Booking number சொல்லுங்க.
- agent: இன்னும் booking confirm ஆகலங்க. உங்க booking number என்னன்னு சொன்னீங்கன்னா, நான் check பண்ணி சொல்றேன்.
- caller: Okay, thanks.
- agent: இன்னும் booking confirm ஆகலங்க. என்னால இப்பவே booking-அ confirm பண்ண முடியாது, ஆனா நீங்க சொன்ன details-அ note பண்ணி வெச்சிருக்கேன். உங்க booking number-அ மட்டும் கொஞ்சம் சொல்லுங்க, நான் check பண்ணி சொல்றேன்.

### ta-IN/refusal/academy PASS — disposition not_interested []
- opening: வணக்கம்! நான் Teja Data Academy-ல இருந்து Madhavi பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: இல்ல, எனக்கு interest இல்ல. Thanks.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### te-IN/callback/realestate PASS — disposition callback_required []
- opening: హలో, నేను Green Acres Realty నుండి Ravi. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు busy గా ఉన్నాను. రేపు సాయంత్రం 6 కి మళ్ళీ call చేయగలరా?
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/dnd/appliance PASS — disposition not_interested []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: దయచేసి ఈ number కి మళ్ళీ ఎప్పుడూ call చేయకండి. నా number ని మీ list నుంచి తీసేయండి.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/end_no_dnd/printing PASS — disposition interested []
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: Matte visiting cards price ఎంత?
- agent: Matte finish visiting cards 100 cards కి ₹350 అవుతుంది. Minimum order 100 cards ఉంటుంది. మీకు ఎన్ని cards కావాలో చెప్తారా?
- caller: Okay, నాకు కావాల్సింది అంతే. Thanks, bye.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/enquiry/appliance PASS — disposition interested []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: Split AC servicing కి ఎంత అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది.
- caller: Okay, నా enquiry note చేసుకోండి. నా పేరు Kiran, నాకు interest ఉంది.
- agent: సరే కిరణ్ గారు, మీ Split AC servicing enquiry తీసుకున్నాను. మీకు service కావాలంటే, మీ locality మరియు మీకు అనుకూలమైన time చెప్పండి, మా team confirm చేస్తుంది.
- caller: For now అంతే, thank you.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/negated_block/realestate PASS — disposition callback_required []
- opening: హలో, నేను Green Acres Realty నుండి Ravi. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు drive చేస్తున్నాను. నా number block చేయకండి, నాకు interest ఉంది. వచ్చే Monday morning నాకు call చేయండి.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order/printing FAIL — disposition converted ['speech:too_many_sentences:5', 'speech:too_many_sentences:4', 'speech:too_many_sentences:4']
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు 200 matte visiting cards కావాలి.
- agent: సరే, matte finish visiting cards 100 కి ₹350 అవుతాయి. So 200 cards కి మొత్తం ₹700 అవుతుంది. Minimum order 100 cards ఉంటుంది, సో ఇది సరిపోతుంది. మీ పేరు, delivery address చెప్తారా? Order confirm చేస్తాను.
- caller: నా పేరు Ravi Kumar. Vijayawada లోని 12 MG Road కి deliver చేయండి.
- agent: మీ order confirm అయింది. 200 matte visiting cards మీ పేరు Ravi Kumar, address 12 MG Road, Vijayawada కి order చేశాను. Artwork approve అయిన తర్వాత Vijayawada లో delivery 3 working days లో అవుతుంది. Payment cash on delivery ఉంటుంది.
- caller: అవును, order confirm చేయండి.
- agent: సరే, మీ order confirm అయింది. 200 matte visiting cards మీ పేరు Ravi Kumar, address 12 MG Road, Vijayawada కి order చేశాను. Artwork approve అయిన తర్వాత Vijayawada లో delivery 3 working days లో అవుతుంది. Payment cash on delivery ఉంటుంది.
- caller: Thanks, అంతే.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order_unavailable/appliance FAIL — disposition callback_required ['speech:too_many_sentences:4']
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: రేపు ఉదయం 11 కి బుక్ చేయండి, ఇప్పుడే booking confirm చేయండి.
- agent: నేను ఇప్పుడే booking confirm చేయలేను. రేపు ఉదయం 11 గంటలకి visit కోసం note చేస్తున్నాను; మా team ఒకసారి confirm చేశాక మీకు చెప్తారు. మీరు ఏ area లో ఉంటారు?
- caller: Confirm అయిందా లేదా? నాకు booking number ఇవ్వండి.
- agent: ఇంకా confirm అవ్వలేదు. నాకు booking number ఇవ్వడానికి వీలు లేదు. నేను కేవలం మీ preferred time note చేస్తున్నాను, మా team review చేశాక మీకు చెప్తారు. మీరు ఏ locality లో ఉంటారు?
- caller: Okay, thanks.
- agent: ఇంకా confirm అవ్వలేదు, నాకు booking number ఇవ్వడానికి వీలు లేదు. నేను కేవలం మీ preferred time note చేస్తున్నాను, మా team review చేశాక మీకు చెప్తారు. మీరు ఏ locality లో ఉంటారు?

### te-IN/refusal/academy PASS — disposition not_interested []
- opening: నమస్తే! నేను Teja Data Academy నుండి Madhavi. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: లేదు, నాకు interest లేదు. Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
