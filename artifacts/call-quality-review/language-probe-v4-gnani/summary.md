# Language probe language-probe-v4-gnani

Schema `sim_37391ee1996a4eb38db38db88790ba3d`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | gnani | 1/6 | 4.67 | human_naturalness 4.00 |
| gu-IN | gnani | 2/6 | 4.56 | human_naturalness 4.00 |
| hi-IN | gnani | 2/6 | 3.83 | correctness 3.25 |
| kn-IN | gnani | 1/6 | 3.94 | human_naturalness 3.67 |
| ml-IN | gnani | 0/6 | 0.00 | - 0.00 |
| ta-IN | gnani | 2/6 | 4.38 | human_naturalness 4.00 |
| te-IN | gnani | 2/6 | 4.58 | human_naturalness 4.00 |

## Transcripts

### en-IN/gnani/frustration (mixed) PASS
- caller: I am asking one simple thing, just tell me clearly what the fridge inspection charge is.
- agent: The fridge inspection charge is two hundred fifty rupees. However, if you go ahead with the repair after inspection, that inspection fee is waived.
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Clear, correct, and brief. It answers the caller directly, though “However” and the phrasing are a bit formal for a phone receptionist.
  - [too_formal] "However, if you go ahead with the repair after inspection" → Use a more spoken connector: “If you go ahead with the repair after inspection, we’ll waive that fee.”

### en-IN/gnani/greeting_check (mixed) FAIL
- caller: Hello, am I audible? What company are you calling from?
- agent: Yes, you are audible. I am calling from SmartCare Appliance Services. How can I help you today?
  - checks: hard=[] warn=['three_sentences']

### en-IN/gnani/numbers (mixed) FAIL
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For one split AC servicing it is five hundred ninety nine rupees, so two will be one thousand one hundred ninety eight rupees. A window AC is four hundred ninety nine rupees. The total comes to one thousand six hundred ninety seven rupees.
  - checks: hard=[] warn=['over_soft_length:239', 'three_sentences']

### en-IN/gnani/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: We do cover Kondapur, and next-day visits between 10 AM and 6 PM are available. Could you tell me your name so I can note this down?
  - checks: hard=[] warn=['digits_reach_tts']

### en-IN/gnani/price (mixed) FAIL
- caller: What is the charge for split AC service, please?
- agent: Split AC servicing is five hundred ninety nine rupees.

### en-IN/gnani/time_request (mixed) FAIL
- caller: Can you send someone tomorrow morning at ten-thirty? The fridge is not cooling.
- agent: I can arrange a next-day visit between 10 AM and 6 PM. Could you tell me which area you are in, like Madhapur, Gachibowli, Kondapur, or Kukatpally?
  - checks: hard=[] warn=['digits_reach_tts']

### gu-IN/gnani/frustration (mixed) FAIL
- caller: મેં simple question પૂછ્યો છે, fridge inspection feeનો straight answer આપો.
- agent: Fridge inspection ની fee ₹250 છે. જો તમે repair કરાવો તો આ charge માફ થઈ જશે.
  - checks: hard=[] warn=['digits_reach_tts']

### gu-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, મારી voice આવે છે? આ કઈ company છે?
- agent: હા, મારો અવાજ આવે છે. હું SmartCare Appliance Services માંથી સુરેશ બોલું છું. કહો, હું તમારી શું મદદ કરી શકું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — જવાબ સાચી ગુજરાતી ભાષામાં છે, કંપની અને નામ સાચાં કહે છે, અને callerના પ્રશ્નનો સીધો જવાબ આપે છે. માત્ર છેલ્લો ભાગ થોડો scripted લાગે છે, પણ ફોન પર સ્વીકાર્ય છે.
  - [robotic_or_scripted] "કહો, હું તમારી શું મદદ કરી શકું?" → થોડું વધુ સહજ: “કહો, શું કામ હતું?” અથવા “બોલો, શું મદદ જોઈએ?”

### gu-IN/gnani/numbers (mixed) FAIL
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: જુઓ, એક split AC ના servicing ના ₹599 છે અને window AC ના ₹499 છે. એટલે બે split અને એક window ના total ₹1797 થશે. તમારે booking કરાવવું છે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબમાં હિસાબ સાચો છે અને ભાષા મોટેભાગે ગુજરાતી સાથે સ્વાભાવિક code-mixing છે. પરંતુ TTS માટે આંકડા શબ્દોમાં હોવા જોઈએ, phrasing થોડી અણઘડ છે, અને pricing answer પછી તરત booking push કરવાની જરૂર નથી.
  - [number_or_time_readout] "₹599 ... ₹499 ... ₹1797" → TTS digits વાંચતું નથી, એટલે રકમ શબ્દોમાં કહો: “સ્પ્લિટ AC સર્વિસિંગ પાંચસો નવ્વાણું રૂપિયા, વિન્ડો AC ચારસો નવ્વાણું રૂપિયા, એટલે કુલ સત્તરસો સત્તાણું રૂપિયા થશે.”
  - [unnatural_phrasing] "એક split AC ના servicing ના ₹599 છે" → વધુ સ્વાભાવિક: “એક સ્પ્લિટ ACની સર્વિસિંગ પાંચસો નવ્વાણું રૂપિયા છે.”
  - [unneeded_sales_push] "તમારે booking કરાવવું છે?" → કોલરે ફક્ત કુલ કિંમત પૂછી છે; અંતે “કુલ સત્તરસો સત્તાણું રૂપિયા થશે” કહીને અટકવું વધુ સારું.

### gu-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC servicing નો ખર્ચ પાંચસો નવ્વાણું rupees છે. Technician inspection પછી જ spare parts નો ભાવ કહેશે, અને જો તમે repair કરાવો તો inspection charge માફ થઈ જશે. કાલે સવારે slot જોઈતો હોય તો તમારો નામ અને exact address કહેશો?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:272']

### gu-IN/gnani/price (mixed) PASS
- caller: Split AC servicingનો charge કેટલો આવે?
- agent: Split AC servicingનો charge પાંચસો નવ્વાણું rupees છે. તમારે visit book કરાવવી છે?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — ગુજરાતી natural છે અને price સાચો છે. Phone call માટે ટૂંકો જવાબ છે, પણ callerએ ફક્ત charge પૂછ્યો હતો એટલે તરત booking question થોડું sales-y લાગે છે.
  - [unneeded_sales_push] "તમારે visit book કરાવવી છે?" → Price answer પછી રોકાવું, અથવા બહુ નરમ રીતે કહો: “જોઈએ તો visit પણ book કરી આપું.”

### gu-IN/gnani/time_request (mixed) FAIL
- caller: મારું fridge cooling નથી કરતું. Technician કાલે morningમાં 10:30 વાગ્યે આવી શકે?
- agent: Fridge cooling નથી કરતું એ જાણીને અફસોસ થયો. હા, કાલે સવારે દસ ત્રીસનો slot મળી શકે છે, પણ અમારી visits next-day slots માં 10 AM થી 6 PM વચ્ચે જ હોય છે. તમે કયા area માં રહો છો? Madhapur, Gachibowli, Kondapur કે Kukatpally માંથી કોઈ છે?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:236', 'digits_reach_tts']

### hi-IN/gnani/frustration (mixed) PASS
- caller: मैंने simple question पूछा था, fridge inspection fee का straight answer दीजिए।
- agent: Fridge inspection की fee ₹250 है। अगर आप repair के साथ आगे बढ़ते हैं, तो ये charge waive off हो जाएगा। और कोई जानकारी चाहिए?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब सही और नैचुरल Hinglish में है, लेकिन TTS सेटिंग के हिसाब से रकम शब्दों में होनी चाहिए थी। आख़िरी सवाल अनावश्यक है क्योंकि caller ने सिर्फ सीधा जवाब मांगा था।
  - [number_or_time_readout] "₹250" → engine_reads_digits false है, इसलिए कहें: “दो सौ पचास रुपये”
  - [missed_question] "और कोई जानकारी चाहिए?" → Caller ने straight answer मांगा था; इसे हटा दें।

### hi-IN/gnani/greeting_check (mixed) FAIL
- caller: Hello, मेरी आवाज़ clear आ रही है? और ये कौन-सी company है?
- agent: हाँ, आवाज़ बिल्कुल साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh हूँ। बताइए, आज किस चीज़ में help चाहिए आपको?
  - checks: hard=[] warn=['three_sentences']

### hi-IN/gnani/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing पाँच सौ निन्यानवे rupees और window AC की servicing चार सौ निन्यानवे rupees है। तो दो split और एक window AC का total नौ सौ अठानवे rupees आएगा। और कोई जानकारी चाहिए आपको?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 1, 'helpfulness': 2, 'brevity': 4} — मुख्य समस्या गलत जोड़ है: 599+599+499 = 1797, न कि 998। बाकी भाषा समझ में आती है, लेकिन 'rupees' और अंत का सवाल थोड़ा scripted लगता है।
  - [invented_fact] "तो दो split और एक window AC का total नौ सौ अठानवे rupees आएगा" → कुल सत्रह सौ सत्तानवे रुपये कहें: दो split AC = 1198 रुपये, एक window AC = 499 रुपये, total 1797 रुपये।
  - [unneeded_sales_push] "और कोई जानकारी चाहिए आपको?" → कीमत बताकर रुकें, या बस 'कुल सत्रह सौ सत्तानवे रुपये होंगे' कहें।
  - [unnatural_phrasing] "rupees" → हिंदी कॉल में 'रुपये' बोलें।

### hi-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में है। Split AC servicing का charge पांच सौ निन्यानवे rupees है। कल सुबह का slot next-day visit में मिल जाएगा, पर same-day की guarantee नहीं होती। आप अपना नाम बता दीजिए, फिर मैं team को note करवा देता हूँ।
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:239']

### hi-IN/gnani/price (mixed) PASS
- caller: स्प्लिट AC servicing का कितना charge है?
- agent: Split AC servicing का charge पाँच सौ निन्यानवे rupees है।
  - checks: hard=[] warn=['heavy_english_mixing:10/38']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — जवाब सही, छोटा और सीधे सवाल का उत्तर देता है। बस 'rupees' अंग्रेज़ी में थोड़ा कम स्वाभाविक लगता है; हिंदी में 'रुपये' बेहतर होगा।
  - [unnatural_phrasing] "पाँच सौ निन्यानवे rupees" → ज़्यादा स्वाभाविक: “पाँच सौ निन्यानवे रुपये” या “599 रुपये”।

### hi-IN/gnani/time_request (mixed) FAIL
- caller: मेरा fridge cooling नहीं कर रहा। क्या technician कल morning 10:30 पर आ सकता है?
- agent: Fridge की inspection का charge ₹250 है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। कल सुबह दस बजकर तीस मिनट का slot note कर लेता हूँ, पर same-day visit guaranteed नहीं होती। आप किस area में रहते हैं, Madhapur, Gachibowli, Kondapur या Kukatpally?
  - checks: hard=[] warn=['over_soft_length:262', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Hindi is mostly natural and polite, but it wrongly talks about same-day visits when the caller asked for tomorrow, and it sounds like the exact 10:30 slot is being accepted rather than just noted as a preference. Also digits are not suitable for this TTS setting.
  - [number_or_time_readout] "₹250" → दो सौ पचास रुपये
  - [invented_fact] "कल सुबह दस बजकर तीस मिनट का slot note कर लेता हूँ" → कल सुबह दस बजकर तीस मिनट का preference note कर लेता हूँ, team confirm कर देगी
  - [invented_fact] "same-day visit guaranteed नहीं होती" → next-day visit available रहती है, बस exact slot team confirm करेगी

### kn-IN/gnani/frustration (mixed) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ, please straight answer ಕೊಡಿ. Fridge inspection fee ಎಷ್ಟು?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ, ಆ inspection charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay? Fridge inspectionಗೆ exact fee ಎಷ್ಟು ಅಂತ straight ಆಗಿ ಹೇಳಿ.
- agent: ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ ಬೇಜಾರಿಲ್ಲ. Fridge inspection-ಗೆ exact fee ₹250. Repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### kn-IN/gnani/greeting_check (mixed) FAIL
- caller: Hello, ನನ್ನ voice ಕೇಳಿಸ್ತಿದೆಯಾ? ಇದು ಯಾವ company?
- agent: ಹೌದು, clear ಆಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮಗೆ ಏನು help ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- caller: Hi, ನೀವು ನನ್ನನ್ನು hear ಮಾಡ್ತಿದ್ದೀರಾ? ನಿಮ್ಮ company name ಏನು?
- agent: ಹೌದು, ನಿಮ್ಮ voice clear ಆಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮಗೆ ಯಾವ details ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']

### kn-IN/gnani/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: ಒಂದು split AC service-ಗೆ ₹599 ಆಗುತ್ತೆ, ಮತ್ತೆ window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So ಎರಡು split ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — ಲೆಕ್ಕ ಸರಿಯಾಗಿದೆ ಮತ್ತು ಕನ್ನಡ code-mix ಸಹಜವಾಗಿದೆ. ಆದರೆ TTS digits ಓದುವುದಿಲ್ಲವಾದ್ದರಿಂದ ಮೊತ್ತವನ್ನು ಪದಗಳಲ್ಲಿ ಬರೆಯಬೇಕು, ಮತ್ತು caller ಕೇಳಿದ್ದು total ಮಾತ್ರವಾದ್ದರಿಂದ ಕೊನೆಯಲ್ಲಿ booking push ಸ್ವಲ್ಪ ಅನಗತ್ಯ.
  - [number_or_time_readout] "₹1,697" → engine_reads_digits=false ಆಗಿರುವುದರಿಂದ ಸಂಖ್ಯೆಯನ್ನು ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ: “ಒಟ್ಟು ಸಾವಿರ ಆರು ನೂರು ತೊಂಬತ್ತೇಳು ರೂಪಾಯಿ ಆಗುತ್ತೆ.”
  - [missed_question] "ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?" → ಕಾಲರ್ ಮತ್ತೆ total ಮಾತ್ರ ಕೇಳಿದ್ದಾರೆ; booking ಪ್ರಶ್ನೆ ಬೇಡ. ಉತ್ತರವನ್ನು total ಹೇಳುವುದರಲ್ಲೇ ಮುಗಿಸಿ.

### kn-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಖಂಡಿತ, Kondapur ನಮ್ಮ service area-ದಲ್ಲಿ ಬರುತ್ತೆ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ 6 PM ಒಳಗಡೆ next-day slot ಇದೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ? ಹಾಗೇ exact ಆಗಿ ಯಾವ time-ಗೆ ಬರೋದು ಅಂತ ತಿಳಿಸಿ.
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']

### kn-IN/gnani/price (mixed) PASS
- caller: ಸ್ಪ್ಲಿಟ್ AC servicing ಗೆ ಎಷ್ಟು cost ಆಗುತ್ತೆ?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ visit arrange ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ನನ್ನ split AC ಗೆ service ಮಾಡಿಸಬೇಕು, charges ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ? ಯಾಕಂದ್ರೆ ನಾವು ಈ areas-ನಲ್ಲಿ ಮಾತ್ರ service ಮಾಡ್ತೀವಿ.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Reply is mostly natural spoken Kannada with acceptable English code-mixing, and it answers the price plus asks the needed service-area question. Main issue is the digit/rupee amount formatting for this TTS engine.
  - [number_or_time_readout] "₹599" → engine_reads_digits false ಆಗಿರುವುದರಿಂದ, ಇದನ್ನು 'ಐದು ನೂರು ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ' ಅಥವಾ ಮಾತಿನಲ್ಲಿ natural ಆಗಿ 'ಫೈವ್ ನೈನ್ಟಿ ನೈನ್ ರೂಪಾಯಿ' ಎಂದು ಬರೆಯಿರಿ.

### kn-IN/gnani/time_request (mixed) FAIL
- caller: Cooling ಆಗದ ನನ್ನ fridgeಗೆ ನಾಳೆ morning 10:30ಕ್ಕೆ technician ಬರಬಹುದಾ?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ನಮ್ಮ service area ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ. ನಾಳೆ morning 10:30ಕ್ಕೆ next-day slot ಇರುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ area ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:248', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ. ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ?
- agent: ಹೌದು, ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ slot ಇದೆ. ಆದ್ರೆ ನಮ್ಮ service ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ. ನಿಮ್ಮ area ಯಾವುದು ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Kannada is mostly natural and concise, but it wrongly confirms a specific appointment slot and uses digit time despite the TTS setting. It should take details for team confirmation instead.
  - [invented_fact] "ಹೌದು, ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ slot ಇದೆ." → Exact slot availability confirm ಮಾಡಬಾರದು; ಹೇಳಿ: “ನಾಳೆ ಬೆಳಗ್ಗೆ slotಗಾಗಿ request ತೆಗೆದುಕೊಳ್ತೀನಿ, team confirm ಮಾಡ್ತಾರೆ.”
  - [number_or_time_readout] "10:30ಕ್ಕೆ" → engine digits ಓದುವುದಿಲ್ಲ, ಆದ್ದರಿಂದ ಕನ್ನಡದಲ್ಲಿ ಬರೆಯಿರಿ: “ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ” ಅಥವಾ “ಹತ್ತು ಗಂಟೆ ಮೂವತ್ತು ನಿಮಿಷಕ್ಕೆ”.
  - [missed_question] "ನಿಮ್ಮ area ಯಾವುದು ಅಂತ ಹೇಳ್ತೀರಾ?" → Area ಜೊತೆಗೆ visit requestಗೆ ಬೇಕಾದ ಹೆಸರು, appliance/issue already ಗೊತ್ತಿದ್ದರೆ ಕನಿಷ್ಠ locality ಮತ್ತು name ಕೇಳಿ: “ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು area ಹೇಳಿ.”

### ml-IN/gnani/frustration (mixed) FAIL
- caller: ഞാൻ simple question ആണ് ചോദിച്ചത്. Fridge inspection fee എത്രയെന്ന് straight ആയി പറയൂ.
- agent: Fridge inspection-ന് ₹250 ആണ് charge വരുന്നത്. എന്നാൽ repair ചെയ്യാൻ മുന്നോട്ട് പോവുകയാണെങ്കിൽ ഈ inspection charge ഞങ്ങൾ waive off ചെയ്തു തരും.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/gnani/greeting_check (mixed) FAIL
- caller: Hello, എന്റെ voice കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് company ആണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് സംസാരിക്കുന്നത്. എന്താണ് help വേണ്ടത്?
  - checks: hard=[] warn=['three_sentences']

### ml-IN/gnani/numbers (mixed) FAIL
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് 599 രൂപയും window AC-ക്ക് 499 രൂപയുമാണ് വരുന്നത്. അപ്പൊ രണ്ട് split AC-യും ഒരു window AC-യും ചേർത്ത് total 1,697 രൂപയാകും.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. Technician നാളെ വരണമെങ്കിൽ, ഏത് സമയത്താണ് സൗകര്യം എന്ന് പറയാമോ? രാവിലെ പത്ത് മണിക്കും വൈകുന്നേരം ആറ് മണിക്കും ഇടയിലുള്ള next-day slots ആണ് ഞങ്ങൾ കൊടുക്കുന്നത്.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:259', 'digits_reach_tts']

### ml-IN/gnani/price (mixed) FAIL
- caller: Split AC servicing-ന് എത്ര cost വരും?
- agent: Split AC servicing-ന് ₹599 ആണ് വരുന്നത്.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/gnani/time_request (mixed) FAIL
- caller: Cooling ഇല്ലാത്ത fridge-ന് നാളെ morning 10:30-ന് technician വരാമോ?
- agent: Fridge-ന്റെ cooling issue-ന് നാളെ 10:30-ന് വരാൻ പറ്റും. പക്ഷെ നമ്മുടെ service area Madhapur, Gachibowli, Kondapur, Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമാണ്. അങ്ങോട്ട് നിങ്ങളുടെ സ്ഥലം വരുമോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### ta-IN/gnani/frustration (mixed) FAIL
- caller: நான் ஒரு simple question தான் கேட்டேன், please straight answer சொல்லுங்க. Fridge inspection fee எவ்வளவு?
- agent: Fridge inspection-க்கு ₹250 வரும். ஆனா ஒரு விஷயம், நீங்க repair பண்ண முடிவு பண்ணீங்கன்னா அந்த inspection charge waive ஆகிடும்.
  - checks: hard=[] warn=['digits_reach_tts']

### ta-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, என் voice கேட்கிறதா? இது என்ன company?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். உங்களுக்கு என்ன help வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Good Tamil reply with natural urban code-mixing, correctly answers both whether the voice is audible and what the company is. Slightly scripted because it repeats the opening info, but still phone-appropriate.

### ta-IN/gnani/numbers (mixed) FAIL
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599, window AC-க்கு ₹499 ஆகும். Technician வந்து inspect பண்ணதுக்கு அப்புறம் தான் spare parts cost எவ்வளவுனு சொல்லுவாங்க, அதனால அது தனியா extra வரும். உங்களுக்கு visit schedule பண்ணணுமா?
  - checks: hard=[] warn=['over_soft_length:211', 'three_sentences', 'digits_reach_tts']

### ta-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing-க்கு ₹599 ஆகும். நாளைக்கு visit வேணும்னா, உங்க பேரும், எந்த time உங்களுக்கு வசதியா இருக்கும்னு சொல்ல முடியுமா? அப்போதான் team-கிட்ட பேசி slot confirm பண்ண முடியும்.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:235', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Reply is natural spoken Tamil with acceptable code-mixing, and it mostly answers the caller. Main issues are digit/amount formatting for this TTS engine and not clearly anchoring the requested morning visit to the actual slot window.
  - [number_or_time_readout] "₹599" → engine_reads_digits=false என்பதால், 'ஐந்நூற்றி தொண்ணூற்று ஒன்பது ரூபாய்' என்று தமிழில் எழுத வேண்டும்.
  - [missed_question] "எந்த time உங்களுக்கு வசதியா இருக்கும்னு சொல்ல முடியுமா?" → Caller 'tomorrow morning' கேட்டதால், 'நாளைக்கு காலை பத்து மணிக்குப் பிறகு slot பார்க்கலாம்' என்று available visit window-ஐ தெளிவாகச் சொல்லலாம்.

### ta-IN/gnani/price (mixed) PASS
- caller: Split AC service பண்ண எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும்.
  - checks: hard=[] warn=['heavy_english_mixing:5/21', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural and directly answers the pricing question in Tamil, but since this TTS engine does not read digits/amounts in the call language, the amount should be written out in Tamil words.
  - [number_or_time_readout] "₹599" → ஐநூற்று தொண்ணூற்று ஒன்பது ரூபாய்

### ta-IN/gnani/time_request (mixed) FAIL
- caller: Cooling இல்லாத fridge-க்கு நாளைக்கு morning 10:30-க்கு technician வர முடியுமா?
- agent: Sorry, எங்களுக்கு Madhapur, Gachibowli, Kondapur, அப்புறம் Kukatpally areas-ல தான் service இருக்கு. Secunderabad அப்புறம் Old City cover ஆகாது. Fridge inspection-க்கு ₹250 வரும், ஆனா நீங்க repair பண்ணீங்கன்னா அந்த charge waive ஆயிடும்.
  - checks: hard=[] warn=['over_soft_length:235', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 2, 'brevity': 3} — Tamil code-mix natural, and price fact is correct, but the reply doesn’t directly handle the requested next-day 10:30 visit or collect locality/details. It also includes unnecessary non-covered area info and uses digits despite the TTS setting.
  - [missed_question] "Sorry, எங்களுக்கு Madhapur, Gachibowli, Kondapur, அப்புறம் Kukatpally areas-ல தான் service இருக்கு." → Caller கேட்டது நாளைக்கு 10:30 slot பற்றி; முதலில் locality கேட்டு, next-day slots 10 AM–6 PM-க்குள் confirm பண்ணலாம் என்று சொல்ல வேண்டும்.
  - [unneeded_sales_push] "Secunderabad அப்புறம் Old City cover ஆகாது." → Caller locality சொல்லாததால் இந்த தகவல் இப்போது தேவையில்லை; 'நீங்க எந்த area?' என்று கேட்பது போதும்.
  - [number_or_time_readout] "₹250" → engine_reads_digits false என்பதால் 'இருநூற்று ஐம்பது ரூபாய்' என்று எழுத வேண்டும்.

### te-IN/gnani/frustration (mixed) FAIL
- caller: నేను simple question అడిగాను, please straight answer చెప్పండి. Fridge inspection fee ఎంత?
- agent: Fridge inspection కి ₹250 అవుతుంది. ఒకవేళ మీరు repair చేయిస్తే ఆ inspection charge waive అవుతుంది.
  - checks: hard=[] warn=['digits_reach_tts']

### te-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, నా voice వినిపిస్తుందా? ఇది ఏ company?
- agent: అవును, మీ voice clear గా వినిపిస్తోంది. నేను సురేష్, SmartCare Appliance Services నుంచి మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Telugu code-mixing is natural and it directly answers both audibility and company question. Slightly generic receptionist-style ending, but acceptable for a phone call.
  - [robotic_or_scripted] "చెప్పండి, మీకు ఎలా సహాయం చేయగలను?" → కొంచెం సహజంగా: “చెప్పండి, ఏ service కావాలి?”

### te-IN/gnani/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC servicing కి ₹599 అవుతుంది, అలాగే ఒక window AC కి ₹499 అవుతుంది. So రెండు split ACలు, ఒక window AC కి కలిపి ₹1697 అవుతుంది. మీకు మా service area లో visit కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### te-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing కి ₹599 అవుతుంది. మా team next-day visit ని ఉదయం పది నుంచి సాయంత్రం ఆరు మధ్యలో schedule చేస్తారు. మీకు ఏ time వీలవుతుందో చెప్తారా?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']

### te-IN/gnani/price (mixed) PASS
- caller: స్ప్లిట్ AC servicing కి ఎంత cost అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు వేరే ఏదైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — జవాబు సరైన సమాచారమే ఇస్తోంది, Telugu-English code-mix సహజంగానే ఉంది. కానీ TTS digits చదవదు కాబట్టి amountని పదాల్లో రాయాలి; అలాగే అవసరం లేని follow-up question కొంచెం స్క్రిప్టెడ్‌గా ఉంది.
  - [number_or_time_readout] "₹599" → engine_reads_digits false కాబట్టి ‘ఐదు వందల తొంభై తొమ్మిది రూపాయలు’ అని చెప్పాలి.
  - [unneeded_sales_push] "మీకు వేరే ఏదైనా details కావాలా?" → ధర అడిగారు కాబట్టి ‘Split AC servicing కి ఐదు వందల తొంభై తొమ్మిది రూపాయలు అవుతుంది.’ అని మాత్రమే చెప్పడం సరిపోతుంది.

### te-IN/gnani/time_request (mixed) FAIL
- caller: Cooling లేని fridge కి రేపు morning 10:30కి technician రావచ్చా?
- agent: Fridge inspection కి ₹250 అవుతుంది, కానీ మీరు repair చేయిస్తే ఆ inspection charge waive అవుతుంది. మా service area Madhapur, Gachibowli, Kondapur, Kukatpally వరకే ఉంటుంది. మీరు ఈ areas లో ఉన్నారా?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:33/128', 'digits_reach_tts']
