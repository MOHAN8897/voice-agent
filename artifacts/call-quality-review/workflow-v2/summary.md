# Workflow simulation workflow-v2

Schema `sim_3d1132ba1a514e8ebd1ec257dcdecc86`.

| Scenario | Pass | Failures |
|---|---|---|
| enquiry | 7/7 | - |
| callback | 7/7 | - |
| dnd | 7/7 | - |
| end_no_dnd | 7/7 | - |
| negated_block | 7/7 | - |
| order | 7/7 | - |
| order_unavailable | 7/7 | - |
| refusal | 6/7 | agent_did_not_close |

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
- farewell: Understood, we won't call this number again. Thank you for your time. Goodbye.

### en-IN/end_no_dnd/printing PASS — disposition interested []
- opening: Hi, this is Kavitha calling from Sri Krishna Digital Prints. How can I help you today?
- caller: What is the price of matte visiting cards?
- agent: Matte finish visiting cards cost 350 rupees per 100 cards. The minimum order is 100 cards. Would you like to place an order?
- caller: Okay, that's all I needed. Thanks, bye.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/enquiry/appliance PASS — disposition interested []
- opening: Hi, this is Suresh calling from SmartCare Appliance Services. How can I help you today?
- caller: How much is split AC servicing?
- agent: Split AC servicing costs 599 rupees.
- caller: Okay, please note my enquiry. My name is Kiran and I am interested.
- agent: Noted, Kiran. I have your enquiry. What appliance are you interested in?
- caller: That's all for now, thank you.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/negated_block/realestate PASS — disposition callback_required []
- opening: Hi, this is Ravi calling from Green Acres Realty. Do you have a moment?
- caller: I'm driving now. Don't block my number, I am interested. Call me next Monday morning.
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. Thank you for your time. Goodbye.

### en-IN/order/printing PASS — disposition converted []
- opening: Hi, this is Kavitha calling from Sri Krishna Digital Prints. How can I help you today?
- caller: I want 200 matte visiting cards.
- agent: Matte finish visiting cards are 350 rupees per 100 cards, so 200 cards will be 700 rupees. The minimum order of 100 cards is met. To proceed, I will need your name and delivery address.
- caller: My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.
- agent: Your order for 200 matte visiting cards is confirmed for Ravi Kumar, delivery to 12 MG Road, Vijayawada. Delivery will take 3 working days after artwork approval, and payment is cash on delivery.
- caller: Yes, please confirm the order.
- agent: Your order is confirmed in our system. Delivery will take 3 working days after artwork approval, and payment is cash on delivery.
- caller: Thanks, that's all.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: Hi, this is Suresh calling from SmartCare Appliance Services. How can I help you today?
- caller: Book it for tomorrow 11 AM and confirm the booking right now.
- agent: I can note that request for you. To confirm the visit, I need your name, the appliance and issue, and your locality. We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only.
- caller: Is it confirmed? Give me the booking number.
- agent: It is not confirmed yet, so I do not have a booking number. Once our team confirms the visit, I will share it with you.
- caller: Okay, thanks.
- agent: I do not have a booking number yet because the visit is not confirmed. To proceed, I still need your name, the appliance and issue, and your locality. We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only.

### en-IN/refusal/academy PASS — disposition not_interested []
- opening: Hi, this is Madhavi calling from Teja Data Academy. How can I help you today?
- caller: No, I'm not interested. Thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### gu-IN/callback/academy PASS — disposition callback_required []
- opening: નમસ્તે! હું Teja Data Academy માંથી Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: હું અત્યારે busy છું. તમે મને કાલે સાંજે 6 વાગ્યે call કરી શકશો?
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
- agent: Python with Data Analytics course ની fee ₹8,999 છે અને કોઈ instalments નથી. હા, weekend batch ઉપલબ્ધ છે, જે સવારે 10 થી 1 વાગ્યા સુધીનો રહેશે. શું તમે free demo class માટે તમારું નામ અને qualification જણાવશો?
- caller: ઠીક છે, મારે બસ આટલું જ જોઈતું હતું. આભાર, આવજો.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/enquiry/clinic PASS — disposition interested []
- opening: નમસ્તે! હું Sunrise Dental Clinic માંથી Anjali. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: consultation fee કેટલી છે અને તમારી દુકાન ક્યારે ખુલે છે?
- agent: Consultation fee ₹300 છે, અને અમારી clinic Monday થી Saturday, સવારે 10 થી સાંજે 8 સુધી ખુલ્લી રહે છે.
- caller: ઠીક છે, મારી enquiry note કરી લેજો. મારું નામ Kiran છે અને મને interest છે.
- agent: ઠીક છે, Kiran. તમારી enquiry મેં note કરી લીધી છે. શું તમે જણાવશો કે તમારે કઈ સમસ્યા માટે સલાહ લેવી છે?
- caller: અત્યારે બસ આટલું જ, આભાર.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/negated_block/realestate PASS — disposition callback_required []
- opening: નમસ્તે, હું Green Acres Realty માંથી Ravi. એક મિનિટ વાત થઈ શકે?
- caller: હું અત્યારે driving કરું છું. મારો number block ના કરતા, મને interest છે. આવતા સોમવારે સવારે મને call કરજો.
- agent: (silent)
- farewell: તમારી વિગતો અને ફરીથી કૉલ કરવાની વિનંતી નોંધી લીધી છે. તમારા સમય માટે આભાર. આવજો.

### gu-IN/order/printing PASS — disposition converted []
- opening: નમસ્તે! હું Sri Krishna Digital Prints માંથી Kavitha. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: મારે 200 matte visiting cards જોઈએ છે.
- agent: સારું. Matte finish cards ના 200 pieces નો ભાવ ₹350 per 100 cards છે, એટલે total ₹700 થશે. Order confirm કરવા માટે તમારું નામ અને delivery address જણાવશો?
- caller: મારું નામ Ravi Kumar છે. Vijayawada માં 12 MG Road પર delivery કરી દેજો.
- agent: તમારો order confirm થઈ ગયો છે. Vijayawada માં 12 MG Road પર artwork approval પછી 3 working days માં delivery થઈ જશે.
- caller: હા, order confirm કરી દો.
- agent: તમારો order system માં record થઈ ગયો છે. Artwork approval પછી 3 working days માં delivery થઈ જશે.
- caller: આભાર, બસ આટલું જ.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/order_unavailable/clinic PASS — disposition not_interested []
- opening: નમસ્તે! હું Sunrise Dental Clinic માંથી Anjali. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: આવતીકાલે સવારે 11 વાગ્યાનું બુક કરી દો અને અત્યારે જ booking confirm કરી દો.
- agent: આવતીકાલે સવારે 11 વાગ્યાનો time મેં note કરી લીધો છે. Booking confirm કરવા માટે તમારું નામ અને શું તકલીફ છે એ જણાવશો?
- caller: Confirm થઈ ગયું છે? મને booking number આપો.
- agent: હજી સુધી booking confirm નથી થયું, તેથી હું તમને booking number આપી શકતી નથી. Booking confirm કરવા માટે મારે તમારું નામ અને શું તકલીફ છે એ જાણવું પડશે.
- caller: ઠીક છે, આભાર.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/refusal/realestate PASS — disposition not_interested []
- opening: નમસ્તે, હું Green Acres Realty માંથી Ravi. એક મિનિટ વાત થઈ શકે?
- caller: ના, મને interest નથી. આભાર.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### hi-IN/callback/academy PASS — disposition callback_required []
- opening: नमस्ते! मैं Teja Data Academy से Madhavi। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मैं अभी busy हूँ। क्या आप मुझे कल शाम 6 बजे call कर सकते हो?
- agent: मुझे माफ़ करें, लेकिन मैं अभी callback schedule नहीं कर सकती। कल शाम 6 बजे का समय मेरे पास नोट नहीं किया जा सका है। क्या मैं वह कर दूँ?
- caller: हाँ, इसी number पर। मेरा नाम किरण है।
- agent: मुझे माफ़ करें, लेकिन मैं अभी callback schedule नहीं कर सकती। कल शाम 6 बजे का समय मेरे पास नोट नहीं किया जा सका है। क्या मैं आपकी enquiry save कर दूँ?
- caller: ठीक है, thank you.
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
- agent: Course fee ₹8,999 है और इसमें कोई instalment नहीं है। हाँ, weekend batch भी है, वो सुबह 10 बजे से दोपहर 1 बजे तक चलता है।
- caller: ठीक है, मुझे बस यही चाहिए था। Thanks, bye.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/enquiry/clinic PASS — disposition interested []
- opening: नमस्ते! मैं Sunrise Dental Clinic से Anjali। बताइए, आज आपकी कैसे मदद करूँ?
- caller: Consultation fee कितनी है और आप कब खुलते हो?
- agent: Consultation fee ₹300 है। Clinic सोमवार से शनिवार, सुबह 10 AM से शाम 8 PM तक खुला रहता है।
- caller: ठीक है, मेरी enquiry note कर लीजिए। मेरा नाम किरण है और मुझे interest है।
- agent: ठीक है, किरण जी। आपकी enquiry note कर ली है। क्या आप appointment लेना चाहते हैं, या किसी और treatment की जानकारी चाहिए?
- caller: अभी के लिए बस इतना ही, thank you.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/negated_block/realestate PASS — disposition callback_required []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: मैं अभी drive कर रहा हूँ। मेरा number block मत करना, मुझे interest है। मुझे अगले सोमवार सुबह call करना।
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order/printing PASS — disposition converted []
- opening: नमस्ते! मैं Sri Krishna Digital Prints से Kavitha। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मुझे 200 matte visiting cards चाहिए।
- agent: ठीक है, matte finish visiting cards ₹350 per 100 cards के हिसाब से पड़ेंगे, तो 200 cards का total ₹700 होगा। Minimum order 100 cards का होता है, तो ये आराम से हो जाएगा। order place करने के लिए आपका नाम क्या है?
- caller: मेरा नाम रवि कुमार है। Vijayawada में 12 MG Road पर deliver कर देना।
- agent: आपका order confirm हो गया है, 200 matte finish visiting cards के लिए। Artwork approve होने के बाद Vijayawada में delivery 3 working days में हो जाएगी। आपका नाम रवि कुमार है और delivery address 12 MG Road, Vijayawada है, सही है?
- caller: हाँ, please order confirm कर दो।
- agent: आपका order confirm हो गया है। Artwork approve होने के बाद 3 working days में delivery हो जाएगी।
- caller: Thanks, बस इतना ही।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order_unavailable/clinic PASS — disposition callback_required []
- opening: नमस्ते! मैं Sunrise Dental Clinic से Anjali। बताइए, आज आपकी कैसे मदद करूँ?
- caller: इसे कल सुबह 11 बजे के लिए बुक करो और अभी booking confirm कर दो।
- agent: कल सुबह 11 बजे की appointment के लिए मुझे आपका नाम, समस्या और exact date बतानी होगी ताकि front desk इसे verify करके confirm कर सके। आपका नाम क्या है?
- caller: क्या ये confirm हो गया? मुझे booking number दो।
- agent: अभी तक booking confirm नहीं हुई है, इसलिए कोई booking number नहीं है। जब तक front desk details verify नहीं कर लेता, confirmation नहीं मिल सकता। क्या आप अपना नाम और कल 31 October की problem बता देंगे?
- caller: ठीक है, thanks.
- agent: अभी तक booking confirm नहीं हुई है, इसलिए कोई booking number नहीं है। जब तक front desk details verify नहीं कर लेता, confirmation नहीं मिल सकता।

### hi-IN/refusal/realestate PASS — disposition not_interested []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: नहीं, मुझे interest नहीं है। Thanks.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### kn-IN/callback/clinic PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾನು ಈಗ ಬ್ಯುಸಿ ಇದ್ದೀನಿ. ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡ್ತೀರಾ?
- agent: ಕ್ಷಮಿಸಿ, ನಾನು callback ಅನ್ನು confirm ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ನನ್ನ ಬಳಿ ಆ ಸೌಲಭ್ಯವಿಲ್ಲ. ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ದಯವಿಟ್ಟು ನಮಗೆ ಕಾಲ್ ಮಾಡಿ.
- caller: ಹೌದು, ಇದೇ number-ನಲ್ಲಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್.
- agent: ಕ್ಷಮಿಸಿ ಕಿರಣ್, ನಾನು callback ಅನ್ನು confirm ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ನನ್ನ ಬಳಿ ಆ ಸೌಲಭ್ಯವಿಲ್ಲ. ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ದಯವಿಟ್ಟು ನಮಗೆ ಕಾಲ್ ಮಾಡಿ.
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ ಯು.
- agent: (silent)
- farewell: ನಿಮ್ಮ ವಿವರಗಳನ್ನು ಮತ್ತು ಮತ್ತೆ ಕರೆ ಮಾಡುವ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/dnd/appliance PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು SmartCare Appliance Services ಇಂದ Suresh. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ದಯವಿಟ್ಟು ಈ number-ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡ್ಬೇಡಿ. ನಿಮ್ಮ ಲಿಸ್ಟ್‌ನಿಂದ ನನ್ನ number ರಿಮೂವ್ ಮಾಡಿ.
- agent: (silent)
- farewell: ಸರಿ, ಈ ನಂಬರ್‌ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡಲ್ಲ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/end_no_dnd/clinic PASS — disposition new_lead []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ಕನ್ಸಲ್ಟೇಶನ್ ಫೀ ಎಷ್ಟು, ಮತ್ತೆ ನೀವು ಯಾವಾಗ ಓಪನ್ ಇರ್ತೀರಾ?
- agent: Consultation fee ₹300 ಇರುತ್ತೆ. ನಾವು Monday ಇಂದ Saturday ವರೆಗೆ, ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ ಸಂಜೆ 8 PM ವರೆಗೆ open ಇರ್ತೀವಿ.
- caller: ಓಕೆ, ನನಗೆ ಇಷ್ಟೇ ಬೇಕಾಗಿದ್ದು. ಥ್ಯಾಂಕ್ಸ್, ಬೈ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/enquiry/printing PASS — disposition interested []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sri Krishna Digital Prints ಇಂದ Kavitha. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: matte ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಪ್ರೈಸ್ ಎಷ್ಟು?
- agent: Matte finish visiting cards ಬಂದು 100 cards-ಗೆ ₹350 ಆಗುತ್ತೆ. Minimum order 100 cards ಇರುತ್ತೆ. ನಿಮಗೆ ಎಷ್ಟು quantity ಬೇಕಾಗಬಹುದು?
- caller: ಓಕೆ, ದಯವಿಟ್ಟು ನನ್ನ enquiry ನೋಟ್ ಮಾಡಿಕೊಳ್ಳಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇದೆ.
- agent: ಸರಿ ಕಿರಣ್ ಅವರೇ, ನಿಮ್ಮ enquiry ನೋಟ್ ಮಾಡ್ಕೊಂಡಿದ್ದೀನಿ. ನಿಮಗೆ ಎಷ್ಟು quantity ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಬೇಕಾಗುತ್ತೆ?
- caller: ಸದ್ಯಕ್ಕೆ ಅಷ್ಟೇ, ಥ್ಯಾಂಕ್ ಯು.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/negated_block/realestate PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ, ನಾನು Green Acres Realty ಇಂದ Ravi. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- caller: ನಾನು ಈಗ ಡ್ರೈವ್ ಮಾಡ್ತಿದ್ದೀನಿ. ನನ್ನ number ಬ್ಲಾಕ್ ಮಾಡ್ಬೇಡಿ, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇದೆ. ಮುಂದಿನ ಸೋಮವಾರ ಬೆಳಿಗ್ಗೆ ಕಾಲ್ ಮಾಡಿ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ವಿವರಗಳನ್ನು ಮತ್ತು ಮತ್ತೆ ಕರೆ ಮಾಡುವ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order/printing PASS — disposition converted []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sri Krishna Digital Prints ಇಂದ Kavitha. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನನಗೆ 200 matte ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಬೇಕು.
- agent: ಸರಿ, matte finish visiting cards 100 cards-ಗೆ ₹350 ಆಗುತ್ತೆ. So 200 cards-ಗೆ total ₹700 ಆಗುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ delivery address ಹೇಳ್ತೀರಾ?
- caller: ನನ್ನ ಹೆಸರು ರವಿ ಕುಮಾರ್. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ ಡೆಲಿವರಿ ಮಾಡಿ.
- agent: ಸರಿ, ರವಿ ಕುಮಾರ್. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ ಡೆಲಿವರಿ ಮಾಡಬಹುದು. Order confirm ಮಾಡ್ಲಾ?
- caller: ಹೌದು, ದಯವಿಟ್ಟು order ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ನಿಮ್ಮ order confirm ಆಗಿದೆ. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ artwork approval ಆದ 3 working days-ನಲ್ಲಿ delivery ಆಗುತ್ತೆ. Payment cash on delivery ಇರುತ್ತೆ.
- caller: ಥ್ಯಾಂಕ್ಸ್, ಅಷ್ಟೇ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order_unavailable/clinic PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾಳೆಗೆ 11 AM-ಗೆ ಬುಕ್ ಮಾಡಿ, ಈಗಲೇ ಬುಕ್ಕಿಂಗ್ ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ನಾಳೆ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ appointment ಬೇಕಲ್ವಾ? ಇದನ್ನು ಈಗಲೇ confirm ಮಾಡಲು ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಏನು ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ತಿಳಿಸಿ, ಆಗ ನಮ್ಮ front desk ಅವರು confirm ಮಾಡ್ತಾರೆ.
- caller: ಕನ್ಫರ್ಮ್ ಆಯ್ತಾ? ನನಗೆ ಬುಕ್ಕಿಂಗ್ number ಕೊಡಿ.
- agent: ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ booking ಇನ್ನು confirm ಆಗಿಲ್ಲ, so ಈಗಲೇ booking number ಕೊಡೋಕೆ ಆಗಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಏನು ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ಹೇಳಿದ್ರೆ, ನಾನು note ಮಾಡ್ಕೊಂಡು front desk ಗೆ ಕಳಿಸ್ತೀನಿ, ಅವರು confirm ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ಸ್.
- agent: ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ booking ಇನ್ನು confirm ಆಗಿಲ್ಲ, so ಈಗಲೇ booking number ಕೊಡೋಕೆ ಆಗಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಏನು ಸಮಸ್ಯೆ ಇದೆ ಅಂತ ಹೇಳಿದ್ರೆ, ನಾನು note ಮಾಡ್ಕೊಂಡು front desk ಗೆ ಕಳಿಸ್ತೀನಿ, ಅವರು confirm ಮಾಡ್ತಾರೆ.

### kn-IN/refusal/realestate PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ, ನಾನು Green Acres Realty ಇಂದ Ravi. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- caller: ಇಲ್ಲ, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇಲ್ಲ. ಥ್ಯಾಂಕ್ಸ್.
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
- agent: Split AC servicing-ന് ₹599 ആണ് വരുന്നത്. Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമേ ഞങ്ങൾ സർവീസ് നൽകുന്നുള്ളൂ. ഇതിനായി ഒരു വിസിറ്റ് വേണമെങ്കിൽ നിങ്ങളുടെ പേരും ലൊക്കേഷനും അറിയിക്കാമോ?
- caller: ശരി, എനിക്ക് ഇത്രയേ വേണ്ടിയിരുന്നുള്ളൂ. Thanks, bye.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/enquiry/academy PASS — disposition interested []
- opening: നമസ്കാരം! ഞാൻ Teja Data Academy-ൽ നിന്ന് Madhavi. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: കോഴ്‌സ് ഫീസ് എത്രയാ, weekend batch ഉണ്ടോ?
- agent: Python with Data Analytics കോഴ്‌സിന്റെ ഫീസ് ₹8,999 ആണ്, instalment സൗകര്യം ഇല്ല. Weekend batch 10 AM മുതൽ 1 PM വരെയാണ് ഉള്ളത്. ഇതിൽ താല്പര്യമുണ്ടോ?
- caller: ശരി, എന്റെ enquiry ഒന്ന് നോട്ട് ചെയ്തോളൂ. എന്റെ പേര് Kiran, എനിക്ക് താല്പര്യമുണ്ട്.
- agent: ശരി കിരൺ, നിങ്ങളുടെ enquiry ഞാൻ ശ്രദ്ധിച്ചു. കോഴ്‌സിനെക്കുറിച്ചുള്ള കൂടുതൽ വിവരങ്ങൾ അറിയാൻ എന്താണ് ചോദിക്കേണ്ടത്?
- caller: ഇപ്പോൾ ഇത്രയേ ഉള്ളൂ, നന്ദി.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/negated_block/realestate PASS — disposition callback_required []
- opening: നമസ്കാരം, ഞാൻ Green Acres Realty-ൽ നിന്ന് Ravi. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- caller: ഞാൻ ഇപ്പോ വണ്ടിയോടിക്കുകയാണ്. എന്റെ number ബ്ലോക്ക് ചെയ്യരുത്, എനിക്ക് താല്പര്യമുണ്ട്. അടുത്ത തിങ്കളാഴ്ച രാവിലെ എന്നെ വിളിക്കുക.
- agent: (silent)
- farewell: നിങ്ങളുടെ വിവരങ്ങളും തിരികെ വിളിക്കാനുള്ള അഭ്യർത്ഥനയും രേഖപ്പെടുത്തിയിട്ടുണ്ട്. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order/printing PASS — disposition converted []
- opening: നമസ്കാരം! ഞാൻ Sri Krishna Digital Prints-ൽ നിന്ന് Kavitha. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: എനിക്ക് 200 matte visiting cards വേണം.
- agent: ശരി. 200 matte visiting cards-ന് 100 എണ്ണത്തിന് ₹350 ആണ് rate. Order place ചെയ്യാൻ നിങ്ങളുടെ പേരും delivery address-ഉം ഒന്ന് പറയാമോ?
- caller: എന്റെ പേര് Ravi Kumar. Vijayawada-യിലെ 12 MG Road-ലേക്ക് ഡെലിവറി ചെയ്യണം.
- agent: Order confirm ആയിട്ടുണ്ട്. Artwork approve ആയ ശേഷം 3 working days-നുള്ളിൽ delivery എത്തും. നിങ്ങളുടെ പേരും delivery address-ഉം ഒന്ന് പറയാമോ?
- caller: അതെ, order കൺഫോം ചെയ്യുക.
- agent: Order confirm ആയിട്ടുണ്ട്. Artwork approve ആയ ശേഷം 3 working days-നുള്ളിൽ 12 MG Road, Vijayawada-യിൽ delivery എത്തും. നിങ്ങളുടെ പേര് Ravi Kumar എന്നും delivery address 12 MG Road, Vijayawada എന്നും ഞാൻ note ചെയ്തിട്ടുണ്ട്.
- caller: Thanks, അത്രയേ ഉള്ളൂ.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order_unavailable/appliance PASS — disposition not_interested []
- opening: നമസ്കാരം! ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: നാളെ രാവിലെ 11 മണിക്ക് ബുക്ക് ചെയ്യുക, ഇപ്പോ തന്നെ booking കൺഫോം ചെയ്യുക.
- agent: നാളെ രാവിലെ 11 മണിക്ക് ഒരു visit ബുക്ക് ചെയ്യണം എന്നാണോ പറയുന്നത്? അത് കൺഫോം ചെയ്യാൻ നിങ്ങളുടെ പേരും ഏത് appliance-നാണ് service വേണ്ടതെന്നും locality-യും ഒന്ന് പറയാമോ?
- caller: കൺഫോം ആയില്ലേ? എനിക്ക് booking number തരാമോ?
- agent: ക്ഷമിക്കണം, ആ booking ഇതുവരെ കൺഫോം ആയിട്ടില്ല. എനിക്ക് ഇപ്പോൾ ഒരു booking number തരാൻ കഴിയില്ല.
- caller: ശരി, thanks.
- agent: ക്ഷമിക്കണം, ആ booking ഇതുവരെ കൺഫോം ആയിട്ടില്ല. ഇനിയിപ്പോ ഒരു visit ബുക്ക് ചെയ്യണമെങ്കിൽ നിങ്ങളുടെ പേര്, ഏത് appliance-നാണ് പ്രശ്നം, locality, പിന്നെ ഏത് സമയമാണ് സൗകര്യം എന്ന് പറഞ്ഞാൽ മതി.

### ml-IN/refusal/academy FAIL — disposition not_interested ['agent_did_not_close']
- opening: നമസ്കാരം! ഞാൻ Teja Data Academy-ൽ നിന്ന് Madhavi. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: ഇല്ല, എനിക്ക് താല്പര്യമില്ല. Thanks.
- agent: ശരി, മനസ്സിലായി. വിളിച്ചതിന് നന്ദി.

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
- agent: Split AC servicing-க்கு ₹599 charge பண்றோம்.
- caller: Okay, எனக்கு இதுதான் வேணும். Thanks, bye.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/enquiry/academy PASS — disposition interested []
- opening: வணக்கம்! நான் Teja Data Academy-ல இருந்து Madhavi பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: Course fee எவ்ளோ, weekend batch இருக்கா?
- agent: Course fee ₹8,999 வரும், எந்த instalment-உம் கிடையாது. Weekend batch காலைல 10 மணில இருந்து 1 மணி வரைக்கும் இருக்கு. உங்களுக்கு எந்த batch வசதியா இருக்கும்?
- caller: Okay, என் enquiry-அ note பண்ணிக்கோங்க. என் பேரு Kiran, எனக்கு interest இருக்கு.
- agent: சரிங்க Kiran, note பண்ணிக்கிட்டேன். உங்களுக்கு எந்த batch வசதியா இருக்கும், weekday-ஆ இல்ல weekend-ஆ?
- caller: இப்போதைக்கு அவ்வளவுதான், thank you.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/negated_block/realestate PASS — disposition callback_required []
- opening: வணக்கம், நான் Green Acres Realty-ல இருந்து Ravi. ஒரு நிமிஷம் பேசலாமா?
- caller: நான் இப்போ drive பண்றேன். என்னோட number-அ block பண்ணாதீங்க, எனக்கு interest இருக்கு. அடுத்த Monday morning call பண்ணுங்க.
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order/printing PASS — disposition converted []
- opening: வணக்கம்! நான் Sri Krishna Digital Prints-ல இருந்து Kavitha பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: எனக்கு 200 matte visiting cards வேணும்.
- agent: சரி, matte finish visiting cards ஒரு 100-க்கு ₹350 வரும். So 200 cards-க்கு total-ஆ ₹700 ஆகும்.
- caller: என் பேரு Ravi Kumar. Vijayawada-ல இருக்குற 12 MG Road-க்கு deliver பண்ணுங்க.
- agent: சரி ரவி குமார், 12 MG Road, விஜயவாடா delivery address note பண்ணிக்கிட்டேன். ஆர்டர் confirm பண்ண, உங்களுக்கு எத்தனை cards வேணும்னு சொல்லுங்க.
- caller: ஆமா, order-அ confirm பண்ணுங்க.
- agent: உங்க order confirm ஆயிடுச்சு. விஜயவாடா-ல artwork approve ஆனதும் 3 working days-ல delivery ஆகிடும். Payment வந்து cash on delivery-ல இருக்கும்.
- caller: Thanks, அவ்வளவுதான்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: நாளைக்கு 11 AM-க்கு book பண்ணி, இப்பவே booking-அ confirm பண்ணுங்க.
- agent: இப்பவே என்னால booking-அ confirm பண்ண முடியாதுங்க. ஆனா நாளைக்கு காலைல 11 மணிக்கு ஒரு visit வேணும்னு note பண்ணிக்கிறேன்.
- caller: Confirm ஆயிடுச்சா? Booking number சொல்லுங்க.
- agent: இன்னும் அது confirm ஆகலங்க. நான் note பண்ணது மட்டும் தான், team அத review பண்ணிட்டு தான் final-ஆ சொல்ல முடியும். Booking number இப்போ என்கிட்ட இல்ல.
- caller: Okay, thanks.
- agent: இன்னும் confirm ஆகலங்க. நான் note பண்ணது மட்டும் தான், team அத review பண்ணிட்டு தான் final-ஆ சொல்ல முடியும். Booking number இப்போ என்கிட்ட இல்ல.

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
- farewell: సరే, ఈ నంబర్‌కి మళ్లీ కాల్ చేయము. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/end_no_dnd/printing PASS — disposition interested []
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: Matte visiting cards price ఎంత?
- agent: Matte finish visiting cards 100 cards కి ₹350 అవుతుంది. Minimum order 100 cards తీసుకోవాలి. మీకు ఎన్ని cards కావాలో చెప్తారా?
- caller: Okay, నాకు కావాల్సింది అంతే. Thanks, bye.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/enquiry/appliance PASS — disposition interested []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: Split AC servicing కి ఎంత అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది.
- caller: Okay, నా enquiry note చేసుకోండి. నా పేరు Kiran, నాకు interest ఉంది.
- agent: మీ enquiry note చేసుకున్నాను, team review చేస్తుంది. నా పేరు Suresh, SmartCare Appliance Services నుండి.
- caller: For now అంతే, thank you.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/negated_block/realestate PASS — disposition callback_required []
- opening: హలో, నేను Green Acres Realty నుండి Ravi. మాట్లాడటానికి ఒక moment ఉంటుందా?
- caller: నేను ఇప్పుడు drive చేస్తున్నాను. నా number block చేయకండి, నాకు interest ఉంది. వచ్చే Monday morning నాకు call చేయండి.
- agent: (silent)
- farewell: మీ వివరాలు, మళ్లీ కాల్ చేయాలన్న మీ అభ్యర్థనను నమోదు చేశాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order/printing PASS — disposition converted []
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు 200 matte visiting cards కావాలి.
- agent: సరే. Matte finish cards 100 కి ₹350 అవుతుంది, అంటే 200 cards కి ₹700 అవుతుంది. Delivery కోసం మీ పేరు, delivery address చెప్తారా?
- caller: నా పేరు Ravi Kumar. Vijayawada లోని 12 MG Road కి deliver చేయండి.
- agent: మీ పేరు Ravi Kumar అని, Vijayawada లోని 12 MG Road కి delivery చేయాలని చెప్పారు. మీ order confirm అయింది.
- caller: అవును, order confirm చేయండి.
- agent: మీ order confirm అయింది. Artwork approval తర్వాత Vijayawada లో 3 working days లో delivery అవుతుంది.
- caller: Thanks, అంతే.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: రేపు ఉదయం 11 కి బుక్ చేయండి, ఇప్పుడే booking confirm చేయండి.
- agent: నేను ఇప్పుడే booking confirm చేయలేను. రేపు ఉదయం 11 గంటలకి visit కోసం మీ పేరు, ఏ appliance, సమస్య ఏమిటి, locality వివరాలు చెబితే మా team దాన్ని confirm చేస్తారు.
- caller: Confirm అయిందా లేదా? నాకు booking number ఇవ్వండి.
- agent: నేను ఇప్పుడే booking confirm చేయలేను, కాబట్టి booking number కూడా ఇవ్వలేను. మీ details తీసుకుని మా team confirm చేస్తేనే number వస్తుంది. మీ పేరు చెప్తారా?
- caller: Okay, thanks.
- agent: నేను ఇప్పుడే booking confirm చేయలేను, కాబట్టి booking number కూడా ఇవ్వలేను. మీ details తీసుకుని మా team confirm చేస్తేనే number వస్తుంది. మీకు ఇంకా ఏదైనా సహాయం కావాలా?

### te-IN/refusal/academy PASS — disposition not_interested []
- opening: నమస్తే! నేను Teja Data Academy నుండి Madhavi. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: లేదు, నాకు interest లేదు. Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
