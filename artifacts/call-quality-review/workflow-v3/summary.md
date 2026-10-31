# Workflow simulation workflow-v3

Schema `sim_2a37df382bde4abda8aedcd14c43a81b`.

| Scenario | Pass | Failures |
|---|---|---|
| callback | 7/7 | - |
| order | 7/7 | - |
| order_unavailable | 7/7 | - |
| refusal | 6/7 | agent_did_not_close |

| Missed-call mode | DND | Jobs | Pass |
|---|---|---|---|

## Transcripts

### en-IN/callback/realestate PASS — disposition callback_required []
- opening: Hi, this is Ravi. Do you have a moment?
- caller: I'm busy right now. Can you call me back tomorrow at 6 in the evening?
- agent: (silent)
- farewell: I've saved your details and your request for a follow-up call. Thank you for your time. Goodbye.

### en-IN/order/printing PASS — disposition converted []
- opening: Hi, this is Kavitha. How can I help you?
- caller: I want 200 matte visiting cards.
- agent: Matte visiting cards are 350 rupees per 100 cards, so 200 cards will be 700 rupees. The minimum order is 100 cards, so your request is fine. What is your name and delivery address?
- caller: My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.
- agent: Ravi Kumar, I have noted your delivery address as 12 MG Road, Vijayawada. You mentioned 200 matte visiting cards. Would you like to go ahead and place the order?
- caller: Yes, please confirm the order.
- agent: Your order for 200 matte visiting cards has been confirmed. Delivery to 12 MG Road, Vijayawada will take 3 working days after artwork approval, and payment is cash on delivery.
- caller: Thanks, that's all.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### en-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: Hi, this is Suresh calling from SmartCare. How can I help you today?
- caller: Book it for tomorrow 11 AM and confirm the booking right now.
- agent: I can note that request for you. To confirm the visit, I need your name and which locality you are in. We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only.
- caller: Is it confirmed? Give me the booking number.
- agent: I do not have a confirmed booking or a booking number yet, because the visit has not been confirmed by the team.
- caller: Okay, thanks.
- agent: To move ahead, I still need your name and which locality you are in. We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only.

### en-IN/refusal/academy PASS — disposition not_interested []
- opening: Hi, this is Madhavi. How can I help you?
- caller: No, I'm not interested. Thanks.
- agent: (silent)
- farewell: Thank you for your time. Goodbye.

### gu-IN/callback/academy PASS — disposition callback_required []
- opening: નમસ્તે! હું Madhavi. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: હું અત્યારે busy છું. તમે મને કાલે સાંજે 6 વાગ્યે call કરી શકશો?
- agent: (silent)
- farewell: તમારી વિગતો અને ફરીથી કૉલ કરવાની વિનંતી નોંધી લીધી છે. તમારા સમય માટે આભાર. આવજો.

### gu-IN/order/printing PASS — disposition converted []
- opening: નમસ્તે! હું Kavitha. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: મારે 200 matte visiting cards જોઈએ છે.
- agent: સારું, 200 matte visiting cards માટે per 100 cards ના ₹350 થશે, એટલે total ₹700 થશે. Order confirm કરવા માટે તમારું નામ અને delivery address કહેશો?
- caller: મારું નામ Ravi Kumar છે. Vijayawada માં 12 MG Road પર delivery કરી દેજો.
- agent: સમજાયું, રવિ કુમાર. Vijayawada માં 12 MG Road પર delivery થઈ જશે. તમારી પાસે 200 matte visiting cards નો order છે, બરાબર ને?
- caller: હા, order confirm કરી દો.
- agent: તમારો order confirm થઈ ગયો છે. Artwork approve થયા પછી Vijayawada માં delivery થવામાં 3 working days લાગશે.
- caller: આભાર, બસ આટલું જ.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/order_unavailable/clinic PASS — disposition not_interested []
- opening: નમસ્તે! હું Anjali. કહો, હું આપને કેવી રીતે મદદ કરી શકું?
- caller: આવતીકાલે સવારે 11 વાગ્યાનું બુક કરી દો અને અત્યારે જ booking confirm કરી દો.
- agent: ઠીક છે, મેં નોંધી લીધું છે કે તમારે આવતીકાલે સવારે 11 વાગ્યાનું બુકિંગ કરાવવું છે અને અત્યારે જ કન્ફર્મેશન જોઈએ છે. બુકિંગ કન્ફર્મ કરવા માટે મારે તમારું નામ અને દાંતની સમસ્યા જાણવી પડશે. કૃપા કરીને જણાવશો?
- caller: Confirm થઈ ગયું છે? મને booking number આપો.
- agent: માફ કરશો, હજી સુધી booking કન્ફર્મ નથી થયું અને મારી પાસે booking number નથી. booking કન્ફર્મ કરવા માટે મારે તમારું નામ અને દાંતની તકલીફ જાણવી પડશે.
- caller: ઠીક છે, આભાર.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### gu-IN/refusal/realestate PASS — disposition not_interested []
- opening: નમસ્તે, હું Ravi. એક મિનિટ વાત થઈ શકે?
- caller: ના, મને interest નથી. આભાર.
- agent: (silent)
- farewell: તમારા સમય માટે આભાર. આવજો.

### hi-IN/callback/academy PASS — disposition callback_required []
- opening: नमस्ते! मैं Teja Data Academy से Madhavi। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मैं अभी busy हूँ। क्या आप मुझे कल शाम 6 बजे call कर सकते हो?
- agent: मुझे खेद है, लेकिन मैं अभी callback schedule नहीं कर सकती। मैं आपका enquiry save कर सकती हूँ अगर आप चाहें। क्या मैं ऐसा कर दूँ?
- caller: हाँ, इसी number पर। मेरा नाम किरण है।
- agent: आपकी enquiry इसी number पर save कर ली गई है।
- caller: ठीक है, thank you.
- agent: (silent)
- farewell: आपकी जानकारी और दोबारा कॉल करने का अनुरोध दर्ज कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order/printing PASS — disposition converted []
- opening: नमस्ते! मैं Sri Krishna Digital Prints से Kavitha। बताइए, आज आपकी कैसे मदद करूँ?
- caller: मुझे 200 matte visiting cards चाहिए।
- agent: ठीक है, matte finish cards का rate ₹350 per 100 cards है, तो 200 cards का total ₹700 होगा। Minimum order 100 cards का होता है, तो ये आराम से हो जाएगा। Order place करने के लिए अपना नाम और delivery address बता दीजिए।
- caller: मेरा नाम रवि कुमार है। Vijayawada में 12 MG Road पर deliver कर देना।
- agent: ठीक है, रवि जी। Vijayawada में 12 MG Road पर delivery हो जाएगी, artwork approve होने के 3 working days लगेंगे। क्या मैं order confirm कर दूँ?
- caller: हाँ, please order confirm कर दो।
- agent: आपका order confirm हो गया है, 200 matte visiting cards के लिए। Cash on delivery रहेगा, और artwork approve होने के 3 working days में delivery हो जाएगी।
- caller: Thanks, बस इतना ही।
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### hi-IN/order_unavailable/clinic PASS — disposition not_interested []
- opening: नमस्ते! मैं Sunrise Dental Clinic से Anjali। बताइए, आज आपकी कैसे मदद करूँ?
- caller: इसे कल सुबह 11 बजे के लिए बुक करो और अभी booking confirm कर दो।
- agent: कल सुबह 11 बजे की appointment के लिए मुझे आपका नाम और समस्या जाननी होगी, ताकि front desk इसे confirm कर सके। आपका नाम क्या है?
- caller: क्या ये confirm हो गया? मुझे booking number दो।
- agent: अभी तक booking confirm नहीं हुई है, इसलिए कोई booking number नहीं है।
- caller: ठीक है, thanks.
- agent: अभी तक booking confirm नहीं हुई है। कल सुबह 11 बजे का slot confirm करने के लिए मुझे आपका नाम और समस्या जाननी होगी। आपका नाम क्या है?

### hi-IN/refusal/realestate PASS — disposition not_interested []
- opening: नमस्ते, मैं Green Acres Realty से Ravi. क्या अभी एक मिनट बात हो सकती है?
- caller: नहीं, मुझे interest नहीं है। Thanks.
- agent: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।

### kn-IN/callback/clinic PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾನು ಈಗ ಬ್ಯುಸಿ ಇದ್ದೀನಿ. ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡ್ತೀರಾ?
- agent: ಕ್ಷಮಿಸಿ, ನಾನು callback schedule ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ಆದರೆ ನೀವು ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ clinic ಗೆ ಬರಲು appointment ಬೇಕಿದ್ದರೆ ತಿಳಿಸಿ, ನಾನು details ಪಡೆದುಕೊಂಡು front desk ಗೆ ತಿಳಿಸುತ್ತೇನೆ.
- caller: ಹೌದು, ಇದೇ number-ನಲ್ಲಿ. ನನ್ನ ಹೆಸರು ಕಿರಣ್.
- agent: ಸರಿ ಕಿರಣ್, note ಮಾಡ್ಕೊಂಡೆ. ನಾಳೆ ಸಂಜೆ 6 ಗಂಟೆಗೆ appointment ಬೇಕಿದ್ದರೆ, ನಿಮಗೆ ಯಾವ problem ಆಗ್ತಿದೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ ಯು.
- agent: (silent)
- farewell: ನಿಮ್ಮ ವಿವರಗಳನ್ನು ಮತ್ತು ಮತ್ತೆ ಕರೆ ಮಾಡುವ ವಿನಂತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order/printing PASS — disposition converted []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sri Krishna Digital Prints ಇಂದ Kavitha. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನನಗೆ 200 matte ವಿಸಿಟಿಂಗ್ ಕಾರ್ಡ್ಸ್ ಬೇಕು.
- agent: ಸರಿ, matte finish visiting cards ಒಂದು 100 cards-ಗೆ ₹350 ಆಗುತ್ತೆ. So 200 cards-ಗೆ ₹700 ಆಗುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು delivery address ಹೇಳ್ತೀರಾ?
- caller: ನನ್ನ ಹೆಸರು ರವಿ ಕುಮಾರ್. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ ಡೆಲಿವರಿ ಮಾಡಿ.
- agent: ಸರಿ, ರವಿ ಕುಮಾರ್. ವಿಜಯವಾಡದ 12 MG Road-ಗೆ ಡೆಲಿವರಿ ಮಾಡಬಹುದು. ಈಗ order confirm ಮಾಡ್ಲಾ?
- caller: ಹೌದು, ದಯವಿಟ್ಟು order ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ನಿಮ್ಮ order confirm ಆಗಿದೆ.
- caller: ಥ್ಯಾಂಕ್ಸ್, ಅಷ್ಟೇ.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/order_unavailable/clinic PASS — disposition callback_required []
- opening: ನಮಸ್ಕಾರ! ನಾನು Sunrise Dental Clinic ಇಂದ Anjali. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
- caller: ನಾಳೆಗೆ 11 AM-ಗೆ ಬುಕ್ ಮಾಡಿ, ಈಗಲೇ ಬುಕ್ಕಿಂಗ್ ಕನ್ಫರ್ಮ್ ಮಾಡಿ.
- agent: ನಾಳೆ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ appointment ಬುಕ್ ಮಾಡಬೇಕು ಅಂತ ಕೇಳಿದ್ರಿ. ಅದನ್ನು confirm ಮಾಡಲು ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆಗೆ treatment ಬೇಕು ಅಂತ ತಿಳಿಸಬೇಕಾಗುತ್ತದೆ.
- caller: ಕನ್ಫರ್ಮ್ ಆಯ್ತಾ? ನನಗೆ ಬುಕ್ಕಿಂಗ್ number ಕೊಡಿ.
- agent: ಸದ್ಯಕ್ಕೆ booking number generate ಆಗಿಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆಗೆ treatment ಬೇಕು ಅಂತ ಹೇಳಿದ್ರೆ, ನಾನು details note ಮಾಡ್ಕೊಂಡು front desk ಇಂದ confirm ಮಾಡಿಸ್ತೀನಿ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
- caller: ಓಕೆ, ಥ್ಯಾಂಕ್ಸ್.
- agent: ಇಲ್ಲ, ಸದ್ಯಕ್ಕೆ booking confirm ಆಗಿಲ್ಲ ಮತ್ತು ಯಾವುದೇ booking number ಸಿಕ್ಕಿಲ್ಲ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ ಸಮಸ್ಯೆಗೆ treatment ಬೇಕು ಅಂತ ತಿಳಿಸಿದರೆ, ನಾನು details note ಮಾಡ್ಕೊಂಡು front desk ಇಂದ confirm ಮಾಡಿಸ್ತೀನಿ.

### kn-IN/refusal/realestate PASS — disposition not_interested []
- opening: ನಮಸ್ಕಾರ, ನಾನು Ravi. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- caller: ಇಲ್ಲ, ನನಗೆ ಇಂಟರೆಸ್ಟ್ ಇಲ್ಲ. ಥ್ಯಾಂಕ್ಸ್.
- agent: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### ml-IN/callback/appliance PASS — disposition callback_required []
- opening: നമസ്കാരം! ഞാൻ SmartCare-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: ഞാൻ ഇപ്പോ തിരക്കിലാണ്. നാളെ വൈകുന്നേരം 6 മണിക്ക് തിരിച്ചു വിളിക്കാമോ?
- agent: (silent)
- farewell: നിങ്ങളുടെ വിവരങ്ങളും തിരികെ വിളിക്കാനുള്ള അഭ്യർത്ഥനയും രേഖപ്പെടുത്തിയിട്ടുണ്ട്. നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order/printing PASS — disposition converted []
- opening: നമസ്കാരം! ഞാൻ Kavitha. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: എനിക്ക് 200 matte visiting cards വേണം.
- agent: ശരി. 200 matte visiting cards-ന് 100 എണ്ണത്തിന് ₹350 ആണ് rate. ഇനി order confirm ചെയ്യാൻ customer name-ഉം delivery address-ഉം ഒന്ന് പറയാമോ?
- caller: എന്റെ പേര് Ravi Kumar. Vijayawada-യിലെ 12 MG Road-ലേക്ക് ഡെലിവറി ചെയ്യണം.
- agent: ഡെലിവറി അഡ്രസ്സ് 12 MG Road, Vijayawada എന്ന് രേഖപ്പെടുത്തിയിട്ടുണ്ട്. ഓർഡർ confirm ചെയ്യാൻ നിങ്ങളുടെ പേര് Ravi Kumar എന്ന് പറഞ്ഞല്ലോ. ഓർഡർ ഇപ്പോൾ തന്നെ confirm ചെയ്യട്ടേ?
- caller: അതെ, order കൺഫോം ചെയ്യുക.
- agent: ഓർഡർ confirm ആയിട്ടുണ്ട്. artwork approve ആയിക്കഴിഞ്ഞാൽ 3 working days-നുള്ളിൽ delivery എത്തും.
- caller: Thanks, അത്രയേ ഉള്ളൂ.
- agent: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: നമസ്കാരം! ഞാൻ SmartCare-ൽ നിന്ന് Suresh. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: നാളെ രാവിലെ 11 മണിക്ക് ബുക്ക് ചെയ്യുക, ഇപ്പോ തന്നെ booking കൺഫോം ചെയ്യുക.
- agent: നാളെ രാവിലെ 11 മണിക്ക് ഒരു booking വേണമെന്ന് പറഞ്ഞല്ലോ. പക്ഷെ ഞങ്ങളുടെ service area ഇപ്പോൾ Madhapur, Gachibowli, Kondapur, Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമാണ് ഉള്ളത്. ഈ സ്ഥലങ്ങളിൽ ഏതാണ് നിങ്ങളുടെ locality?
- caller: കൺഫോം ആയില്ലേ? എനിക്ക് booking number തരാമോ?
- agent: ക്ഷമിക്കണം, booking ഇതുവരെ കൺഫോം ആയിട്ടില്ല. എനിക്ക് നിലവിൽ booking number നൽകാൻ കഴിയില്ല. ഒരു visit ബുക്ക് ചെയ്യാൻ, നിങ്ങളുടെ പേര്, ഏത് appliance ആണ്, എന്താണ് പ്രശ്നം, locality, ഏത് സമയമാണ് വേണ്ടത് എന്നിവ പറയാമോ?
- caller: ശരി, thanks.
- agent: നിങ്ങളുടെ പേര്, ഏത് appliance ആണ്, എന്താണ് പ്രശ്നം, locality, ഏത് സമയമാണ് വേണ്ടത് എന്നിവ പറഞ്ഞാൽ visit ബുക്ക് ചെയ്യാൻ ഞാൻ സഹായിക്കാം.

### ml-IN/refusal/academy FAIL — disposition not_interested ['agent_did_not_close']
- opening: നമസ്കാരം! ഞാൻ Madhavi. പറയൂ, എങ്ങനെ സഹായിക്കണം?
- caller: ഇല്ല, എനിക്ക് താല്പര്യമില്ല. Thanks.
- agent: ശരി, മനസ്സിലായി. വിളിച്ചതിന് നന്ദി.

### ta-IN/callback/appliance PASS — disposition callback_required []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: நான் இப்போ busy-ஆ இருக்கேன். நாளைக்கு evening 6 மணிக்கு திரும்ப call பண்ண முடியுமா?
- agent: (silent)
- farewell: உங்கள் விவரங்களையும் மீண்டும் அழைக்க வேண்டிய கோரிக்கையையும் பதிவு செய்துள்ளேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order/printing PASS — disposition converted []
- opening: வணக்கம்! நான் Sri Krishna Digital Prints-ல இருந்து Kavitha பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: எனக்கு 200 matte visiting cards வேணும்.
- agent: சரி. Matte finish visiting cards 100-க்கு ₹350 வரும். உங்க பேர், delivery address சொல்ல முடியுமா?
- caller: என் பேரு Ravi Kumar. Vijayawada-ல இருக்குற 12 MG Road-க்கு deliver பண்ணுங்க.
- agent: சரி ரவி குமார். 200 matte visiting cards-க்கு மொத்தம் ₹700 வரும். உங்க order-அ இப்போவே confirm பண்ணட்டுமா?
- caller: ஆமா, order-அ confirm பண்ணுங்க.
- agent: உங்க order confirm ஆயிடுச்சு. Artwork approval முடிஞ்சதும் Vijayawada-ல 3 working days-ல delivery வந்துடும்.
- caller: Thanks, அவ்வளவுதான்.
- agent: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/order_unavailable/appliance PASS — disposition site_visit_planned []
- opening: வணக்கம்! நான் SmartCare Appliance Services-ல இருந்து Suresh பேசுறேன். உங்களுக்கு எப்படி உதவலாம்?
- caller: நாளைக்கு 11 AM-க்கு book பண்ணி, இப்பவே booking-அ confirm பண்ணுங்க.
- agent: Sorry, இப்பவே direct-ஆ booking confirm பண்ண முடியாதுங்க. ஆனா நாளைக்கு 11 AM-க்கு ஒரு visit schedule பண்ணி வைக்கிறேன்.
- caller: Confirm ஆயிடுச்சா? Booking number சொல்லுங்க.
- agent: இன்னும் booking confirm ஆகலங்க. நான் note பண்ணது என்னன்னா, நாளைக்கு 11 AM-க்கு visit schedule பண்ணலாம்னு தான். Booking number வந்து team confirm பண்ணதுக்கு அப்புறம் தான் வரும்.
- caller: Okay, thanks.
- agent: Team confirm பண்ணதுக்கு அப்புறம் தான் உங்களுக்கு booking number வரும்.

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

### te-IN/order/printing PASS — disposition converted []
- opening: నమస్తే! నేను Sri Krishna Digital Prints నుండి Kavitha. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: నాకు 200 matte visiting cards కావాలి.
- agent: సరే, matte finish visiting cards 100 కి ₹350 అవుతుంది. అంటే 200 cards కి ₹700 అవుతుంది. మీ పేరు మరియు delivery address చెబితే order confirm చేస్తాను.
- caller: నా పేరు Ravi Kumar. Vijayawada లోని 12 MG Road కి deliver చేయండి.
- agent: సరే, మీ delivery address 12 MG Road, Vijayawada కదా, ఒకసారి సరిచూసుకోండి. Vijayawada లో delivery కి artwork approval తర్వాత 3 working days పడుతుంది. Order confirm చేయమంటారా?
- caller: అవును, order confirm చేయండి.
- agent: మీ order confirm అయింది. Artwork approval తర్వాత 3 working days లో delivery అవుతుంది.
- caller: Thanks, అంతే.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### te-IN/order_unavailable/appliance PASS — disposition callback_required []
- opening: నమస్తే! నేను SmartCare Appliance Services నుండి Suresh. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: రేపు ఉదయం 11 కి బుక్ చేయండి, ఇప్పుడే booking confirm చేయండి.
- agent: రేపు ఉదయం 11 కి మీ visit note చేశాను. మా service areas Madhapur, Gachibowli, Kondapur మరియు Kukatpally మాత్రమే. మీరు ఏ locality లో ఉన్నారో చెప్తారా?
- caller: Confirm అయిందా లేదా? నాకు booking number ఇవ్వండి.
- agent: ఇంకా booking number generate కాలేదు. మీకు booking confirm అయిందో లేదో చెప్పడానికి నా దగ్గర ఆ వివరాలు లేవు. చేయమంటారా?
- caller: Okay, thanks.
- agent: ఇంకా booking confirm కాలేదు, booking number కూడా generate కాలేదు. మీ locality చెప్తే, మా team visit confirm చేస్తుంది. మీరు ఏ area లో ఉన్నారో చెప్పండి?

### te-IN/refusal/academy PASS — disposition not_interested []
- opening: నమస్తే! నేను Teja Data Academy నుండి Madhavi. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
- caller: లేదు, నాకు interest లేదు. Thanks.
- agent: (silent)
- farewell: సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
