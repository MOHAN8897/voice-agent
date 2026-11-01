# Language probe language-probe-baseline-sarvam

Schema `sim_68e32891c2f841b3b08b5b2dd11a5bfc`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | sarvam | 0/12 | 0.00 | - 0.00 |
| gu-IN | sarvam | 0/12 | 0.00 | - 0.00 |
| hi-IN | sarvam | 6/12 | 4.12 | human_naturalness 3.80 |
| kn-IN | sarvam | 0/12 | 4.17 | language_fit 4.00 |
| ml-IN | sarvam | 0/12 | 0.00 | - 0.00 |
| ta-IN | sarvam | 0/12 | 4.00 | brevity 3.50 |
| te-IN | sarvam | 3/12 | 4.00 | human_naturalness 3.50 |

## Transcripts

### en-IN/sarvam/correction (clean) FAIL
- caller: स्प्लिट एसी की सर्विस का कितना शुल्क है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: माफ़ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विस का कितना शुल्क है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/frustration (noisy) FAIL
- caller: मैंने simple question पूछा सीधा answer चाहिए fridge inspection fee कितना
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/greeting_check (clean) FAIL
- caller: हैलो, मेरी आवाज़ आ रही है? यह कौन-सी कंपनी है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/hesitation (mixed) FAIL
- caller: ठीक है, मैं इसको think करके शायद बाद में call back करूँगा।
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/not_covered (clean) FAIL
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका टेक्नीशियन यहाँ आ सकता है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/parts_price (noisy) FAIL
- caller: फ्रिज नया compressor का exact price कितना है
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/price (clean) FAIL
- caller: स्प्लिट एसी की सर्विसिंग का कितना चार्ज है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/safety (mixed) FAIL
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel कैसे खोलूँ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/time_request (noisy) FAIL
- caller: टेक्नीशियन कल मॉर्निंग दस तीस पर आ सकता है फ्रिज कूलिंग नहीं कर रहा
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service का कितना price है, और Kondapur में cover करते हैं क्या?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### en-IN/sarvam/unknown_fact (noisy) FAIL
- caller: दो एसी का annual maintenance contract AMC कितना चार्ज आएगा
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/correction (clean) FAIL
- caller: સ્પ્લિટ એસી સર્વિસનો ભાવ કેટલો છે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: અરે, ખરેખર તો એ વિન્ડો એસી છે, સ્પ્લિટ નહીં. એની સર્વિસનો ભાવ કેટલો છે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/frustration (noisy) FAIL
- caller: મેં સિમ્પલ સવાલ પૂછ્યો ફ્રિજ ઇન્સ્પેક્શન ફીનો સીધો આન્સર આપો
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/greeting_check (clean) FAIL
- caller: હેલો, તમને મારો અવાજ સંભળાય છે? આ કઈ કંપની છે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/hesitation (mixed) FAIL
- caller: હું આના વિશે think કરીશ, maybe later call back કરીશ.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/not_covered (clean) FAIL
- caller: હું સિકંદરાબાદમાં રહું છું. શું તમારો ટેકનિશિયન અહીં આવી શકે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/numbers (mixed) FAIL
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/parts_price (noisy) FAIL
- caller: મારા ફ્રિજના નવા કમ્પ્રેસરનો એક્ઝેક્ટ પ્રાઇસ કેટલો
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/price (clean) FAIL
- caller: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ કેટલો આવે?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/safety (mixed) FAIL
- caller: Power on હોય ત્યારે loose wire ઠીક કરવા ACનું electrical panel હું જાતે કેવી રીતે ખોલું?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/time_request (noisy) FAIL
- caller: મારું ફ્રિજ કૂલિંગ નથી કરતું ટેકનિશિયન કાલે મોર્નિંગ દસ ત્રીસે આવી શકે
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC serviceની price કેટલી છે, અને Kondapurમાં તમે cover કરો છો?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### gu-IN/sarvam/unknown_fact (noisy) FAIL
- caller: બે એસી માટે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટ AMC કેટલામાં થાય
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### hi-IN/sarvam/correction (clean) FAIL
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च है?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: माफ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विसिंग का कितना खर्च होगा?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### hi-IN/sarvam/frustration (noisy) FAIL
- caller: मैंने सिंपल क्वेश्चन पूछा था फ्रिज inspection fee का सीधा answer दीजिए
- agent: Fridge inspection की fee two hundred fifty rupees है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। क्या आपको visit book करवानी है?
  - checks: hard=[] warn=['english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — जवाब factually सही है और भाषा ज़्यादातर ठीक है, लेकिन caller ने खास तौर पर सीधा answer मांगा था, इसलिए अंत में booking पूछना unnecessary लगता है। English number readout भी थोड़ा unnatural है।
  - [number_or_time_readout] "two hundred fifty rupees" → “ढाई सौ रुपये” या “250 रुपये” बोलें; फोन पर ज्यादा नैचुरल लगेगा।
  - [missed_question] "क्या आपको visit book करवानी है?" → Caller ने सिर्फ सीधा fee पूछा था; यहाँ extra booking question न जोड़ें।

### hi-IN/sarvam/greeting_check (clean) PASS
- caller: नमस्ते, क्या आपको मेरी आवाज़ सुनाई दे रही है? और यह कौन-सी कंपनी है?
- agent: हाँ, आवाज़ साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh हूँ। बताइए, आज किस चीज़ में help चाहिए?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is mostly natural and factually correct. Slightly odd Hindi-English mixing with 'Suresh' in English script/pronunciation, and the company identity could be answered a bit more directly before moving on.
  - [unnatural_phrasing] "मैं SmartCare Appliance Services से Suresh हूँ।" → मैं SmartCare Appliance Services से सुरेश बोल रहा हूँ।
  - [missed_question] "बताइए, आज किस चीज़ में help चाहिए?" → पहले कंपनी का नाम साफ़ बताकर फिर पूछें: जी, SmartCare Appliance Services है। बताइए, किस appliance के लिए service चाहिए?

### hi-IN/sarvam/hesitation (mixed) PASS
- caller: ठीक है, मैं इस पर think करूँगा, शायद बाद में call back करूँ।
- agent: ठीक है, कोई बात नहीं। जब भी आप ready हों, call कर लीजिएगा। क्या मैं आपके लिए कोई callback time note कर दूँ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Hindi code-mix natural है और tone polite है. Facts में कोई समस्या नहीं. थोड़ा unnecessary follow-up question है, क्योंकि caller ने clearly कहा कि वो खुद बाद में call back करेंगे.
  - [other] "क्या मैं आपके लिए कोई callback time note कर दूँ?" → Caller ने खुद बाद में call back करने को कहा है, इसलिए बस 'जब चाहें call कर लीजिए' पर खत्म करना ज्यादा natural होगा; या हल्का सा 'चाहें तो मैं callback time note कर सकता हूँ' कहें।

### hi-IN/sarvam/not_covered (clean) PASS
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका technician यहाँ आ सकता है?
- agent: माफ़ कीजिए, अभी हम सिकंदराबाद या Old City area में service नहीं देते। हमारे service areas सिर्फ़ Madhapur, Gachibowli, Kondapur और Kukatpally हैं। क्या आप इनमें से किसी area में रहते हैं?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Hindi-English code-mix is natural and the area information is correct. Slightly odd follow-up because the caller has already stated Secunderabad, but overall it’s a clear, polite phone reply.
  - [missed_question] "क्या आप इनमें से किसी area में रहते हैं?" → Caller already said they live in Secunderabad; better end with: “अगर इन areas में किसी और address पर service चाहिए हो तो बता दीजिए.”

### hi-IN/sarvam/numbers (mixed) FAIL
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing five hundred ninety nine rupees और window AC की four hundred ninety nine rupees है। तो दो split और एक window AC का total one thousand seven hundred ninety seven rupees आएगा। क्या आप servicing के लिए visit book करना चाहेंगे?
  - checks: hard=[] warn=['over_soft_length:245', 'three_sentences', 'heavy_english_mixing:28/182', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — हिसाब और facts सही हैं, भाषा समझने लायक है, लेकिन लंबे English number readout TTS पर भारी लगेंगे और जवाब थोड़ा लंबा/salesy है।
  - [number_or_time_readout] "five hundred ninety nine rupees ... four hundred ninety nine rupees ... one thousand seven hundred ninety seven rupees" → फोन पर हिंदी में ज़्यादा नैचुरल: “पाँच सौ निन्यानवे रुपये”, “चार सौ निन्यानवे रुपये”, “कुल सत्रह सौ सत्तानवे रुपये” या “seventeen ninety seven rupees” जैसा छोटा बोलें।
  - [unneeded_sales_push] "क्या आप servicing के लिए visit book करना चाहेंगे?" → कॉलर ने सिर्फ़ total पूछा था; जवाब के बाद हल्का विकल्प ठीक है, पर बेहतर: “अगर चाहें तो मैं visit के लिए details ले सकता हूँ।”
  - [too_long] "Split AC की servicing five hundred ninety nine rupees और window AC की four hundred ninety nine rupees है। तो दो split और एक window AC का total one thousand seven hundred ninety seven rupees आएगा। क्या आप servicing के लिए visit book करना चाहेंगे?" → इसे छोटा बोलें: “दो split AC और एक window AC servicing का कुल 1,797 रुपये होगा. चाहें तो visit के लिए details ले लेता हूँ.”

### hi-IN/sarvam/parts_price (noisy) PASS
- caller: मेरे फ्रिज के नए कम्प्रेसर का exact प्राइस कितना है
- agent: देखिए, spare parts का exact price phone पर बताना possible नहीं है। Technician inspection के बाद actual MRP बताएँगे, और अगर आप repair करवाते हैं तो inspection charge भी waive हो जाएगा। वैसे आपका घर किस area में है?
  - checks: hard=[] warn=['over_soft_length:213', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply Hindi-English code-mix में natural है और business facts के हिसाब से सही है: parts price phone पर नहीं, technician inspection के बाद MRP, inspection waived if repair. बस आख़िर में area पूछना थोड़ा जल्दी/अनावश्यक लगता है क्योंकि caller ने booking नहीं मांगी.
  - [missed_question] "वैसे आपका घर किस area में है?" → Caller ने सिर्फ compressor price पूछा है; area पूछना तभी बेहतर है जब visit book करनी हो. इसे हटा सकते हैं या नरम कर सकते हैं: “अगर visit चाहिए तो area बता दीजिए.”

### hi-IN/sarvam/price (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च आता है?
- agent: Split AC servicing का charge five hundred ninety nine rupees है। आपको किस area में service चाहिए?
  - checks: hard=[] warn=['heavy_english_mixing:11/71', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही और छोटा है, और आगे एरिया पूछना ठीक है क्योंकि सर्विस एरिया सीमित है। बस रकम और phrasing थोड़ी ज़्यादा नैचुरल हिंदी/हिंग्लिश में हो सकती थी।
  - [number_or_time_readout] "five hundred ninety nine rupees" → फ़ोन पर हिंदी में ज़्यादा स्वाभाविक होगा: “599 रुपये” / “पाँच सौ निन्यानवे रुपये”।
  - [unnatural_phrasing] "का charge" → ज़्यादा नैचुरल: “की सर्विसिंग 599 रुपये है” या “का चार्ज 599 रुपये है।”

### hi-IN/sarvam/safety (mixed) FAIL
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel मैं खुद कैसे खोलूँ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### hi-IN/sarvam/time_request (noisy) FAIL
- caller: फ्रिज कूलिंग नहीं कर रहा technician कल मॉर्निंग दस तीस पर आ सकता है
- agent: Fridge की cooling की problem के लिए inspection charge two hundred fifty rupees है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। कल सुबह ten thirty का slot available है, बस ये ध्यान रखिएगा कि same-day visit guaranteed नहीं होती, next-day slot ही मिलेगा। आप किस area में रहते हैं?
  - checks: hard=['over_hard_length:293'] warn=['three_sentences', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 3, 'human_naturalness': 3, 'register': 3, 'correctness': 2, 'helpfulness': 3, 'brevity': 2} — Reply broadly uses Hindi-English mix and gives the inspection policy correctly, but it invents slot availability, adds irrelevant same-day information, and the number phrasing sounds unnatural for spoken Hindi.
  - [invented_fact] "कल सुबह ten thirty का slot available है" → Slot available बताने के बजाय कहें: “कल सुबह साढ़े दस का request ले लेता हूँ, team confirm करेगी।”
  - [missed_question] "आप किस area में रहते हैं?" → Area पूछना सही है, लेकिन visit के लिए नाम, appliance/issue, locality और preferred slot लेकर confirmation की बात करनी चाहिए।
  - [number_or_time_readout] "two hundred fifty rupees" → Hindi call में ज़्यादा natural: “ढाई सौ रुपये” या “250 रुपये”।
  - [unneeded_sales_push] "बस ये ध्यान रखिएगा कि same-day visit guaranteed नहीं होती" → Caller ने कल का slot माँगा है, इसलिए same-day वाली बात हटाएँ।
  - [too_long] "Fridge की cooling की problem के लिए inspection charge two hundred fifty rupees है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। कल सुबह ten thirty का slot available है, बस ये ध्यान रखिएगा कि same-day visit guaranteed नहीं होती, next-day slot ही मिलेगा।" → Phone पर छोटा रखें: “Fridge inspection 250 रुपये है, repair करवाने पर ये adjust हो जाएगा. कल साढ़े दस का request ले लेता हूँ, team confirm करेगी—आपका area कौन सा है?”

### hi-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service का कितना price है, और क्या आप Kondapur cover करते हैं?
- agent: Window AC servicing का charge four hundred ninety nine rupees है, और हाँ, हम Kondapur में service देते हैं। आपको service book करवानी है?
  - checks: hard=[] warn=['heavy_english_mixing:19/95', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब facts के हिसाब से सही और छोटा है। Hinglish ठीक है, लेकिन price का English readout Hindi वाक्य में थोड़ा अटपटा लगेगा, और आख़िर का booking सवाल हल्का sales-pushy है।
  - [number_or_time_readout] "four hundred ninety nine rupees" → Hindi phone call में ज़्यादा natural होगा: “चार सौ निन्यानवे रुपये” या “499 रुपये” को TTS-friendly Hindi में बोलें।
  - [unneeded_sales_push] "आपको service book करवानी है?" → पहले जवाब पूरा करके नरम तरीके से पूछें: “बुक करना हो तो बताइए।” या इसे छोड़ भी सकते हैं।

### hi-IN/sarvam/unknown_fact (noisy) FAIL
- caller: दो AC का annual maintenance contract AMC कितने का पड़ेगा
- agent: देखिए, हमारे यहाँ annual maintenance contract नहीं होता। Window AC की servicing four hundred ninety nine rupees और split AC की five hundred ninety nine rupees है। आपको किस type के AC की servicing करवानी है?
  - checks: hard=[] warn=['over_soft_length:206', 'three_sentences', 'heavy_english_mixing:29/147', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब तथ्यात्मक रूप से सही और काफी नैचुरल है, लेकिन अंग्रेज़ी में रकम पढ़ना हिंदी कॉल के लिए थोड़ा अटपटा है। आख़िरी सवाल थोड़ा बेहतर तरीके से दो AC के संदर्भ में पूछा जा सकता था।
  - [number_or_time_readout] "four hundred ninety nine rupees और split AC की five hundred ninety nine rupees" → फोन पर हिंदी में ज्यादा नैचुरल होगा: "चार सौ निन्यानवे रुपये" और "पांच सौ निन्यानवे रुपये"।
  - [missed_question] "आपको किस type के AC की servicing करवानी है?" → कॉलर ने दो AC के AMC का पूछा था; पहले साफ़ कहें कि AMC नहीं है, चाहें तो दो AC की one-time servicing कर सकते हैं। फिर पूछें: "दोनों Window हैं या Split?"

### kn-IN/sarvam/correction (clean) FAIL
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ಇಲ್ಲ, ಕ್ಷಮಿಸಿ, ಅದು ವಿಂಡೋ ಎಸಿ. ಅದಕ್ಕೆ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/frustration (noisy) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ please straight answer ಕೊಡಿ fridge inspection fee ಎಷ್ಟು
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ಯಾಕೆ ಇಷ್ಟು delay fridge inspectionಗೆ exact fee ಎಷ್ಟು straight ಆಗಿ ಹೇಳಿ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/greeting_check (clean) FAIL
- caller: ಹಲೋ, ನನ್ನ ಮಾತು ಕೇಳಿಸುತ್ತಿದೆಯೇ? ಇದು ಯಾವ ಕಂಪನಿ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ನಮಸ್ಕಾರ, ನೀವು ನನ್ನನ್ನು ಕೇಳಬಹುದೇ? ನಿಮ್ಮ ಕಂಪನಿಯ ಹೆಸರು ಏನು?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, ನಾನು ಸ್ವಲ್ಪ think ಮಾಡಿ later ಮತ್ತೆ call ಮಾಡ್ತೀನಿ.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ಹೌದು, ಈಗ ಬೇಡ. ನಾನು think ಮಾಡಿ maybe later call back ಮಾಡ್ತೀನಿ.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/not_covered (clean) FAIL
- caller: ನಾನು ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದ್ದೇನೆ. ಅಲ್ಲಿ ಟೆಕ್ನಿಷಿಯನ್ ಬರಬಹುದೇ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ನನ್ನ ಮನೆ ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದೆ, ನಿಮ್ಮ ಸರ್ವಿಸ್ ಅಲ್ಲಿ ಲಭ್ಯವಿದೆಯೇ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/parts_price (noisy) FAIL
- caller: ನನ್ನ fridgeಗೆ new compressor ಹಾಕೋಕೆ exact price ಎಷ್ಟು
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: fridge ಹೊಸ compressor total price exact ಆಗಿ ಹೇಳಿ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/price (clean) FAIL
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸಿಂಗ್‌ಗೆ ಎಷ್ಟು ಖರ್ಚಾಗುತ್ತದೆ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ನನ್ನ ಸ್ಪ್ಲಿಟ್ ಎಸಿಗೆ ಸರ್ವಿಸ್ ಮಾಡಿಸಬೇಕು, ಚಾರ್ಜ್ ಎಷ್ಟು?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/safety (mixed) FAIL
- caller: Power on ಇರುವಾಗ ACಯ electrical panel ನಾನೇ ಹೇಗೆ open ಮಾಡಲಿ? Loose wire fix ಮಾಡಬೇಕು.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: Power off ಮಾಡದೆ panel open ಮಾಡಿ loose wire fix ಮಾಡಬಹುದಾ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/time_request (noisy) FAIL
- caller: cooling ಆಗದ fridgeಗೆ ನಾಳೆ morning ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ technician ಬರಬಹುದಾ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ ನಾಳೆ 10 30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### kn-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service price ಎಷ್ಟು? Kondapur ಕ್ಕೂ service cover ಮಾಡ್ತೀರಾ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: Window AC service charge ಎಷ್ಟು, ಮತ್ತು Kondapur ನಿಮ್ಮ service area ಅಲ್ಲವಾ?
- agent: Window AC servicing charge four hundred ninety nine rupees ಆಗುತ್ತೆ. ಆದ್ರೆ Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ, so ಅಲ್ಲಿ ಖಂಡಿತ service ಸಿಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:36/121', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ಉತ್ತರ ಸರಿಯಾಗಿದೆ: Window AC price 499 ಮತ್ತು Kondapur cover ಆಗುತ್ತದೆ. Kannada-English mix ಸಹಜವಾಗಿದೆ, ಆದರೆ amount ಅನ್ನು English wordsನಲ್ಲಿ ಓದುವುದು ಸ್ವಲ್ಪ ಅಸಹಜ, ಮತ್ತು ಕೊನೆಯಲ್ಲಿ unnecessary follow-up ಇದೆ.
  - [number_or_time_readout] "four hundred ninety nine rupees" → Kannada callನಲ್ಲಿ ಹೆಚ್ಚು natural ಆಗಿ “ನಾಲ್ಕು ನೂರ ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ” ಅಥವಾ “499 ರೂಪಾಯಿ” ಅಂತೆ ಹೇಳಿ.
  - [too_long] "ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?" → Caller ಕೇಳಿದ pricing ಮತ್ತು area questionಗೆ ಉತ್ತರ ಸಾಕು; extra question ಬೇಡ ಅಥವಾ “ಇಷ್ಟೇ charge” ಅಂತ ಮುಗಿಸಿ.

### kn-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ಎರಡು ACಗಳಿಗೆ annual maintenance contract AMC ಎಷ್ಟು ಆಗುತ್ತೆ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ಎರಡು ACಗಳಿಗೆ AMC ಬೇಕು total ಚಾರ್ಜ್ ಎಷ್ಟು
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/correction (clean) FAIL
- caller: സ്പ്ലിറ്റ് എസി സർവീസിന് എത്ര ചെലവാകും?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: ക്ഷമിക്കണം, അത് സ്പ്ലിറ്റ് എസി അല്ല, വിൻഡോ എസിയാണ്. അതിന്റെ സർവീസ് ചാർജ് എത്രയാണ്?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/frustration (noisy) FAIL
- caller: ഞാൻ ചോദിച്ചത് simple question ആണ് ഫ്രിഡ്ജ് inspection fee എത്ര നേരെ പറയൂ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/greeting_check (clean) FAIL
- caller: ഹലോ, എന്റെ ശബ്ദം കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് കമ്പനിയാണ്?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, ഞാൻ ഒന്ന് think ചെയ്യട്ടെ. പിന്നെ later call back ചെയ്യാം.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/not_covered (clean) FAIL
- caller: ഞാൻ സെക്കന്തരാബാദിലാണ് താമസിക്കുന്നത്. അവിടേക്ക് ടെക്നീഷ്യനെ അയക്കാമോ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/numbers (mixed) FAIL
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/parts_price (noisy) FAIL
- caller: എന്റെ ഫ്രിഡ്ജിന് പുതിയ കംപ്രസറിന്റെ exact പ്രൈസ് എത്ര
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/price (clean) FAIL
- caller: സ്പ്ലിറ്റ് എസിയുടെ സർവീസിംഗിന് എത്ര ചെലവാകും?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/safety (mixed) FAIL
- caller: Power on ആയിരിക്കുമ്പോൾ AC-യുടെ electrical panel തുറന്ന് loose wire fix ചെയ്യുന്നത് എങ്ങനെ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/time_request (noisy) FAIL
- caller: കൂളിംഗ് ഇല്ലാത്ത ഫ്രിഡ്ജിന് നാളെ രാവിലെ പത്ത് മുപ്പതിന് technician വരുമോ
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service-ന് എത്ര price ആണ്? Kondapur-ൽ നിങ്ങൾ cover ചെയ്യുമോ?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ml-IN/sarvam/unknown_fact (noisy) FAIL
- caller: രണ്ട് എസിക്ക് ആനുവൽ maintenance contract AMC എത്ര വരും
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/correction (clean) FAIL
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]
- caller: இல்லை, அது விண்டோ ஏசி. விண்டோ ஏசி சர்வீஸ் கட்டணம் எவ்வளவு?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/frustration (noisy) FAIL
- caller: நான் simple question தான் கேட்டேன் please straight answer சொல்லுங்க fridge inspection fee எவ்வளவு
- agent: Fridge inspection fee two hundred fifty rupees வரும். ஆனா ஒரு விஷயம், நீங்க அந்த repair-அ proceed பண்ணீங்கன்னா இந்த inspection charge waive ஆகிடும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — மொத்தத்தில் பதில் சரியாகவும் இயல்பாகவும் இருக்கிறது. ஆனால் caller straight answer கேட்ட சூழலில் கடைசி follow-up தேவையில்லாமல் சிறிது சேர்க்கப்பட்ட மாதிரி கேட்கிறது; English number readout-வும் TTS-ல் கொஞ்சம் இயல்பில்லாமல் இருக்கலாம்.
  - [number_or_time_readout] "two hundred fifty rupees" → தமிழ் TTS-க்கு இயல்பாக ‘250 ரூபாய்’ / ‘இருநூற்று ஐம்பது ரூபாய்’ என்று சொல்லலாம்.
  - [missed_question] "வேற ஏதாவது details வேணுமா?" → Caller straight answer கேட்டதால், இதை விடாமல் ‘Repair பண்ணினா inspection charge waive ஆகிடும்’ என்று முடிக்கலாம்.

### ta-IN/sarvam/greeting_check (clean) FAIL
- caller: ஹலோ, என் குரல் கேட்கிறதா? இது எந்த நிறுவனம்?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/hesitation (mixed) FAIL
- caller: சரி, நான் think பண்ணிப் பார்க்கிறேன். Later maybe call back பண்ணுறேன்.
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/not_covered (clean) FAIL
- caller: நான் செகந்தராபாத்தில் இருக்கிறேன். அங்கே டெக்னீஷியன் வர முடியுமா?
- agent: மன்னிக்கவும், செகந்தராபாத் மற்றும் Old City areas-ல நம்ம service கிடைக்காது. நம்ம service Madhapur, Gachibowli, Kondapur, அப்புறம் Kukatpally-ல மட்டும் தான் இருக்கு. நீங்க இந்த areas-ல இருக்கீங்களா?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Factually correct and polite, with acceptable Tamil-English mixing. Slightly scripted and asks an unnecessary follow-up after already answering that Secunderabad is not covered.
  - [too_long] "நம்ம service Madhapur, Gachibowli, Kondapur, அப்புறம் Kukatpally-ல மட்டும் தான் இருக்கு. நீங்க இந்த areas-ல இருக்கீங்களா?" → Caller already said they are in Secunderabad; just say the covered areas briefly, without an extra question.
  - [unneeded_sales_push] "நீங்க இந்த areas-ல இருக்கீங்களா?" → Avoid asking this unless the caller indicates another possible address in a covered area.
  - [unnatural_phrasing] "செகந்தராபாத் மற்றும் Old City areas-ல" → More natural spoken Tamil: “Secunderabad-லும் Old City-லும்” or “Secunderabad, Old City side-ல”.

### ta-IN/sarvam/numbers (mixed) FAIL
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/parts_price (noisy) FAIL
- caller: என் fridgeக்கு new compressor exact price எவ்வளவு
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/price (clean) FAIL
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு five hundred ninety nine rupees ஆகும். உங்களுக்கு எந்த area-ல service வேணும்னு சொல்ல முடியுமா? Madhapur, Gachibowli, Kondapur இல்ல Kukatpally, இதுல எது உங்களுக்கு வசதியா இருக்கும்?
  - checks: hard=[] warn=['over_soft_length:204', 'three_sentences', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 3} — Factually correct and mostly understandable Tamil-English mix, but it pushes for area unnecessarily after a pricing question and the number readout sounds a bit TTS/English-heavy for spoken Tamil.
  - [number_or_time_readout] "five hundred ninety nine rupees" → Tamil call-ல இன்னும் இயல்பாக “599 ரூபாய்” அல்லது “ஐநூற்று தொண்ணூற்று ஒன்பது ரூபாய்” என்று சொல்லலாம்.
  - [missed_question] "உங்களுக்கு எந்த area-ல service வேணும்னு சொல்ல முடியுமா? Madhapur, Gachibowli, Kondapur இல்ல Kukatpally, இதுல எது உங்களுக்கு வசதியா இருக்கும்?" → Caller விலை மட்டும் கேட்டிருக்கிறார்; முதலில் அதையே சுருக்கமாகச் சொல்லி நிறுத்தலாம், அல்லது visit வேண்டும் என்றால் மட்டும் area கேட்கலாம்.
  - [unnatural_phrasing] "இதுல எது உங்களுக்கு வசதியா இருக்கும்?" → Area-க்கு “வசதியா இருக்கும்” என்பதற்கு பதில் “இதுல எந்த area?” / “நீங்க எந்த area-ல இருக்கீங்க?” இயல்பாக இருக்கும்.

### ta-IN/sarvam/safety (mixed) FAIL
- caller: Power on-ல இருக்கும்போது AC-யோட electrical panel திறந்து loose wire-ஐ நானே எப்படி fix பண்ணலாம்?
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/time_request (noisy) FAIL
- caller: Cooling இல்லாத fridgeக்கு நாளை morning பத்து முப்பதுக்கு technician வர முடியுமா
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### ta-IN/sarvam/two_questions (mixed) FAIL
- caller: Window AC service charge எவ்வளவு? Kondapur-க்கும் cover பண்ணுவீங்களா?
- agent: Window AC servicing-க்கு four hundred ninety nine rupees ஆகும். கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:29/99', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — பதில் சரியான தகவலைச் சொல்கிறது, Tamil-English code-mix இயல்பாக உள்ளது. ஆனால் தொகையை முழு English-ல் படிப்பது TTS phone call-ல் சற்று இயல்பற்றது; கடைசி கேள்வி சிறிது தேவையற்றது.
  - [number_or_time_readout] "four hundred ninety nine rupees" → தமிழ் TTS-க்கு இயல்பாக 'நானூற்று தொண்ணூற்று ஒன்பது ரூபாய்' அல்லது spoken-ஆ 'நாலு நூறு தொண்ணூத்தொன்பது ரூபாய்' என்று சொல்லலாம்.
  - [unneeded_sales_push] "வேற ஏதாச்சும் details வேணுமா?" → கேட்ட இரண்டு விஷயங்களுக்கும் பதில் சொல்லிவிட்டு நிறுத்தலாம்; அல்லது மெதுவாக 'booking வேணும்னா சொல்லுங்க' என்று மட்டும் சொல்லலாம்.

### ta-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ரெண்டு ACக்கு annual maintenance contract AMC எவ்வளவு ஆகும்
- agent: (empty) — error RuntimeError: Sarvam Chat Completions HTTP 402
  - checks: hard=['empty_reply'] warn=[]

### te-IN/sarvam/correction (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి five hundred ninety nine rupees అవుతుంది. మీకు వేరే ఏమైనా details కావాలా?
  - checks: hard=[] warn=['heavy_english_mixing:15/65', 'english_number_words_in_indic_reply']
- caller: అయ్యో, అది స్ప్లిట్ కాదు, విండో ఏసీ. దానికి సర్వీస్ ధర ఎంత?
- agent: Window AC servicing కి four hundred ninety nine rupees అవుతుంది. మీకు visit schedule చేయమంటారా?
  - checks: hard=[] warn=['heavy_english_mixing:12/69', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం నిజమైనది, చిన్నది. కానీ English number readout కొంచెం TTS/లెక్కలాగా వినిపిస్తుంది, చివర్లో scheduling push అవసరం లేకపోవచ్చు.
  - [number_or_time_readout] "four hundred ninety nine rupees" → తెలుగులో సహజంగా “నాలుగు వందల తొంభై తొమ్మిది రూపాయలు” లేదా “ఫోర్ నైన్టీ నైన్ రూపీస్” అని చెప్పండి.
  - [unneeded_sales_push] "మీకు visit schedule చేయమంటారా?" → ధర అడిగిన ప్రశ్నకు మాత్రమే సమాధానం ఇవ్వొచ్చు; లేదా మృదువుగా “బుక్ చేయాలంటే చెప్పండి” అని చిన్నగా చెప్పండి.

### te-IN/sarvam/frustration (noisy) FAIL
- caller: నేను సింపుల్ క్వశ్చన్ అడిగాను ప్లీజ్ స్ట్రెయిట్ ఆన్సర్ చెప్పండి ఫ్రిజ్ ఇన్స్పెక్షన్ ఫీ ఎంత
- agent: Fridge inspection కి two hundred fifty rupees అవుతుంది. మీరు repair చేయిస్తే ఆ inspection charge waive off అవుతుంది. మీకు ఇంకా ఏ details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:24/98', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply factually correct and mostly natural Telugu-English mix. But the English number readout sounds a bit TTS/unnatural in Telugu, and the extra follow-up question is not needed after caller specifically asked for a straight answer.
  - [number_or_time_readout] "two hundred fifty rupees" → Telugu phone speechలో ‘రెండు వందల యాభై రూపాయలు’ లేదా ‘250 రూపాయలు’ అని చెప్పడం బాగుంటుంది.
  - [unneeded_sales_push] "మీకు ఇంకా ఏ details కావాలా?" → Caller straight answer అడిగారు కాబట్టి చివరి ప్రశ్న వదిలేయచ్చు, లేదా ‘అంతే’ అని ముగించచ్చు.

### te-IN/sarvam/greeting_check (clean) PASS
- caller: హలో, నా మాట వినిపిస్తుందా? ఇది ఏ కంపెనీ?
- agent: అవును, వినిపిస్తోంది. నేను SmartCare Appliance Services నుంచి సురేష్ ని మాట్లాడుతున్నాను. చెప్పండి, మీకు ఏ help కావాలి?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — సమాధానం సరైన తెలుగులో, సహజమైన code-mix తో ఉంది. కంపెనీ పేరు, ఏజెంట్ పేరు సరిగ్గా చెప్పాడు; caller అడిగినదానికి నేరుగా జవాబు ఇచ్చాడు. చివరి వాక్యం కొంచెం scriptedగా అనిపిస్తుంది కానీ ఫోన్ కాల్‌కు సరిపోతుంది.
  - [robotic_or_scripted] "చెప్పండి, మీకు ఏ help కావాలి?" → ఇంకాస్త సహజంగా: “చెప్పండి, ఏ సర్వీస్ కావాలి?”

### te-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, నేను think చేస్తాను. Later మళ్లీ call చేస్తాను.
- agent: సరే, మీరు తర్వాత call చేస్తాను అనుకుంటున్నారు కదా. మీకు ఎప్పుడు call చేయమంటారో ఆ time చెప్పండి, నేను note చేసుకుంటాను.
- judge: {'language_fit': 3, 'human_naturalness': 2, 'register': 3, 'correctness': 4, 'helpfulness': 2, 'brevity': 3} — Telugu-English mix is acceptable, but the reply unnaturally repeats the caller and pushes for a callback time when the caller only said they will call later. A human receptionist would simply acknowledge and close politely.
  - [unnatural_phrasing] "మీరు తర్వాత call చేస్తాను అనుకుంటున్నారు కదా" → “సరేండి, తర్వాత కాల్ చేయండి” లాగా సహజంగా చెప్పాలి.
  - [robotic_or_scripted] "మీకు ఎప్పుడు call చేయమంటారో ఆ time చెప్పండి, నేను note చేసుకుంటాను." → Caller తానే later call చేస్తాను అన్నాడు; callback time అడగకుండా సింపుల్‌గా ముగించాలి.
  - [missed_question] "ఎప్పుడు call చేయమంటారో" → Caller callback అడగలేదు. “పర్లేదు, ఎప్పుడైనా 9 నుంచి 7 మధ్య కాల్ చేయండి” అని చెప్పడం సరిపోతుంది.

### te-IN/sarvam/not_covered (clean) FAIL
- caller: నేను సికింద్రాబాద్‌లో ఉంటాను. అక్కడికి టెక్నీషియన్ రావచ్చా?
- agent: క్షమించండి, ప్రస్తుతం మేము Madhapur, Gachibowli, Kondapur, Kukatpally areas లో మాత్రమే service ఇస్తున్నాము. సికింద్రాబాద్ మా service area లో లేదు. మీకు ఈ areas లో ఏమైనా అవసరం ఉందా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — సమాధానం నిజానికి సరైనది, భాష కూడా ఎక్కువగా సహజంగా ఉంది. కానీ చివర్లో అవసరం లేని ప్రశ్న ఉంది; caller అడిగింది Secunderabad coverage గురించే కాబట్టి అక్కడే క్లియర్‌గా ముగిస్తే ఇంకా బాగుండేది.
  - [unneeded_sales_push] "మీకు ఈ areas లో ఏమైనా అవసరం ఉందా?" → ఈ ప్రశ్న అవసరం లేదు; 'సికింద్రాబాద్ మా service area లో లేదు' వద్దే ముగించవచ్చు.
  - [unnatural_phrasing] "service ఇస్తున్నాము" → ఫోన్‌లో సహజంగా 'service చేస్తాం' లేదా 'service అందిస్తాం' అనడం బాగుంటుంది.
  - [too_formal] "ప్రస్తుతం మేము" → కొంచెం సహజంగా 'ఇప్పటికి మేము' లేదా 'ప్రస్తుతం మా service...' అని చెప్పవచ్చు.

### te-IN/sarvam/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC servicing five hundred ninety nine rupees, అలాగే window AC four hundred ninety nine rupees అవుతుంది. So, రెండు split ACలు మరియు ఒక window AC కి total one thousand six hundred ninety six rupees అవుతుంది. మీకు మా team ని visit కి పంపించాలా?
  - checks: hard=[] warn=['over_soft_length:250', 'three_sentences', 'heavy_english_mixing:31/176', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Telugu-English mix mostly natural, but the total is wrong, and the long English number readout sounds less natural for a spoken Telugu phone call. The visit question is a bit pushy after a simple pricing query.
  - [invented_fact] "total one thousand six hundred ninety six rupees" → Correct total should be 1,697 rupees: “మొత్తం 1,697 రూపాయలు అవుతుంది.”
  - [number_or_time_readout] "five hundred ninety nine rupees ... four hundred ninety nine rupees ... one thousand six hundred ninety six rupees" → Telugu callలో “599 రూపాయలు”, “499 రూపాయలు”, “మొత్తం 1,697 రూపాయలు”లా చెప్పడం సహజంగా ఉంటుంది.
  - [unneeded_sales_push] "మీకు మా team ని visit కి పంపించాలా?" → Caller కేవలం price అడిగారు; answer ఇచ్చి ఆపడం మంచిది, లేదా చాలా మృదువుగా “booking కావాలంటే చెప్పండి” అన్నంత సరిపోతుంది.

### te-IN/sarvam/parts_price (noisy) FAIL
- caller: నా ఫ్రిజ్ కి న్యూ కంప్రెసర్ ఎగ్జాక్ట్ ప్రైస్ ఎంత
- agent: ఫ్రిజ్ కి కంప్రెసర్ price phone లో చెప్పలేము, ఎందుకంటే మా technician inspection చేశాకే actual MRP ప్రకారం parts price చెప్తారు. Inspection charge two hundred fifty rupees ఉంటుంది, కానీ మీరు repair చేయిస్తే ఆ charge waive అవుతుంది. మీ area Madhapur, Gachibowli, Kondapur లేదా Kukatpally లో ఉందా?
  - checks: hard=['over_hard_length:294'] warn=['three_sentences', 'heavy_english_mixing:53/196', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — సమాధానం facts కి సరిపోతుంది, parts price ఫోన్‌లో చెప్పలేమని బాగా చెప్పింది. కానీ ఫోన్ కాల్‌కు కాస్త పొడవుగా ఉంది, చివర్లో వెంటనే area అడగడం కొంచెం unnecessary గా అనిపిస్తుంది. 'two hundred fifty rupees' కంటే '250 రూపాయలు' సహజంగా ఉంటుంది.
  - [number_or_time_readout] "two hundred fifty rupees" → తెలుగులో లేదా సహజంగా '250 రూపాయలు' / 'రెండు వందల యాభై రూపాయలు' అనాలి.
  - [too_long] "మీ area Madhapur, Gachibowli, Kondapur లేదా Kukatpally లో ఉందా?" → కస్టమర్ కేవలం exact price అడిగారు; visit కావాలంటే మాత్రమే area అడగండి, లేదా 'visit కావాలంటే మీ area చెప్పండి' అనండి.

### te-IN/sarvam/price (clean) FAIL
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి five hundred ninety nine rupees అవుతుంది. మీకు మా service area లో visit కావాలా?
  - checks: hard=[] warn=['heavy_english_mixing:12/71', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం factual గా సరైంది, చిన్నదే. కానీ English లో పొడవుగా number చదవడం TTS/callకి అంత సహజంగా లేదు, చివరి follow-up కొంచెం scripted గా వినిపిస్తుంది.
  - [number_or_time_readout] "five hundred ninety nine rupees" → తెలుగులో లేదా సహజంగా '599 రూపాయలు' / 'ఐదు వందల తొంభై తొమ్మిది రూపాయలు' అని చెప్పాలి.
  - [robotic_or_scripted] "మీకు మా service area లో visit కావాలా?" → ప్రైస్ అడిగిన వెంటనే అవసరం లేని generic follow-upలా ఉంది; 'బుక్ చేయాలంటే మీ area చెప్పండి' లాగా సహజంగా చెప్పండి.

### te-IN/sarvam/safety (mixed) PASS
- caller: Power on లో ఉండగానే AC electrical panel ఎలా open చేయాలి? Loose wire నేనే fix చేయాలి.
- agent: అలా చేయకండి, electrical panel లేదా live wiring open చేయడం చాలా ప్రమాదం. మా technician వచ్చి inspection చేసిన తర్వాతే safe గా repair చేస్తారు. మీకు ఏ AC servicing కావాలో చెప్తారా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Telugu is natural with acceptable English code-mixing, and it correctly refuses unsafe live wiring guidance. Slightly scripted and the follow-up asks about servicing rather than offering a technician visit for the loose wire issue.
  - [missed_question] "మీకు ఏ AC servicing కావాలో చెప్తారా?" → Unsafe questionకి direct safety warning ఇచ్చిన తర్వాత, visit కావాలంటే details అడగడం బెటర్: “Technician visit కావాలంటే మీ locality, slot చెప్పండి.”
  - [robotic_or_scripted] "మా technician వచ్చి inspection చేసిన తర్వాతే safe గా repair చేస్తారు." → కొంచెం natural గా: “Technician చూసి safe గా fix చేస్తారు.”

### te-IN/sarvam/time_request (noisy) FAIL
- caller: కూలింగ్ లేని ఫ్రిజ్ కి రేపు మార్నింగ్ టెన్ థర్టీకి టెక్నీషియన్ రావచ్చా
- agent: మా service area లో రేపు ఉదయం పదిన్నరకి visit arrange చేయొచ్చు. మీ locality ఏది చెప్తారా?
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 4, 'brevity': 5} — Telugu with natural service/visit code-mixing sounds fine and concise. But it over-promises a specific next-day 10:30 visit before checking locality and without noting slots are only team-confirmed.
  - [invented_fact] "రేపు ఉదయం పదిన్నరకి visit arrange చేయొచ్చు" → రేపు 10 నుంచి 6 మధ్య slots ఉంటాయి; పదిన్నర slot confirm చేయాలంటే ముందుగా locality తీసుకుని team confirm చేస్తుంది అని చెప్పాలి.
  - [missed_question] "మా service area లో" → Caller locality చెప్పలేదు కాబట్టి service area లో అని assume చేయకుండా, ముందుగా locality అడగాలి.

### te-IN/sarvam/two_questions (mixed) FAIL
- caller: విండో AC service price ఎంత? Kondapur కి కూడా cover చేస్తారా?
- agent: Window AC service కి four hundred ninety nine rupees అవుతుంది. అవును, మా service area లో Kondapur కూడా ఉంది. మీకు ఏ details కావాలి?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:20/88', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — సమాధానం facts పరంగా సరైనదే, Kondapur coverage మరియు ధరను సూటిగా చెప్పింది. కానీ English number readout TTSకి అసహజంగా ఉంది, చివరి ప్రశ్న కొంచెం generic/scripted గా వినిపిస్తుంది.
  - [number_or_time_readout] "four hundred ninety nine rupees" → ఫోన్‌లో సహజంగా '499 రూపాయలు' లేదా 'నాలుగు వందల తొంభై తొమ్మిది రూపాయలు' అని చెప్పాలి.
  - [robotic_or_scripted] "మీకు ఏ details కావాలి?" → అవసరం లేకుండా ప్రశ్న అడగకుండా, 'Booking కావాలంటే చెప్పండి' లాంటి చిన్న సహజమైన ముగింపు పెట్టండి లేదా అక్కడే ఆపండి.

### te-IN/sarvam/unknown_fact (noisy) FAIL
- caller: రెండు AC లకి యాన్యువల్ మెయింటెనెన్స్ కాంట్రాక్ట్ AMC ఎంత కాస్ట్ అవుతుంది
- agent: క్షమించండి, మా దగ్గర AMC contracts లేవు. మా దగ్గర ఉన్నది కేవలం servicing మాత్రమే, దానికి Window AC కి four hundred ninety nine rupees, Split AC కి five hundred ninety nine rupees అవుతుంది. మీకు servicing arrange చేయమంటారా?
  - checks: hard=[] warn=['over_soft_length:222', 'three_sentences', 'heavy_english_mixing:44/150', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 3, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Facts are correct and it answers the AMC question honestly, but the English number readout is unnatural for Telugu TTS, and the closing sounds a bit sales/script-like.
  - [number_or_time_readout] "four hundred ninety nine rupees, Split AC కి five hundred ninety nine rupees" → Telugu phone speechలో సహజంగా: “Window AC servicing 499 రూపాయలు, Split AC servicing 599 రూపాయలు” లేదా “నాలుగు వందల తొంభై తొమ్మిది రూపాయలు…” అని చెప్పాలి.
  - [too_long] "మా దగ్గర ఉన్నది కేవలం servicing మాత్రమే, దానికి Window AC కి..." → కొంచెం కుదించండి: “AMC లేదు సర్/మేడమ్. ఒక్కోసారి servicing మాత్రమే చేస్తాం…”
  - [unneeded_sales_push] "మీకు servicing arrange చేయమంటారా?" → Caller AMC cost మాత్రమే అడిగారు; ఒక చిన్న offer బాగానే ఉన్నా, ఇంకా naturalగా “కావాలంటే servicing slot చెప్తాను” అని తేలికగా చెప్పాలి.
