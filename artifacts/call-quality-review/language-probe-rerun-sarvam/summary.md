# Language probe language-probe-rerun-sarvam

Schema `sim_c207b9bb1d8942929926552a92460710`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | sarvam | 0/12 | 3.56 | language_fit 2.08 |
| gu-IN | sarvam | 9/12 | 4.39 | human_naturalness 4.00 |
| hi-IN | sarvam | 7/12 | 4.17 | human_naturalness 3.92 |
| kn-IN | sarvam | 3/12 | 4.14 | human_naturalness 3.75 |
| ml-IN | sarvam | 5/12 | 4.38 | human_naturalness 4.00 |
| ta-IN | sarvam | 7/12 | 4.15 | human_naturalness 3.75 |
| te-IN | sarvam | 6/12 | 4.17 | human_naturalness 3.75 |

## Transcripts

### en-IN/sarvam/correction (clean) FAIL
- caller: स्प्लिट एसी की सर्विस का कितना शुल्क है?
- agent: Split AC servicing का charge 599 rupees है। क्या आपको visit book करवानी है?
  - checks: hard=['indic_script_in_english_call'] warn=['digits_reach_tts']
- caller: माफ़ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विस का कितना शुल्क है?
- agent: Window AC servicing का charge 499 rupees है। क्या मैं आपकी visit arrange करवा दूँ?
  - checks: hard=['indic_script_in_english_call'] warn=['digits_reach_tts']
- judge: {'language_fit': 3, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Factually correct and brief, but it is mostly Hinglish/Devanagari rather than Indian English, and it adds a booking prompt after a simple price question.
  - [wrong_language] "Window AC servicing का charge 499 rupees है।" → Caller is speaking Hindi/Hinglish, while target is Indian English; in Indian English say: “Window AC servicing is 499 rupees.”
  - [unneeded_sales_push] "क्या मैं आपकी visit arrange करवा दूँ?" → Since caller only asked the price, avoid immediately pushing booking; a softer English option: “If you’d like, I can also help book a visit.”

### en-IN/sarvam/frustration (noisy) FAIL
- caller: मैंने simple question पूछा सीधा answer चाहिए fridge inspection fee कितना
- agent: Fridge inspection की fee 250 rupees है। अगर आप repair के साथ आगे बढ़ते हैं, तो ये charge waive off हो जाएगा।
  - checks: hard=['indic_script_in_english_call'] warn=['digits_reach_tts']
- judge: {'language_fit': 3, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Factually correct, direct, polite, and brief. But it is mostly Hindi/Hinglish while the target language is Indian English.
  - [wrong_language] "Fridge inspection की fee 250 rupees है। अगर आप repair के साथ आगे बढ़ते हैं, तो ये charge waive off हो जाएगा।" → The requested language is Indian English, so say it fully in natural Indian English: “Fridge inspection is 250 rupees. If you go ahead with the repair, we’ll waive the inspection charge.”

### en-IN/sarvam/greeting_check (clean) FAIL
- caller: हैलो, मेरी आवाज़ आ रही है? यह कौन-सी कंपनी है?
- agent: हाँ, मेरी आवाज़ आ रही है। मैं Suresh बोल रहा हूँ, SmartCare Appliance Services से। बताइए, आज मैं आपकी क्या मदद करूँ?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences']
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The content is factually fine and brief, but it is in Hindi rather than the required Indian English. It also sounds a bit scripted with the standard help prompt after already answering the caller.
  - [wrong_language] "हाँ, मेरी आवाज़ आ रही है। मैं Suresh बोल रहा हूँ, SmartCare Appliance Services से।" → Caller context is in Hindi, but requested language is Indian English; say it in natural Indian English: “Yes, I can hear you. This is Suresh from SmartCare Appliance Services.”
  - [wrong_language] "बताइए, आज मैं आपकी क्या मदद करूँ?" → Use Indian English: “Please tell me, what do you need help with?”
  - [robotic_or_scripted] "बताइए, आज मैं आपकी क्या मदद करूँ?" → A phone receptionist would more directly answer the company question and then pause, e.g. “We do home appliance repairs in Hyderabad.”

### en-IN/sarvam/hesitation (mixed) FAIL
- caller: ठीक है, मैं इसको think करके शायद बाद में call back करूँगा।
- agent: ठीक है, कोई बात नहीं। जब भी आप ready हों, call कर लीजिएगा। नमस्कार।
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences']
- judge: {'language_fit': 2, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — The reply is polite, natural, brief, and contextually correct, but it is in Hindi/Hinglish rather than Indian English as specified.
  - [wrong_language] "ठीक है, कोई बात नहीं। जब भी आप ready हों, call कर लीजिएगा। नमस्कार।" → Expected Indian English, e.g. “Sure, no problem. Please call us back whenever you’re ready. Thank you.”

### en-IN/sarvam/not_covered (clean) FAIL
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका टेक्नीशियन यहाँ आ सकता है?
- agent: अभी हम सिकंदराबाद या Old City area में service नहीं देते हैं। हमारे coverage areas सिर्फ Madhapur, Gachibowli, Kondapur और Kukatpally हैं। क्या आप इनमें से किसी area में रहते हैं?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences']
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Factually correct and brief, but it is in Hindi/Hinglish rather than Indian English, so it fails the requested language. The follow-up question is a bit unnecessary after the caller already gave Secunderabad.
  - [wrong_language] "अभी हम सिकंदराबाद या Old City area में service नहीं देते हैं।" → The requested language is Indian English, so say it in English: “Sorry, we don’t service Secunderabad or Old City right now.”
  - [wrong_language] "हमारे coverage areas सिर्फ Madhapur, Gachibowli, Kondapur और Kukatpally हैं।" → Use Indian English: “We cover only Madhapur, Gachibowli, Kondapur and Kukatpally.”
  - [unneeded_sales_push] "क्या आप इनमें से किसी area में रहते हैं?" → Avoid an unnecessary follow-up after clearly saying Secunderabad is not covered; if needed: “If you have an address in those areas, we can arrange a visit there.”

### en-IN/sarvam/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC servicing पाँच सौ निन्यानवे rupees है, और window AC servicing चार सौ निन्यानवे rupees है। तो दो split AC और एक window AC का total एक हज़ार एक सौ निन्यानवे rupees आएगा। क्या आपको visit book करवानी है?
  - checks: hard=['indic_script_in_english_call'] warn=['over_soft_length:208', 'three_sentences']
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 1, 'helpfulness': 2, 'brevity': 4} — The main issue is a serious pricing error: the total should be 1,697 rupees, not 1,199. It also doesn’t match the requested Indian English language setting.
  - [wrong_language] "Split AC servicing पाँच सौ निन्यानवे rupees है..." → The requested language is Indian English; reply should be in natural Indian English, e.g. “Split AC servicing is 599 rupees each...”
  - [invented_fact] "total एक हज़ार एक सौ निन्यानवे rupees आएगा" → Correct total is 1,697 rupees: 2 × 599 + 499.
  - [unneeded_sales_push] "क्या आपको visit book करवानी है?" → For a pure pricing question, answer the total first and avoid pushing booking unless the caller asks.

### en-IN/sarvam/parts_price (noisy) FAIL
- caller: फ्रिज नया compressor का exact price कितना है
- agent: मुझे exact price नहीं पता, क्योंकि spare parts का charge actual MRP पर लगता है और technician inspection के बाद ही quote करता है। क्या मैं आपकी service request note कर दूँ?
  - checks: hard=['indic_script_in_english_call'] warn=[]
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Factually correct and brief, but it is in Hindi/Hinglish instead of Indian English, and the booking question is a bit pushy for a simple price query.
  - [wrong_language] "मुझे exact price नहीं पता..." → Caller used Hindi, but required language is Indian English; reply should be in natural Indian English.
  - [unneeded_sales_push] "क्या मैं आपकी service request note कर दूँ?" → For a price-only question, first answer and optionally mention inspection charge; avoid pushing booking unless caller asks.
  - [other] "technician inspection के बाद ही quote करता है" → In English: “The technician can quote it only after inspection.”

### en-IN/sarvam/price (clean) FAIL
- caller: स्प्लिट एसी की सर्विसिंग का कितना चार्ज है?
- agent: Split AC servicing का charge five hundred and ninety nine rupees है। क्या आपको visit book करवानी है?
  - checks: hard=['indic_script_in_english_call'] warn=[]
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The price is correct and the reply is brief, but it mixes Hindi despite the requested language being Indian English. The number readout is also a bit unnatural for spoken Indian English.
  - [wrong_language] "Split AC servicing का charge five hundred and ninety nine rupees है।" → Use Indian English, e.g. “Split AC servicing is 599 rupees.”
  - [number_or_time_readout] "five hundred and ninety nine rupees" → For phone TTS in Indian English, “five ninety-nine rupees” or “599 rupees” sounds more natural.
  - [wrong_language] "क्या आपको visit book करवानी है?" → Keep it in Indian English: “Would you like to book a visit?”

### en-IN/sarvam/safety (mixed) FAIL
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel कैसे खोलूँ?
- agent: मैं electrical panel खोलने या live wiring पर काम करने की सलाह नहीं दे सकता, क्योंकि यह काफी unsafe है। Safety के लिए, please unit को power off करके ही servicing करवाएं। क्या मैं आपकी AC servicing के लिए visit arrange कर दूँ?
  - checks: hard=['indic_script_in_english_call'] warn=['over_soft_length:224', 'three_sentences']
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — The safety advice is correct and helpful, but the reply is mostly Hindi/Hinglish while the target language is Indian English. It should be natural spoken Indian English for the phone call.
  - [wrong_language] "मैं electrical panel खोलने या live wiring पर काम करने की सलाह नहीं दे सकता" → The requested language is Indian English; say it fully in English, e.g. “Please don’t open the electrical panel or touch live wiring.”
  - [wrong_language] "क्योंकि यह काफी unsafe है" → Use Indian English, e.g. “It’s very unsafe.”
  - [wrong_language] "क्या मैं आपकी AC servicing के लिए visit arrange कर दूँ?" → Use English: “If you want, I can arrange an AC service visit.”
  - [unnatural_phrasing] "Safety के लिए, please unit को power off करके ही servicing करवाएं।" → In spoken Indian English: “For safety, please switch off the unit and let a technician handle it.”

### en-IN/sarvam/time_request (noisy) FAIL
- caller: टेक्नीशियन कल मॉर्निंग दस तीस पर आ सकता है फ्रिज कूलिंग नहीं कर रहा
- agent: ठीक है, समझ गया। कल सुबह दस तीस बजे का slot note कर लिया है। बस एक बात confirm कर दीजिए, आप Madhapur, Gachibowli, Kondapur या Kukatpally में से किस area में रहते हैं?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences']
- judge: {'language_fit': 1, 'human_naturalness': 3, 'register': 3, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — The reply is in Hindi/Hinglish despite the requested language being Indian English. It also sounds like the exact 10:30 slot is booked, which goes beyond the business facts; the slot should be noted as a preference pending confirmation.
  - [wrong_language] "ठीक है, समझ गया। कल सुबह दस तीस बजे का slot note कर लिया है।" → The required language is Indian English; say it in natural en-IN, e.g. “Okay, tomorrow 10:30 morning is preferred, but the team will confirm the slot.”
  - [invented_fact] "कल सुबह दस तीस बजे का slot note कर लिया है" → Do not confirm a fixed 10:30 slot. Facts say next-day slots are between 10 AM and 6 PM and the team should confirm; same-day/fixed slots are not guaranteed.
  - [missed_question] "बस एक बात confirm कर दीजिए" → Also collect the caller’s name and mention fridge inspection charge if relevant, instead of only asking locality.

### en-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service का कितना price है, और Kondapur में cover करते हैं क्या?
- agent: Window AC servicing का charge 499 rupees है। हाँ, हम Kondapur में service देते हैं। क्या आपको visit book करवानी है?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 2, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Factually correct, helpful, and short, but it does not match the requested Indian English language; it is mainly Hindi with English terms.
  - [wrong_language] "Window AC servicing का charge 499 rupees है। हाँ, हम Kondapur में service देते हैं। क्या आपको visit book करवानी है?" → The target is Indian English, but the reply is mostly Hindi/Hinglish. Say it in Indian English, e.g. “Window AC servicing is 499 rupees. Yes, we cover Kondapur. Would you like to book a visit?”

### en-IN/sarvam/unknown_fact (noisy) FAIL
- caller: दो एसी का annual maintenance contract AMC कितना चार्ज आएगा
- agent: देखिए, हम phone पर AMC plans या contract pricing share नहीं करते। हम सिर्फ servicing देते हैं, window AC के लिए 499 rupees और split AC के लिए 599 rupees। क्या आपको अभी servicing करवानी है?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 2, 'human_naturalness': 3, 'register': 3, 'correctness': 3, 'helpfulness': 3, 'brevity': 3} — The reply answers with available service prices, but it is in Hindi despite the requested Indian English, invents a policy about AMC pricing, and adds a slightly pushy booking question.
  - [wrong_language] "देखिए, हम phone पर AMC plans या contract pricing share नहीं करते।" → Caller is in Hindi, but target language is Indian English; reply should be in Indian English, not Devanagari Hindi.
  - [invented_fact] "हम phone पर AMC plans या contract pricing share नहीं करते।" → Facts do not say AMC plans exist or that pricing can't be shared; better say SmartCare only provides one-time servicing rates as listed, and AMC pricing isn't available.
  - [number_or_time_readout] "499 rupees और split AC के लिए 599 rupees" → In spoken Indian English say 'four ninety-nine rupees' and 'five ninety-nine rupees', or in Hindi context 'चार सौ निन्यानवे रुपये'.
  - [unneeded_sales_push] "क्या आपको अभी servicing करवानी है?" → After answering AMC pricing, avoid pushing; if needed ask softly, 'Would you like to book regular servicing for the two ACs?'

### gu-IN/sarvam/correction (clean) PASS
- caller: સ્પ્લિટ એસી સર્વિસનો ભાવ કેટલો છે?
- agent: સ્પ્લિટ AC servicingનો ખર્ચ 599 rupees છે. તમારે visit schedule કરાવવી છે?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: અરે, ખરેખર તો એ વિન્ડો એસી છે, સ્પ્લિટ નહીં. એની સર્વિસનો ભાવ કેટલો છે?
- agent: Window AC servicingનો ખર્ચ 499 rupees છે. તમારે visit schedule કરાવવી છે?
  - checks: hard=[] warn=['heavy_english_mixing:13/49', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સાચો અને ટૂંકો છે, પણ Gujaratiમાં થોડું English-heavy અને સ્ક્રિપ્ટેડ લાગે છે. ભાવનો સીધો જવાબ આપે છે, છતાં તરત scheduling પૂછવું થોડું sales-pushy લાગે છે.
  - [unnatural_phrasing] "Window AC servicingનો ખર્ચ 499 rupees છે." → વધુ સ્વાભાવિક: “વિન્ડો AC સર્વિસિંગ 499 રૂપિયા પડશે.”
  - [unneeded_sales_push] "તમારે visit schedule કરાવવી છે?" → ભાવ પૂછ્યો છે, તો ફક્ત ભાવ કહીને રોકાઈ શકે; અથવા નરમ રીતે “બુક કરાવવી હોય તો કહેજો.”

### gu-IN/sarvam/frustration (noisy) PASS
- caller: મેં સિમ્પલ સવાલ પૂછ્યો ફ્રિજ ઇન્સ્પેક્શન ફીનો સીધો આન્સર આપો
- agent: ફ્રિજ inspection નો charge 250 rupees છે. પણ જો તમે repair કરાવો, તો આ inspection charge માફ થઈ જશે. બીજું કંઈ પૂછવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સાચો અને ટૂંકો છે, અને ગુજરાતી સાથે સામાન્ય service/repair/inspection code-mix સ્વાભાવિક લાગે છે. છેલ્લો પ્રશ્ન થોડો અનાવશ્યક છે કારણ કે કૉલરે ખાસ સીધો જવાબ માગ્યો હતો.
  - [number_or_time_readout] "250 rupees" → ગુજરાતી TTS માટે 'બસો પચાસ રૂપિયા' અથવા કુદરતી રીતે 'ટુ ફિફ્ટી રૂપિયા' કહો; '250' લખાણ વાંચવામાં અડચણ પડી શકે.
  - [unneeded_sales_push] "બીજું કંઈ પૂછવું છે તમારે?" → કૉલરે સીધો જવાબ માગ્યો હતો, એટલે આ ઉમેરવું ટાળી શકાય: 'ફ્રિજ inspection નો charge બસો પચાસ રૂપિયા છે; repair કરાવો તો inspection charge માફ થઈ જશે.'

### gu-IN/sarvam/greeting_check (clean) PASS
- caller: હેલો, તમને મારો અવાજ સંભળાય છે? આ કઈ કંપની છે?
- agent: હા, અવાજ બરાબર આવે છે. હું SmartCare Appliance Servicesમાંથી સુરેશ બોલું છું. કહો, શું કામ હતું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Gujarati, directly confirms audibility and identifies the company. Polite, brief, and appropriate for a phone call.

### gu-IN/sarvam/hesitation (mixed) PASS
- caller: હું આના વિશે think કરીશ, maybe later call back કરીશ.
- agent: બરાબર, તમે શાંતિથી વિચારી લો. જ્યારે પણ call back કરવો હોય ત્યારે અમે અહીં જ છીએ. બીજું કોઈ કામ હતું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Gujarati natural છે, polite છે, અને facts સાથે કોઈ conflict નથી. Reply phone call માટે ટૂંકી છે, પણ caller clearly later call back કહ્યા પછી અંતે વધુ પૂછવું થોડું scripted લાગે છે.
  - [robotic_or_scripted] "બીજું કોઈ કામ હતું?" → Call end contextમાં આ થોડું unnecessary લાગે છે; બદલે 'ઠીક છે, ધન્યવાદ' કહીને બંધ કરો.

### gu-IN/sarvam/not_covered (clean) PASS
- caller: હું સિકંદરાબાદમાં રહું છું. શું તમારો ટેકનિશિયન અહીં આવી શકે?
- agent: માફ કરશો, અત્યારે અમે ફક્ત Madhapur, Gachibowli, Kondapur અને Kukatpally areaમાં જ service આપીએ છીએ. સિકંદરાબાદ અત્યારે અમારા service areaમાં આવતું નથી. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Gujarati is natural with acceptable urban code-mixing for area/service terms. Facts are correct and the answer is polite and concise. The final extra question is a bit appended/agent-like, but not a major issue.
  - [missed_question] "બીજું કંઈ જાણવું છે તમારે?" → Area question answered already; this add-on is okay but slightly unnecessary. Could end after saying Secunderabad is not covered, or say 'હમણાં આવવું શક્ય નથી.'

### gu-IN/sarvam/numbers (mixed) FAIL
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service 599 rupees અને window AC ની 499 rupees છે. એટલે બે split અને એક window AC નો total 1,697 rupees થશે. તમારે અત્યારે booking કરાવવું છે કે ખાલી information જોઈએ છે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબ સાચો છે અને ભાષા મોટાભાગે સ્વાભાવિક છે. કુલ રકમ યોગ્ય છે, પણ નંબર TTS માટે અનુકૂળ નથી અને અંતે બુકિંગનો પ્રશ્ન થોડો અનાવશ્યક લાગે છે.
  - [number_or_time_readout] "1,697 rupees" → TTS માટે 'સોળસો સત્તાણું રૂપિયા' અથવા 'one thousand six ninety-seven rupees' વધુ બોલચાલૂ રીતે કહો.
  - [unneeded_sales_push] "તમારે અત્યારે booking કરાવવું છે કે ખાલી information જોઈએ છે?" → કિંમતનો જવાબ આપ્યા પછી નરમ રીતે 'બુક કરાવવું હોય તો કહેજો' પૂરતું રાખો, અથવા પ્રશ્ન ન ઉમેરો.
  - [unnatural_phrasing] "booking કરાવવું છે" → ગુજરાતીમાં વધુ સ્વાભાવિક: 'બુકિંગ કરાવવું છે' અથવા 'બુક કરાવવું છે'.

### gu-IN/sarvam/parts_price (noisy) PASS
- caller: મારા ફ્રિજના નવા કમ્પ્રેસરનો એક્ઝેક્ટ પ્રાઇસ કેટલો
- agent: જુઓ, spare partsનો ભાવ અત્યારે phone પર કહી શકાય એમ નથી. Technician જ્યારે inspection કરશે ને, ત્યારે જ actual MRP પ્રમાણે તમને ભાવ જણાવશે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સ્વાભાવિક ગુજરાતી code-mixમાં છે અને factually સાચો છે: spare partsનો ભાવ phone પર ન આપવો અને technician inspection પછી actual MRP કહે એ બરાબર છે. છેલ્લો પ્રશ્ન થોડો વધારાનો લાગે છે, પણ મોટો issue નથી.
  - [unneeded_sales_push] "બીજું કંઈ જાણવું છે તમારે?" → આ કાઢી નાખો, અથવા જો જરૂરી હોય તો વધુ નરમ રીતે કહો: “Inspection કરાવવું હોય તો કહેજો.”

### gu-IN/sarvam/price (clean) PASS
- caller: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ કેટલો આવે?
- agent: સ્પ્લિટ AC servicing નો ખર્ચ 599 rupees થાય છે. બીજું કઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સાચો અને ટૂંકો છે, અને ગુજરાતી સાથે AC/servicing જેવી code-mixing સ્વાભાવિક છે. પરંતુ “599 rupees” TTS પર અપ્રાકૃતિક લાગી શકે છે અને છેલ્લો પ્રશ્ન થોડો અનાવશ્યક છે.
  - [number_or_time_readout] "599 rupees" → ગુજરાતીમાં બોલવામાં વધુ સ્વાભાવિક: “પાંચસો નવ્વાણું રૂપિયા” અથવા “ફાઇવ નાઇન્ટી નાઇન રૂપિયા”.
  - [unneeded_sales_push] "બીજું કઈ જાણવું છે તમારે?" → માહિતીનો સીધો જવાબ આપીને રોકાઈ જવું, અથવા વધુ નરમ રીતે: “બસ, સ્પ્લિટ AC સર્વિસિંગ પાંચસો નવ્વાણું રૂપિયા છે.”

### gu-IN/sarvam/safety (mixed) PASS
- caller: Power on હોય ત્યારે loose wire ઠીક કરવા ACનું electrical panel હું જાતે કેવી રીતે ખોલું?
- agent: માફ કરજો, પણ electrical panel ખોલવા કે live wiring કરવા માટે હું તમને સલાહ નહીં આપી શકું, એમાં safety risk છે. જો તમને AC માં કોઈ issue હોય, તો હું અમારા technician ની visit arrange કરી શકું છું. શું હું તમારી details લઈ શકું?
  - checks: hard=[] warn=['over_soft_length:226', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — જવાબ સલામત અને સાચો છે; live wiring/panel ખોલવાની સૂચના આપતો નથી અને technician visit ઓફર કરે છે. ગુજરાતી સાથે English mix સ્વાભાવિક છે, બસ છેલ્લો સવાલ થોડો generic/scripted લાગે છે.
  - [robotic_or_scripted] "શું હું તમારી details લઈ શકું?" → થોડું વધુ બોલચાલનું કરો: “જો તમે ઇચ્છો તો visit માટે તમારું નામ અને area લઈ લઉં?”

### gu-IN/sarvam/time_request (noisy) FAIL
- caller: મારું ફ્રિજ કૂલિંગ નથી કરતું ટેકનિશિયન કાલે મોર્નિંગ દસ ત્રીસે આવી શકે
- agent: સારું, ફ્રિજનું cooling નથી થતું એટલે કાલે 10:30 AM ની visit માટે હું તમારી details note કરી લઉં છું. તમારું નામ જણાવશો?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — જવાબ કુદરતી અને ઉપયોગી છે, પણ exact 10:30 visit તરીકે કહી દેવું થોડું misleading છે; preferred slot તરીકે note કરીને confirmation જણાવવું જોઈએ.
  - [number_or_time_readout] "10:30 AM" → TTS માટે 'સવારે સાડા દસ' કહો; અને slot confirm થશે એવું કહો.
  - [other] "કાલે 10:30 AM ની visit માટે" → Business facts મુજબ visits next-day slots between 10 AM and 6 PM છે, team confirm કરે છે; exact 10:30 પક્કું ન કહો.

### gu-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC serviceની price કેટલી છે, અને Kondapurમાં તમે cover કરો છો?
- agent: Window AC servicingનો ખર્ચ ₹499 છે. અને હા, અમે Kondapur area cover કરીએ છીએ. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Gujarati is natural with acceptable service-related code-mixing, and the price and Kondapur coverage are correct. The final extra question is a bit unnecessary for a direct pricing/area answer, but still sounds fairly human.
  - [unneeded_sales_push] "બીજું કંઈ જાણવું છે તમારે?" → Question can be omitted after directly answering, or say only if keeping the call open: “જો booking કરાવવી હોય તો કહેજો.”

### gu-IN/sarvam/unknown_fact (noisy) FAIL
- caller: બે એસી માટે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટ AMC કેટલામાં થાય
- agent: માફ કરશો, અત્યારે અમારી પાસે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટનો કોઈ ભાવ નથી. અમે ફક્ત servicing કરીએ છીએ, જેમાં Window AC માટે 499 rupees અને Split AC માટે 599 rupees charge છે. તમારે અત્યારે servicing કરાવવું છે?
  - checks: hard=[] warn=['over_soft_length:211', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — જવાબ સાચી દિશામાં છે અને AMC ના અજાણ્યા ભાવ બનાવતો નથી, પણ ગુજરાતી-અંગ્રેજી મિશ્રણ થોડું અણઘડ છે અને અંતે વેચાણ જેવી પૂછપરછ છે. ફોન પર વધુ સ્વાભાવિક રીતે per-AC servicing rates કહીને રોકાઈ શકાય.
  - [unnatural_phrasing] "કોઈ ભાવ નથી" → ‘AMC માટે rate available નથી’ અથવા ‘AMC અમે આપતા નથી’ વધુ સ્વાભાવિક છે.
  - [number_or_time_readout] "499 rupees અને Split AC માટે 599 rupees charge" → ગુજરાતીમાં ફોન પર ‘ચારસો નવ્વાણું રૂપિયા’ અને ‘પાંચસો નવ્વાણું રૂપિયા’ અથવા natural mix: ‘four ninety-nine રૂપિયા’ કહી શકાય; ‘499 rupees charge’ અણઘડ લાગે છે.
  - [robotic_or_scripted] "તમારે અત્યારે servicing કરાવવું છે?" → પ્રશ્ન થોડો pushy લાગે છે; ‘જો servicing કરાવવી હોય તો details લઈ લઉં’ પૂરતું છે.
  - [missed_question] "અમે ફક્ત servicing કરીએ છીએ" → કોલરે બે AC માટે AMC પૂછ્યું છે; સ્પષ્ટ કહો: ‘બે AC માટે AMC package નથી, per-visit servicing જ છે.’

### hi-IN/sarvam/correction (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च है?
- agent: Split AC servicing का charge 599 rupees है। क्या आपको visit book करवानी है?
  - checks: hard=[] warn=['heavy_english_mixing:12/49', 'digits_reach_tts']
- caller: माफ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विसिंग का कितना खर्च होगा?
- agent: Window AC servicing का charge 499 rupees है। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — जवाब सही, छोटा और सीधे सवाल का उत्तर देता है। बस अंग्रेज़ी शब्दों और अंक पढ़ने का अंदाज़ थोड़ा कम नैचुरल है।
  - [number_or_time_readout] "499 rupees" → फोन पर हिंदी में ज़्यादा प्राकृतिक: “चार सौ निन्यानवे रुपये” या “चार निन्यानवे रुपये”।
  - [unnatural_phrasing] "Window AC servicing का charge" → थोड़ा ज़्यादा बोलचाल वाला: “विंडो एसी की सर्विसिंग चार सौ निन्यानवे रुपये है।”

### hi-IN/sarvam/frustration (noisy) PASS
- caller: मैंने सिंपल क्वेश्चन पूछा था फ्रिज inspection fee का सीधा answer दीजिए
- agent: Fridge inspection की fee 250 rupees है। अगर आप repair करवाते हैं, तो ये charge waive off हो जाएगा। और कुछ जानना है आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब तथ्यात्मक और छोटा है, और caller के सवाल का सीधा जवाब देता है। आख़िर में अतिरिक्त सवाल थोड़ा unnecessary है क्योंकि caller ने specifically सीधा answer मांगा था; spoken Hindi में रुपये को शब्दों में बोलना बेहतर रहेगा.
  - [unneeded_sales_push] "और कुछ जानना है आपको?" → Caller ने सीधा answer मांगा था; इसे हटाकर सिर्फ fee और waiver बताइए.
  - [number_or_time_readout] "250 rupees" → TTS के लिए ज़्यादा natural: "ढाई सौ रुपये" या "दो सौ पचास रुपये" कहें.

### hi-IN/sarvam/greeting_check (clean) PASS
- caller: नमस्ते, क्या आपको मेरी आवाज़ सुनाई दे रही है? और यह कौन-सी कंपनी है?
- agent: हाँ, आवाज़ साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh हूँ। बताइए, आज किस चीज़ में help चाहिए आपको?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply सही जानकारी देता है और caller के दोनों सवालों का सीधे जवाब देता है। थोड़ा code-mixing ठीक है, लेकिन “किस चीज़ में help चाहिए” फोन पर हल्का अटपटा लगता है।
  - [unnatural_phrasing] "किस चीज़ में help चाहिए" → कहें: “बताइए, क्या मदद चाहिए?” या “किस appliance के लिए बात कर रहे हैं?”
  - [other] "SmartCare Appliance Services से Suresh हूँ" → पूरी तरह हिंदी में अधिक सहज: “मैं SmartCare Appliance Services से सुरेश बोल रहा हूँ।”

### hi-IN/sarvam/hesitation (mixed) PASS
- caller: ठीक है, मैं इस पर think करूँगा, शायद बाद में call back करूँ।
- agent: ठीक है, कोई बात नहीं। जब भी आपको ज़रूरत हो, आप call back कर लीजिएगा। अपना ख्याल रखिएगा।
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural, polite Hindi with common code-mixing, and it fits the caller’s intent without adding unnecessary sales pitch or questions.

### hi-IN/sarvam/not_covered (clean) PASS
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका technician यहाँ आ सकता है?
- agent: सिकंदराबाद में हमारी service अभी available नहीं है। हम सिर्फ Madhapur, Gachibowli, Kondapur और Kukatpally में ही service देते हैं। क्या आपका घर इनमें से किसी area में आता है?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Hindi code-mixing is natural and facts are correct. The reply is polite and concise, though the follow-up question sounds a little unnecessary because the caller already specified Secunderabad.
  - [missed_question] "क्या आपका घर इनमें से किसी area में आता है?" → Caller already said they live in Secunderabad; better end with: "अगर आपका कोई दूसरा address इन areas में हो तो बता दीजिए."

### hi-IN/sarvam/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing 599 rupees और window AC की 499 rupees है। तो दो split और एक window AC का total 1,797 rupees आएगा। क्या आप visit book करवाना चाहेंगे?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:26/95', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 1, 'helpfulness': 2, 'brevity': 4} — भाषा और टोन ठीक हैं, लेकिन मुख्य जवाब में टोटल गलत है, इसलिए correctness बहुत कम है।
  - [invented_fact] "total 1,797 rupees आएगा" → सही टोटल 1,697 रुपये है: दो split AC 1,198 रुपये + window AC 499 रुपये.
  - [number_or_time_readout] "1,797 rupees" → फोन पर साफ़ बोलें: “सोलह सौ सत्तानवे रुपये” या “1,697 रुपये” सही संख्या के साथ.
  - [unneeded_sales_push] "क्या आप visit book करवाना चाहेंगे?" → पहले सिर्फ़ कीमत का जवाब दें; अगर जोड़ना हो तो नरमी से: “अगर चाहें तो visit के लिए details ले सकता हूँ.”

### hi-IN/sarvam/parts_price (noisy) FAIL
- caller: मेरे फ्रिज के नए कम्प्रेसर का exact प्राइस कितना है
- agent: Fridge के spare parts की exact price phone पर बताना possible नहीं है। Technician inspection के बाद actual MRP के हिसाब से quote देगा। अगर आप repair करवाना चाहते हैं, तो inspection charge 250 rupees है, जो repair आगे बढ़ाने पर waive हो जाएगा। क्या आप visit book करवाना चाहेंगे?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:275', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — जवाब तथ्यात्मक रूप से सही है और Hindi-English code-mix ठीक है, लेकिन फोन कॉल के लिए थोड़ा लंबा और scripted लगता है। अंत में booking push थोड़ा unnecessary है, हालांकि पूरी तरह गलत नहीं है।
  - [too_long] "अगर आप repair करवाना चाहते हैं, तो inspection charge 250 rupees है, जो repair आगे बढ़ाने पर waive हो जाएगा। क्या आप visit book करवाना चाहेंगे?" → इसे छोटा करके कहें: “Inspection 250 रुपये है, repair करवाई तो waive हो जाएगा. चाहें तो visit book कर देता हूँ.”
  - [unneeded_sales_push] "क्या आप visit book करवाना चाहेंगे?" → कॉलर ने सिर्फ exact price पूछा था; हल्का विकल्प ठीक है, पर इसे ज्यादा स्वाभाविक बनाएं: “चाहें तो inspection visit book कर सकता हूँ.”
  - [unnatural_phrasing] "जो repair आगे बढ़ाने पर waive हो जाएगा" → ज़्यादा बोलचाल में: “repair करवाने पर ये charge waive हो जाएगा” या “repair करवाई तो 250 adjust/waive हो जाएगा.”

### hi-IN/sarvam/price (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च आता है?
- agent: Split AC servicing का charge 599 rupees है। बताइए, आपको किस area में service चाहिए?
  - checks: hard=[] warn=['heavy_english_mixing:15/54', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब तथ्यात्मक और छोटा है, लेकिन कीमत के तुरंत बाद area पूछना हल्का-सा pushy लगता है।
  - [number_or_time_readout] "599 rupees" → फोन पर हिंदी में ज़्यादा नैचुरल: “पाँच सौ निन्यानवे रुपये” या “फाइव नाइंटी नाइन रुपये”.
  - [unneeded_sales_push] "बताइए, आपको किस area में service चाहिए?" → पहले सिर्फ कीमत बता सकते थे; अगर आगे बढ़ना हो तो पूछें: “अगर बुक करना है, तो area बता दीजिए।”

### hi-IN/sarvam/safety (mixed) FAIL
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel मैं खुद कैसे खोलूँ?
- agent: मैं इसकी सलाह नहीं दे सकता। Live wiring या electrical panel खोलना dangerous है, इसलिए please खुद ऐसा मत कीजिएगा। अगर आपको servicing चाहिए तो मैं help कर सकता हूँ। क्या आपके पास कौन सा AC है, ये बता सकते हैं?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:207']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Reply is safe and mostly natural Hindi-English code-mix. It correctly refuses dangerous electrical guidance, but is a bit long for a phone response and the last question sounds awkward.
  - [too_long] "अगर आपको servicing चाहिए तो मैं help कर सकता हूँ। क्या आपके पास कौन सा AC है, ये बता सकते हैं?" → Safety warning के बाद छोटा रखें: 'AC में दिक्कत है तो technician visit book करवा सकता हूँ.'
  - [unnatural_phrasing] "क्या आपके पास कौन सा AC है, ये बता सकते हैं?" → ज़्यादा natural: 'आपके पास window AC है या split AC?'

### hi-IN/sarvam/time_request (noisy) FAIL
- caller: फ्रिज कूलिंग नहीं कर रहा technician कल मॉर्निंग दस तीस पर आ सकता है
- agent: Fridge की inspection charge 250 rupees है, लेकिन अगर आप repair करवाते हैं तो वो charge waive हो जाएगा। कल 10:30 AM का slot note कर लेता हूँ, बस अपना नाम बता दीजिए।
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Pricing part mostly correct, but the agent wrongly sounds like 10:30 is booked/confirmed even though slots are only next-day between 10 AM and 6 PM and team confirmation is needed. It also doesn’t collect locality, which is important because service is limited to certain areas.
  - [invented_fact] "कल 10:30 AM का slot note कर लेता हूँ" → कल की visits 10 से 6 के बीच होती हैं, लेकिन 10:30 confirm नहीं कर सकता; team confirm करेगी.
  - [missed_question] "बस अपना नाम बता दीजिए" → Visit के लिए नाम के साथ locality और fridge issue भी लेना चाहिए, और बताना चाहिए कि area covered हो तभी visit हो पाएगी.
  - [number_or_time_readout] "250 rupees" → फोन पर हिंदी में 'ढाई सौ रुपये' ज्यादा natural लगेगा.
  - [number_or_time_readout] "10:30 AM" → 'सुबह साढ़े दस' बोलना ज्यादा natural है.
  - [unnatural_phrasing] "inspection charge 250 rupees है" → 'फ्रिज inspection का charge ढाई सौ रुपये है' या 'फ्रिज देखने का charge ढाई सौ रुपये है' कहें.

### hi-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service का कितना price है, और क्या आप Kondapur cover करते हैं?
- agent: Window AC servicing का charge 499 rupees है। हाँ, हम Kondapur में service देते हैं। और कुछ जानना है आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही और छोटा है, कीमत और एरिया दोनों ठीक बताए गए हैं। भाषा थोड़ी code-mixed है जो चल सकती है, लेकिन '499 rupees' TTS में कम नैचुरल लगेगा और आख़िर का सवाल थोड़ा unnecessary है।
  - [number_or_time_readout] "499 rupees" → फोन पर हिंदी में ज़्यादा नैचुरल: "चार सौ निन्यानवे रुपये" या "चार नाइन्टी नाइन रुपये"।
  - [unneeded_sales_push] "और कुछ जानना है आपको?" → सीधे जवाब के बाद रुकना बेहतर है, या बहुत हल्का: "जी, Kondapur cover होता है।"

### hi-IN/sarvam/unknown_fact (noisy) FAIL
- caller: दो AC का annual maintenance contract AMC कितने का पड़ेगा
- agent: देखिए, हमारे यहाँ annual maintenance contract का कोई fixed package नहीं है। Window AC की servicing 499 rupees और split AC की 599 rupees है। आपको किस type के AC की servicing करवानी है?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:31/119', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब तथ्यात्मक रूप से सही है और बोलचाल की हिंदी में है। थोड़ा और सीधे दो AC के संदर्भ में जवाब देता तो ज़्यादा helpful होता।
  - [number_or_time_readout] "499 rupees और split AC की 599 rupees" → फोन पर हिंदी में 'चार सौ निन्यानवे रुपये' और 'पाँच सौ निन्यानवे रुपये' ज़्यादा नैचुरल लगेगा, या 'four ninety-nine rupees' अगर आम बोलचाल रखनी हो।
  - [other] "आपको किस type के AC की servicing करवानी है?" → कॉलर ने दो AC के AMC के बारे में पूछा है; बेहतर होगा पहले दो AC के हिसाब से servicing estimate बता दें और फिर पूछें: 'दोनों window हैं या split?'

### kn-IN/sarvam/correction (clean) PASS
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: ಸ್ಪ್ಲಿಟ್ AC servicing-ಗೆ 599 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಇಲ್ಲ, ಕ್ಷಮಿಸಿ, ಅದು ವಿಂಡೋ ಎಸಿ. ಅದಕ್ಕೆ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: ಓಹ್ ಸರಿ, ವಿಂಡೋ AC servicing-ಗೆ 499 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — ಉತ್ತರ factual ಆಗಿ ಸರಿಯಾಗಿದೆ ಮತ್ತು ಚಿಕ್ಕದಾಗಿದೆ. ಆದರೆ ಕನ್ನಡ ವಾಕ್ಯದಲ್ಲಿ “servicing” ಮತ್ತು “rupees” ಬದಲು “ಸರ್ವಿಸ್” ಮತ್ತು “ರೂಪಾಯಿ” ಹೆಚ್ಚು ಸಹಜ; ಕೊನೆಯಲ್ಲಿ ಹೆಚ್ಚುವರಿ ಪ್ರಶ್ನೆ ಅಗತ್ಯವಿಲ್ಲ.
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಿತ್ತಾ?" → ಬೆಲೆ ಕೇಳಿದ್ದಕ್ಕೆ ಉತ್ತರಿಸಿ ನಿಲ್ಲಿಸಬಹುದು: “ವಿಂಡೋ AC servicing-ಗೆ 499 rupees ಆಗುತ್ತೆ.”
  - [unnatural_phrasing] "AC servicing-ಗೆ 499 rupees" → ಸ್ವಲ್ಪ ಹೆಚ್ಚು ಸಹಜವಾಗಿ: “ವಿಂಡೋ AC ಸರ್ವಿಸ್‌ಗೆ 499 ರೂಪಾಯಿ ಆಗುತ್ತೆ.”

### kn-IN/sarvam/frustration (noisy) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ please straight answer ಕೊಡಿ fridge inspection fee ಎಷ್ಟು
- agent: Fridge inspection-ಗೆ 250 rupees ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ inspection charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay fridge inspectionಗೆ exact fee ಎಷ್ಟು straight ಆಗಿ ಹೇಳಿ
- agent: ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ sorry. Fridge inspection-ಗೆ exact fee 250 rupees. Repair ಮುಂದುವರಿಸಿದ್ರೆ ಈ charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada-English code-mix ಸಹಜವಾಗಿದೆ ಮತ್ತು fee ಸರಿಯಾಗಿದೆ. ಆದರೆ caller ನೇರ ಉತ್ತರ ಕೇಳಿದ್ದಾಗ apology ಮತ್ತು ಕೊನೆಯ ಪ್ರಶ್ನೆ ಸ್ವಲ್ಪ scripted ಆಗಿ ಕೇಳುತ್ತದೆ.
  - [robotic_or_scripted] "ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ sorry." → ಒಂದೇ apology ಸಾಕು; 'Sorry, fridge inspection fee 250 rupees.' ಅಂತ ನೇರವಾಗಿ ಹೇಳಿ.
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?" → Caller straight answer ಕೇಳಿರುವುದರಿಂದ ಇದನ್ನು ಬಿಡಿ.
  - [too_long] "Repair ಮುಂದುವರಿಸಿದ್ರೆ ಈ charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?" → ಮೊದಲು exact fee ಮಾತ್ರ ಹೇಳಿ; ಬೇಕಾದರೆ waiver ವಿಷಯವನ್ನು ಚಿಕ್ಕದಾಗಿ ಸೇರಿಸಿ, follow-up question ಬೇಡ.

### kn-IN/sarvam/greeting_check (clean) PASS
- caller: ಹಲೋ, ನನ್ನ ಮಾತು ಕೇಳಿಸುತ್ತಿದೆಯೇ? ಇದು ಯಾವ ಕಂಪನಿ?
- agent: ಹೌದು, ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸ್ತಾ ಇದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್ ಮಾತಾಡ್ತಿರೋದು. ನಿಮಗೆ ಏನು ಸಹಾಯ ಮಾಡಲಿ?
  - checks: hard=[] warn=['three_sentences']
- caller: ನಮಸ್ಕಾರ, ನೀವು ನನ್ನನ್ನು ಕೇಳಬಹುದೇ? ನಿಮ್ಮ ಕಂಪನಿಯ ಹೆಸರು ಏನು?
- agent: ಹೌದು, ಕೇಳಿಸ್ತಾ ಇದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮಗೆ ಯಾವ details ಬೇಕು?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is correct and brief, and it answers that the caller is audible and gives the company/name. Slightly mixed English “details” and English-script company name may sound less natural in Kannada TTS, but overall acceptable.
  - [unnatural_phrasing] "ನಿಮಗೆ ಯಾವ details ಬೇಕು?" → “ಯಾವ ಮಾಹಿತಿ ಬೇಕು?” ಅಥವಾ “ಏನು ತಿಳ್ಕೊಳ್ಳಬೇಕು?” ಎಂದು ಹೇಳಿ.
  - [other] "SmartCare Appliance Services" → ಕನ್ನಡ TTSನಲ್ಲಿ ಅಸಹಜವಾಗದಂತೆ “ಸ್ಮಾರ್ಟ್‌ಕೇರ್ ಅಪ್ಲಯನ್ಸ್ ಸರ್ವಿಸಸ್” ಎಂದು ಹೇಳುವುದು ಉತ್ತಮ.

### kn-IN/sarvam/hesitation (mixed) PASS
- caller: Okay, ನಾನು ಸ್ವಲ್ಪ think ಮಾಡಿ later ಮತ್ತೆ call ಮಾಡ್ತೀನಿ.
- agent: ಸರಿ, ತೊಂದ್ರೆ ಇಲ್ಲ. ನೀವು ಯಾವಾಗ ಬೇಕಾದ್ರೂ call ಮಾಡಬಹುದು. ಇನ್ನೇನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: ಹೌದು, ಈಗ ಬೇಡ. ನಾನು think ಮಾಡಿ maybe later call back ಮಾಡ್ತೀನಿ.
- agent: ಖಂಡಿತ, ತೊಂದ್ರೆ ಇಲ್ಲ. ನೀವು ಆರಾಮಾಗಿ ಯೋಚಿಸಿ ಆಮೇಲೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Kannada with acceptable English code-mixing for a Hyderabad service call. Polite, brief, and directly closes the call. Slightly generic, but still something a human receptionist could say.

### kn-IN/sarvam/not_covered (clean) FAIL
- caller: ನಾನು ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದ್ದೇನೆ. ಅಲ್ಲಿ ಟೆಕ್ನಿಷಿಯನ್ ಬರಬಹುದೇ?
- agent: ಕ್ಷಮಿಸಿ, ಸಿಕಂದರಾಬಾದ್ ಮತ್ತು ಓಲ್ಡ್ ಸಿಟಿಗೆ ನಾವು service ಕೊಡಲ್ಲ. ನಮ್ಮ service area ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ. ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: ನನ್ನ ಮನೆ ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದೆ, ನಿಮ್ಮ ಸರ್ವಿಸ್ ಅಲ್ಲಿ ಲಭ್ಯವಿದೆಯೇ?
- agent: ಇಲ್ಲ, ಸಿಕಂದರಾಬಾದ್ ಕವರ್ ಆಗಲ್ಲ. ನಮ್ಮ service Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ನಲ್ಲಿ ಮಾತ್ರ ಇದೆ. ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — Factually correct and mostly natural Kannada-English code-mix, but it repeats the same area question unnecessarily after the caller clearly said Secunderabad.
  - [missed_question] "ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?" → Caller has already said their home is in Secunderabad, so don’t ask again. Say: “ಹೀಗಾಗಿ ಅಲ್ಲಿ ಟೆಕ್ನಿಷಿಯನ್ ಕಳುಹಿಸಲು ಆಗಲ್ಲ.”
  - [robotic_or_scripted] "ಇಲ್ಲ, ಸಿಕಂದರಾಬಾದ್ ಕವರ್ ಆಗಲ್ಲ. ನಮ್ಮ service Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ನಲ್ಲಿ ಮಾತ್ರ ಇದೆ." → Slightly soften it for a phone call: “ಇಲ್ಲ ಸರ್/ಮ್ಯಾಡಂ, ಸಿಕಂದರಾಬಾದ್‌ಗೆ ನಮ್ಮ service ಇಲ್ಲ. ನಾವು Madhapur, Gachibowli, Kondapur, Kukatpally ಮಾತ್ರ cover ಮಾಡ್ತೀವಿ.”

### kn-IN/sarvam/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC service-ಗೆ 599 rupees ಆಗುತ್ತೆ, window AC-ಗೆ 499 rupees. So, ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC-ಗೆ total 1,697 rupees ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:26/101', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC-ಗೆ 599 rupees ಅಂತೆ, so ಒಟ್ಟು 1,198 rupees ಆಗುತ್ತೆ. window AC service-ಗೆ 499 rupees ಸೇರಿಸಿ, final total 1,697 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — ಗಣನೆ ಸರಿಯಾಗಿದೆ ಮತ್ತು ಅರ್ಥವಾಗುತ್ತದೆ, ಆದರೆ ಮಾತಿನ ಹರಿವು ಸ್ವಲ್ಪ scripted/ಲೆಕ್ಕಾಚಾರ ಓದಿದಂತೆ ಇದೆ. ಚಿಕ್ಕದಾಗಿ ಒಟ್ಟು ಮೊತ್ತವನ್ನು ನೇರವಾಗಿ ಹೇಳಿದರೆ ಹೆಚ್ಚು ಸಹಜವಾಗುತ್ತಿತ್ತು.
  - [unnatural_phrasing] "599 rupees ಅಂತೆ" → “ಒಂದಕ್ಕೆ 599 ರೂಪಾಯಿ” ಎಂದು ಹೇಳಿ; “ಅಂತೆ” ಇಲ್ಲಿ ಸರಿಯಲ್ಲ.
  - [too_long] "ಎರಡು split AC-ಗೆ 599 rupees ಅಂತೆ, so ಒಟ್ಟು 1,198 rupees ಆಗುತ್ತೆ. window AC service-ಗೆ 499 rupees ಸೇರಿಸಿ, final total 1,697 rupees ಆಗುತ್ತೆ." → ಸರಳವಾಗಿ: “ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service ಒಟ್ಟು 1,697 ರೂಪಾಯಿ ಆಗುತ್ತೆ.”
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?" → ಪ್ರಶ್ನೆಗೆ ಉತ್ತರಿಸಿ ನಿಲ್ಲಬಹುದು, ಅಥವಾ “ಇಷ್ಟೇ service charge, parts ಬೇಕಾದ್ರೆ extra.” ಎಂಬ ಉಪಯುಕ್ತ ಮಾಹಿತಿ ಮಾತ್ರ ಸೇರಿಸಿ.
  - [number_or_time_readout] "1,198 rupees / 1,697 rupees" → TTS-friendly ಆಗಿ “ಒಂದು ಸಾವಿರ ನೂರ ತೊಂಬತ್ತೆಂಟು ರೂಪಾಯಿ” ಮತ್ತು “ಒಂದು ಸಾವಿರ ಆರು ನೂರ ತೊಂಬತ್ತೇಳು ರೂಪಾಯಿ” ಎಂದು ಹೇಳುವುದು ಉತ್ತಮ.

### kn-IN/sarvam/parts_price (noisy) FAIL
- caller: ನನ್ನ fridgeಗೆ new compressor ಹಾಕೋಕೆ exact price ಎಷ್ಟು
- agent: ಕ್ಷಮಿಸಿ, exact price phone-ನಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ actual MRP ಪ್ರಕಾರ spare parts price ಹೇಳ್ತಾರೆ. Fridge inspection charge 250 rupees ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['over_soft_length:242', 'three_sentences', 'digits_reach_tts']
- caller: fridge ಹೊಸ compressor total price exact ಆಗಿ ಹೇಳಿ
- agent: ಕ್ಷಮಿಸಿ, exact price ಈಗ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ actual MRP price ಹೇಳ್ತಾರೆ. Inspection charge 250 rupees ಇದೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಅದು free ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:220', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Factually correct and mostly natural Kannada-English service-call code mixing, but a little repetitive and adds an unnecessary booking prompt after a direct pricing question.
  - [too_long] "ಕ್ಷಮಿಸಿ, exact price ಈಗ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ actual MRP price ಹೇಳ್ತಾರೆ. Inspection charge 250 rupees ಇದೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಅದು free ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?" → Repeated caller’s question can be answered a bit shorter: “Exact compressor price inspection ಆದ್ಮೇಲೇ ಹೇಳ್ತಾರೆ. Fridge inspection 250 rupees; repair ಮಾಡಿಸಿದ್ರೆ waive ಆಗುತ್ತೆ.”
  - [unneeded_sales_push] "ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?" → Since caller asked only for exact price again, avoid appending scheduling question unless they show interest.
  - [unnatural_phrasing] "actual MRP price" → Use either “actual MRP” or “MRP ಪ್ರಕಾರ price”; not both together.

### kn-IN/sarvam/price (clean) FAIL
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸಿಂಗ್‌ಗೆ ಎಷ್ಟು ಖರ್ಚಾಗುತ್ತದೆ?
- agent: Split AC servicing-ಗೆ 599 rupees ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['heavy_english_mixing:12/43', 'digits_reach_tts']
- caller: ನನ್ನ ಸ್ಪ್ಲಿಟ್ ಎಸಿಗೆ ಸರ್ವಿಸ್ ಮಾಡಿಸಬೇಕು, ಚಾರ್ಜ್ ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ 599 rupees charge ಆಗುತ್ತೆ. ನಿಮ್ಮ area ಯಾವುದು ಅಂತ ಹೇಳ್ತೀರಾ? Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಮಾತ್ರ ನಾವು service ಕೊಡ್ತೀವಿ.
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:32/107', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is factually correct and mostly natural Kannada-English code-mix for an urban Hyderabad service call. It answers the price first and then asks for area, which is appropriate since the caller wants service. Minor issue is the mixed numeric readout and slightly stiff area sentence.
  - [number_or_time_readout] "599 rupees" → Kannada TTSಗೆ ಹೆಚ್ಚು ಸಹಜವಾಗಿ “ಐನೂರ ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ” ಅಥವಾ “ಫೈವ್ ನೈನ್ಟಿ ನೈನ್ ರೂಪಾಯಿ” ಎಂದು ಹೇಳಿ.
  - [unnatural_phrasing] "Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಮಾತ್ರ ನಾವು service ಕೊಡ್ತೀವಿ." → ಕನ್ನಡ ಮಾತಿನಲ್ಲಿ ಹೆಚ್ಚು ಸಹಜವಾಗಿ: “ನಾವು Madhapur, Gachibowli, Kondapur, Kukatpally ಏರಿಯಾಗಳಲ್ಲಿ ಮಾತ್ರ ಸರ್ವಿಸ್ ಕೊಡ್ತೀವಿ.”

### kn-IN/sarvam/safety (mixed) FAIL
- caller: Power on ಇರುವಾಗ ACಯ electrical panel ನಾನೇ ಹೇಗೆ open ಮಾಡಲಿ? Loose wire fix ಮಾಡಬೇಕು.
- agent: ದಯವಿಟ್ಟು electrical panel ಅಥವಾ live wiring ನ ನೀವೇ open ಮಾಡೋಕೆ ಹೋಗ್ಬೇಡಿ, ಅದು ತುಂಬಾ ಅಪಾಯ. ನಮ್ಮ technician ಬಂದು inspection ಮಾಡಿ safe ಆಗಿ ಸರಿ ಮಾಡಿಕೊಡ್ತಾರೆ. ನಿಮಗೆ ಯಾವ AC-ಗೆ service ಬೇಕಿತ್ತು? Window ಅಥವಾ split AC-ಯಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:210']
- caller: Power off ಮಾಡದೆ panel open ಮಾಡಿ loose wire fix ಮಾಡಬಹುದಾ?
- agent: ಇಲ್ಲ, power on ಇರುವಾಗ panel open ಮಾಡೋದು safe ಅಲ್ಲ. ನಮ್ಮ technician inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ ಎಲ್ಲಾ ಸರಿ ಮಾಡ್ತಾರೆ. ನಿಮ್ಮದು window AC ಅಥವಾ split AC ಯಾವುದು ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ಉತ್ತರ ಸುರಕ್ಷಿತವಾಗಿ ಸರಿಯಾಗಿದೆ ಮತ್ತು Kannada-English code-mix ಸಹಜವಾಗಿದೆ. ಆದರೆ caller ಕೇಳಿದ್ದು dangerous action ಮಾಡಬಹುದಾ ಅನ್ನೋದು; ಅದಕ್ಕೆ ನೇರವಾಗಿ ಹೇಳಿ ನಿಲ್ಲಿಸಿದರೆ ಇನ್ನಷ್ಟು ಮಾನವೀಯವಾಗುತ್ತಿತ್ತು, appliance type ಕೇಳೋದು ಸ್ವಲ್ಪ sales/booking push ಆಗಿ ಕೇಳಿಸುತ್ತದೆ.
  - [unneeded_sales_push] "ನಿಮ್ಮದು window AC ಅಥವಾ split AC ಯಾವುದು ಅಂತ ಹೇಳ್ತೀರಾ?" → Caller safety questionಗೆ ಉತ್ತರಿಸಿದ ಮೇಲೆ, visit ಬೇಕಿದ್ದರೆ ಮಾತ್ರ ವಿವರ ಕೇಳಿ; e.g. "ಬೇಕಿದ್ದರೆ technician visit book ಮಾಡಬಹುದು."
  - [unnatural_phrasing] "ನಮ್ಮ technician inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ ಎಲ್ಲಾ ಸರಿ ಮಾಡ್ತಾರೆ." → ಸ್ವಲ್ಪ natural ಆಗಿ: "ನಮ್ಮ technician ಬಂದು check ಮಾಡಿ safe ಆಗಿ repair ಮಾಡ್ತಾರೆ."

### kn-IN/sarvam/time_request (noisy) FAIL
- caller: cooling ಆಗದ fridgeಗೆ ನಾಳೆ morning ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ technician ಬರಬಹುದಾ
- agent: Fridge cooling ಆಗದಿದ್ರೆ, inspection charge 250 rupees ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ನಮ್ಮ service Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally-ಗೆ ಮಾತ್ರ ಇರೋದು, so ನಾಳೆ 10:30 AM slot-ಗೆ visit arrange ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['over_soft_length:267', 'three_sentences', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ ನಾಳೆ 10 30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ
- agent: ಹೌದು, ನಾಳೆ 10:30 AM-ಗೆ visit arrange ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 4, 'brevity': 5} — Mostly natural Kannada-English mix and brief, but it over-confirms an exact appointment slot instead of saying it can be requested/confirmed by the team.
  - [invented_fact] "ನಾಳೆ 10:30 AM-ಗೆ visit arrange ಮಾಡಬಹುದು" → Facts say next-day slots are between 10 AM and 6 PM and team confirms; don't promise the exact slot. Say: "ನಾಳೆ 10:30 slot request ಹಾಕಬಹುದು/ತಂಡ confirm ಮಾಡ್ತಾರೆ."
  - [number_or_time_readout] "10:30 AM-ಗೆ" → For spoken Kannada TTS, say "ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ" or "ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ" instead.

### kn-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service price ಎಷ್ಟು? Kondapur ಕ್ಕೂ service cover ಮಾಡ್ತೀರಾ?
- agent: Window AC servicing-ಗೆ 499 rupees ಆಗುತ್ತೆ. ಹೌದು, ನಾವು Kondapur-ಗೂ service ಮಾಡ್ತೀವಿ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: Window AC service charge ಎಷ್ಟು, ಮತ್ತು Kondapur ನಿಮ್ಮ service area ಅಲ್ಲವಾ?
- agent: Window AC servicing-ಗೆ 499 rupees ಆಗುತ್ತೆ. ಹೌದು, Kondapur ನಮ್ಮ service area-ದಲ್ಲಿ ಬರುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ಉತ್ತರ ಸರಿಯಾದದ್ದು ಮತ್ತು Kannada-English mix ಸಹಜವಾಗಿದೆ. ಆದರೆ ಕೊನೆಯ ಹೆಚ್ಚುವರಿ ಪ್ರಶ್ನೆ ಅಗತ್ಯವಿಲ್ಲ, ಮತ್ತು ಸಂಖ್ಯೆಯ ಬರವಣಿಗೆ TTS ನಲ್ಲಿ ಸ್ವಲ್ಪ ಅಸಹಜವಾಗಿ ಕೇಳಿಸಬಹುದು.
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?" → ಇದನ್ನು ಬಿಡಬಹುದು, ಅಥವಾ ಹೆಚ್ಚು ಸಹಜವಾಗಿ: “ಇಷ್ಟೇ charge, Kondapur cover ಆಗುತ್ತೆ.”
  - [number_or_time_readout] "499 rupees" → TTSಗಾಗಿ ಕನ್ನಡದಲ್ಲಿ “ನಾಲ್ಕು ನೂರು ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ” ಅಥವಾ ಮಾತಿನಲ್ಲಿ ಸಹಜವಾಗಿ “four ninety nine rupees” ಎಂದು ಬರೆಯುವುದು ಉತ್ತಮ.

### kn-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ಎರಡು ACಗಳಿಗೆ annual maintenance contract AMC ಎಷ್ಟು ಆಗುತ್ತೆ
- agent: ಕ್ಷಮಿಸಿ, ನಮ್ಮಲ್ಲಿ annual maintenance contract ಬಗ್ಗೆ ಮಾಹಿತಿ ಇಲ್ಲ. ನಾವು ಬರೀ servicing ಮಾತ್ರ ಮಾಡ್ತೀವಿ, window AC ಗೆ 499 rupees ಮತ್ತೆ split AC ಗೆ 599 rupees ಆಗುತ್ತೆ. ನಿಮಗೆ servicing ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು ACಗಳಿಗೆ AMC ಬೇಕು total ಚಾರ್ಜ್ ಎಷ್ಟು
- agent: ಕ್ಷಮಿಸಿ, AMC details ನನ್ನ ಬಳಿ ಇಲ್ಲ. ನಾವು ಬರೀ one-time servicing ಮಾಡ್ತೀವಿ, window AC ಗೆ 499 rupees ಮತ್ತೆ split AC ಗೆ 599 rupees ಆಗುತ್ತೆ. ನಿಮಗೆ servicing book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — ಉತ್ತರ factual ಆಗಿ ಸರಿಯಿದೆ ಮತ್ತು ಕನ್ನಡ code-mix ಒಟ್ಟಾರೆ ಸರಿ. ಆದರೆ caller ಎರಡನೇ ಬಾರಿ AMC total ಕೇಳಿದಾಗ booking push ಸ್ವಲ್ಪ ಬೇಡದಂತೆ ಬರುತ್ತದೆ; phrasing ಕೂಡ ಸ್ವಲ್ಪ scripted.
  - [missed_question] "ನಿಮಗೆ servicing book ಮಾಡ್ಬೇಕಾ?" → Caller AMC total ಕೇಳುತ್ತಿದ್ದಾರೆ; ಮೊದಲು AMC ಇಲ್ಲ/ಮಾಹಿತಿ ಇಲ್ಲ ಎಂದು ಹೇಳಿ, ಬೇಕಿದ್ದರೆ one-time service rate ಮಾತ್ರ ಹೇಳಿ. Booking ಪ್ರಶ್ನೆ ಬೇಕಾದರೆ ಮೃದುವಾಗಿ optional ಆಗಿರಲಿ.
  - [unnatural_phrasing] "499 rupees ಮತ್ತೆ split AC ಗೆ 599 rupees" → ಕನ್ನಡದಲ್ಲಿ ಹೆಚ್ಚು ಸಹಜವಾಗಿ: “ವಿಂಡೋ ACಗೆ 499 ರೂಪಾಯಿ, ಸ್ಪ್ಲಿಟ್ ACಗೆ 599 ರೂಪಾಯಿ.”
  - [robotic_or_scripted] "ಕ್ಷಮಿಸಿ, AMC details ನನ್ನ ಬಳಿ ಇಲ್ಲ." → ಹಿಂದೆಯೇ ಇದೇ ಮಾತು ಹೇಳಿದ್ದರಿಂದ ಸ್ವಲ್ಪ ಮಾನವೀಯವಾಗಿ: “AMC ನಾವು ಮಾಡಲ್ಲ/ಅದರ rate ಇಲ್ಲ ಸರ್.”

### ml-IN/sarvam/correction (clean) PASS
- caller: സ്പ്ലിറ്റ് എസി സർവീസിന് എത്ര ചെലവാകും?
- agent: Split AC servicing-ന് 599 rupees ആകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ക്ഷമിക്കണം, അത് സ്പ്ലിറ്റ് എസി അല്ല, വിൻഡോ എസിയാണ്. അതിന്റെ സർവീസ് ചാർജ് എത്രയാണ്?
- agent: Window AC servicing-ന് 499 rupees ആണ് charge വരുന്നത്. വേറെ എന്തെങ്കിലും details അറിയണോ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct price and brief, but the English-heavy phrasing is a bit less natural, and the extra follow-up is not needed for a direct pricing answer.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും details അറിയണോ?" → Asked price was answered; better end with just “Window AC servicing-ന് 499 രൂപയാണ്.” or a softer “ബുക്കിംഗ് വേണമെങ്കിൽ പറയൂ.” only if appropriate.
  - [unnatural_phrasing] "499 rupees ആണ് charge വരുന്നത്" → More natural Malayalam phone phrasing: “499 രൂപയാണ്” or “സർവീസ് ചാർജ് 499 രൂപയാണ്.”

### ml-IN/sarvam/frustration (noisy) PASS
- caller: ഞാൻ ചോദിച്ചത് simple question ആണ് ഫ്രിഡ്ജ് inspection fee എത്ര നേരെ പറയൂ
- agent: ഫ്രിഡ്ജ് inspection-ന് 250 rupees ആണ് charge. പക്ഷേ, repair ചെയ്യാൻ തീരുമാനിച്ചാൽ ഈ fee waive off ആകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Mostly natural Malayalam with common service-call English mixing, and the pricing/waiver facts are correct. The only issue is the unnecessary extra question after a caller specifically asked for a direct answer.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Caller asked for a straight price; end after the fee/waiver information without adding a follow-up question.

### ml-IN/sarvam/greeting_check (clean) PASS
- caller: ഹലോ, എന്റെ ശബ്ദം കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് കമ്പനിയാണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് സംസാരിക്കുന്നത്. എന്താണ് അറിയേണ്ടത്?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — സ്വാഭാവികവും ചുരുക്കവുമായ മറുപടി. കമ്പനിയുടെ പേര് ശരിയായി പറയുന്നു, caller ചോദിച്ചതിന് നേരിട്ട് ഉത്തരം നൽകുന്നു. ചെറിയതായി 'എന്താണ് അറിയേണ്ടത്?' കുറച്ച് generic ആണെങ്കിലും ഫോൺ സംഭാഷണത്തിൽ സ്വാഭാവികമാണ്.

### ml-IN/sarvam/hesitation (mixed) PASS
- caller: Okay, ഞാൻ ഒന്ന് think ചെയ്യട്ടെ. പിന്നെ later call back ചെയ്യാം.
- agent: ശരി, ആലോചിച്ചിട്ട് പിന്നീട് വിളിച്ചാൽ മതി. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Malayalam response for ending or pausing the call. It is polite, brief, and fits the caller’s statement. The follow-up question is acceptable here, though a very human receptionist might simply say they can call back anytime.

### ml-IN/sarvam/not_covered (clean) FAIL
- caller: ഞാൻ സെക്കന്തരാബാദിലാണ് താമസിക്കുന്നത്. അവിടേക്ക് ടെക്നീഷ്യനെ അയക്കാമോ?
- agent: ക്ഷമിക്കണം, ഞങ്ങൾ നിലവിൽ Madhapur, Gachibowli, Kondapur, Kukatpally എന്നീ areas-ൽ മാത്രമേ service നൽകുന്നുള്ളൂ. Secunderabad-ലേക്ക് ഇപ്പോൾ വരാൻ കഴിയില്ല. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — മറുപടി factually ശരിയാണ്, Malayalam-English code-mix സ്വാഭാവികമായി കേൾക്കുന്നു. അവസാനം ചേർത്ത ചോദ്യം അനാവശ്യമാണ്, പക്ഷേ വലിയ പ്രശ്നമല്ല.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?" → ഇത് ഒഴിവാക്കാം; പ്രധാന ചോദ്യം നേരിട്ട് മറുപടി നൽകി അവസാനിപ്പിക്കുക.
  - [unnatural_phrasing] "എന്നീ areas-ൽ" → "ഈ ഏരിയകളിൽ" അല്ലെങ്കിൽ "Madhapur, Gachibowli, Kondapur, Kukatpally ഭാഗങ്ങളിൽ" എന്ന് പറയുന്നത് കൂടുതൽ സ്വാഭാവികം.

### ml-IN/sarvam/numbers (mixed) FAIL
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് 599 rupees-ഉം window AC-ക്ക് 499 rupees-ഉം ആണ് വരുന്നത്. അപ്പോൾ രണ്ട് split AC-യും ഒരു window AC-യും ചേർത്ത് total 1,697 rupees ആകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — മലയാളം ഫോൺ സംഭാഷണത്തിന് മൊത്തത്തിൽ സ്വാഭാവികമാണ്, കണക്ക് ശരിയാണ്. പക്ഷേ അക്കത്തിൽ എഴുതിയ തുക TTS-ൽ awkward ആകാം, അവസാനത്തെ ചോദ്യം അല്പം അനാവശ്യമാണ്.
  - [number_or_time_readout] "1,697 rupees" → TTS-ന് സ്വാഭാവികമായി വായിക്കാൻ “ആയിരത്തി അറുനൂറ്റി തൊണ്ണൂറ്റി ഏഴ് രൂപ” അല്ലെങ്കിൽ “one thousand six ninety seven rupees” പോലെ എഴുതുക.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → വില പറഞ്ഞ് നിർത്താം; അല്ലെങ്കിൽ “ഇതാണ് total.” പോലെ ചുരുക്കാം.

### ml-IN/sarvam/parts_price (noisy) FAIL
- caller: എന്റെ ഫ്രിഡ്ജിന് പുതിയ കംപ്രസറിന്റെ exact പ്രൈസ് എത്ര
- agent: ക്ഷമിക്കണം, spare parts-ന്റെ വില phone-ൽ പറയാൻ കഴിയില്ല. Technician വന്ന് inspection കഴിഞ്ഞാൽ മാത്രമേ actual MRP പറയൂ. Inspection charge 250 rupees ആണ്, പക്ഷെ repair ചെയ്യുകയാണെങ്കിൽ ആ charge ഒഴിവാകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:227', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — മറുപടി മൊത്തത്തിൽ ശരിയാണ്, business facts പാലിക്കുന്നു. പക്ഷേ TTS-ന് ‘250 rupees’ അല്പം അസ്വാഭാവികമാണ്, കൂടാതെ അവസാനം ചേർത്ത follow-up ചോദ്യം ഫോൺ സംഭാഷണത്തിൽ അനാവശ്യമായി തോന്നുന്നു.
  - [number_or_time_readout] "250 rupees" → “250 രൂപ” അല്ലെങ്കിൽ “ഇരുനൂറ്റി അമ്പത് രൂപ” എന്ന് പറയുക.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → ഇത് ഒഴിവാക്കി മറുപടി അവിടെ തന്നെ അവസാനിപ്പിക്കുക; വിവരചോദ്യത്തിന് ശേഷം അധിക ചോദ്യം വേണ്ട.

### ml-IN/sarvam/price (clean) PASS
- caller: സ്പ്ലിറ്റ് എസിയുടെ സർവീസിംഗിന് എത്ര ചെലവാകും?
- agent: സ്പ്ലിറ്റ് AC servicing-ന് 599 rupees ആണ് വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Factually correct and brief. Malayalam-English code-mix is acceptable, but “rupees” instead of “രൂപ” and the extra follow-up sound a bit scripted for a simple pricing question.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?" → വില പറഞ്ഞിട്ട് നിർത്താം, അല്ലെങ്കിൽ കൂടുതൽ സ്വാഭാവികമായി: “സ്പ്ലിറ്റ് AC servicing 599 രൂപയാണ്.”
  - [unnatural_phrasing] "599 rupees ആണ് വരുന്നത്" → Malayalam phone call-ൽ കൂടുതൽ സ്വാഭാവികം: “599 രൂപയാണ്”

### ml-IN/sarvam/safety (mixed) FAIL
- caller: Power on ആയിരിക്കുമ്പോൾ AC-യുടെ electrical panel തുറന്ന് loose wire fix ചെയ്യുന്നത് എങ്ങനെ?
- agent: Power on ആയിരിക്കുമ്പോൾ electrical panel തുറക്കാനോ live wiring തൊടാനോ ഒരിക്കലും ശ്രമിക്കരുത്. അത് വളരെ അപകടമാണ്. സുരക്ഷിതമായ service-ന് ഞങ്ങളെ വിളിച്ചാൽ മതി, ഞങ്ങൾ സഹായിക്കാം. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:201']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — മലയാളം സ്വാഭാവികവും സുരക്ഷിതവുമാണ്. പക്ഷേ caller ഇതിനകം വിളിച്ചിരിക്കുമ്പോൾ ‘ഞങ്ങളെ വിളിച്ചാൽ മതി’ എന്ന് പറയുന്നത് അല്പം അസ്വാഭാവികമാണ്, അവസാനത്തെ generic ചോദ്യം കുറച്ച് unnecessary ആയി തോന്നുന്നു.
  - [unneeded_sales_push] "സുരക്ഷിതമായ service-ന് ഞങ്ങളെ വിളിച്ചാൽ മതി, ഞങ്ങൾ സഹായിക്കാം." → ഇത് ഒഴിവാക്കി, “സുരക്ഷിതമായി ഒരു technician നോക്കുന്നതാണ് നല്ലത്” എന്ന് പറയാം.
  - [other] "വേറെ എന്തെങ്കിലും അറിയണോ?" → അപകടകരമായ ചോദ്യം നേരിട്ട് മറുപടി നൽകിയതിനുശേഷം ഇത് ആവശ്യമില്ല; അല്ലെങ്കിൽ “visit വേണമെങ്കിൽ details എടുക്കാം” എന്ന് പറയാം.

### ml-IN/sarvam/time_request (noisy) FAIL
- caller: കൂളിംഗ് ഇല്ലാത്ത ഫ്രിഡ്ജിന് നാളെ രാവിലെ പത്ത് മുപ്പതിന് technician വരുമോ
- agent: Fridge-ന്റെ cooling issue ആണല്ലേ. നാളെ 10:30 AM-ന് visit schedule ചെയ്യാം, പക്ഷേ അത് team confirm ചെയ്ത ശേഷമേ ഉറപ്പിക്കാൻ പറ്റൂ. ഏത് area-യിലാണ് ഉള്ളത് എന്ന് പറയാമോ? Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally ഇതിൽ ഏതെങ്കിലും ആണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:239', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — മലയാളം code-mixing സ്വാഭാവികമാണ്, ഉത്തരം നേരിട്ട് സഹായകരവുമാണ്. പക്ഷേ സമയം TTS-ൽ അക്കങ്ങളായി വരുന്നത് അസ്വാഭാവികം, കൂടാതെ ‘schedule ചെയ്യാം’ എന്നു പറയുന്നത് ഉറപ്പുള്ളതുപോലെ കേൾക്കാം; ‘request ചെയ്യാം/team confirm ചെയ്യും’ കൂടുതൽ കൃത്യം.
  - [number_or_time_readout] "10:30 AM-ന്" → ഫോണിൽ പറയാൻ സ്വാഭാവികമായി: “പത്ത് മുപ്പതിന്” അല്ലെങ്കിൽ “രാവിലെ പത്ത് മുപ്പതിന്” എന്ന് പറയുക.
  - [too_long] "ഏത് area-യിലാണ് ഉള്ളത് എന്ന് പറയാമോ? Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally ഇതിൽ ഏതെങ്കിലും ആണോ?" → ഒന്ന് ചുരുക്കി: “ഏത് ഏരിയയാണ്—Madhapur, Gachibowli, Kondapur, അല്ലെങ്കിൽ Kukatpally ആണോ?”
  - [other] "നാളെ 10:30 AM-ന് visit schedule ചെയ്യാം" → Business fact പ്രകാരം next-day slots 10 AM–6 PM, team confirm ചെയ്യണം. “നാളെ പത്ത് മുപ്പതിന് slot request ചെയ്യാം” എന്നത് കൂടുതൽ കൃത്യം.

### ml-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service-ന് എത്ര price ആണ്? Kondapur-ൽ നിങ്ങൾ cover ചെയ്യുമോ?
- agent: Window AC servicing-ന് 499 rupees ആണ് charge വരുന്നത്. ഞങ്ങൾ Madhapur, Gachibowli, Kondapur, പിന്നെ Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമേ service കൊടുക്കാറുള്ളൂ. അപ്പോൾ Kondapur ഞങ്ങളുടെ area-യിൽ തന്നെയാണ് വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:237', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Malayalam code-mixing sounds natural and the pricing/coverage facts are correct. Slightly more detailed than needed for a phone answer, but still conversational.
  - [too_long] "ഞങ്ങൾ Madhapur, Gachibowli, Kondapur, പിന്നെ Kukatpally എന്നിവിടങ്ങളിൽ മാത്രമേ service കൊടുക്കാറുള്ളൂ. അപ്പോൾ Kondapur ഞങ്ങളുടെ area-യിൽ തന്നെയാണ് വരുന്നത്." → Caller asked only about Kondapur, so say simply: “Kondapur cover ചെയ്യും.”
  - [other] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Acceptable, but for a direct info answer it can be omitted or replaced with a softer pause like “Booking വേണമെങ്കിൽ പറഞ്ഞോളൂ.” only if appropriate.

### ml-IN/sarvam/unknown_fact (noisy) FAIL
- caller: രണ്ട് എസിക്ക് ആനുവൽ maintenance contract AMC എത്ര വരും
- agent: ക്ഷമിക്കണം, ആ വിവരം എനിക്കറിയില്ല. ഞങ്ങൾ mainly servicing ആണ് ചെയ്യുന്നത് — window AC-ക്ക് 499 rupees-ഉം split AC-ക്ക് 599 rupees-ഉം ആണ് charge വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is factually correct and mostly natural Malayalam with acceptable code-mixing. It directly says AMC pricing is unknown and offers known servicing prices, but the final generic question is a bit unnecessary for the caller’s specific pricing question.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → AMC അറിയില്ലെന്ന് പറഞ്ഞ് servicing rates പറഞ്ഞാൽ മതി; അല്ലെങ്കിൽ 'servicing വേണമെങ്കിൽ പറയൂ' പോലെ കൂടുതൽ പ്രസക്തമായി പറയാം.
  - [number_or_time_readout] "499 rupees-ഉം split AC-ക്ക് 599 rupees-ഉം" → TTS-ക്ക് സ്വാഭാവികമായി 'നാനൂറ്റി തൊണ്ണൂറ്റൊമ്പത് രൂപ' / 'അഞ്ഞൂറ്റി തൊണ്ണൂറ്റൊമ്പത് രൂപ' എന്ന് പറയുന്നത് നല്ലത്, പക്ഷേ urban Malayalam-ൽ 'four ninety nine rupees' എന്നും കേൾക്കാം.

### ta-IN/sarvam/correction (clean) PASS
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு 599 rupees ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: இல்லை, அது விண்டோ ஏசி. விண்டோ ஏசி சர்வீஸ் கட்டணம் எவ்வளவு?
- agent: Window AC servicing-க்கு 499 rupees ஆகும். வேற ஏதாவது தகவல் வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct and brief, with natural Tamil-English service wording. The follow-up question is a bit unnecessary after directly answering the price, and the numeric form may be awkward for TTS.
  - [unneeded_sales_push] "வேற ஏதாவது தகவல் வேணுமா?" → Asked price only; better stop after the price, or say a softer 'அவ்வளவுதான்' if needed.
  - [number_or_time_readout] "499 rupees" → For spoken Tamil, say 'நானூற்று தொண்ணூற்று ஒன்பது ரூபாய்' or naturally 'four ninety nine rupees' depending TTS style; avoid digit readout risk.

### ta-IN/sarvam/frustration (noisy) PASS
- caller: நான் simple question தான் கேட்டேன் please straight answer சொல்லுங்க fridge inspection fee எவ்வளவு
- agent: Fridge inspection-க்கு 250 rupees ஆகும். ஆனா ஒரு விஷயம், நீங்க repair பண்ணிக்கிறதா முடிவு பண்ணிட்டீங்கன்னா அந்த inspection charge waive ஆகிடும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural Tamil-English code-mix and the pricing/waiver facts are correct. Slightly less ideal because the caller asked for a straight answer, but the agent adds a follow-up question.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Caller specifically asked for a straight answer, so end after the fee/waiver without an extra question.

### ta-IN/sarvam/greeting_check (clean) PASS
- caller: ஹலோ, என் குரல் கேட்கிறதா? இது எந்த நிறுவனம்?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். சொல்லுங்க, என்ன help வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Tamil with common code-mixing, directly confirms audibility and identifies the company. Slightly receptionist-script-like due to repeating the opening, but appropriate for the caller’s question.

### ta-IN/sarvam/hesitation (mixed) FAIL
- caller: சரி, நான் think பண்ணிப் பார்க்கிறேன். Later maybe call back பண்ணுறேன்.
- agent: சரிங்க, நீங்க பொறுமையா யோசிச்சுட்டு அப்புறமா call பண்ணுங்க. வேற ஏதாவது details வேணுமா?
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Tamil is mostly natural with common code-mixing, and no factual issues. But the follow-up question is a bit unnecessary after the caller clearly wants to end the call, and "பொறுமையா யோசிச்சுட்டு" sounds slightly unnatural for a receptionist.
  - [unnatural_phrasing] "நீங்க பொறுமையா யோசிச்சுட்டு" → "சரி, யோசிச்சு பார்த்துட்டு call பண்ணுங்க" மாதிரி சொல்லலாம்; "பொறுமையா" இங்கே கொஞ்சம் odd.
  - [missed_question] "வேற ஏதாவது details வேணுமா?" → Caller already said later call back; better close politely: "சரி, எப்போ வேண்டுமானாலும் call பண்ணுங்க."

### ta-IN/sarvam/not_covered (clean) PASS
- caller: நான் செகந்தராபாத்தில் இருக்கிறேன். அங்கே டெக்னீஷியன் வர முடியுமா?
- agent: மன்னிக்கவும், செகந்தராபாத் மற்றும் Old City area எங்க service-ல cover ஆகாதுங்க. நாங்க Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally-ல மட்டும் தான் service பண்றோம். உங்களுக்கு வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['over_soft_length:209', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Tamil code-mixing is natural for an urban service call, facts are correct, and it directly answers the area question. Slightly more concise without the extra follow-up question would sound more human.
  - [other] "உங்களுக்கு வேற ஏதாச்சும் details வேணுமா?" → இந்த கேள்வி தேவையில்லாமல் கொஞ்சம் appended மாதிரி கேட்கிறது; 'சாரி, செகந்தராபாத் எங்க coverage-ல இல்லைங்க.' என்று முடித்தால் இன்னும் இயல்பாக இருக்கும்.

### ta-IN/sarvam/numbers (mixed) FAIL
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing 599 rupees, அப்புறம் window AC servicing 499 rupees. So ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total-ஆ 1797 rupees வரும். Technician வந்து inspection பண்ணதுக்கு அப்புறம் தான் spare parts-ஓட actual MRP சொல்லி quote பண்ணுவாங்க. நீங்க எந்த area-ல இருக்கீங்க?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:279', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — The answer is factually correct and mostly natural Tamil-English service-call style. It directly computes the total correctly, but is a bit longer than needed for the pricing question and adds a booking-style area question unnecessarily.
  - [too_long] "Technician வந்து inspection பண்ணதுக்கு அப்புறம் தான் spare parts-ஓட actual MRP சொல்லி quote பண்ணுவாங்க. நீங்க எந்த area-ல இருக்கீங்க?" → Caller asked only total servicing cost; keep it shorter. Add parts note only briefly if needed, and don't append area question unless moving to booking.
  - [number_or_time_readout] "1797 rupees" → In Tamil speech, say “ஆயிரத்து எழுநூற்று தொண்ணூற்று ஏழு ரூபாய்” or “seventeen ninety-seven rupees” more naturally for TTS; raw digits may be read awkwardly.

### ta-IN/sarvam/parts_price (noisy) FAIL
- caller: என் fridgeக்கு new compressor exact price எவ்வளவு
- agent: Sorry, exact price இப்போ phone-ல சொல்ல முடியாது. Technician வந்து inspection பண்ணிட்டு தான் அந்த parts-ஓட actual MRP சொல்வாரு. Fridge inspection charge 250 rupees வரும், ஆனா நீங்க repair பண்ண proceed பண்ணீங்கன்னா அந்த charge waive ஆகிடும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:269', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Tamil code-mix mostly natural and facts are correct: no phone quote for compressor, technician quotes after inspection, inspection fee and waiver are accurate. It’s a bit wordy for a live call and the ending question is not needed.
  - [too_long] "Fridge inspection charge 250 rupees வரும், ஆனா நீங்க repair பண்ண proceed பண்ணீங்கன்னா அந்த charge waive ஆகிடும்." → சுருக்கமாக: “Fridge inspection 250 rupees; repair பண்ணினா அது waive ஆகிடும்.”
  - [unneeded_sales_push] "வேற ஏதாச்சும் details வேணுமா?" → Caller கேட்ட compressor price-க்கு மட்டும் பதில் போதும்; visit வேண்டுமா என்று கேட்கலாம், ஆனால் இங்கே அவசியமில்லை.
  - [unnatural_phrasing] "repair பண்ண proceed பண்ணீங்கன்னா" → “repairக்கு ok சொன்னீங்கன்னா” அல்லது “repair பண்ணினா” என்று சொல்லலாம்.

### ta-IN/sarvam/price (clean) PASS
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு 599 rupees ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — பதில் சரியான தகவலைச் சுருக்கமாக சொல்கிறது. Tamil-English code-mix இயல்பாகவே இருக்கிறது, ஆனால் விலை வாசிப்பு TTS-ல் சற்று இயல்பில்லாமல் கேட்கலாம்; கடைசி கேள்வியும் கொஞ்சம் scripted போல உள்ளது.
  - [number_or_time_readout] "599 rupees" → TTS-க்கு தெளிவாக 'ஐநூத்து தொண்ணூற்று ஒன்பது ரூபாய்' அல்லது பேச்சுவழக்கில் 'five ninety-nine ரூபாய்' என்று சொல்லலாம்.
  - [unnatural_phrasing] "வேற ஏதாச்சும் details வேணுமா?" → சற்றே இயல்பாக: 'வேற ஏதாவது தெரிஞ்சிக்கணுமா?'

### ta-IN/sarvam/safety (mixed) FAIL
- caller: Power on-ல இருக்கும்போது AC-யோட electrical panel திறந்து loose wire-ஐ நானே எப்படி fix பண்ணலாம்?
- agent: மன்னிக்கவும், electrical panel அல்லது live wiring-ஐ நீங்களே open பண்ண வேண்டாம். அது ரொம்ப ஆபத்து. நம்ம technician வந்து inspection பண்ணிட்டு பாதுகாப்பா சரி பண்ணி தருவாங்க. உங்களுக்கு AC servicing வேணுமா? அதுல Window AC-க்கு 499 rupees, Split AC-க்கு 599 rupees ஆகும்.
  - checks: hard=['too_many_sentences:5'] warn=['over_soft_length:267', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Safety refusal is good and mostly natural Tamil-English code-mix. But it adds unsolicited AC servicing prices and slightly over-promises the repair, making it less like a concise human receptionist response.
  - [unneeded_sales_push] "உங்களுக்கு AC servicing வேணுமா? அதுல Window AC-க்கு 499 rupees, Split AC-க்கு 599 rupees ஆகும்." → Caller safety/how-to கேட்டிருக்காங்க; முதலில் unsafe-னு சொல்லி technician visit offer பண்ணலாம். Pricing கேட்காத வரை சேர்க்க வேண்டாம்.
  - [too_long] "மன்னிக்கவும், electrical panel அல்லது live wiring-ஐ நீங்களே open பண்ண வேண்டாம். அது ரொம்ப ஆபத்து. நம்ம technician வந்து inspection பண்ணிட்டு பாதுகாப்பா சரி பண்ணி தருவாங்க. உங்களுக்கு AC servicing வேணுமா? அதுல Window AC-க்கு 499 rupees, Split AC-க்கு 599 rupees ஆகும்." → Phone call-க்கு 1–2 short sentences போதும்: “Electrical panel/live wiring நீங்களே open பண்ணாதீங்க, ஆபத்து. Technician visit book பண்ணணும்னா உங்கள் locality, preferred slot சொல்லுங்க.”
  - [other] "நம்ம technician வந்து inspection பண்ணிட்டு பாதுகாப்பா சரி பண்ணி தருவாங்க." → Repair கண்டிப்பா சரியாகும் போல guarantee செய்யாமல், “check பண்ணி safe-aa என்ன repair வேணும்னு சொல்வாங்க” என்று சொல்லலாம்.

### ta-IN/sarvam/time_request (noisy) PASS
- caller: Cooling இல்லாத fridgeக்கு நாளை morning பத்து முப்பதுக்கு technician வர முடியுமா
- agent: Fridge-ல cooling வரலன்னா, நம்ம technician நாளைக்கு வந்து inspection பண்ணுவாங்க. Madhapur, Gachibowli, Kondapur இல்ல Kukatpally area-ல தான் service இருக்கு. நீங்க இந்த areas-ல இருக்கீங்களா?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Natural spoken Tamil with appropriate code-mixing and a useful area check. It should address the requested 10:30 slot more directly and include the fridge inspection charge for a booking-related answer.
  - [missed_question] "நாளைக்கு வந்து inspection பண்ணுவாங்க" → Caller asked specifically for 10:30 morning; say next-day slots are between 10 AM and 6 PM and team can confirm 10:30 if available.
  - [other] "inspection பண்ணுவாங்க" → Mention fridge inspection charge is ₹250, waived if repair is done, if discussing a visit.

### ta-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service charge எவ்வளவு? Kondapur-க்கும் cover பண்ணுவீங்களா?
- agent: Window AC servicing charge 499 rupees வரும். ஆமா, Kondapur நம்ம service area-ல தான் வருது. வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Tamil-English code-mix and the facts are correct: ₹499 for Window AC servicing and Kondapur is covered. The final question is mildly unnecessary, but still plausible for a receptionist.
  - [unneeded_sales_push] "வேற ஏதாச்சும் details வேணுமா?" → If just answering pricing and area, stop after the answer or say briefly: “Booking வேணும்னா சொல்லுங்க.”

### ta-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ரெண்டு ACக்கு annual maintenance contract AMC எவ்வளவு ஆகும்
- agent: Sorry, phone-ல parts இல்லாம AMC pricing details என்கிட்ட இல்ல. நம்ம technician வந்து inspection பண்ணிட்டு, actual MRP-க்கு parts எவ்ளோன்னு சொல்லிடுவாங்க. நீங்க servicing மட்டும் பண்ணிக்கிறீங்களா இல்ல inspection வேணுமா?
  - checks: hard=[] warn=['over_soft_length:218', 'three_sentences']
- judge: {'language_fit': 3, 'human_naturalness': 2, 'register': 3, 'correctness': 2, 'helpfulness': 2, 'brevity': 3} — Tamil code-mix is understandable, but the answer doesn’t properly address AMC for two ACs, adds unsupported inspection/parts framing, and sounds a bit scripted. A better phone reply: “AMC rate இப்போ என்கிட்ட available இல்லைங்க. Regular service மட்டும் என்றால் Window AC 499, Split AC 599 per AC; visit book பண்ணணும்னா AC type, locality, preferred slot சொல்லுங்க.”
  - [missed_question] "AMC pricing details என்கிட்ட இல்ல" → AMC விலை தெரியவில்லை என்றால் நேராகச் சொல்லி, கிடைக்கும் AC servicing rates-ஐ சொல்லலாம்: Window AC 499, Split AC 599.
  - [invented_fact] "நம்ம technician வந்து inspection பண்ணிட்டு" → AC-க்கு inspection charge/AMC inspection process business facts-ல் இல்லை; visit வேண்டுமா என்றால் next-day slot எடுக்கலாம் என்று மட்டும் சொல்லவும்.
  - [unneeded_sales_push] "actual MRP-க்கு parts எவ்ளோன்னு சொல்லிடுவாங்க" → Caller AMC கேட்டுள்ளார்; parts பற்றி தேவையில்லாமல் இழுக்க வேண்டாம். Parts only if repair/spares needed.
  - [missed_question] "நீங்க servicing மட்டும் பண்ணிக்கிறீங்களா இல்ல inspection வேணுமா?" → முதலில் AMC pricing available இல்லை என்று சொல்லி, per-service cost தெரிவிக்கவும்; பிறகு வேண்டுமெனில் booking details கேட்கலாம்.
  - [unnatural_phrasing] "phone-ல parts இல்லாம AMC pricing details" → “AMC rate இப்போ phone-ல சொல்ல முடியாது/என்கிட்ட இல்லை” மாதிரி இயல்பாகச் சொல்லவும்.

### te-IN/sarvam/correction (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి 599 rupees అవుతుంది. మీకు వేరే ఏమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: అయ్యో, అది స్ప్లిట్ కాదు, విండో ఏసీ. దానికి సర్వీస్ ధర ఎంత?
- agent: Window AC servicing కి 499 rupees అవుతుంది. ఇంకేమైనా తెలుసుకోవాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — జవాబు సరైనది, చిన్నది, సందర్భానికి నేరుగా ఉంది. కానీ చివర్లో unnecessary follow-up ఉంది; అలాగే '499 rupees' TTSలో సహజంగా వినిపించకపోవచ్చు.
  - [unneeded_sales_push] "ఇంకేమైనా తెలుసుకోవాలా?" → ధర చెప్పాక ఆపేయొచ్చు, లేదా సహజంగా 'అంతే సర్/మేడమ్' అనొచ్చు.
  - [number_or_time_readout] "499 rupees" → TTS కోసం 'నాలుగు వందల తొంభై తొమ్మిది రూపాయలు' లేదా సహజ code-mixలో 'ఫోర్ నైన్టీ నైన్ రూపీస్' అని చెప్పండి.

### te-IN/sarvam/frustration (noisy) PASS
- caller: నేను సింపుల్ క్వశ్చన్ అడిగాను ప్లీజ్ స్ట్రెయిట్ ఆన్సర్ చెప్పండి ఫ్రిజ్ ఇన్స్పెక్షన్ ఫీ ఎంత
- agent: Fridge inspection charge 250 rupees అవుతుంది. ఒకవేళ మీరు repair చేయిస్తే ఆ inspection fee waive అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం నిజమైనది, చిన్నది, సహజమైన Telugu-English mix ఉంది. కానీ caller straight answer అడిగినందున చివరి follow-up unnecessaryగా ఉంది; '250 rupees' TTSలో కొంచెం unnaturalగా వినిపించే అవకాశం ఉంది.
  - [unneeded_sales_push] "మీకు ఇంకా ఏమైనా details కావాలా?" → Caller asked for a straight answer; stop after the fee and waiver info, or say nothing extra.
  - [number_or_time_readout] "250 rupees" → TTS కోసం 'రెండు వందల యాభై రూపాయలు' లేదా సహజంగా 'టూ ఫిఫ్టీ' అని చెప్పండి.

### te-IN/sarvam/greeting_check (clean) PASS
- caller: హలో, నా మాట వినిపిస్తుందా? ఇది ఏ కంపెనీ?
- agent: అవును, వినిపిస్తోంది. నేను SmartCare Appliance Services నుంచి సురేష్ ని మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం సరైనదే, కంపెనీ పేరు మరియు వినిపిస్తున్నదని స్పష్టంగా చెప్పింది. చిన్న వ్యాకరణ/సహజత్వ సమస్యలు ఉన్నాయి, కానీ ఫోన్ కాల్‌కు బాగా సరిపోతుంది.
  - [unnatural_phrasing] "సురేష్ ని మాట్లాడుతున్నాను" → “సురేష్ మాట్లాడుతున్నాను” లేదా “నేను సురేష్, SmartCare Appliance Services నుంచి” అని చెప్పాలి.
  - [robotic_or_scripted] "మీకు ఎలా సహాయం చేయగలను?" → ఫోన్‌లో సహజంగా “చెప్పండి, ఏ service కావాలి?” లాంటిది బాగుంటుంది.

### te-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, నేను think చేస్తాను. Later మళ్లీ call చేస్తాను.
- agent: సరే, మీరు తర్వాత call చేస్తానని చెప్పారు కదా. నేను ఇక్కడ note చేసుకుంటాను. ఇంకేమైనా help కావాలా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Telugu is understandable and polite, but it sounds like a scripted bot because it repeats the caller and says it will make a note without any details. A more natural phone reply would be: 'సరేండి, ఎప్పుడైనా call చేయండి. ధన్యవాదాలు.'
  - [robotic_or_scripted] "మీరు తర్వాత call చేస్తానని చెప్పారు కదా" → ఇది repeat చేయకుండా సహజంగా 'సరేండి, ఎప్పుడైనా call చేయండి' అనాలి.
  - [invented_fact] "నేను ఇక్కడ note చేసుకుంటాను" → Caller నుంచి వివరాలు ఏమీ తీసుకోలేదు కాబట్టి note చేసుకోవడం అనవసరం; తీసేయాలి.
  - [unneeded_sales_push] "ఇంకేమైనా help కావాలా?" → Caller call ముగిస్తున్నాడు కాబట్టి చిన్న closing సరిపోతుంది: 'ధన్యవాదాలు.'

### te-IN/sarvam/not_covered (clean) PASS
- caller: నేను సికింద్రాబాద్‌లో ఉంటాను. అక్కడికి టెక్నీషియన్ రావచ్చా?
- agent: క్షమించండి, మా service కేవలం Madhapur, Gachibowli, Kondapur, Kukatpally areas లో మాత్రమే ఉంది. Secunderabad కి ప్రస్తుతం రావడం కుదరదు. మీకు వేరే location లో service కావాలా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Correct Telugu-English code-mix, polite, and factually accurate. It directly answers the Secunderabad coverage question. Minor phrasing could be more natural and shorter for a live call.
  - [other] "మీకు వేరే location లో service కావాలా?" → Slightly smoother: “వేరే ఏదైనా covered areaలో service కావాలా?”
  - [too_long] "మా service కేవలం Madhapur, Gachibowli, Kondapur, Kukatpally areas లో మాత్రమే ఉంది." → For phone brevity: “మేము Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover చేస్తాం.”

### te-IN/sarvam/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: Split AC service కి 599 rupees, window AC కి 499 rupees అవుతుంది. So, రెండు split ACలు, ఒక window AC కి total 1,697 rupees అవుతుంది. మీకు మా team ని visit కి పంపించాలా?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:25/96', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — సమాధానం మొత్తానికి సరైనదే, math కూడా కరెక్ట్. కానీ ఫోన్‌లో వినిపించడానికి amount readout ఇంకాస్త సహజంగా ఉండాలి, అలాగే అడగని visit question వెంటనే జోడించడం కొంచెం sales push లా ఉంది.
  - [unneeded_sales_push] "మీకు మా team ని visit కి పంపించాలా?" → Caller కేవలం total అడిగారు; price చెప్పి ఆపండి, లేదా చాలా సాఫ్ట్‌గా “Book చేయాలంటే చెప్పండి” అనండి.
  - [number_or_time_readout] "total 1,697 rupees అవుతుంది" → TTSకి సహజంగా వినిపించేలా “మొత్తం వెయ్యి ఆరు వందల తొంభై ఏడు రూపాయలు అవుతుంది” అని చెప్పండి.

### te-IN/sarvam/parts_price (noisy) FAIL
- caller: నా ఫ్రిజ్ కి న్యూ కంప్రెసర్ ఎగ్జాక్ట్ ప్రైస్ ఎంత
- agent: ఫ్రిజ్ spare parts price నేను phone లో చెప్పలేను. మా technician వచ్చి inspection చేశాక, actual MRP ప్రకారం మీకు చెప్తారు. Inspection charge 250 rupees ఉంటుంది, కానీ మీరు repair కి ఒప్పుకుంటే ఆ charge waive అవుతుంది. మీకు మా team వచ్చి inspection చేయించాలా?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:256', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — సమాధానం విషయపరంగా సరైనది, caller అడిగిన exact compressor price ఎందుకు phone‌లో చెప్పలేమో స్పష్టంగా చెప్పింది. కొంచెం English-heavyగా ఉంది, కానీ Hyderabad service-call Teluguకి మొత్తంగా సహజంగానే ఉంది.
  - [number_or_time_readout] "250 rupees" → “రెండు వందల యాభై రూపాయలు” అని చెప్పడం TTSకి, ఫోన్ కాల్‌కి సహజంగా ఉంటుంది.
  - [unnatural_phrasing] "ఆ charge waive అవుతుంది" → “ఆ charge మాఫీ అవుతుంది” లేదా “ఆ charge తీసుకోము” అనడం మరింత సహజం.

### te-IN/sarvam/price (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి 599 rupees అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం సరైనదే, చిన్నదే. తెలుగు-ఇంగ్లీష్ మిక్సింగ్ సహజంగా ఉంది, కానీ '599 rupees' TTSలో అంకెలుగా చదివే ప్రమాదం ఉంది; చివరి ప్రశ్న కొద్దిగా స్క్రిప్టెడ్‌గా ఉంది.
  - [number_or_time_readout] "599 rupees" → TTS కోసం 'ఐదు వందల తొంభై తొమ్మిది రూపాయలు' లేదా సహజంగా 'ఫైవ్ నైన్టీ నైన్ రూపీస్' అనొచ్చు.
  - [unneeded_sales_push] "మీకు ఇంకా ఏమైనా details కావాలా?" → ప్రశ్నకు సమాధానం ఇచ్చి ఆపితే చాలు, లేదా 'ఇంకేమైనా తెలుసుకోవాలా?' అని మరింత సహజంగా చెప్పాలి.

### te-IN/sarvam/safety (mixed) PASS
- caller: Power on లో ఉండగానే AC electrical panel ఎలా open చేయాలి? Loose wire నేనే fix చేయాలి.
- agent: మీరు electrical panel open చేయకండి, live wiring దగ్గర పని చేయడం చాలా ప్రమాదకరం. మా technician వచ్చి inspection చేసి, అవసరమైతే safe గా repair చేస్తారు. మీకు ఏ AC service కావాలో చెప్తారా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Good Telugu-English code-mix and clear safety warning. It correctly refuses unsafe electrical guidance. The final question is slightly generic and less helpful for booking a technician.
  - [missed_question] "మీకు ఏ AC service కావాలో చెప్తారా?" → Caller is asking about a dangerous DIY repair; better ask for locality/visit details or say technician can check it, instead of asking what AC service they want.

### te-IN/sarvam/time_request (noisy) FAIL
- caller: కూలింగ్ లేని ఫ్రిజ్ కి రేపు మార్నింగ్ టెన్ థర్టీకి టెక్నీషియన్ రావచ్చా
- agent: Sorry అండి, మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover అవుతాయి. Secunderabad, Old City రావడం కుదరదు. మీది ఈ areas లో ఏది వస్తుంది?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:29/110']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 3} — Factually correct and mostly Telugu-English natural, but it doesn’t directly respond to the requested tomorrow 10:30 fridge visit and sounds a bit like a service-area script.
  - [missed_question] "మీది ఈ areas లో ఏది వస్తుంది?" → Caller asked for a fridge visit tomorrow at 10:30; first mention next-day slots are 10 AM–6 PM and ask locality/name to check/confirm.
  - [robotic_or_scripted] "మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover అవుతాయి. Secunderabad, Old City రావడం కుదరదు." → Sounds like a scripted area list. More natural: “మీ location ఏ area అండి? మేము Madhapur, Gachibowli, Kondapur, Kukatpallyలో మాత్రమే service చేస్తాం.”
  - [too_long] "Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే cover అవుతాయి. Secunderabad, Old City రావడం కుదరదు." → No need to mention Secunderabad/Old City unless caller says those areas.

### te-IN/sarvam/two_questions (mixed) FAIL
- caller: విండో AC service price ఎంత? Kondapur కి కూడా cover చేస్తారా?
- agent: విండో AC service కి 499 rupees అవుతుంది. అవును, మా service area లో Kondapur కూడా ఉంది. మీకు ఇంకా ఏ details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — సమాధానం facts పరంగా సరైనదే, Telugu-English mix కూడా బాగానే ఉంది. కానీ సంఖ్య చదవడం TTSకి మెరుగుపరచాలి, చివరి ప్రశ్న కొంచెం generic గా ఉంది.
  - [number_or_time_readout] "499 rupees" → Telugu TTS కోసం “నాలుగు వందల తొంభై తొమ్మిది రూపాయలు” లేదా సహజంగా “ఫోర్ నైన్టీ నైన్ రూపీస్” అని చెప్పడం బాగుంటుంది.
  - [unnatural_phrasing] "మా service area లో Kondapur కూడా ఉంది" → “Kondapur మా service area లోకి వస్తుంది” అనడం మరింత సహజం.
  - [missed_question] "మీకు ఇంకా ఏ details కావాలా?" → Caller price/area మాత్రమే అడిగాడు; చివరలో ప్రశ్న అవసరం లేదు, లేదా booking ఆసక్తి ఉంటే “visit కావాలంటే slot చూసి చెప్పగలం” అని చిన్నగా చెప్పొచ్చు.

### te-IN/sarvam/unknown_fact (noisy) FAIL
- caller: రెండు AC లకి యాన్యువల్ మెయింటెనెన్స్ కాంట్రాక్ట్ AMC ఎంత కాస్ట్ అవుతుంది
- agent: నేను phone లో parts prices లేదా AMC కాస్ట్ చెప్పలేను. మా technician వచ్చి inspection చేశాక, actual MRP మీద spare parts ఎంత అవుతుందో చెప్తారు. ప్రస్తుతానికి మా దగ్గర Window AC servicing కి 499 rupees, Split AC కి 599 rupees అవుతుంది. మీకు visit ఏమైనా schedule చేయమంటారా?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:269', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — సమాధానం మొత్తానికి factual గా mostly సరైనదే, కానీ AMC ప్రశ్నకి బదులుగా parts/MRP explanation ఎక్కువైంది. ఫోన్‌లో చెప్పడానికి కాస్త scripted గా, పొడవుగా ఉంది; one-time servicing prices మాత్రం ఉపయోగకరంగా చెప్పింది.
  - [robotic_or_scripted] "నేను phone లో parts prices లేదా AMC కాస్ట్ చెప్పలేను." → "AMC rate ఇప్పుడే confirm చేయలేను" లాగా సహజంగా చెప్పాలి; parts prices విషయం అడగలేదు కాబట్టి అవసరం లేదు.
  - [missed_question] "parts prices లేదా AMC కాస్ట్" → Caller AMC అడిగాడు; AMC ధర తెలియదని స్పష్టంగా చెప్పి, available one-time servicing rates చెప్పాలి.
  - [too_long] "మా technician వచ్చి inspection చేశాక, actual MRP మీద spare parts ఎంత అవుతుందో చెప్తారు." → AC AMC ప్రశ్నకి spare parts/MRP వివరాలు అవసరం లేదు; చిన్నగా ఉంచాలి.
  - [number_or_time_readout] "499 rupees, Split AC కి 599 rupees" → TTSకి సహజంగా "నాలుగు వందల తొంభై తొమ్మిది రూపాయలు", "ఐదు వందల తొంభై తొమ్మిది రూపాయలు" అని చెప్పాలి.
