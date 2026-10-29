# Language probe language-probe-v4-sarvam

Schema `sim_db3314718b764d6899a9290f2273b323`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | sarvam | 4/13 | 4.47 | human_naturalness 4.00 |
| gu-IN | sarvam | 4/13 | 4.47 | brevity 4.17 |
| hi-IN | sarvam | 4/13 | 4.44 | human_naturalness 4.00 |
| kn-IN | sarvam | 4/13 | 4.43 | human_naturalness 4.00 |
| ml-IN | sarvam | 4/13 | 4.50 | human_naturalness 4.00 |
| ta-IN | sarvam | 3/13 | 4.89 | human_naturalness 4.33 |
| te-IN | sarvam | 5/13 | 4.15 | helpfulness 3.75 |

## Transcripts

### en-IN/sarvam/correction (clean) PASS
- caller: How much do you charge for split AC servicing?
- agent: Split AC servicing is 599 rupees. Which area are you located in?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: Actually, it is a window AC, not a split AC. How much would the service cost?
- agent: Window AC servicing is 499 rupees. Is your location in Madhapur, Gachibowli, Kondapur, or Kukatpally?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The reply is correct, concise, and in Indian English. It answers the updated pricing question clearly. The follow-up area question is relevant if moving toward booking, though the phrasing is a little scripted.
  - [robotic_or_scripted] "Is your location in Madhapur, Gachibowli, Kondapur, or Kukatpally?" → Slightly more natural: “Which area are you in?” or “Are you in Madhapur, Gachibowli, Kondapur or Kukatpally?”

### en-IN/sarvam/frustration (noisy) PASS
- caller: I asked simple question just tell me clearly fridge inspection charge
- agent: The fridge inspection costs 250 rupees. If you go ahead with the repair, that inspection charge is waived. Would you like to book an inspection?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Clear, correct Indian English and concise. The booking question is a mild push after the caller specifically asked only for the inspection charge.
  - [unneeded_sales_push] "Would you like to book an inspection?" → Since the caller explicitly asked to just tell the charge, stop after the price and waiver information.

### en-IN/sarvam/greeting_check (clean) FAIL
- caller: Hello, can you hear me? Which company is this?
- agent: This is SmartCare Appliance Services. How can I help you today?

### en-IN/sarvam/hesitation (mixed) PASS
- caller: Let me think about it, I may call back later.
- agent: No problem at all. Just let me know whenever you decide to go ahead, and we will be here to help. Have a good day.
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural and appropriate Indian English for a caller saying they may call back. Slightly polished, but perfectly acceptable for a phone receptionist and brief.

### en-IN/sarvam/not_covered (clean) FAIL
- caller: I live in Secunderabad. Can a technician come there?
- agent: Unfortunately, we don't cover Secunderabad right now. Our service areas are limited to Madhapur, Gachibowli, Kondapur, and Kukatpally only.

### en-IN/sarvam/numbers (mixed) FAIL
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For 2 split ACs at 599 rupees each and 1 window AC at 499 rupees, the total comes to 1,797 rupees. Would you like to go ahead and book a service visit?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 1, 'helpfulness': 3, 'brevity': 4} — The language and tone are fine for Indian English, but the total is wrong. The booking prompt is a bit pushy after a straightforward pricing question.
  - [invented_fact] "the total comes to 1,797 rupees" → Correct total is 1,697 rupees.
  - [unneeded_sales_push] "Would you like to go ahead and book a service visit?" → Since the caller only asked the total, just answer the price; optionally stop after the total.

### en-IN/sarvam/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: We do cover Kondapur, and same-day visits are not guaranteed. We can book a next-day slot between 10 AM and 6 PM. Could you tell me your name so I can note this down?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### en-IN/sarvam/parts_price (noisy) FAIL
- caller: how much exactly new fridge compressor cost
- agent: I don't have the price for a new compressor over the phone. The technician will quote the actual MRP for spare parts only after inspecting the fridge. Would you like to go ahead with a fridge inspection?
  - checks: hard=[] warn=['over_soft_length:203', 'three_sentences']

### en-IN/sarvam/price (clean) FAIL
- caller: How much do you charge for servicing a split AC?
- agent: Servicing a split AC costs 599 rupees. Would you like to go ahead and book a visit?
  - checks: hard=[] warn=['digits_reach_tts']

### en-IN/sarvam/safety (mixed) FAIL
- caller: Can I open the AC electrical panel with the power on and tighten the loose wire myself?
- agent: I would not recommend opening the electrical panel or working on live wiring yourself. It is safer to have a technician inspect and fix it. Would you like to book a service visit?
  - checks: hard=[] warn=['three_sentences']

### en-IN/sarvam/time_request (noisy) FAIL
- caller: can you send someone tomorrow morning at 10 30 the fridge is not cooling
- agent: I can certainly note that request for you. Just to confirm, is your locality in Madhapur, Gachibowli, Kondapur, or Kukatpally?

### en-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service price how much, and do you provide service in Kondapur?
- agent: Window AC servicing is 499 rupees, and yes, we do cover Kondapur.
  - checks: hard=[] warn=['digits_reach_tts']

### en-IN/sarvam/unknown_fact (noisy) PASS
- caller: for two ACs what will AMC cost one year
- agent: I don't have AMC pricing on hand. We do window AC servicing at 499 rupees and split AC servicing at 599 rupees. Which type of ACs do you have?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good Indian English, factual, and clear. It correctly says AMC pricing is not available and gives the known servicing rates. Slightly less ideal because it adds a follow-up question instead of just answering the pricing question.
  - [other] "Which type of ACs do you have?" → Avoid adding a question if the caller only asked AMC cost, or phrase it as optional: “For regular servicing, it’s 499 for window AC and 599 for split AC.”

### gu-IN/sarvam/correction (clean) FAIL
- caller: સ્પ્લિટ એસી સર્વિસનો ભાવ કેટલો છે?
- agent: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ ₹599 છે. તમારે visit માટે booking કરાવવું છે?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: અરે, ખરેખર તો એ વિન્ડો એસી છે, સ્પ્લિટ નહીં. એની સર્વિસનો ભાવ કેટલો છે?
- agent: વિન્ડો એસી સર્વિસિંગનો ખર્ચ ₹499 છે.
  - checks: hard=[] warn=['digits_reach_tts']

### gu-IN/sarvam/frustration (noisy) FAIL
- caller: મેં સિમ્પલ સવાલ પૂછ્યો ફ્રિજ ઇન્સ્પેક્શન ફીનો સીધો આન્સર આપો
- agent: ફ્રિજ inspection ની fee ₹250 છે. જો તમે repair આગળ વધારો તો આ charge માફ થઈ જશે. બીજું કઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Correct Gujarati with natural service-industry code-mixing and accurate price/waiver. Slightly less natural phrasing and the extra follow-up question is unnecessary given the caller explicitly asked for a direct answer.
  - [unneeded_sales_push] "બીજું કઈ જાણવું છે તમારે?" → Caller asked for a direct answer; stop after the fee and waiver info.
  - [unnatural_phrasing] "જો તમે repair આગળ વધારો" → Say more naturally: "જો તમે રિપેર કરાવો તો..."

### gu-IN/sarvam/greeting_check (clean) FAIL
- caller: હેલો, તમને મારો અવાજ સંભળાય છે? આ કઈ કંપની છે?
- agent: હા, અવાજ બરાબર આવે છે. હું SmartCare Appliance Services માંથી Suresh બોલું છું. કહો, શું કામ હતું?
  - checks: hard=[] warn=['three_sentences']

### gu-IN/sarvam/hesitation (mixed) PASS
- caller: હું આના વિશે think કરીશ, maybe later call back કરીશ.
- agent: ચોક્કસ, તમે આરામથી વિચારી લો. જ્યારે પણ જરૂર હોય ત્યારે call કરી શકો છો.
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural, polite Gujarati with acceptable everyday English code-mixing. It directly acknowledges the caller’s plan to think and call later, without adding pressure or unnecessary details.

### gu-IN/sarvam/not_covered (clean) FAIL
- caller: હું સિકંદરાબાદમાં રહું છું. શું તમારો ટેકનિશિયન અહીં આવી શકે?
- agent: માફ કરજો, અત્યારે અમે ફક્ત Madhapur, Gachibowli, Kondapur અને Kukatpallyમાં જ service આપીએ છીએ. Secunderabad અત્યારે અમારા service areaમાં આવતું નથી, એટલે ત્યાં technician મોકલવો શક્ય નથી. બીજું કોઈ કામ હતું?
  - checks: hard=[] warn=['over_soft_length:208', 'three_sentences']

### gu-IN/sarvam/numbers (mixed) FAIL
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service ₹599 અને window AC ની ₹499 થશે. તો બે split અને એક window AC માટે total ₹1,797 થશે.
  - checks: hard=[] warn=['heavy_english_mixing:16/56', 'digits_reach_tts']

### gu-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC ના servicing નો charge ₹599 છે. Technician inspection પછી જ spare parts નું actual MRP જણાવશે, જેની price અમે phone પર નથી આપતા. આવતીકાલે સવારે 10 થી 6 ની વચ્ચે next-day slot મળી શકે. તમારે કઈ time ફાવશે?
  - checks: hard=['too_many_sentences:5'] warn=['over_soft_length:257', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 2} — Gujarati is mostly natural and the area/pricing facts are broadly right, but the slot wording is wrong/awkward for a phone call and the answer is longer than needed. It should move more directly into confirming a morning slot and collecting booking details.
  - [number_or_time_readout] "આવતીકાલે સવારે 10 થી 6 ની વચ્ચે" → કહો: “આવતીકાલે સવારના દસથી સાંજે છ વચ્ચે slot હોય છે.”
  - [invented_fact] "સવારે 10 થી 6" → છ વાગ્યા સુધીનો સમય ‘સવાર’ નથી; “સવારના દસથી સાંજે છ” કહો.
  - [too_long] "Technician inspection પછી જ spare parts નું actual MRP જણાવશે, જેની price અમે phone પર નથી આપતા." → આટલું ટૂંકું કરો: “Parts extra હશે, technician જોઈને quote કરશે.”
  - [missed_question] "તમારે કઈ time ફાવશે?" → Caller એ tomorrow morning કહ્યું છે; હવે booking details લો: “દસથી બાર ચાલશે? તમારું નામ અને address કહેશો?”

### gu-IN/sarvam/parts_price (noisy) FAIL
- caller: મારા ફ્રિજના નવા કમ્પ્રેસરનો એક્ઝેક્ટ પ્રાઇસ કેટલો
- agent: જુઓ, અત્યારે phone પર spare parts ના ભાવ આપવાનું શક્ય નથી. Technician જ્યારે inspection કરશે, ત્યારે actual MRP પ્રમાણે તમને ભાવ જણાવશે.

### gu-IN/sarvam/price (clean) PASS
- caller: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ કેટલો આવે?
- agent: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ ₹599 આવે છે.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — સંદર્ભમાં જવાબ સ્વાભાવિક, ટૂંકો અને સાચો છે. ₹599 લખવું યોગ્ય છે કારણ કે TTS engine digits/amounts સ્થાનિક ભાષામાં વાંચે છે.

### gu-IN/sarvam/safety (mixed) PASS
- caller: Power on હોય ત્યારે loose wire ઠીક કરવા ACનું electrical panel હું જાતે કેવી રીતે ખોલું?
- agent: માફ કરજો, હું તમને electrical panel ખોલવાની કે live wiring કરવાની સલાહ નહીં આપી શકું, એમાં safety નો risk છે. જો AC માં કોઈ issue હોય, તો અમારા technician આવીને inspection કરી લેશે. શું હું તમારા માટે visit arrange કરી દઉં?
  - checks: hard=[] warn=['over_soft_length:223', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Gujarati is natural with acceptable urban code-mixing. The reply safely refuses instructions for live electrical work and offers a technician visit without inventing pricing or unsupported details. Slightly longer than ideal for a phone reply, but still fine.

### gu-IN/sarvam/time_request (noisy) FAIL
- caller: મારું ફ્રિજ કૂલિંગ નથી કરતું ટેકનિશિયન કાલે મોર્નિંગ દસ ત્રીસે આવી શકે
- agent: ફ્રિજનું cooling નથી થતું એ સાંભળીને અફસોસ થયો. Fridge inspection નો charge ₹250 છે, પણ જો તમે repair કરાવો તો એ charge માફ થઈ જશે. કાલે સવારે 10:30 એ visit માટે team confirm કરી શકશે. તમારું નામ કહેશો?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:202', 'digits_reach_tts']

### gu-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC serviceની price કેટલી છે, અને Kondapurમાં તમે cover કરો છો?
- agent: Window AC servicingનો ખર્ચ ₹499 છે, અને હા, અમે Kondapurમાં service આપીએ છીએ.
  - checks: hard=[] warn=['digits_reach_tts']

### gu-IN/sarvam/unknown_fact (noisy) PASS
- caller: બે એસી માટે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટ AMC કેટલામાં થાય
- agent: માફ કરશો, અત્યારે અમારી પાસે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટની કોઈ માહિતી નથી. અમે ફક્ત servicingના ભાવ જણાવી શકીએ છીએ, જેમ કે Window AC માટે ₹499 અને Split AC માટે ₹599 છે.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — જવાબ સાચો અને સીધો છે, Gujaratiમાં છે, અને pricing વિશે facts સાથે મેળ ખાય છે. થોડું પુસ્તકિય/translated લાગે છે, પણ ફોન પર ચાલે એવો ટૂંકો જવાબ છે.
  - [unnatural_phrasing] "અત્યારે અમારી પાસે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટની કોઈ માહિતી નથી" → વધુ સહજ: “AMC વિશે અમારી પાસે હાલ details નથી” અથવા “અમે AMC આપીએ છીએ કે નહીં એની information હાલ નથી.”
  - [unnatural_phrasing] "servicingના ભાવ" → ગુજરાતી બોલચાલમાં “સર્વિસિંગના રેટ” વધુ સ્વાભાવિક લાગે.

### hi-IN/sarvam/correction (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च है?
- agent: Split AC servicing का charge ₹599 है।
  - checks: hard=[] warn=['heavy_english_mixing:2/24', 'digits_reach_tts']
- caller: माफ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विसिंग का कितना खर्च होगा?
- agent: Window AC servicing का charge ₹499 है।
  - checks: hard=[] warn=['heavy_english_mixing:2/25', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is correct, brief, and natural enough for urban Hindi phone speech. Slightly script-like with English words, but acceptable code-mixing and directly answers the corrected pricing question.

### hi-IN/sarvam/frustration (noisy) FAIL
- caller: मैंने सिंपल क्वेश्चन पूछा था फ्रिज inspection fee का सीधा answer दीजिए
- agent: Fridge inspection की fee ₹250 है। अगर आप repair करवाते हैं, तो ये charge waive off हो जाएगा। और कोई जानकारी चाहिए?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### hi-IN/sarvam/greeting_check (clean) FAIL
- caller: नमस्ते, क्या आपको मेरी आवाज़ सुनाई दे रही है? और यह कौन-सी कंपनी है?
- agent: हाँ, आवाज़ साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh हूँ। बताइए, क्या service चाहिए आपको?
  - checks: hard=[] warn=['three_sentences']

### hi-IN/sarvam/hesitation (mixed) PASS
- caller: ठीक है, मैं इस पर think करूँगा, शायद बाद में call back करूँ।
- agent: ठीक है, कोई बात नहीं। जब भी आपको ज़रूरत हो, आप call कर लीजिएगा।
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural, polite Hindi with common code-mixing, directly acknowledges the caller and keeps it brief without adding unnecessary information.

### hi-IN/sarvam/not_covered (clean) PASS
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका technician यहाँ आ सकता है?
- agent: सिकंदराबाद में अभी service available नहीं है। हम सिर्फ Madhapur, Gachibowli, Kondapur और Kukatpally में ही visit करते हैं। क्या आपका area इनमें से किसी में आता है?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is in natural Hindi-English code-mix, polite, and factually correct. The follow-up question is a bit unnecessary because the caller already specified Secunderabad, but it’s not a major issue.
  - [missed_question] "क्या आपका area इनमें से किसी में आता है?" → Caller already said they are in Secunderabad; better end with a brief alternative like: "माफ़ कीजिए, वहाँ हम visit नहीं कर पाएँगे."

### hi-IN/sarvam/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing ₹599 और window AC की ₹499 है। तो दो split और एक window AC का total ₹1,697 आएगा। और हाँ, technician inspection के बाद जो spare parts लगेंगे, वो actual MRP पर extra लगेंगे, उसकी price phone पर नहीं बताई जा सकती।
  - checks: hard=[] warn=['over_soft_length:231', 'three_sentences', 'digits_reach_tts']

### hi-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में है। Split AC servicing का charge ₹599 है। Technician inspection के बाद जो भी spare parts लगेंगे, वो actual MRP पर extra लगेंगे, उसकी price phone पर नहीं बता सकते। कल सुबह visit के लिए slot note करने के लिए, अपना नाम बता दीजिए।
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:263', 'digits_reach_tts']

### hi-IN/sarvam/parts_price (noisy) FAIL
- caller: मेरे फ्रिज के नए कम्प्रेसर का exact प्राइस कितना है
- agent: Fridge के spare parts का exact price phone पर बताना possible नहीं है। Technician पहले inspection करके actual MRP के हिसाब से quote दे देगा। Inspection charge ₹250 है, लेकिन अगर आप repair करवाते हैं तो वो charge waive हो जाएगा। और कोई जानकारी चाहिए?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:248', 'digits_reach_tts']

### hi-IN/sarvam/price (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च आता है?
- agent: Split AC servicing का charge ₹599 है।
  - checks: hard=[] warn=['heavy_english_mixing:2/24', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — जवाब सही, छोटा और सीधे पूछा गया दाम बताता है। हल्का-सा English-heavy phrasing है, लेकिन शहरी Hindi कॉल में समझ में आने वाला है।
  - [unnatural_phrasing] "Split AC servicing का charge" → स्प्लिट एसी सर्विसिंग का चार्ज

### hi-IN/sarvam/safety (mixed) FAIL
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel मैं खुद कैसे खोलूँ?
- agent: मैं इसकी सलाह नहीं दे सकता। Live wiring या electrical panel खोलना dangerous हो सकता है, इसलिए कृपया खुद कोशिश मत कीजिए। Safety के लिए technician को बुलाना ही बेहतर रहेगा। क्या आप service के लिए visit book करवाना चाहेंगे?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:220']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Reply सही भाषा में है, safety advice सही है और electrical panel खोलने की सलाह नहीं देता. Overall phone call के लिए अच्छा है, बस थोड़ा और natural/less scripted हो सकता था.
  - [too_formal] "मैं इसकी सलाह नहीं दे सकता।" → इसे थोड़ा बोलचाल में कहें: “नहीं सर, ये आप खुद मत कीजिए।”
  - [robotic_or_scripted] "क्या आप service के लिए visit book करवाना चाहेंगे?" → ज़्यादा natural: “चाहें तो technician visit के लिए details ले लेता हूँ।”

### hi-IN/sarvam/time_request (noisy) FAIL
- caller: फ्रिज कूलिंग नहीं कर रहा technician कल मॉर्निंग दस तीस पर आ सकता है
- agent: Fridge की cooling की problem के लिए inspection charge ₹250 है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। कल सुबह 10:30 का slot note कर लेता हूँ, बस अपना नाम बता दीजिए।
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 3} — Hindi code-mix mostly natural and price info is correct, but it over-confirms a specific appointment time, uses digit clock time, and doesn’t ask locality needed for serviceability/booking.
  - [invented_fact] "कल सुबह 10:30 का slot note कर लेता हूँ" → Exact 10:30 slot confirm/note नहीं करना चाहिए; facts के हिसाब से next-day slots 10 AM से 6 PM के बीच हैं और team confirm करेगी. कहें: "कल सुबह का preference note कर लेता हूँ, team slot confirm कर देगी."
  - [number_or_time_readout] "10:30" → Indic spoken sentence में clock time digits में न लिखें; TTS के लिए "साढ़े दस" या "दस तीस" लिखें.
  - [missed_question] "बस अपना नाम बता दीजिए।" → Visit के लिए सिर्फ नाम नहीं; appliance/issue already है, locality और preferred slot भी लेना है. Area coverage check करने के लिए locality पूछें.

### hi-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service का कितना price है, और क्या आप Kondapur cover करते हैं?
- agent: Window AC servicing का charge ₹499 है, और हाँ, हम Kondapur में service देते हैं।
  - checks: hard=[] warn=['heavy_english_mixing:11/49', 'digits_reach_tts']

### hi-IN/sarvam/unknown_fact (noisy) FAIL
- caller: दो AC का annual maintenance contract AMC कितने का पड़ेगा
- agent: देखिए, हम यहाँ annual maintenance contract नहीं देते। हमारे पास सिर्फ servicing है, window AC की ₹499 और split AC की ₹599। आपको servicing करवानी है क्या?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### kn-IN/sarvam/correction (clean) PASS
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['heavy_english_mixing:5/21', 'digits_reach_tts']
- caller: ಇಲ್ಲ, ಕ್ಷಮಿಸಿ, ಅದು ವಿಂಡೋ ಎಸಿ. ಅದಕ್ಕೆ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['heavy_english_mixing:5/22', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — ಉತ್ತರ ಸರಿಯಾದ ಬೆಲೆ ಹೇಳುತ್ತದೆ ಮತ್ತು ಚಿಕ್ಕದಾಗಿದೆ. ಆದರೆ ಆರಂಭದ English phrase ಸ್ವಲ್ಪ ಅಸಹಜ/ಭಾಷೆ mismatch ಆಗಿದೆ; ‘ವಿಂಡೋ ಎಸಿ ಸರ್ವಿಸಿಂಗ್‌ಗೆ ₹499 ಆಗುತ್ತೆ’ ಹೆಚ್ಚು ಸಹಜ.
  - [wrong_language] "Window AC servicing" → ಕನ್ನಡದಲ್ಲೇ ಅಥವಾ ಸಹಜ code-mix ಆಗಿ ‘ವಿಂಡೋ ಎಸಿ ಸರ್ವಿಸಿಂಗ್’ ಎಂದು ಹೇಳಿ.

### kn-IN/sarvam/frustration (noisy) PASS
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ please straight answer ಕೊಡಿ fridge inspection fee ಎಷ್ಟು
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು ಮುಂದೆ repair ಮಾಡಿಸಿದ್ರೆ, ಆ inspection charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay fridge inspectionಗೆ exact fee ಎಷ್ಟು straight ಆಗಿ ಹೇಳಿ
- agent: ಕ್ಷಮಿಸಿ, ಸ್ವಲ್ಪ delay ಆಯ್ತು. Fridge inspection-ಗೆ exact fee ₹250 ಇದೆ.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Kannada with natural urban code-mixing, directly answers the exact fee, and the ₹250 format is fine for this TTS. Slightly repetitive/script-like because it mirrors “exact fee,” but overall suitable for a phone call.

### kn-IN/sarvam/greeting_check (clean) PASS
- caller: ಹಲೋ, ನನ್ನ ಮಾತು ಕೇಳಿಸುತ್ತಿದೆಯೇ? ಇದು ಯಾವ ಕಂಪನಿ?
- agent: ಹೌದು, ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸ್ತಾ ಇದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ಹೇಳಿ, ನಿಮಗೆ ಏನು ಸಹಾಯ ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- caller: ನಮಸ್ಕಾರ, ನೀವು ನನ್ನನ್ನು ಕೇಳಬಹುದೇ? ನಿಮ್ಮ ಕಂಪನಿಯ ಹೆಸರು ಏನು?
- agent: ಹೌದು, ಕೇಳಿಸ್ತಾ ಇದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮ್ಮ AC ಅಥವಾ fridge ಬಗ್ಗೆ ಏನಾದ್ರೂ service ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is mostly natural Kannada with common English service terms and correctly identifies the company. It answers the question, but adds a mild service-push question that wasn’t needed for this turn.
  - [unneeded_sales_push] "ನಿಮ್ಮ AC ಅಥವಾ fridge ಬಗ್ಗೆ ಏನಾದ್ರೂ service ಬೇಕಿತ್ತಾ?" → Caller only asked the company name; stop after identifying the company, or say briefly: “SmartCare Appliance Services, ನಾನು ಸುರೇಶ್.”

### kn-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, ನಾನು ಸ್ವಲ್ಪ think ಮಾಡಿ later ಮತ್ತೆ call ಮಾಡ್ತೀನಿ.
- agent: ಸರಿ, ತೊಂದ್ರೆ ಇಲ್ಲ. ನೀವು ಯಾವಾಗ ಬೇಕಾದ್ರೂ call ಮಾಡಬಹುದು. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿದ್ರೆ ತಿಳಿಸಿ.
  - checks: hard=[] warn=['three_sentences']
- caller: ಹೌದು, ಈಗ ಬೇಡ. ನಾನು think ಮಾಡಿ maybe later call back ಮಾಡ್ತೀನಿ.
- agent: ಸರಿ, ಅರ್ಥ ಆಯ್ತು. ನೀವು ಆರಾಮಾಗಿ ಯೋಚಿಸಿ ಆಮೇಲೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.
  - checks: hard=[] warn=['three_sentences']

### kn-IN/sarvam/not_covered (clean) FAIL
- caller: ನಾನು ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದ್ದೇನೆ. ಅಲ್ಲಿ ಟೆಕ್ನಿಷಿಯನ್ ಬರಬಹುದೇ?
- agent: ಕ್ಷಮಿಸಿ, ಸಿಕಂದರಾಬಾದ್ ಮತ್ತು ಓಲ್ಡ್ ಸಿಟಿ area-ದಲ್ಲಿ ನಾವು service ಕೊಡಲ್ಲ. ನಮ್ಮ service ಬರೀ Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ಯಲ್ಲಿ ಮಾತ್ರ ಇರೋದು. ನೀವು ಈ areas-ಗಳಲ್ಲಿ ಯಾವುದಾದ್ರೂ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: ನನ್ನ ಮನೆ ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದೆ, ನಿಮ್ಮ ಸರ್ವಿಸ್ ಅಲ್ಲಿ ಲಭ್ಯವಿದೆಯೇ?
- agent: ಇಲ್ಲ, ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ service available ಇಲ್ಲ. ನಾವು ಬರೀ Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ಯಲ್ಲಿ ಮಾತ್ರ ಕೆಲಸ ಮಾಡ್ತೀವಿ. ನೀವು ಈ areas-ಗಳಲ್ಲಿ ಯಾವುದಾದ್ರೂ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']

### kn-IN/sarvam/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ, ಮತ್ತೆ window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So, ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1697 ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC service-ಗೆ total ₹1697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit ಏನಾದ್ರೂ schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']

### kn-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಾಳೆ morning slot ಬೇಕಂದ್ರೆ, 10 AM ಇಂದ 6 PM ಒಳಗೆ next-day visit arrange ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Overall Kannada is natural with acceptable English code-mixing, and it answers area and price well. Main issues are TTS-unfriendly time formatting and slightly over-confirming the visit instead of saying the team will confirm the slot.
  - [number_or_time_readout] "10 AM ಇಂದ 6 PM ಒಳಗೆ" → ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಗಂಟೆಯಿಂದ ಸಂಜೆ ಆರು ಗಂಟೆ ಒಳಗೆ
  - [invented_fact] "next-day visit arrange ಮಾಡಬಹುದು" → ನಾಳೆ slot request ತೆಗೆದುಕೊಳ್ತೀನಿ, team confirm ಮಾಡ್ತಾರೆ ಎಂದು ಹೇಳಿ; direct confirmation ಕೊಡಬೇಡಿ.

### kn-IN/sarvam/parts_price (noisy) PASS
- caller: ನನ್ನ fridgeಗೆ new compressor ಹಾಕೋಕೆ exact price ಎಷ್ಟು
- agent: ಆ exact price ನಂಗೆ phone-ಅಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ spare parts-ನ actual MRP ಹೇಳ್ತಾರೆ. Inspection charge ₹250 ಇರುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['over_soft_length:216', 'three_sentences', 'digits_reach_tts']
- caller: fridge ಹೊಸ compressor total price exact ಆಗಿ ಹೇಳಿ
- agent: ಆ exact price ನಂಗೆ phone-ಅಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ, ಯಾಕಂದ್ರೆ technician inspection ಮುಗಿಸಿದ ಮೇಲೆ ಮಾತ್ರ actual MRP ಹೇಳ್ತಾರೆ. ನಿಮಗೆ ನಮ್ಮ team ಇಂದ visit arrange ಮಾಡ್ಬೇಕಾ?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Kannada with natural urban code-mixing, and the pricing policy is correct. The visit offer is relevant, but one phrase sounds a bit awkward for spoken Kannada.
  - [unnatural_phrasing] "ನಮ್ಮ team ಇಂದ" → ನಮ್ಮ team‌ನಿಂದ / ನಮ್ಮ ತಂಡದಿಂದ

### kn-IN/sarvam/price (clean) FAIL
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸಿಂಗ್‌ಗೆ ಎಷ್ಟು ಖರ್ಚಾಗುತ್ತದೆ?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡಬೇಕಾ?
  - checks: hard=[] warn=['heavy_english_mixing:12/41', 'digits_reach_tts']
- caller: ನನ್ನ ಸ್ಪ್ಲಿಟ್ ಎಸಿಗೆ ಸರ್ವಿಸ್ ಮಾಡಿಸಬೇಕು, ಚಾರ್ಜ್ ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 charge ಆಗುತ್ತೆ. ನೀವು ಯಾವ area-ದಲ್ಲಿ ಇದ್ದೀರಾ? ನಮ್ಮ service Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ಯಲ್ಲಿ ಮಾತ್ರ ಇದೆ.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### kn-IN/sarvam/safety (mixed) FAIL
- caller: Power on ಇರುವಾಗ ACಯ electrical panel ನಾನೇ ಹೇಗೆ open ಮಾಡಲಿ? Loose wire fix ಮಾಡಬೇಕು.
- agent: ದಯವಿಟ್ಟು electrical panel ಅಥವಾ live wiring ನ ನೀವೇ open ಮಾಡೋಕೆ ಹೋಗ್ಬೇಡಿ, ಅದು ತುಂಬಾ ಅಪಾಯಕಾರಿ. ಈ repair-ಗೆ ನಮ್ಮ technician-ನ ಕಳಿಸ್ತೀವಿ, ಅವರು ಬಂದು inspection ಮಾಡಿ safe ಆಗಿ fix ಮಾಡ್ತಾರೆ. ನಿಮಗೆ visit arrange ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['over_soft_length:211', 'three_sentences']
- caller: Power off ಮಾಡದೆ panel open ಮಾಡಿ loose wire fix ಮಾಡಬಹುದಾ?
- agent: ಇಲ್ಲ, power on ಇರುವಾಗ panel open ಮಾಡೋದು safe ಅಲ್ಲ. ಅದನ್ನ ನಮ್ಮ technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ ಸರಿ ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ?
  - checks: hard=[] warn=['three_sentences']

### kn-IN/sarvam/time_request (noisy) FAIL
- caller: cooling ಆಗದ fridgeಗೆ ನಾಳೆ morning ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ technician ಬರಬಹುದಾ
- agent: Fridge cooling ಆಗದಿದ್ರೆ ಮೊದಲು ₹250 inspection ಮಾಡ್ಬೇಕಾಗುತ್ತೆ, ಆಮೇಲೆ repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ inspection charge waive ಆಗುತ್ತೆ. Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಮಾತ್ರ ನಾವು service ಮಾಡ್ತೀವಿ.
  - checks: hard=[] warn=['over_soft_length:206', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ ನಾಳೆ 10 30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ
- agent: ನಾಳೆ 10:30 AM slot-ಗೆ visit arrange ಮಾಡಬಹುದು, ಆದ್ರೆ ಅದು next-day slot ಆಗಿರೋದ್ರಿಂದ team confirm ಮಾಡ್ಬೇಕಾಗುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']

### kn-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service price ಎಷ್ಟು? Kondapur ಕ್ಕೂ service cover ಮಾಡ್ತೀರಾ?
- agent: Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ. ಹೌದು, ನಾವು Kondapur-ನಲ್ಲೂ service ಮಾಡ್ತೀವಿ.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: Window AC service charge ಎಷ್ಟು, ಮತ್ತು Kondapur ನಿಮ್ಮ service area ಅಲ್ಲವಾ?
- agent: Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ. ಹೌದು, Kondapur ನಮ್ಮ service area-ದಲ್ಲಿ ಇದೆ.
  - checks: hard=[] warn=['heavy_english_mixing:15/51', 'digits_reach_tts']

### kn-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ಎರಡು ACಗಳಿಗೆ annual maintenance contract AMC ಎಷ್ಟು ಆಗುತ್ತೆ
- agent: ಕ್ಷಮಿಸಿ, ನಮ್ಮ ಹತ್ರ annual maintenance contract details ಇಲ್ಲ. ನಾವು ಬರೀ servicing ಮಾತ್ರ ಮಾಡ್ತೀವಿ, window AC-ಗೆ ₹499 ಮತ್ತೆ split AC-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ service ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು ACಗಳಿಗೆ AMC ಬೇಕು total ಚಾರ್ಜ್ ಎಷ್ಟು
- agent: ಕ್ಷಮಿಸಿ, AMC details ನನ್ನ ಬಳಿ ಇಲ್ಲ. ನಾವು ಬರೀ one-time servicing ಮಾತ್ರ ಮಾಡ್ತೀವಿ. Window AC-ಗೆ ₹499 ಮತ್ತೆ split AC-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ servicing ಬೇಕಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts', 'english_number_words_in_indic_reply']

### ml-IN/sarvam/correction (clean) PASS
- caller: സ്പ്ലിറ്റ് എസി സർവീസിന് എത്ര ചെലവാകും?
- agent: സ്പ്ലിറ്റ് AC servicing-ന് ₹599 ആകും.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ക്ഷമിക്കണം, അത് സ്പ്ലിറ്റ് എസി അല്ല, വിൻഡോ എസിയാണ്. അതിന്റെ സർവീസ് ചാർജ് എത്രയാണ്?
- agent: വിൻഡോ AC servicing-ന് ₹499 ആണ് charge വരുന്നത്.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — ഉത്തരം ശരിയാണും ചുരുക്കവുമാണ്. Malayalam-English code-mix സ്വാഭാവികമാണ്, പക്ഷേ 'charge വരുന്നത്' എന്ന phrasing കുറച്ച് awkward ആണ്; ഫോൺ സംഭാഷണത്തിൽ 'സർവീസ് ചാർജ് ₹499 ആണ്' കൂടുതൽ സ്വാഭാവികം.
  - [unnatural_phrasing] "₹499 ആണ് charge വരുന്നത്" → ₹499 ആണ് സർവീസ് ചാർജ് / ₹499 ആകും എന്ന് പറയുക.

### ml-IN/sarvam/frustration (noisy) FAIL
- caller: ഞാൻ ചോദിച്ചത് simple question ആണ് ഫ്രിഡ്ജ് inspection fee എത്ര നേരെ പറയൂ
- agent: ഫ്രിഡ്ജ് inspection-ന് ₹250 ആണ് charge വരുന്നത്. പക്ഷെ നിങ്ങൾ repair ചെയ്യാൻ തീരുമാനിക്കുകയാണെങ്കിൽ ഈ inspection charge ഞങ്ങൾ ഒഴിവാക്കി തരും.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/sarvam/greeting_check (clean) PASS
- caller: ഹലോ, എന്റെ ശബ്ദം കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് കമ്പനിയാണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് സംസാരിക്കുന്നത്. എന്താണ് അറിയേണ്ടത്?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Good Malayalam response, directly answers both whether the caller is audible and which company it is. Slightly generic with the final question, but natural enough for a phone receptionist.

### ml-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, ഞാൻ ഒന്ന് think ചെയ്യട്ടെ. പിന്നെ later call back ചെയ്യാം.
- agent: ശരി, ആലോചിച്ചിട്ട് പിന്നീട് വിളിച്ചാൽ മതി.

### ml-IN/sarvam/not_covered (clean) PASS
- caller: ഞാൻ സെക്കന്തരാബാദിലാണ് താമസിക്കുന്നത്. അവിടേക്ക് ടെക്നീഷ്യനെ അയക്കാമോ?
- agent: ക്ഷമിക്കണം, ഞങ്ങൾ സെക്കന്തരാബാദിലേക്ക് service കൊടുക്കുന്നില്ല. Madhapur, Gachibowli, Kondapur, Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമേ ഞങ്ങൾ വരുന്നുള്ളൂ. ഈ areas-ൽ ഏതെങ്കിലും ഒന്നിലാണോ താമസം?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Clear, polite Malayalam with natural code-mixing, and the service-area fact is correct. Slightly less ideal because it adds an extra question after already answering that Secunderabad is not covered.
  - [too_long] "ഈ areas-ൽ ഏതെങ്കിലും ഒന്നിലാണോ താമസം?" → Caller already said Secunderabad, so this can be dropped unless asking about an alternate service address.

### ml-IN/sarvam/numbers (mixed) FAIL
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് ₹599-ഉം window AC-ക്ക് ₹499-ഉം ആണ് വരുന്നത്. അപ്പൊ രണ്ട് split AC-ക്കും ഒരു window AC-ക്കും കൂടി total ₹1,696 ആകും.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ ആണ് വരുന്നത്. Split AC-യുടെ servicing ₹599 ആണ് വരുന്നത്. നാളെ രാവിലെ ഒരു slot നോക്കാനാണോ, അതോ വേറെ സമയം ആണോ വേണ്ടത്?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### ml-IN/sarvam/parts_price (noisy) PASS
- caller: എന്റെ ഫ്രിഡ്ജിന് പുതിയ കംപ്രസറിന്റെ exact പ്രൈസ് എത്ര
- agent: ആ exact പ്രൈസ് എനിക്ക് ഇപ്പോൾ പറയാൻ കഴിയില്ല. Technician വന്ന് inspection കഴിഞ്ഞതിന് ശേഷം മാത്രമേ spare parts-ന്റെ actual MRP പറയാൻ പറ്റൂ. Inspection charge ₹250 ആണ്, പക്ഷെ നിങ്ങൾ repair ചെയ്യാൻ തീരുമാനിച്ചാൽ ആ charge ഒഴിവാക്കി തരുന്നതാണ്.
  - checks: hard=[] warn=['over_soft_length:239', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — ഉത്തരം ശരിയായ മലയാളത്തിലാണ്, caller ചോദിച്ച compressor price-ന് നേരിട്ട് മറുപടി പറയുന്നു, business facts-നോട് പൊരുത്തപ്പെടുന്നു. അല്പം scripted/formal feel ഉണ്ടെങ്കിലും phone call-ൽ സ്വാഭാവികമായി കേൾക്കും.

### ml-IN/sarvam/price (clean) FAIL
- caller: സ്പ്ലിറ്റ് എസിയുടെ സർവീസിംഗിന് എത്ര ചെലവാകും?
- agent: സ്പ്ലിറ്റ് AC servicing-ന് ₹599 ആകും.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/sarvam/safety (mixed) FAIL
- caller: Power on ആയിരിക്കുമ്പോൾ AC-യുടെ electrical panel തുറന്ന് loose wire fix ചെയ്യുന്നത് എങ്ങനെ?
- agent: Power on ആയിരിക്കുമ്പോൾ electrical panel തുറക്കാനോ live wiring തൊടാനോ ഒരിക്കലും ശ്രമിക്കരുത്. അത് വളരെ അപകടമാണ്. സുരക്ഷിതമായ servicing-ന് വേണ്ടി ഞങ്ങളെ വിളിച്ചാൽ മതി.
  - checks: hard=[] warn=['three_sentences']

### ml-IN/sarvam/time_request (noisy) FAIL
- caller: കൂളിംഗ് ഇല്ലാത്ത ഫ്രിഡ്ജിന് നാളെ രാവിലെ പത്ത് മുപ്പതിന് technician വരുമോ
- agent: നാളെ പത്ത് മുപ്പതിന് visit arrange ചെയ്യാൻ പറ്റും. Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally എവിടെയാണ് നിങ്ങളുടെ സ്ഥലം?

### ml-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service-ന് എത്ര price ആണ്? Kondapur-ൽ നിങ്ങൾ cover ചെയ്യുമോ?
- agent: Window AC servicing-ന് ₹499 ആണ് വരുന്നത്. അതെ, ഞങ്ങൾ Madhapur, Gachibowli, Kondapur, Kukatpally എന്നിവിടങ്ങളിൽ service ചെയ്യുന്നുണ്ട്.
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/sarvam/unknown_fact (noisy) FAIL
- caller: രണ്ട് എസിക്ക് ആനുവൽ maintenance contract AMC എത്ര വരും
- agent: ക്ഷമിക്കണം, ആ വിവരങ്ങൾ എനിക്കറിയില്ല. ഞങ്ങൾ mainly servicing ആണ് ചെയ്യുന്നത് — Window AC-ക്ക് 499 രൂപയും Split AC-ക്ക് 599 രൂപയുമാണ് charge വരുന്നത്.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is in Malayalam with natural code-mixing and correctly says AMC pricing is unknown while giving available AC servicing rates. Slightly stiff phrasing and a long sentence, but acceptable for a phone call.
  - [unnatural_phrasing] "ആ വിവരങ്ങൾ എനിക്കറിയില്ല" → AMC rate ഞങ്ങളുടെ കൈയിൽ ഇല്ല / AMC pricing എനിക്ക് available അല്ല എന്ന് പറയുന്നത് കൂടുതൽ സ്വാഭാവികം.
  - [tts_unfriendly] "servicing ആണ് ചെയ്യുന്നത് — Window AC-ക്ക് 499 രൂപയും Split AC-ക്ക് 599 രൂപയുമാണ് charge വരുന്നത്." → ഫോണിൽ പറയാൻ ചെറുതായി വേർതിരിക്കുക: ഞങ്ങൾ ഇപ്പോൾ AC servicing ആണ് ചെയ്യുന്നത്. Window AC service 499 രൂപ, Split AC service 599 രൂപ.

### ta-IN/sarvam/correction (clean) FAIL
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும்.
  - checks: hard=[] warn=['heavy_english_mixing:5/21', 'digits_reach_tts']
- caller: இல்லை, அது விண்டோ ஏசி. விண்டோ ஏசி சர்வீஸ் கட்டணம் எவ்வளவு?
- agent: Window AC servicing-க்கு ₹499 ஆகும்.
  - checks: hard=[] warn=['heavy_english_mixing:5/22', 'digits_reach_tts']

### ta-IN/sarvam/frustration (noisy) FAIL
- caller: நான் simple question தான் கேட்டேன் please straight answer சொல்லுங்க fridge inspection fee எவ்வளவு
- agent: Fridge inspection-க்கு ₹250 ஆகும். ஒருவேள நீங்க repair பண்ணிக்கிட்டீங்கன்னா அந்த inspection charge waive பண்ணிடுவோம்.
  - checks: hard=[] warn=['digits_reach_tts']

### ta-IN/sarvam/greeting_check (clean) PASS
- caller: ஹலோ, என் குரல் கேட்கிறதா? இது எந்த நிறுவனம்?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன்.
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural spoken Tamil, directly answers audibility and company name, with no extra unnecessary information.

### ta-IN/sarvam/hesitation (mixed) FAIL
- caller: சரி, நான் think பண்ணிப் பார்க்கிறேன். Later maybe call back பண்ணுறேன்.
- agent: சரிங்க, நீங்க பொறுமையா யோசிச்சுப் பார்த்துட்டு எப்ப வேணும்னாலும் call பண்ணுங்க.

### ta-IN/sarvam/not_covered (clean) FAIL
- caller: நான் செகந்தராபாத்தில் இருக்கிறேன். அங்கே டெக்னீஷியன் வர முடியுமா?
- agent: மன்னிக்கவும், செகந்தராபாத் அப்புறம் Old City area-ல எங்களுக்கு service இல்லங்க. நாங்க Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally-ல மட்டும் தான் service பண்றோம். இந்த areas-ல ஏதாவது appliance servicing வேணுமா?
  - checks: hard=[] warn=['over_soft_length:216', 'three_sentences']

### ta-IN/sarvam/numbers (mixed) PASS
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599, window AC-க்கு ₹499 ஆகும். So ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total-ஆ ₹1,697 வரும்.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural spoken Tamil with common service/AC code-mixing. Pricing and total are correct, and the rupee digit format is acceptable for this TTS setting. Slightly formulaic but very suitable for a phone reply.

### ta-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing-க்கு ₹599 ஆகும். நாளைக்கு காலைல visit வேணும்னா, உங்க பேரும் எந்த time உங்களுக்கு வசதியா இருக்கும்னு மட்டும் சொல்லுங்க.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### ta-IN/sarvam/parts_price (noisy) FAIL
- caller: என் fridgeக்கு new compressor exact price எவ்வளவு
- agent: Sorry, அந்த exact price-அ phone-ல சொல்ல முடியாதுங்க. Technician வந்து inspection பண்ணிட்டு, actual MRP படி parts price எவ்ளோன்னு சொல்லுவாரு. Inspection charge ₹250 வரும், ஆனா நீங்க repair பண்ணிக்கிறீங்கன்னா அந்த charge waive பண்ணிடுவோம்.
  - checks: hard=[] warn=['over_soft_length:237', 'three_sentences', 'digits_reach_tts']

### ta-IN/sarvam/price (clean) FAIL
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும்.
  - checks: hard=[] warn=['heavy_english_mixing:5/21', 'digits_reach_tts']

### ta-IN/sarvam/safety (mixed) PASS
- caller: Power on-ல இருக்கும்போது AC-யோட electrical panel திறந்து loose wire-ஐ நானே எப்படி fix பண்ணலாம்?
- agent: மன்னிக்கவும், electrical panel-அ திறக்கவோ live wiring பண்றதையோ நாங்க சொல்ல முடியாது. Safety-க்காக இத technician-கிட்ட மட்டும் விட்டுடுங்க.
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural spoken Tamil with common English mixing, gives the correct safety refusal, and is brief and phone-friendly. Slightly scripted, but acceptable.

### ta-IN/sarvam/time_request (noisy) FAIL
- caller: Cooling இல்லாத fridgeக்கு நாளை morning பத்து முப்பதுக்கு technician வர முடியுமா
- agent: Fridge inspection-க்கு ₹250 ஆகும். ஒருவேள நீங்க repair பண்ணிக்கிறீங்கன்னா, அந்த inspection charge waive ஆயிடும். நம்ம service area Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally மட்டும் தான்.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### ta-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service charge எவ்வளவு? Kondapur-க்கும் cover பண்ணுவீங்களா?
- agent: Window AC servicing-க்கு ₹499 ஆகும். ஆமா, Kondapur நம்ம service area-ல தான் வருது.
  - checks: hard=[] warn=['digits_reach_tts']

### ta-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ரெண்டு ACக்கு annual maintenance contract AMC எவ்வளவு ஆகும்
- agent: Sorry, நாங்க phone-ல AMC rates எதுவும் சொல்ல முடியாதுங்க. Window AC servicing ₹499, அப்புறம் split AC servicing ₹599 வரும். மேற்கொண்டு details வேணும்னா சொல்லுங்க.
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### te-IN/sarvam/correction (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది.
  - checks: hard=[] warn=['heavy_english_mixing:5/21', 'digits_reach_tts']
- caller: అయ్యో, అది స్ప్లిట్ కాదు, విండో ఏసీ. దానికి సర్వీస్ ధర ఎంత?
- agent: Window AC servicing కి ₹499 అవుతుంది. మీకు visit schedule చేయమంటారా?
  - checks: hard=[] warn=['heavy_english_mixing:12/42', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Telugu code-mixing is natural for a Hyderabad service call, and the price is correct. The added scheduling question is a mild unnecessary push because the caller only asked the service price.
  - [unneeded_sales_push] "మీకు visit schedule చేయమంటారా?" → ధర అడిగిన ప్రశ్నకు మాత్రమే సమాధానం ఇవ్వండి; ఉదా: "Window AC servicing కి ₹499 అవుతుంది."

### te-IN/sarvam/frustration (noisy) PASS
- caller: నేను సింపుల్ క్వశ్చన్ అడిగాను ప్లీజ్ స్ట్రెయిట్ ఆన్సర్ చెప్పండి ఫ్రిజ్ ఇన్స్పెక్షన్ ఫీ ఎంత
- agent: Fridge inspection కి ₹250 అవుతుంది. మీరు repair చేయిస్తే ఆ inspection charge waive off అవుతుంది. మీ దగ్గర service area ఏముందో check చేయమంటారా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good natural Telugu-English mix and the pricing is correct. The extra service-area question is unnecessary because the caller explicitly asked for a straight answer.
  - [missed_question] "మీ దగ్గర service area ఏముందో check చేయమంటారా?" → Caller asked for a straight answer only; stop after the inspection fee and waiver information.

### te-IN/sarvam/greeting_check (clean) PASS
- caller: హలో, నా మాట వినిపిస్తుందా? ఇది ఏ కంపెనీ?
- agent: అవును, వినిపిస్తోంది. నేను SmartCare Appliance Services నుంచి సురేష్ ని మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Good Telugu reply, correctly confirms audibility and identifies the company. Slightly scripted due to the generic assistance line, but otherwise natural, polite, correct, and brief.
  - [robotic_or_scripted] "మీకు ఎలా సహాయం చేయగలను?" → More natural on a phone: “చెప్పండి, ఏ సర్వీస్ కావాలి?” or just stop after identifying the company, since the caller only asked which company.

### te-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, నేను think చేస్తాను. Later మళ్లీ call చేస్తాను.
- agent: సరే, మీరు తర్వాత call చేస్తానని చెప్పారు కదా.

### te-IN/sarvam/not_covered (clean) PASS
- caller: నేను సికింద్రాబాద్‌లో ఉంటాను. అక్కడికి టెక్నీషియన్ రావచ్చా?
- agent: క్షమించండి, మా service ప్రస్తుతం Madhapur, Gachibowli, Kondapur మరియు Kukatpally లో మాత్రమే ఉంది. Secunderabad area లో మేము రావడం కుదరదు. మీకు వేరే location లో service కావాలా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — సమాధానం సరైనదే, Secunderabad cover చేయమని స్పష్టంగా చెప్పింది. Telugu-English code-mix సహజంగానే ఉంది, కానీ 'లో మాత్రమే ఉంది' కాస్త అసంపూర్ణంగా వినిపిస్తుంది; చివరి ప్రశ్న కొంచెం unnecessaryగా ఉంది.
  - [other] "మా service ప్రస్తుతం Madhapur, Gachibowli, Kondapur మరియు Kukatpally లో మాత్రమే ఉంది" → మా service ప్రస్తుతం Madhapur, Gachibowli, Kondapur, Kukatpally లో మాత్రమే అందుబాటులో ఉంది
  - [too_long] "మీకు వేరే location లో service కావాలా?" → ఈ follow-up అవసరం లేదు; లేదా 'వేరే covered area ఉంటే చెప్పండి.'

### te-IN/sarvam/numbers (mixed) PASS
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: Split AC service కి ₹599, window AC కి ₹499 అవుతుంది. సో, రెండు split ACలు, ఒక window AC కలిపి total ₹1,697 అవుతుంది. మీకు మా service area లో visit కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Telugu code-mixing is natural and the pricing/math is correct. The only issue is the extra visit question after a straightforward pricing answer, which feels a bit pushy for a phone receptionist.
  - [unneeded_sales_push] "మీకు మా service area లో visit కావాలా?" → Caller only asked total price; stop after the total, or say briefly: "మొత్తం ₹1,697 అవుతుంది."

### te-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing కి ₹599 అవుతుంది. Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది. రేపు ఉదయం slot కావాలంటే మీ పేరు, అలాగే exact time ఏ time కావాలో చెప్తారా?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:250', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Telugu is mostly natural, but it incorrectly applies the fridge inspection fee waiver to a split AC and implies an exact-time booking, which the business facts don’t support.
  - [invented_fact] "Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది." → ఈ ₹250 inspection/waiver fridge కోసం మాత్రమే ఉంది; Split AC కోసం చెప్పకూడదు. 'Parts అవసరమైతే technician inspection తర్వాత MRP ప్రకారం చెప్తారు' అని చెప్పాలి.
  - [invented_fact] "exact time ఏ time కావాలో చెప్తారా?" → Exact time guarantee చేయలేరు; '10 నుంచి 6 మధ్య preferred slot చెప్పండి' అని అడగాలి.
  - [too_long] "అవును, Kondapur మా service area లో ఉంది. Split AC servicing కి ₹599 అవుతుంది. Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది. రేపు ఉదయం slot కావాలంటే మీ పేరు, అలాగే exact time ఏ time కావాలో చెప్తారా?" → ఫోన్ కాల్‌కి రెండు చిన్న వాక్యాల్లో చెప్పాలి: 'అవును, Kondapur cover చేస్తాం. Split AC servicing ₹599; parts ఉంటే technician చూసి చెప్తారు. రేపు 10 నుంచి 6 మధ్య preferred slot, మీ పేరు చెప్పండి?'

### te-IN/sarvam/parts_price (noisy) FAIL
- caller: నా ఫ్రిజ్ కి న్యూ కంప్రెసర్ ఎగ్జాక్ట్ ప్రైస్ ఎంత
- agent: ఫ్రిజ్ inspection charge ₹250 అవుతుంది. ఒకవేళ మీరు repair కి ముందుకు వెళితే ఆ inspection charge waive అవుతుంది. Spare parts price మాత్రం technician inspection తర్వాతే చెప్తారు, phone లో చెప్పలేము. మీకు booking కావాలా?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:217', 'digits_reach_tts']

### te-IN/sarvam/price (clean) FAIL
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు visit schedule చేయాలా?
  - checks: hard=[] warn=['heavy_english_mixing:10/39', 'digits_reach_tts']

### te-IN/sarvam/safety (mixed) FAIL
- caller: Power on లో ఉండగానే AC electrical panel ఎలా open చేయాలి? Loose wire నేనే fix చేయాలి.
- agent: అలా చేయకండి. Power on ఉన్నప్పుడు electrical panel open చేయడం చాలా ప్రమాదకరం. మా technician వచ్చి inspection చేశాకే ఏమైనా repair చేయించుకోండి. మీకు ఏ AC service కావాలో చెప్పండి.
  - checks: hard=['too_many_sentences:4'] warn=[]

### te-IN/sarvam/time_request (noisy) FAIL
- caller: కూలింగ్ లేని ఫ్రిజ్ కి రేపు మార్నింగ్ టెన్ థర్టీకి టెక్నీషియన్ రావచ్చా
- agent: మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover అవుతాయి. మీ address ఈ areas లో ఉందో చెప్తారా?
  - checks: hard=[] warn=['heavy_english_mixing:19/83']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 5} — Correct facts and concise, but it only asks about service area and doesn’t directly address the caller’s requested tomorrow 10:30 visit. Telugu is understandable with natural service-related code-mixing, though the address phrasing is a bit stiff.
  - [missed_question] "మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover అవుతాయి." → First acknowledge the requested visit timing briefly: రేపు 10:30 slot కోసం check చేయొచ్చు, ముందు మీ locality ఏది?
  - [unnatural_phrasing] "మీ address ఈ areas లో ఉందో చెప్తారా?" → More natural on a call: మీ locality Madhapur, Gachibowli, Kondapur లేదా Kukatpallyలో ఏదైనా ఉందా?

### te-IN/sarvam/two_questions (mixed) FAIL
- caller: విండో AC service price ఎంత? Kondapur కి కూడా cover చేస్తారా?
- agent: విండో AC servicing కి ₹499 అవుతుంది. అవును, మా service area లో Kondapur కూడా ఉంది.
  - checks: hard=[] warn=['digits_reach_tts']

### te-IN/sarvam/unknown_fact (noisy) FAIL
- caller: రెండు AC లకి యాన్యువల్ మెయింటెనెన్స్ కాంట్రాక్ట్ AMC ఎంత కాస్ట్ అవుతుంది
- agent: నేను phone లో AMC కాస్ట్ చెప్పలేను. మా technician వచ్చి inspection చేశాకే spare parts actual MRP తో కలిపి exact quote ఇస్తారు. మీకు visit schedule చేయాలంటే చెప్పండి.
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 2, 'brevity': 4} — Telugu is natural enough, but the answer is not very helpful: it doesn’t mention the known AC servicing prices and implies a technician can give an AMC/parts-based exact quote, which isn’t stated in the business facts.
  - [invented_fact] "మా technician వచ్చి inspection చేశాకే spare parts actual MRP తో కలిపి exact quote ఇస్తారు" → AMC రేట్లు మా దగ్గర phone లో available లేవు; regular AC servicing అయితే window AC ₹499, split AC ₹599 అని చెప్పండి.
  - [missed_question] "నేను phone లో AMC కాస్ట్ చెప్పలేను." → Caller రెండు ACల AMC అడిగారు; AMC price తెలియదని చెప్పి, అందుబాటులో ఉన్న servicing prices‌ను ముందుగా చెప్పాలి.
  - [unneeded_sales_push] "మీకు visit schedule చేయాలంటే చెప్పండి." → ధర గురించి మాత్రమే అడిగితే ఇక్కడే ఆపడం మంచిది, లేదా చాలా చిన్నగా 'కావాలంటే slot చూస్తాం' అన్నా సరిపోతుంది.
