# Language probe language-probe-v3-sarvam

Schema `sim_c61d0962505543319f1d5efa2be09951`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | sarvam | 7/13 | 4.40 | human_naturalness 3.69 |
| gu-IN | sarvam | 9/13 | 4.40 | human_naturalness 3.85 |
| hi-IN | sarvam | 8/13 | 4.28 | human_naturalness 3.85 |
| kn-IN | sarvam | 6/13 | 4.22 | human_naturalness 3.77 |
| ml-IN | sarvam | 8/13 | 4.38 | human_naturalness 3.85 |
| ta-IN | sarvam | 9/13 | 4.33 | human_naturalness 3.85 |
| te-IN | sarvam | 6/13 | 4.22 | human_naturalness 3.69 |

## Transcripts

### en-IN/sarvam/correction (clean) PASS
- caller: How much do you charge for split AC servicing?
- agent: Split AC servicing costs 599 rupees. Which area are you located in?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: Actually, it is a window AC, not a split AC. How much would the service cost?
- agent: Window AC servicing is 499 rupees. Which locality are you in?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Clear, correct Indian English and brief. The follow-up area question is reasonable for booking/serviceability, but slightly unnecessary since the caller only asked the cost.
  - [other] "Which locality are you in?" → If only answering the price, stop after the price, unless trying to check serviceability for a visit.

### en-IN/sarvam/frustration (noisy) FAIL
- caller: I asked simple question just tell me clearly fridge inspection charge
- agent: The fridge inspection charge is two hundred and fifty rupees. However, if you go ahead with the repair, that inspection fee will be waived. Is there anything else you would like to know?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Factually correct and in the right language, but a bit scripted and longer than needed for an irritated caller asking for a simple clear answer.
  - [robotic_or_scripted] "However, if you go ahead with the repair, that inspection fee will be waived." → Use more natural spoken phrasing: “If you get the repair done, we’ll adjust that charge.”
  - [missed_question] "Is there anything else you would like to know?" → Avoid appending a generic question after the caller asked for a clear direct answer; just answer the charge.

### en-IN/sarvam/greeting_check (clean) PASS
- caller: Hello, can you hear me? Which company is this?
- agent: This is SmartCare Appliance Services. How can I help you today?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Clear, correct Indian English response. Slightly scripted because it repeats the standard help prompt, but it answers the caller’s question naturally enough for a phone receptionist.

### en-IN/sarvam/hesitation (mixed) PASS
- caller: Let me think about it, I may call back later.
- agent: Of course, take your time. Just let me know whenever you are ready to reach out.
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct and polite Indian English, and it answers the caller appropriately. Slightly corporate phrasing; a receptionist would more naturally say, "Sure, take your time. You can call us back anytime."
  - [unnatural_phrasing] "whenever you are ready to reach out" → Say "You can call us back anytime" or "Call us back whenever you're ready."

### en-IN/sarvam/not_covered (clean) FAIL
- caller: I live in Secunderabad. Can a technician come there?
- agent: Unfortunately, we do not cover Secunderabad right now. Our service areas are limited to Madhapur, Gachibowli, Kondapur, and Kukatpally only. Is there anything else I can help you with?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Correct and in Indian English, but it sounds a bit scripted and slightly long for a direct area-coverage answer.
  - [robotic_or_scripted] "Is there anything else I can help you with?" → Drop this or make it more natural, e.g. “Sorry about that.”
  - [too_long] "Our service areas are limited to Madhapur, Gachibowli, Kondapur, and Kukatpally only." → Shorten for a phone call: “We only cover Madhapur, Gachibowli, Kondapur and Kukatpally.”

### en-IN/sarvam/numbers (mixed) PASS
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For two split ACs, that is one thousand one hundred and ninety eight rupees, and one window AC is four hundred and ninety nine rupees. So, the total comes to one thousand six hundred and ninety seven rupees.
  - checks: hard=[] warn=['over_soft_length:207']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Correct pricing and total, in appropriate Indian English. Slightly wordy and calculated-sounding for a phone call, but still clear and natural enough.
  - [robotic_or_scripted] "For two split ACs, that is one thousand one hundred and ninety eight rupees, and one window AC is four hundred and ninety nine rupees." → Make it a bit more conversational: "Two split ACs will be ₹1,198, and one window AC is ₹499."

### en-IN/sarvam/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: Yes, we cover Kondapur. For a split AC, servicing is five hundred and ninety nine rupees. Since same-day visits are not guaranteed, we can book you for a next-day slot between 10 AM and 6 PM. What is your name, so I can note this down?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:235', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 3} — Mostly understandable Indian English and factually close, but it misframes the caller’s tomorrow request as same-day, slightly overconfirms the booking, and gives extra pricing before answering the slot question cleanly.
  - [missed_question] "Since same-day visits are not guaranteed" → Caller asked for tomorrow morning, so say: “Tomorrow is possible as a next-day request; morning availability will need confirmation.”
  - [invented_fact] "we can book you for a next-day slot between 10 AM and 6 PM" → Do not confirm booking directly; say the team can confirm the slot after taking details.
  - [too_long] "For a split AC, servicing is five hundred and ninety nine rupees. Since same-day visits are not guaranteed, we can book you for a next-day slot between 10 AM and 6 PM." → Keep it shorter and focused: “Yes, Kondapur is covered. Tomorrow between 10 AM and 6 PM is possible, and the team can confirm a morning slot.”

### en-IN/sarvam/parts_price (noisy) FAIL
- caller: how much exactly new fridge compressor cost
- agent: I don't have the price for a new fridge compressor on hand, as spare parts are charged at actual MRP and quoted by the technician only after inspection. Which area are you located in?
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Correct and in Indian English, but slightly scripted and formal for a phone call. It answers the parts-price question honestly, though it could mention the fridge inspection charge and avoid jumping to area unless booking is implied.
  - [robotic_or_scripted] "I don't have the price for a new fridge compressor on hand, as spare parts are charged at actual MRP and quoted by the technician only after inspection." → Make it more conversational: “Sorry, compressor price we can’t confirm on phone. Technician will check and quote the actual MRP after inspection.”
  - [missed_question] "Which area are you located in?" → Only ask locality if moving toward booking; first add the inspection charge if useful: “Fridge inspection is ₹250, and it’s waived if you go ahead with the repair.”

### en-IN/sarvam/price (clean) PASS
- caller: How much do you charge for servicing a split AC?
- agent: Split AC servicing costs 599 rupees. Which area are you located in?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct, natural Indian English and factually accurate. The added area question is a small unnecessary follow-up for a pure pricing question, though it is relevant if trying to book a visit.
  - [missed_question] "Which area are you located in?" → If the caller only asked the price, answer the price without adding a question, unless moving to booking.

### en-IN/sarvam/safety (mixed) FAIL
- caller: Can I open the AC electrical panel with the power on and tighten the loose wire myself?
- agent: No, please do not open the electrical panel or work on live wiring. It is unsafe and can damage the unit. If you have a loose wire, our technician can inspect and fix it safely during a visit. Would you like to book a slot?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:223']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Safe, correct, and in appropriate Indian English. Slightly polished/script-like, but it answers directly and does not give unsafe DIY advice.
  - [robotic_or_scripted] "during a visit. Would you like to book a slot?" → Make it a bit more conversational: “We can send a technician to check it safely. Shall I book a visit?”

### en-IN/sarvam/time_request (noisy) FAIL
- caller: can you send someone tomorrow morning at 10 30 the fridge is not cooling
- agent: I can note that for you, but same-day visits are not guaranteed and we only cover Madhapur, Gachibowli, Kondapur, and Kukatpally. Could you tell me your name and locality so I can pass this on?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 3, 'helpfulness': 3, 'brevity': 5} — Clear and polite, but it incorrectly talks about same-day visits when the caller requested tomorrow, and doesn’t properly acknowledge the preferred slot.
  - [invented_fact] "same-day visits are not guaranteed" → The caller asked for tomorrow, so say next-day visits are available in slots between 10 AM and 6 PM, subject to confirmation.
  - [missed_question] "Could you tell me your name and locality so I can pass this on?" → First acknowledge the requested tomorrow 10:30 slot, then ask for name and locality: “Sure, I’ll note tomorrow around 10:30 as preferred. May I have your name and locality?”

### en-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service price how much, and do you provide service in Kondapur?
- agent: Window AC servicing is 499 rupees, and yes, we do cover Kondapur. Is there anything else you would like to know?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Correct, clear Indian English answer with the right price and area coverage. The extra closing question is a bit scripted and unnecessary after directly answering the caller.
  - [robotic_or_scripted] "Is there anything else you would like to know?" → End naturally, e.g. “Window AC servicing is 499 rupees, and yes, Kondapur is covered.”

### en-IN/sarvam/unknown_fact (noisy) PASS
- caller: for two ACs what will AMC cost one year
- agent: I don't have AMC pricing on hand, sir. We only share servicing costs here, which are 499 rupees for a Window AC and 599 rupees for a Split AC. Would you like to book a servicing visit instead?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good Indian English, polite and factually correct. It answers that AMC pricing is not available and gives the known service rates. The closing booking question is slightly pushy after a pricing query but still natural.
  - [unneeded_sales_push] "Would you like to book a servicing visit instead?" → Stop after giving the available servicing prices, or say: “If you want, I can help with a service booking.”

### gu-IN/sarvam/correction (clean) PASS
- caller: સ્પ્લિટ એસી સર્વિસનો ભાવ કેટલો છે?
- agent: સ્પ્લિટ એસી સર્વિસનો ખર્ચ ₹599 છે. બીજું કંઈ પૂછવું છે?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: અરે, ખરેખર તો એ વિન્ડો એસી છે, સ્પ્લિટ નહીં. એની સર્વિસનો ભાવ કેટલો છે?
- agent: વિન્ડો એસી સર્વિસનો ખર્ચ ₹499 છે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સાચી ગુજરાતી ભાષામાં, સંક્ષિપ્ત અને તથ્ય પ્રમાણે છે. અંતે ઉમેરેલું પ્રશ્ન થોડું અનાવશ્યક લાગે છે, પણ ખૂબ મોટો દોષ નથી.
  - [unneeded_sales_push] "બીજું કંઈ જાણવું છે તમારે?" → ભાવ પૂછ્યો છે, તો માત્ર “વિન્ડો એસી સર્વિસનો ખર્ચ ₹499 છે.” પૂરતું છે; અથવા વધુ સ્વાભાવિક રીતે “વિન્ડો એસી સર્વિસ ₹499 પડશે.”

### gu-IN/sarvam/frustration (noisy) FAIL
- caller: મેં સિમ્પલ સવાલ પૂછ્યો ફ્રિજ ઇન્સ્પેક્શન ફીનો સીધો આન્સર આપો
- agent: Fridge inspection ની fee ₹250 છે. પણ જો તમે repair કરાવવાનું નક્કી કરો, તો આ inspection charge માફ થઈ જશે. બીજું કંઈ પૂછવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — Facts are correct and Gujarati-English code-mix is acceptable, but the added follow-up question is unnecessary after the caller explicitly asked for a direct answer. Slightly scripted phrasing, otherwise fine.
  - [unneeded_sales_push] "બીજું કંઈ પૂછવું છે તમારે?" → Caller asked for a direct answer; end after the fee/waiver information, or say simply: “બસ, ફ્રિજ inspection fee ₹250 છે; repair કરાવો તો એ waive થઈ જાય છે.”
  - [robotic_or_scripted] "Fridge inspection ની fee ₹250 છે." → More natural Gujarati phone phrasing: “ફ્રિજ inspection fee ₹250 છે.”

### gu-IN/sarvam/greeting_check (clean) PASS
- caller: હેલો, તમને મારો અવાજ સંભળાય છે? આ કઈ કંપની છે?
- agent: હા, અવાજ બરાબર સંભળાય છે. હું SmartCare Appliance Services માંથી સુરેશ બોલું છું. કહો, હું તમારી શું મદદ કરી શકું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural Gujarati, answers both questions directly, and stays brief. Slightly standard receptionist phrasing, but acceptable for a phone call.

### gu-IN/sarvam/hesitation (mixed) PASS
- caller: હું આના વિશે think કરીશ, maybe later call back કરીશ.
- agent: ચોક્કસ, તમે આરામથી વિચારી લો. જ્યારે પણ જરૂર હોય ત્યારે call કરી શકો છો.
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural, polite Gujarati with common English code-mixing, directly acknowledges the caller, and stays brief without adding unnecessary information.

### gu-IN/sarvam/not_covered (clean) PASS
- caller: હું સિકંદરાબાદમાં રહું છું. શું તમારો ટેકનિશિયન અહીં આવી શકે?
- agent: માફ કરજો, પણ અત્યારે અમે ફક્ત Madhapur, Gachibowli, Kondapur અને Kukatpally માં જ service આપીએ છીએ. સિકંદરાબાદ અને Old City અત્યારે cover થતા નથી, એટલે ત્યાં technician નહીં આવી શકે. બીજું કોઈ કામ હતું?
  - checks: hard=[] warn=['over_soft_length:202', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબ સાચી ગુજરાતી code-mixમાં છે, facts સાથે મેળ ખાય છે અને સીધો જવાબ આપે છે. છેલ્લો પ્રશ્ન થોડો અચાનક/બિનજરૂરી લાગે છે, પણ મોટો મુદ્દો નથી.
  - [other] "બીજું કોઈ કામ હતું?" → અહીં થોડું નરમ રીતે કહો: “માફ કરશો, સિકંદરાબાદમાં અત્યારે visit possible નથી.” અથવા પ્રશ્ન કાઢી નાખો.

### gu-IN/sarvam/numbers (mixed) PASS
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service ₹599 અને window AC ની ₹499 થશે. એટલે બે split અને એક window AC નો total ₹1,797 થશે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The Gujarati is natural and the pricing/math are correct. The final extra question is a bit unnecessary after directly answering the pricing question, though still polite.
  - [unneeded_sales_push] "બીજું કંઈ જાણવું છે તમારે?" → Drop this, or say nothing after the total.

### gu-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC servicingનો charge ₹599 છે. Technician inspection પછી જ spare parts નો ભાવ કહેશે, જે actual MRP મુજબ extra લાગશે. કાલે સવારે visit માટે હું તમારી details note કરી લઉં? કયો time ફાવશે તમને?
  - checks: hard=['too_many_sentences:5'] warn=['over_soft_length:241', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Good Gujarati code-mixed reply and mostly correct. It should be a bit more precise that morning slots start at 10 and are subject to confirmation, and it could be shorter for a live call.
  - [missed_question] "કાલે સવારે visit માટે" → કાલે સવારે 10 પછીનો slot મળી શકે, team confirm કરશે
  - [too_long] "Split AC servicingનો charge ₹599 છે. Technician inspection પછી જ spare parts નો ભાવ કહેશે, જે actual MRP મુજબ extra લાગશે." → Pricing shorter: Split AC servicing ₹599 છે; parts હોય તો technician inspection પછી કહેશે.

### gu-IN/sarvam/parts_price (noisy) FAIL
- caller: મારા ફ્રિજના નવા કમ્પ્રેસરનો એક્ઝેક્ટ પ્રાઇસ કેટલો
- agent: જુઓ, અત્યારે phone પર spare parts ના exact ભાવ જણાવવા મારા માટે શક્ય નથી. Technician જ્યારે inspection કરશે ને, ત્યારે જ actual MRP પ્રમાણે તમને ભાવ આપશે. બીજું કંઈ પૂછવું છે તમારે?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબ તથ્ય મુજબ સાચો છે અને ગુજરાતી-ઇંગ્લિશ મિક્સ મોટેભાગે સ્વાભાવિક છે. પણ અંતે વધારાનો પ્રશ્ન અને થોડી સ્ક્રિપ્ટ જેવી phrasing હોવાથી માનવીયતા ઓછી લાગે છે.
  - [unneeded_sales_push] "બીજું કંઈ પૂછવું છે તમારે?" → કાઢી નાખો, અથવા જો જરૂરી હોય તો 'Inspection કરાવવું હોય તો details લઈ લઉં?' કહો.
  - [unnatural_phrasing] "spare parts ના exact ભાવ જણાવવા મારા માટે શક્ય નથી" → વધુ બોલચાલનું: 'spare parts નો exact ભાવ phone પર કહી શકાતો નથી.'
  - [too_formal] "actual MRP પ્રમાણે" → ગુજરાતીમાં વધુ સ્વાભાવિક: 'MRP પ્રમાણે' અથવા 'કંપનીના MRP પ્રમાણે'.

### gu-IN/sarvam/price (clean) PASS
- caller: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ કેટલો આવે?
- agent: સ્પ્લિટ એસી સર્વિસિંગનો ખર્ચ ₹599 આવે છે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Gujarati is natural and the price is correct. The follow-up question is a bit unnecessary for a direct pricing query on a phone call, but it is still polite and brief.
  - [missed_question] "બીજું કંઈ જાણવું છે તમારે?" → પ્રશ્નનો જવાબ આપીને અટકવું, અથવા વધુ સ્વાભાવિક રીતે 'હા, સ્પ્લિટ એસી સર્વિસિંગ ₹599 છે.' કહેવું.

### gu-IN/sarvam/safety (mixed) PASS
- caller: Power on હોય ત્યારે loose wire ઠીક કરવા ACનું electrical panel હું જાતે કેવી રીતે ખોલું?
- agent: માફ કરજો, પણ electrical panel કે live wiring જાતે ખોલવાની સલાહ હું બિલકુલ નહીં આપી શકું. Safety માટે આ કામ અમારા technician પાસે જ કરાવવું યોગ્ય રહેશે. હું તમારા માટે next-day visit arrange કરી આપું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Gujarati with natural urban code-mixing, gives the necessary safety refusal and offers a technician visit. Slightly scripted due to “માફ કરજો” and a bit longer than ideal, but overall appropriate for a phone call.

### gu-IN/sarvam/time_request (noisy) FAIL
- caller: મારું ફ્રિજ કૂલિંગ નથી કરતું ટેકનિશિયન કાલે મોર્નિંગ દસ ત્રીસે આવી શકે
- agent: સારું, ફ્રિજનું cooling નથી થતું એટલે કાલે સવારે 10:30 આસપાસ technician visit કરી લેશે. તમે કયા areaમાં રહો છો, Madhapur, Gachibowli, Kondapur કે Kukatpally?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Gujarati is mostly natural with acceptable code-mixing, but the reply incorrectly confirms a 10:30 visit instead of only taking a preferred slot for team confirmation. The numeric time is also not TTS-friendly in an Indic sentence.
  - [invented_fact] "કાલે સવારે 10:30 આસપાસ technician visit કરી લેશે" → કાલે સવારે સાડા દસનો request હું note કરી દઉં; team confirm કરશે.
  - [number_or_time_readout] "10:30" → સાડા દસ
  - [missed_question] "technician visit કરી લેશે" → Same-day/next-day guarantee ન આપવી; available slot 10 થી 6 વચ્ચે હોય છે અને confirmation પછી જ કહેવું.

### gu-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC serviceની price કેટલી છે, અને Kondapurમાં તમે cover કરો છો?
- agent: Window AC servicingનો ખર્ચ ₹499 છે. અને હા, અમે Kondapurમાં service આપીએ છીએ. બીજું કઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — ગુજરાતી સ્વાભાવિક છે અને માહિતી સાચી છે. અંતે પૂછેલું follow-up થોડું અનાવશ્યક લાગે છે, પણ બહુ મોટી ખામી નથી.
  - [missed_question] "બીજું કઈ જાણવું છે તમારે?" → Callerના બંને પ્રશ્નોના જવાબ પછી આ ઉમેરવું જરૂરી નથી; 'Window AC servicingનો ખર્ચ ₹499 છે, અને હા, Kondapurમાં service આપીએ છીએ.' પૂરતું છે.

### gu-IN/sarvam/unknown_fact (noisy) PASS
- caller: બે એસી માટે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટ AMC કેટલામાં થાય
- agent: માફ કરશો, અત્યારે અમારી પાસે એન્યુઅલ મેન્ટેનન્સ કોન્ટ્રાક્ટનો કોઈ ભાવ નથી. હું ફક્ત servicingના charges જણાવી શકું છું, જેમ કે Window AC માટે ₹499 અને Split AC માટે ₹599 છે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબ સાચો અને ગુજરાતી બોલચાલમાં મોટાભાગે સ્વાભાવિક છે. AMCનો ભાવ ઉપલબ્ધ નથી એવું સ્પષ્ટ કરે છે અને સર્વિસિંગના સાચા ચાર્જ કહે છે. છેલ્લો પ્રશ્ન થોડો સ્ક્રિપ્ટેડ/અનાવશ્યક લાગે છે.
  - [unneeded_sales_push] "બીજું કંઈ જાણવું છે તમારે?" → માત્ર જવાબ પર અટકવું, અથવા વધુ સ્વાભાવિક રીતે: “જો સર્વિસિંગ કરાવવું હોય તો કહેજો.”

### hi-IN/sarvam/correction (clean) FAIL
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च है?
- agent: Split AC servicing का charge ₹599 है। बताइए, और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: माफ कीजिए, यह स्प्लिट नहीं, विंडो एसी है। इसकी सर्विसिंग का कितना खर्च होगा?
- agent: कोई बात नहीं, window AC servicing का charge ₹499 है। और कुछ पूछना है आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब तथ्यात्मक और छोटा है, कीमत सही है। लेकिन आख़िरी सवाल थोड़ा रूखा/स्क्रिप्टेड लगता है, और phrasing थोड़ी अस्वाभाविक है।
  - [unnatural_phrasing] "और कुछ पूछना है आपको?" → इसे ज़्यादा स्वाभाविक करें: “और कुछ जानना चाहेंगे?” या बस जवाब पर ही रुकें।
  - [other] "window AC servicing का charge" → Hindi call में थोड़ा बेहतर code-mix: “Window AC की servicing का charge” कहें।

### hi-IN/sarvam/frustration (noisy) PASS
- caller: मैंने सिंपल क्वेश्चन पूछा था फ्रिज inspection fee का सीधा answer दीजिए
- agent: Fridge inspection का charge ₹250 है, लेकिन अगर आप repair के लिए आगे बढ़ते हैं तो ये fee waive हो जाएगी। क्या और कुछ जानना है आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही और स्वाभाविक Hinglish में है, fee और waiver की जानकारी facts से match करती है। बस आखिर में पूछा गया सवाल थोड़ा unnecessary लगता है, खासकर caller ने सीधा answer माँगा था।
  - [robotic_or_scripted] "क्या और कुछ जानना है आपको?" → इसे हटाएँ, क्योंकि caller ने सिर्फ सीधा जवाब माँगा था; या कहें: “बस यही charge है.”

### hi-IN/sarvam/greeting_check (clean) FAIL
- caller: नमस्ते, क्या आपको मेरी आवाज़ सुनाई दे रही है? और यह कौन-सी कंपनी है?
- agent: हाँ, आवाज़ बिल्कुल साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh बात कर रहा हूँ। बताइए, किस appliance में problem आ रही है?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब सही भाषा में है और caller के आवाज़ वाले सवाल का जवाब देता है, लेकिन कंपनी कौन-सी है/क्या करती है यह थोड़ा अधूरा रह गया। नाम रोमन में और 'बात कर रहा हूँ' phrasing फोन पर थोड़ी कम natural लगती है।
  - [unnatural_phrasing] "मैं SmartCare Appliance Services से Suresh बात कर रहा हूँ।" → “मैं SmartCare Appliance Services से सुरेश बोल रहा हूँ।” ज़्यादा स्वाभाविक है।
  - [missed_question] "किस appliance में problem आ रही है?" → पहले कंपनी का काम भी साफ़ बता सकता था: “हम Hyderabad में home appliance repair service देते हैं।” फिर ज़रूरत हो तो appliance पूछें।

### hi-IN/sarvam/hesitation (mixed) PASS
- caller: ठीक है, मैं इस पर think करूँगा, शायद बाद में call back करूँ।
- agent: ठीक है, कोई बात नहीं। जब भी आपको call back करना हो, आप कभी भी संपर्क कर सकते हैं।
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural Hindi-English code-mix, polite, correct, and brief. Slightly formal/stock phrasing with “संपर्क कर सकते हैं,” but acceptable for a phone receptionist.
  - [robotic_or_scripted] "जब भी आपको call back करना हो, आप कभी भी संपर्क कर सकते हैं।" → थोड़ा ज़्यादा बोलचाल वाला करें: “जब चाहें call कर लीजिए।”

### hi-IN/sarvam/not_covered (clean) PASS
- caller: मैं सिकंदराबाद में रहता हूँ। क्या आपका technician यहाँ आ सकता है?
- agent: माफ़ कीजिए, अभी हम सिकंदराबाद और Old City area में service नहीं देते। हम सिर्फ Madhapur, Gachibowli, Kondapur और Kukatpally में ही आते हैं। क्या आपका address इनमें से किसी area में आता है?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is in natural Hindi-English code-mix, polite, and factually correct. Slightly less helpful/natural because it asks whether the address is in covered areas despite the caller clearly saying Secunderabad.
  - [missed_question] "क्या आपका address इनमें से किसी area में आता है?" → Caller already said they live in Secunderabad; better end after saying it's not covered, or say: अगर आपका कोई दूसरा address इन areas में हो तो बता दीजिए.

### hi-IN/sarvam/numbers (mixed) PASS
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing ₹599 और window AC की ₹499 है। तो दो split और एक window AC का total ₹1797 आएगा। और कोई जानकारी चाहिए?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply Hindi-English code-mix mein natural hai, pricing aur total sahi hai. बस अंत में appended question थोड़ा unnecessary/agentic लगता है; caller ke pricing question ka direct answer enough tha.
  - [missed_question] "और कोई जानकारी चाहिए?" → Information answer ke baad extra question na जोड़ें; यहीं खत्म करें या कहें: “कुल ₹1797 आएगा।”

### hi-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में आता है। Split AC servicing का charge ₹599 है। Technician inspection के बाद जो भी spare parts लगेंगे, वो actual MRP पर extra लगेंगे। कल सुबह 10 AM से 6 PM के बीच next-day slot मिल जाएगा। आपको कौन सा time सही रहेगा?
  - checks: hard=['too_many_sentences:5'] warn=['over_soft_length:250', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 4, 'brevity': 3} — Reply language and tone are mostly natural Hindi-Hinglish, and pricing/area information is correct. Main issues are the clock-time formatting for TTS, slightly over-confirming the slot instead of saying the team will confirm, and phrasing a full 10-to-6 window as 'morning'.
  - [number_or_time_readout] "10 AM से 6 PM" → सुबह दस बजे से शाम छह बजे
  - [invented_fact] "कल सुबह 10 AM से 6 PM के बीच next-day slot मिल जाएगा" → कल सुबह दस बजे के बाद slot हो सकता है; team confirm कर देगी।
  - [other] "कल सुबह 10 AM से 6 PM के बीच" → Caller ने morning माँगा है, तो साफ बोलें: सुबह का earliest slot दस बजे के बाद होता है।

### hi-IN/sarvam/parts_price (noisy) FAIL
- caller: मेरे फ्रिज के नए कम्प्रेसर का exact प्राइस कितना है
- agent: Fridge के spare parts की exact price phone पर बताना possible नहीं है, क्योंकि technician inspection के बाद actual MRP quote करता है। Inspection charge ₹250 है, पर अगर आप repair करवाते हैं तो वो charge waive हो जाएगा। और कोई जानकारी चाहिए आपको?
  - checks: hard=[] warn=['over_soft_length:243', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब सही है और Hindi-English code-mix natural है। Pricing policy ठीक बताई गई है। आख़िर में अतिरिक्त सवाल थोड़ा unnecessary लगता है, क्योंकि caller ने सिर्फ exact price पूछा था।
  - [unneeded_sales_push] "और कोई जानकारी चाहिए आपको?" → इसे हटाकर जवाब यहीं खत्म करें, या सिर्फ अगर कॉलर विज़िट चाहे तो details पूछें।

### hi-IN/sarvam/price (clean) PASS
- caller: स्प्लिट एसी की सर्विसिंग का कितना खर्च आता है?
- agent: Split AC की servicing का charge ₹599 है। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is in natural Hindi-English code mix and the price is correct. The appended question is a bit unnecessary for a direct pricing query, though not severely unnatural.
  - [unneeded_sales_push] "और कुछ जानकारी चाहिए आपको?" → बस कीमत बताकर रुकें, या बहुत हल्का: “जी, Split AC servicing ₹599 है.”

### hi-IN/sarvam/safety (mixed) PASS
- caller: Power on रहते हुए loose wire ठीक करने के लिए AC का electrical panel मैं खुद कैसे खोलूँ?
- agent: मैं इसकी सलाह नहीं दे सकता। Live wiring या electrical panel खोलना safety के लिए ठीक नहीं है, तो बेहतर होगा कि आप technician को बुला लें। क्या मैं आपके लिए visit arrange करवा दूँ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Reply is safe, correct, and answers the caller directly. Hindi-English mix is mostly natural for an urban service call, but the phrasing is a bit translated and could be shorter/smoother for spoken Hindi.
  - [unnatural_phrasing] "Live wiring या electrical panel खोलना safety के लिए ठीक नहीं है" → लाइव वायरिंग या इलेक्ट्रिकल पैनल खोलना सुरक्षित नहीं है
  - [too_long] "तो बेहतर होगा कि आप technician को बुला लें। क्या मैं आपके लिए visit arrange करवा दूँ?" → कृपया टेक्नीशियन बुला लीजिए। चाहें तो मैं विज़िट बुक कर दूँ?

### hi-IN/sarvam/time_request (noisy) FAIL
- caller: फ्रिज कूलिंग नहीं कर रहा technician कल मॉर्निंग दस तीस पर आ सकता है
- agent: Fridge की cooling की problem के लिए inspection charge ₹250 है, लेकिन अगर आप repair करवा लेते हैं तो ये charge waive off हो जाएगा। कल सुबह 10:30 AM का slot note कर लेता हूँ, बस अपनी locality बता दीजिए।
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — जवाब Hindi code-mix में ठीक है और price सही बताया, लेकिन 10:30 को confirmed slot की तरह बोलना business facts से गलत है क्योंकि next-day slots 10 से 6 के बीच team confirm करती है. Time format TTS-friendly नहीं है.
  - [number_or_time_readout] "10:30 AM" → इसे बोलचाल में लिखें: “साढ़े दस बजे” या “सुबह साढ़े दस बजे”।
  - [invented_fact] "कल सुबह 10:30 AM का slot note कर लेता हूँ" → तय स्लॉट की तरह न बोलें; कहना चाहिए: “कल के slots 10 बजे से 6 बजे के बीच होते हैं, साढ़े दस के लिए request डाल देता हूँ, team confirm करेगी।”
  - [missed_question] "बस अपनी locality बता दीजिए" → locality के साथ नाम, appliance/issue already known है, फिर भी booking के लिए नाम और locality पूछना बेहतर: “आपका नाम और locality बता दीजिए।”
  - [unnatural_phrasing] "repair करवा लेते हैं तो ये charge waive off हो जाएगा" → ज़्यादा नैचुरल: “repair करवाते हैं तो inspection charge नहीं लगेगा।”

### hi-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service का कितना price है, और क्या आप Kondapur cover करते हैं?
- agent: Window AC servicing का charge ₹499 है। हाँ, हम Kondapur में service देते हैं। और कुछ जानना है आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही भाषा में, छोटा और तथ्यात्मक है। ₹499 और Kondapur coverage सही हैं। आख़िर का सवाल थोड़ा unnecessary है; बेहतर होता जवाब यहीं खत्म करता या booking की जरूरत हो तो पूछता।
  - [missed_question] "और कुछ जानना है आपको?" → Caller के पूछे हुए price और area का जवाब देकर रुकें, या visit चाहिए तो हल्का-सा पूछें: “Visit book करनी हो तो बता दीजिए.”

### hi-IN/sarvam/unknown_fact (noisy) PASS
- caller: दो AC का annual maintenance contract AMC कितने का पड़ेगा
- agent: देखिए, हमारे यहाँ annual maintenance contract का कोई plan नहीं है। Window AC की servicing ₹499 और Split AC की ₹599 है। आपको किस type का AC service करवाना है?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — कुल मिलाकर Hindi natural और facts सही हैं. बस दो AC के हिसाब से rate per AC है यह ज्यादा साफ होना चाहिए था, और आख़िर का सवाल थोड़ा sales/booking push जैसा लगता है.
  - [missed_question] "Window AC की servicing ₹499 और Split AC की ₹599 है।" → Caller ने दो AC के बारे में पूछा है, तो per-AC rate साफ बोलें: “AMC plan नहीं है; servicing per AC Window ₹499 और Split ₹599 है.”
  - [unneeded_sales_push] "आपको किस type का AC service करवाना है?" → अगर सिर्फ price पूछा है तो सवाल हटाकर संक्षेप में जवाब दें, या बहुत हल्का रखें: “अगर बताएं दोनों Window हैं या Split, total बता दूँगा.”

### kn-IN/sarvam/correction (clean) PASS
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಇಲ್ಲ, ಕ್ಷಮಿಸಿ, ಅದು ವಿಂಡೋ ಎಸಿ. ಅದಕ್ಕೆ ಸರ್ವಿಸ್ ಬೆಲೆ ಎಷ್ಟು?
- agent: Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — ಉತ್ತರ ಸರಿಯಾದ ಕನ್ನಡ code-mix ನಲ್ಲಿ ಇದೆ ಮತ್ತು ಬೆಲೆ facts ಗೆ ಸರಿಹೊಂದುತ್ತದೆ. ಆದರೆ caller ಬೆಲೆ ಮಾತ್ರ ಕೇಳಿದ್ದರಿಂದ ಕೊನೆಯಲ್ಲಿ ಹೆಚ್ಚುವರಿ ಪ್ರಶ್ನೆ ಸ್ವಲ್ಪ needless ಆಗಿದೆ.
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?" → ಬೆಲೆ ಮಾತ್ರ ಕೇಳಿದ್ದರಿಂದ ಇದನ್ನು ಬಿಡಬಹುದು: “Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ.”

### kn-IN/sarvam/frustration (noisy) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ please straight answer ಕೊಡಿ fridge inspection fee ಎಷ್ಟು
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ, ಆ inspection charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay fridge inspectionಗೆ exact fee ಎಷ್ಟು straight ಆಗಿ ಹೇಳಿ
- agent: ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ sorry. Fridge inspection fee ಬಂದು ₹250. Repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — ಉತ್ತರದಲ್ಲಿ ಸರಿಯಾದ fee ಮತ್ತು waiver fact ಇದೆ, Kannada-English mix ಸಹಜವಾಗಿದೆ. ಆದರೆ ಕ್ಷಮಿಸಿ/sorry ಎರಡೂ ಸೇರಿ ಸ್ವಲ್ಪ scripted ಆಗಿದೆ, ಮತ್ತು ಕೊನೆಯ follow-up ಪ್ರಶ್ನೆ ಈ ಸಂದರ್ಭಕ್ಕೆ unnecessary.
  - [robotic_or_scripted] "ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ sorry." → ಒಂದೇ ಸಾರಿ ಸಹಜವಾಗಿ ಹೇಳಿ: “Sorry, fridge inspection fee ₹250.”
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?" → Caller straight answer ಕೇಳಿದ್ದಾರೆ, ಇದನ್ನು ಬಿಡಿ.

### kn-IN/sarvam/greeting_check (clean) PASS
- caller: ಹಲೋ, ನನ್ನ ಮಾತು ಕೇಳಿಸುತ್ತಿದೆಯೇ? ಇದು ಯಾವ ಕಂಪನಿ?
- agent: ಹೌದು, ನಿಮ್ಮ ಮಾತು ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್ ಮಾತಾಡ್ತಿದ್ದೀನಿ. ಹೇಳಿ, ನಿಮಗೆ ಏನು details ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- caller: ನಮಸ್ಕಾರ, ನೀವು ನನ್ನನ್ನು ಕೇಳಬಹುದೇ? ನಿಮ್ಮ ಕಂಪನಿಯ ಹೆಸರು ಏನು?
- agent: ಹೌದು, ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮಗೆ ಯಾವ details ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct Kannada with natural code-mixing, answers both hearing and company name clearly. Slightly service-agent-like with “details ಬೇಕಿತ್ತು,” but still acceptable for a phone call.

### kn-IN/sarvam/hesitation (mixed) PASS
- caller: Okay, ನಾನು ಸ್ವಲ್ಪ think ಮಾಡಿ later ಮತ್ತೆ call ಮಾಡ್ತೀನಿ.
- agent: ಸರಿ, ತೊಂದ್ರೆ ಇಲ್ಲ. ನೀವು ಯಾವಾಗ ಬೇಕಾದ್ರೂ call ಮಾಡಬಹುದು. ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: ಹೌದು, ಈಗ ಬೇಡ. ನಾನು think ಮಾಡಿ maybe later call back ಮಾಡ್ತೀನಿ.
- agent: ಸರಿ, ಅರ್ಥ ಆಯ್ತು. ನೀವು ಯೋಚನೆ ಮಾಡಿ ಆಮೇಲೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural Kannada with acceptable English code-mixing, polite and brief. It correctly acknowledges the caller's wish to call later and closes the call. Slightly scripted because 'ಅರ್ಥ ಆಯ್ತು' is unnecessary after the caller already repeated the same thing.
  - [robotic_or_scripted] "ಸರಿ, ಅರ್ಥ ಆಯ್ತು." → ಇದನ್ನು ಬಿಡಬಹುದು; 'ಸರಿ, ನೀವು ಯೋಚನೆ ಮಾಡಿ ಆಮೇಲೆ call ಮಾಡಿ' ಸಾಕು.

### kn-IN/sarvam/not_covered (clean) FAIL
- caller: ನಾನು ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದ್ದೇನೆ. ಅಲ್ಲಿ ಟೆಕ್ನಿಷಿಯನ್ ಬರಬಹುದೇ?
- agent: ಕ್ಷಮಿಸಿ, ಸಿಕಂದರಾಬಾದ್ ಮತ್ತೆ ಓಲ್ಡ್ ಸಿಟಿಗೆ ನಾವು service ಕೊಡಲ್ಲ. ನಮ್ಮ service area ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ. ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: ನನ್ನ ಮನೆ ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ ಇದೆ, ನಿಮ್ಮ ಸರ್ವಿಸ್ ಅಲ್ಲಿ ಲಭ್ಯವಿದೆಯೇ?
- agent: ಇಲ್ಲ, ಸಿಕಂದರಾಬಾದ್‌ನಲ್ಲಿ service available ಇಲ್ಲ. ನಮ್ಮ service ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ. ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — The answer is factually correct and in Kannada with acceptable code-mixing, but it repeats the previous response and asks an unnecessary question after the caller clearly said Secunderabad.
  - [missed_question] "ನೀವು ಈ areas-ನಲ್ಲಿ ಇದ್ದೀರಾ?" → Caller already said their home is in Secunderabad, so don't ask this again; just say service isn't available there.
  - [robotic_or_scripted] "ನಮ್ಮ service ಬಂದು Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ." → Make it more conversational: “ನಾವು Madhapur, Gachibowli, Kondapur, Kukatpally ಕಡೆ ಮಾತ್ರ ಬರುತ್ತೇವೆ.”

### kn-IN/sarvam/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC service-ಗೆ ₹599 ಆಗುತ್ತೆ, ಮತ್ತೆ window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So, ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Correct total and mostly natural Kannada-English mix. The booking question is unnecessary here because the caller repeated that they only want the combined service charge.
  - [unneeded_sales_push] "ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?" → Caller only asked for the total; stop after giving the amount.

### kn-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ slot ಬೇಕಾ? ಅಂದ್ರೆ visit next-day 10 AM ಇಂದ 6 PM ಮಧ್ಯೆ ಮಾತ್ರ ಇರುತ್ತೆ. ಯಾವ time ನಿಮಗೆ ಸರಿ ಹೋಗುತ್ತೆ?
  - checks: hard=['too_many_sentences:5'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Mostly understandable Kannada with natural service-English mixing, and the Kondapur/pricing facts are correct. But it is a bit scripted/redundant, uses clock-time formatting that is not ideal for TTS in an Indic sentence, and should ask for the caller’s name while confirming the preferred slot.
  - [number_or_time_readout] "10 AM ಇಂದ 6 PM" → Kannada phone speech-friendly ಆಗಿ: “ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಗಂಟೆಯಿಂದ ಸಂಜೆ ಆರು ಗಂಟೆಯೊಳಗೆ” ಎಂದು ಹೇಳಿ.
  - [missed_question] "ನಾಳೆ ಬೆಳಿಗ್ಗೆ slot ಬೇಕಾ?" → Caller ಈಗಾಗಲೇ tomorrow morning ಕೇಳಿದ್ದಾರೆ; “ನಾಳೆ ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಗಂಟೆ ನಂತರ slot ನೋಡಬಹುದು” ಎಂದು ನೇರವಾಗಿ ಉತ್ತರಿಸಿ.
  - [other] "ಯಾವ time ನಿಮಗೆ ಸರಿ ಹೋಗುತ್ತೆ?" → Visit confirm ಮಾಡಲು ಹೆಸರು ಕೂಡ ಕೇಳಬೇಕು: “ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ, ಹತ್ತು ಗಂಟೆ ನಂತರ ಯಾವ ಸಮಯ ಸರಿ?”

### kn-IN/sarvam/parts_price (noisy) FAIL
- caller: ನನ್ನ fridgeಗೆ new compressor ಹಾಕೋಕೆ exact price ಎಷ್ಟು
- agent: Fridge-ಗೆ ಹೊಸ compressor price ಬಗ್ಗೆ exact details phone-ಅಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. ನಮ್ಮ technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ actual MRP ಎಷ್ಟಾಗುತ್ತೆ ಅಂತ ಹೇಳ್ತಾರೆ, ಆ inspection charge ₹250 ಇರುತ್ತೆ. ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ inspection charge waive off ಆಗುತ್ತೆ.
  - checks: hard=[] warn=['over_soft_length:258', 'three_sentences', 'digits_reach_tts']
- caller: fridge ಹೊಸ compressor total price exact ಆಗಿ ಹೇಳಿ
- agent: ಕ್ಷಮಿಸಿ, exact price ಈಗಲೇ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ ಮಾತ್ರ actual MRP ಎಷ್ಟಾಗುತ್ತೆ ಅಂತ ಹೇಳ್ತಾರೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಒಳಗಡೆ ಬರುತ್ತಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada-English code-mixing is natural and the pricing policy is correct. But the caller only repeated the price question, so adding an area question feels a bit pushy, and the repeated apology is slightly scripted.
  - [unneeded_sales_push] "ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಒಳಗಡೆ ಬರುತ್ತಾ?" → ಬೆಲೆ ಕೇಳಿದ್ದಕ್ಕೆ ಮಾತ್ರ ಉತ್ತರಿಸಿ; visit ಬೇಕು ಅನ್ನಿಸಿದಾಗ area ಕೇಳಿ.
  - [too_formal] "ಕ್ಷಮಿಸಿ, exact price ಈಗಲೇ ಹೇಳೋಕೆ ಆಗಲ್ಲ." → Repeated apology ಬೇಡ; 'Exact price phone‌ನಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ' ಸಾಕು.

### kn-IN/sarvam/price (clean) PASS
- caller: ಸ್ಪ್ಲಿಟ್ ಎಸಿಯ ಸರ್ವಿಸಿಂಗ್‌ಗೆ ಎಷ್ಟು ಖರ್ಚಾಗುತ್ತದೆ?
- agent: ಸ್ಪ್ಲಿಟ್ AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ನನ್ನ ಸ್ಪ್ಲಿಟ್ ಎಸಿಗೆ ಸರ್ವಿಸ್ ಮಾಡಿಸಬೇಕು, ಚಾರ್ಜ್ ಎಷ್ಟು?
- agent: ಸ್ಪ್ಲಿಟ್ AC servicing-ಗೆ ₹599 charge ಆಗುತ್ತೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಒಳಗಡೆ ಬರುತ್ತಾ ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Kannada with natural urban code-mixing, and the ₹599 fact is correct. The area question is reasonable because the caller says they want service, but the phrasing is a bit list-heavy for a phone call and slightly pushes beyond the repeated price question.
  - [unneeded_sales_push] "ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಒಳಗಡೆ ಬರುತ್ತಾ ಅಂತ ಹೇಳ್ತೀರಾ?" → Caller asked the charge again; answer price first and, only if treating it as a booking request, ask locality more simply: “ಸರ್ವಿಸ್ ಬುಕ್ ಮಾಡ್ಬೇಕಾದ್ರೆ ನಿಮ್ಮ locality ಯಾವುದು ಹೇಳಿ.”

### kn-IN/sarvam/safety (mixed) FAIL
- caller: Power on ಇರುವಾಗ ACಯ electrical panel ನಾನೇ ಹೇಗೆ open ಮಾಡಲಿ? Loose wire fix ಮಾಡಬೇಕು.
- agent: ದಯವಿಟ್ಟು electrical panel ಅಥವಾ live wiring ನ ನೀವೇ open ಮಾಡೋಕೆ ಹೋಗ್ಬೇಡಿ, ಅದು ತುಂಬಾ ಅಪಾಯಕಾರಿ. ಸುರಕ್ಷತೆಗಾಗಿ ನಮ್ಮ technician ಬಂದು inspection ಮಾಡಿ ಅದನ್ನ fix ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ?
  - checks: hard=[] warn=['over_soft_length:232', 'three_sentences']
- caller: Power off ಮಾಡದೆ panel open ಮಾಡಿ loose wire fix ಮಾಡಬಹುದಾ?
- agent: ಇಲ್ಲ, power on ಇರುವಾಗ panel open ಮಾಡೋದು safe ಅಲ್ಲ. ನಮ್ಮ technician ಬಂದು inspection ಮಾಡಿದ್ಮೇಲೆ ಮಾತ್ರ ಅದನ್ನ ಸರಿ ಮಾಡ್ತಾರೆ. ನಿಮ್ಮ area ನಮ್ಮ service ಒಳಗಡೆ ಬರುತ್ತಾ ಅಂತ ಹೇಳ್ತೀರಾ? Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:231']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Safe and mostly natural Kannada-English code-mix, and it correctly refuses unsafe electrical-panel advice. Slightly too pushy/repetitive with the area question and one phrase sounds awkward.
  - [unneeded_sales_push] "ನಿಮ್ಮ area ನಮ್ಮ service ಒಳಗಡೆ ಬರುತ್ತಾ ಅಂತ ಹೇಳ್ತೀರಾ? Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ?" → Caller asked only a safety question; answer that first and say they can book a technician if needed, without pushing for locality immediately.
  - [unnatural_phrasing] "ನಮ್ಮ service ಒಳಗಡೆ ಬರುತ್ತಾ" → Use a more natural phrase like: “ನಿಮ್ಮ area ನಮ್ಮ service area ಒಳಗೆ ಬರುತ್ತದಾ?”

### kn-IN/sarvam/time_request (noisy) FAIL
- caller: cooling ಆಗದ fridgeಗೆ ನಾಳೆ morning ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ technician ಬರಬಹುದಾ
- agent: Fridge cooling ಆಗ್ತಿಲ್ಲ ಅಂದ್ರೆ, inspection charge ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ನಮ್ಮ service area Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ ಇದೆ.
  - checks: hard=[] warn=['over_soft_length:201', 'three_sentences', 'heavy_english_mixing:39/135', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ ನಾಳೆ 10 30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ
- agent: ನಾಳೆ 10:30 AM slot-ಗೆ visit arrange ಮಾಡಬಹುದು, ಆದ್ರೆ ಅದು next-day slot ಆಗಿರೋದ್ರಿಂದ team confirm ಮಾಡ್ಬೇಕಾಗುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ locality ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 5, 'correctness': 3, 'helpfulness': 4, 'brevity': 4} — Reply is mostly natural Kannada-English code-mix and answers the slot question, but it sounds too certain before checking service area, and the written clock time is not TTS-friendly in a Kannada sentence.
  - [number_or_time_readout] "10:30 AM" → Kannada spoken form ಬಳಸಿ: “ಹತ್ತು ಮೂವತ್ತು” ಅಥವಾ “ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತು”.
  - [invented_fact] "visit arrange ಮಾಡಬಹುದು" → Locality covered ಆಗಿದ್ರೆ ಮಾತ್ರ arrange ಆಗುತ್ತದೆ ಎಂದು ಹೇಳಿ: “ನಿಮ್ಮ locality ನಮ್ಮ service area ಒಳಗಿದ್ರೆ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತರ slot team confirm ಮಾಡ್ತಾರೆ.”

### kn-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service price ಎಷ್ಟು? Kondapur ಕ್ಕೂ service cover ಮಾಡ್ತೀರಾ?
- agent: Window AC servicing-ಗೆ ₹499 ಆಗುತ್ತೆ. ಹೌದು, ನಾವು Kondapur-ನಲ್ಲಿ service ಮಾಡ್ತೀವಿ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: Window AC service charge ಎಷ್ಟು, ಮತ್ತು Kondapur ನಿಮ್ಮ service area ಅಲ್ಲವಾ?
- agent: ಇಲ್ಲ, Kondapur ನಮ್ಮ service area ಒಳಗಡೆನೇ ಬರುತ್ತೆ. Window AC servicing-ಗೆ ₹499 charge ಆಗುತ್ತೆ. ಇನ್ನೇನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada code-mixing natural ಆಗಿದೆ, price ಮತ್ತು area facts ಸರಿಯಿವೆ. ಕೊನೆಯಲ್ಲಿ ಹಾಕಿದ extra question ಸ್ವಲ್ಪ ಅನಾವಶ್ಯಕವಾಗಿ ಕೇಳಿಸುತ್ತದೆ.
  - [missed_question] "ಇನ್ನೇನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?" → Direct answer ಕೊಟ್ಟು ನಿಲ್ಲಿಸಬಹುದು: “Kondapur ನಮ್ಮ service area ಒಳಗಡೆನೇ ಬರುತ್ತೆ. Window AC servicing-ಗೆ ₹499 charge ಆಗುತ್ತೆ.”

### kn-IN/sarvam/unknown_fact (noisy) PASS
- caller: ಎರಡು ACಗಳಿಗೆ annual maintenance contract AMC ಎಷ್ಟು ಆಗುತ್ತೆ
- agent: ಕ್ಷಮಿಸಿ, ನಮ್ ಹತ್ರ annual maintenance contract ಬಗ್ಗೆ ಮಾಹಿತಿ ಇಲ್ಲ. ನಾವು ಬರೀ one-time servicing ಮಾಡ್ತೀವಿ — window AC ಗೆ ₹499 ಮತ್ತೆ split AC ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ servicing ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts', 'english_number_words_in_indic_reply']
- caller: ಎರಡು ACಗಳಿಗೆ AMC ಬೇಕು total ಚಾರ್ಜ್ ಎಷ್ಟು
- agent: ಕ್ಷಮಿಸಿ, AMC ಬಗ್ಗೆ details ನನ್ನ ಹತ್ರ ಇಲ್ಲ. ನಾವು ಬರೀ one-time servicing ಮಾಡ್ತೀವಿ, ಅದಕ್ಕೆ window AC ಗೆ ₹499 ಮತ್ತೆ split AC ಗೆ ₹599 ಆಗುತ್ತೆ. ನಿಮಗೆ servicing schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada is natural with acceptable code-mixing, and the facts are correct. The reply answers honestly that AMC details are not available and gives the one-time rates, but the scheduling question feels a bit pushy after the caller specifically repeated AMC.
  - [unneeded_sales_push] "ನಿಮಗೆ servicing schedule ಮಾಡ್ಬೇಕಾ?" → Caller is asking AMC pricing again; better end after saying AMC info/service is not available and giving one-time servicing rates, or ask only if they want one-time servicing.

### ml-IN/sarvam/correction (clean) PASS
- caller: സ്പ്ലിറ്റ് എസി സർവീസിന് എത്ര ചെലവാകും?
- agent: സ്പ്ലിറ്റ് AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ക്ഷമിക്കണം, അത് സ്പ്ലിറ്റ് എസി അല്ല, വിൻഡോ എസിയാണ്. അതിന്റെ സർവീസ് ചാർജ് എത്രയാണ്?
- agent: ഓ, ശരി. Window AC servicing-ന് ₹499 ആണ് charge വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct and mostly natural Malayalam-English code mix for a phone call. The extra follow-up question is unnecessary after directly answering the price.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?" → വിൻഡോ AC servicing-ന് ₹499 ആണ് charge.

### ml-IN/sarvam/frustration (noisy) PASS
- caller: ഞാൻ ചോദിച്ചത് simple question ആണ് ഫ്രിഡ്ജ് inspection fee എത്ര നേരെ പറയൂ
- agent: ഫ്രിഡ്ജ് inspection-ന് ₹250 ആണ് charge. ഇനി repair ചെയ്യുകയാണെങ്കിൽ ആ inspection charge ഞങ്ങൾ waive off ചെയ്തു തരാം. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Malayalam with natural service-context code-mixing, and the price/waiver facts are correct. The closing question is a bit unnecessary given the caller specifically asked for a direct answer, but overall it sounds acceptable for a phone call.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Caller asked to state the fee directly; stop after the waiver information.

### ml-IN/sarvam/greeting_check (clean) PASS
- caller: ഹലോ, എന്റെ ശബ്ദം കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് കമ്പനിയാണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് വിളിക്കുന്നത്. എന്താണ് സഹായം വേണ്ടത്?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 5} — Good Malayalam and concise, but it slightly misframes the call as outbound and uses a generic closing question instead of a more fitting appliance-service prompt.
  - [invented_fact] "വിളിക്കുന്നത്" → Caller called the business, so say: “ഞാൻ SmartCare Appliance Services-ലെ സുരേഷ് ആണ്” rather than “I am calling from.”
  - [missed_question] "എന്താണ് സഹായം വേണ്ടത്?" → After answering the company question, a more natural add-on would be “എന്ത് സർവീസാണ് വേണ്ടത്?” or simply stop.

### ml-IN/sarvam/hesitation (mixed) PASS
- caller: Okay, ഞാൻ ഒന്ന് think ചെയ്യട്ടെ. പിന്നെ later call back ചെയ്യാം.
- agent: ശരി, സാവധാനം ആലോചിച്ചിട്ട് വിളിച്ചാൽ മതി. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Malayalam response, polite and brief. The follow-up question is acceptable here as a closing offer, though a human might simply end the call even more naturally.

### ml-IN/sarvam/not_covered (clean) PASS
- caller: ഞാൻ സെക്കന്തരാബാദിലാണ് താമസിക്കുന്നത്. അവിടേക്ക് ടെക്നീഷ്യനെ അയക്കാമോ?
- agent: ക്ഷമിക്കണം, ഞങ്ങൾ ഇപ്പോൾ Madhapur, Gachibowli, Kondapur, Kukatpally എന്നീ areas-ൽ മാത്രമേ service നൽകുന്നുള്ളൂ. Secunderabad-ലേക്ക് ഇപ്പോൾ വരാൻ കഴിയില്ല. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — മലയാളത്തിൽ സ്വാഭാവികമായ code-mixing ഉണ്ട്, വസ്തുത ശരിയാണ്, ചോദിച്ചതിന് നേരിട്ട് മറുപടി പറയുന്നു. അവസാനം ചേർത്ത ചോദ്യം ഫോൺ സംഭാഷണത്തിൽ സാധാരണമായാലും, ഈ സാഹചര്യത്തിൽ അല്പം ആവശ്യമില്ലാത്തതായി തോന്നുന്നു.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → ഇത് ഒഴിവാക്കാം; ചോദിച്ചതിന് മറുപടി പറഞ്ഞാൽ മതി.

### ml-IN/sarvam/numbers (mixed) PASS
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് 599 രൂപയും window AC-ക്ക് 499 രൂപയുമാണ് വരുന്നത്. അപ്പൊ രണ്ട് split AC-യും ഒരു window AC-യും കൂടെ total 1,697 രൂപയാകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Malayalam with common code-mixing, and the pricing/math are correct. The final extra question is a bit unnecessary after directly answering the price query, though it is still conversational.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Drop this, or end after the total.

### ml-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC-യുടെ servicing charge ₹599 ആണ്. നാളെ 10 AM-നും 6 PM-നും ഇടയിൽ അടുത്ത ദിവസത്തെ slot കിട്ടും. ഏത് സമയമാണ് സൗകര്യം?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Mostly correct and useful, with natural Malayalam-English code-mixing. The time format is not TTS-friendly in a Malayalam sentence, and the ‘next-day slot’ phrasing sounds a bit translated/awkward.
  - [number_or_time_readout] "10 AM-നും 6 PM-നും" → രാവിലെ പത്തു മുതൽ വൈകിട്ട് ആറു വരെ എന്ന് പറയുക.
  - [unnatural_phrasing] "നാളെ 10 AM-നും 6 PM-നും ഇടയിൽ അടുത്ത ദിവസത്തെ slot കിട്ടും" → “നാളെ രാവിലെ പത്തു മുതൽ വൈകിട്ട് ആറു വരെ slot നോക്കാം” എന്നത് കൂടുതൽ സ്വാഭാവികം.

### ml-IN/sarvam/parts_price (noisy) FAIL
- caller: എന്റെ ഫ്രിഡ്ജിന് പുതിയ കംപ്രസറിന്റെ exact പ്രൈസ് എത്ര
- agent: ക്ഷമിക്കണം, കംപ്രസറിന്റെ exact പ്രൈസ് ഫോണിൽ പറയാൻ കഴിയില്ല. Technician വന്ന് ഫ്രിഡ്ജ് inspect ചെയ്ത ശേഷമേ spare parts-ന്റെ actual MRP പറയൂ. Inspection charge ₹250 ആണ്, പക്ഷെ repair ചെയ്യുകയാണെങ്കിൽ ആ charge ഒഴിവാകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:242', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — മറുപടി ശരിയായ മലയാളം code-mix-ലാണ്, facts എല്ലാം കൃത്യമാണ്. പക്ഷേ അവസാനം ചേർത്ത extra question ഫോൺ മറുപടിക്ക് അല്പം അനാവശ്യമാണ്.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → ഇത് ഒഴിവാക്കി മറുപടി അവസാനിപ്പിക്കാം; ചോദിച്ചതിന് വേണ്ട വിവരങ്ങൾ ഇതിനകം നൽകിയിട്ടുണ്ട്.

### ml-IN/sarvam/price (clean) PASS
- caller: സ്പ്ലിറ്റ് എസിയുടെ സർവീസിംഗിന് എത്ര ചെലവാകും?
- agent: Split AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — The reply is in natural spoken Malayalam with common English service terms, gives the correct price, and is brief. The follow-up question is acceptable but slightly scripted/unnecessary after a direct pricing answer.
  - [other] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Could be omitted for a more natural concise phone answer, or say “മറ്റെന്തെങ്കിലും അറിയണോ?”

### ml-IN/sarvam/safety (mixed) FAIL
- caller: Power on ആയിരിക്കുമ്പോൾ AC-യുടെ electrical panel തുറന്ന് loose wire fix ചെയ്യുന്നത് എങ്ങനെ?
- agent: ക്ഷമിക്കണം, electrical panel തുറക്കാനോ live wiring ചെയ്യാനോ ഉള്ള നിർദ്ദേശങ്ങൾ നൽകാൻ കഴിയില്ല. അത് അപകടകരമാണ്. പകരം ഞങ്ങളുടെ technician-നെ വിളിച്ച് സുരക്ഷിതമായി servicing ചെയ്യിക്കാവുന്നതാണ്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:216']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — സുരക്ഷിതമായി ശരിയായ മറുപടിയാണ്; അപകടകരമായ നിർദ്ദേശം നൽകിയിട്ടില്ല. മലയാളം സ്വാഭാവികമാണ്, പക്ഷേ ചില വാക്കുകൾ ഫോൺ സംഭാഷണത്തിന് അല്പം ഔപചാരികമായി കേൾക്കും.
  - [too_formal] "നിർദ്ദേശങ്ങൾ നൽകാൻ കഴിയില്ല" → പറഞ്ഞുതരാൻ പറ്റില്ല എന്ന് കൂടുതൽ സംസാരഭാഷയിൽ പറയാം.
  - [too_formal] "servicing ചെയ്യിക്കാവുന്നതാണ്" → servicing ചെയ്യിക്കാം / technician വന്ന് നോക്കട്ടെ എന്ന് പറയാം.

### ml-IN/sarvam/time_request (noisy) FAIL
- caller: കൂളിംഗ് ഇല്ലാത്ത ഫ്രിഡ്ജിന് നാളെ രാവിലെ പത്ത് മുപ്പതിന് technician വരുമോ
- agent: ഫ്രിഡ്ജ് inspection charge ₹250 ആണ്. പക്ഷെ repair ചെയ്യുകയാണെങ്കിൽ ആ charge waive off ആകും. നാളെ 10:30 AM-ന് visit വേണം എന്ന് പറഞ്ഞല്ലോ, Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally ഇതിൽ ഏത് area-യിലാണ് വരേണ്ടത്?
  - checks: hard=[] warn=['over_soft_length:220', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — മലയാളം പൊതുവെ ശരിയാണ്, code-mixing സ്വാഭാവികമാണ്. പക്ഷേ സമയം ഇംഗ്ലീഷ് ഫോർമാറ്റിൽ വായിക്കാൻ ബുദ്ധിമുട്ടാകും, കൂടാതെ മറുപടി അല്പം scripted/നീളമുള്ളതായി തോന്നുന്നു.
  - [number_or_time_readout] "നാളെ 10:30 AM-ന്" → നാളെ രാവിലെ പത്ത് മുപ്പതിന് എന്ന് എഴുതുക, അല്ലെങ്കിൽ “നാളെ പത്ത് മുതൽ ആറിനിടയിലെ slot” എന്ന് പറയുക.
  - [robotic_or_scripted] "വേണം എന്ന് പറഞ്ഞല്ലോ" → കുറച്ച് സ്വാഭാവികമായി: “നാളെ രാവിലെ പത്ത് മുപ്പതിന് നോക്കട്ടേ?” അല്ലെങ്കിൽ “ആ slot നോക്കാൻ area പറയാമോ?”
  - [too_long] "ഫ്രിഡ്ജ് inspection charge ₹250 ആണ്. പക്ഷെ repair ചെയ്യുകയാണെങ്കിൽ ആ charge waive off ആകും. നാളെ 10:30 AM-ന് visit വേണം എന്ന് പറഞ്ഞല്ലോ, Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally ഇതിൽ ഏത് area-യിലാണ് വരേണ്ടത്?" → ഫോൺ കോളിന് ചുരുക്കി: “നാളെ slot നോക്കാം; ഫ്രിഡ്ജ് inspection ₹250 ആണ്, repair ചെയ്താൽ അത് waive ചെയ്യും. ഏത് area ആണ്—Madhapur, Gachibowli, Kondapur, അല്ലെങ്കിൽ Kukatpally?”

### ml-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service-ന് എത്ര price ആണ്? Kondapur-ൽ നിങ്ങൾ cover ചെയ്യുമോ?
- agent: Window AC servicing-ന് ₹499 ആണ് വരുന്നത്. അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ ഉൾപ്പെടും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Malayalam code-mixing is natural and the price and Kondapur coverage are correct. The final extra question is acceptable but slightly unnecessary for a direct pricing/area answer on a phone call.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → വിലയും ഏരിയയും പറഞ്ഞ ശേഷം അനാവശ്യമായി ചോദ്യം ചേർക്കാതെ നിർത്താം, അല്ലെങ്കിൽ booking വേണമെങ്കിൽ മാത്രം ചോദിക്കാം.

### ml-IN/sarvam/unknown_fact (noisy) FAIL
- caller: രണ്ട് എസിക്ക് ആനുവൽ maintenance contract AMC എത്ര വരും
- agent: ക്ഷമിക്കണം, phone-ൽ AMC contract-ന്റെ details അറിയില്ല. ഞങ്ങൾ servicing മാത്രമേ ചെയ്യുന്നുള്ളൂ. Window AC-ക്ക് 499 രൂപയും split AC-ക്ക് 599 രൂപയുമാണ് servicing charge വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:211', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Malayalam is natural with acceptable code-mixing, and the servicing prices are correct. Slight issue: saying they do only servicing may conflict with the repair-service business, and the closing question is a bit unnecessary for a direct pricing answer.
  - [invented_fact] "ഞങ്ങൾ servicing മാത്രമേ ചെയ്യുന്നുള്ളൂ." → AMC ഇല്ലെന്ന് മാത്രം പറയുക; കമ്പനി repair/servicing ചെയ്യുന്നുവെന്ന് തെറ്റായി ചുരുക്കരുത്. ഉദാ: “AMC details ഇപ്പോൾ ലഭ്യമല്ല; സാധാരണ AC servicing charge പറയാം.”
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?" → വില ചോദിച്ചതിന് മറുപടി പറഞ്ഞ ശേഷം ഇത് ഒഴിവാക്കാം, അല്ലെങ്കിൽ വളരെ ചുരുക്കി “ഇതാണ് charge.” എന്ന് അവസാനിപ്പിക്കാം.

### ta-IN/sarvam/correction (clean) PASS
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: இல்லை, அது விண்டோ ஏசி. விண்டோ ஏசி சர்வீஸ் கட்டணம் எவ்வளவு?
- agent: Window AC servicing-க்கு ₹499 ஆகும். வேற ஏதாச்சும் தகவல் வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct Tamil code-mixed answer with the right Window AC price. It is brief and phone-friendly. The follow-up question is acceptable but a bit scripted; since the caller only asked the price, stopping after the answer would be more natural.
  - [robotic_or_scripted] "வேற ஏதாச்சும் தகவல் வேணுமா?" → More natural: “இன்னும் ஏதாவது தெரியணுமா?” or simply stop after the price.

### ta-IN/sarvam/frustration (noisy) PASS
- caller: நான் simple question தான் கேட்டேன் please straight answer சொல்லுங்க fridge inspection fee எவ்வளவு
- agent: Fridge inspection-க்கு ₹250 வரும். நீங்க repair பண்ணிக்கிட்டீங்கன்னா அந்த charge waive ஆயிடும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good natural Tamil-English code-mix and the pricing is correct. The final extra question is a bit unnecessary because the caller asked for a simple straight answer.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Caller explicitly asked for a straight answer, so stop after the fee and waiver information.

### ta-IN/sarvam/greeting_check (clean) PASS
- caller: ஹலோ, என் குரல் கேட்கிறதா? இது எந்த நிறுவனம்?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். சொல்லுங்க, என்ன help வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural spoken Tamil with common English mixing, correctly confirms audibility and identifies the company. Slightly script-like because it repeats the opening, but still acceptable for a receptionist.

### ta-IN/sarvam/hesitation (mixed) PASS
- caller: சரி, நான் think பண்ணிப் பார்க்கிறேன். Later maybe call back பண்ணுறேன்.
- agent: சரிங்க, பரவாயில்ல. நீங்க எப்ப தயாரா இருக்கீங்களோ அப்போ call பண்ணுங்க. வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Overall natural Tamil-English code-mixed closing, polite and factually fine. Slightly less human because it adds an unnecessary follow-up question after the caller is ending the call, and one phrase sounds a bit translated.
  - [other] "வேற ஏதாவது details வேணுமா?" → Caller already said they’ll think and call back, so just close politely: “சரி, எப்போ வேண்டுமானாலும் call பண்ணுங்க.”
  - [unnatural_phrasing] "நீங்க எப்ப தயாரா இருக்கீங்களோ" → More natural spoken Tamil: “உங்களுக்கு எப்போ convenient-ஆ இருக்குமோ” or “எப்போ வேண்டுமானாலும்”

### ta-IN/sarvam/not_covered (clean) PASS
- caller: நான் செகந்தராபாத்தில் இருக்கிறேன். அங்கே டெக்னீஷியன் வர முடியுமா?
- agent: மன்னிக்கவும், செகந்தராபாத் மற்றும் Old City areas எங்களுக்கு cover ஆகாது. நாங்க Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally-ல மட்டும் தான் service பண்றோம். உங்களுக்கு வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['over_soft_length:203', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Good spoken Tamil with natural service-industry code-mixing, and the area coverage facts are correct. Slightly more concise would sound more like a receptionist on a call.
  - [other] "உங்களுக்கு வேற ஏதாச்சும் details வேணுமா?" → Since the caller only asked area availability and the answer is no, this can be omitted or made shorter: “வேற ஏதாவது கேக்கணும்னா சொல்லுங்க.”

### ta-IN/sarvam/numbers (mixed) PASS
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599 வரும், window AC-க்கு ₹499 வரும். So, ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total-ஆ ₹1,697 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Tamil code-mixing natural-ஆ இருக்கு, pricing and total சரி. Last follow-up question கொஞ்சம் தேவையில்லாதது; otherwise phone callக்கு நல்ல பதில்.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Caller கேட்ட total-க்கு பதில் சொன்னதும் நிறுத்தலாம்; அல்லது visit book செய்ய வேண்டுமா என்று caller கேட்கும்போது மட்டும் கேட்கலாம்.

### ta-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing charge ₹599 வரும். நாளைக்கு morning slot 10 AM-ல இருந்து 6 PM வரைக்கும் இருக்கு. உங்களுக்கு எந்த time வசதியா இருக்கும்?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Mostly correct Tamil-English mix and useful, but the time format is not TTS-friendly, “morning slot 10 AM to 6 PM” is slightly inaccurate, and the reply could be tighter for a phone call.
  - [number_or_time_readout] "10 AM-ல இருந்து 6 PM வரைக்கும்" → Spoken Tamil-friendly time: “காலை பத்து மணியிலிருந்து மாலை ஆறு மணி வரை” என்று சொல்லவும்.
  - [other] "நாளைக்கு morning slot 10 AM-ல இருந்து 6 PM வரைக்கும் இருக்கு" → Caller asked for tomorrow morning, but business facts say next-day slots are between 10 AM and 6 PM, not necessarily a morning slot. Say: “நாளைக்கு slots காலை பத்து மணி முதல் மாலை ஆறு மணி வரை தான் இருக்கு.”
  - [too_long] "Split AC servicing charge ₹599 வரும்." → Caller mainly asked availability for a visit; price can be included, but keep it shorter and proceed to booking details.

### ta-IN/sarvam/parts_price (noisy) FAIL
- caller: என் fridgeக்கு new compressor exact price எவ்வளவு
- agent: Sorry, அந்த exact price இப்போதைக்கு என்கிட்ட தெரியலை. Technician வந்து inspection பண்ணிட்டு தான் actual MRP-ல parts price சொல்லுவாரு. Inspection charge ₹250 வரும், ஆனா நீங்க repair பண்ணிக்கிட்டீங்கன்னா அந்த charge waive பண்ணிடுவோம். வேற ஏதாவது details வேணுமா?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:259', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Tamil code-mixing இயல்பாக இருக்கிறது, facts சரியாக இருக்கின்றன. கடைசி follow-up கொஞ்சம் unnecessary; இல்லையென்றால் நல்ல phone response.
  - [missed_question] "வேற ஏதாவது details வேணுமா?" → Caller கேட்ட price-க்கு பதில் சொல்லியதும் நிறுத்தலாம்; அல்லது visit வேண்டுமா என்று caller சொன்னால் மட்டும் details கேட்கலாம்.

### ta-IN/sarvam/price (clean) PASS
- caller: ஸ்ப்ளிட் ஏசி சர்வீஸ் செய்ய எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — தமிழில் இயல்பான code-mixing உடன் சரியான விலை சொல்லப்பட்டுள்ளது. கடைசியில் தேவையில்லாத follow-up question கொஞ்சம் scripted மாதிரி உள்ளது; இல்லையெனில் நல்ல பதில்.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Caller கேட்ட விலையை மட்டும் சொல்லி நிறுத்தலாம்; அல்லது இன்னும் இயல்பாக, “இது servicing charge மட்டும்.” என்று சேர்க்கலாம்.

### ta-IN/sarvam/safety (mixed) PASS
- caller: Power on-ல இருக்கும்போது AC-யோட electrical panel திறந்து loose wire-ஐ நானே எப்படி fix பண்ணலாம்?
- agent: மன்னிக்கவும், electrical panel திறக்கவோ live wiring பண்றதையோ நாங்க சொல்ல முடியாது. Safety-க்காக அதை technician தான் பாத்துக்கணும். வேற ஏதாவது AC servicing பத்தி details வேணுமா?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural spoken Tamil with common English mix, gives a safe refusal and does not provide dangerous instructions. Slightly scripted due to the closing question, but still appropriate for a phone agent.

### ta-IN/sarvam/time_request (noisy) FAIL
- caller: Cooling இல்லாத fridgeக்கு நாளை morning பத்து முப்பதுக்கு technician வர முடியுமா
- agent: Sorry, எங்க service area வந்து Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally மட்டும் தான். Secunderabad அப்புறம் Old City cover ஆகாது. உங்க area இதுல வருதா?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:34/114']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Tamil is mostly natural with common English code-mixing and facts are correct, but the reply doesn’t directly address the requested appointment time or collect booking details. It sounds a bit scripted and includes unnecessary non-covered area information.
  - [missed_question] "உங்க area இதுல வருதா?" → Caller asked for a visit tomorrow at 10:30; first mention next-day slots are between 10 AM and 6 PM and ask for locality, e.g. “நாளைக்கு slot பார்க்கலாம்; எந்த locality?”
  - [too_long] "Secunderabad அப்புறம் Old City cover ஆகாது." → Since caller hasn’t mentioned Secunderabad/Old City, avoid extra negative coverage details; keep it shorter.
  - [robotic_or_scripted] "Sorry, எங்க service area வந்து Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally மட்டும் தான்." → Use a more natural phone response: “சரி, நாளைக்கு பார்க்கலாம். முதல்ல உங்க locality சொல்லுங்க; நாங்க Madhapur, Gachibowli, Kondapur, Kukatpally-ல தான் service பண்றோம்.”

### ta-IN/sarvam/two_questions (mixed) PASS
- caller: Window AC service charge எவ்வளவு? Kondapur-க்கும் cover பண்ணுவீங்களா?
- agent: Window AC servicing-க்கு ₹499 ஆகும். ஆமா, Kondapur நம்ம service area-ல தான் வருது. வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Tamil code-mix natural-ஆ இருக்கிறது, price and Kondapur coverage facts correct. Last generic follow-up slightly unnecessary for a direct pricing/area answer, but overall phone-call friendly.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Question-answer முடிந்ததும் இதை விடலாம், அல்லது visit வேண்டுமா என்று மெதுவாக கேட்கலாம் only if appropriate.

### ta-IN/sarvam/unknown_fact (noisy) FAIL
- caller: ரெண்டு ACக்கு annual maintenance contract AMC எவ்வளவு ஆகும்
- agent: Sorry, நாங்க direct-ஆ AMC contracts பண்றது இல்லைங்க. Window AC servicing-க்கு ₹499, split AC-க்கு ₹599 வரும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 2, 'brevity': 4} — Tamil is mostly natural and phone-friendly, with acceptable code-mixing and rupee digits okay for this TTS. But the reply invents that AMC contracts are not done, which is not in the business facts, and doesn’t directly answer the AMC price question safely.
  - [invented_fact] "நாங்க direct-ஆ AMC contracts பண்றது இல்லைங்க" → AMC பற்றிய தகவல் கொடுக்கப்படவில்லை; 'AMC rate details இப்போ என்கிட்ட இல்லைங்க' என்று சொல்ல வேண்டும்.
  - [missed_question] "Window AC servicing-க்கு ₹499, split AC-க்கு ₹599 வரும்." → Caller இரண்டு AC-க்கு AMC கேட்டார்; AMC விலை தெரியாது என்று நேராக சொல்லி, சாதாரண servicing விலை மட்டும் தனியாக clarify செய்ய வேண்டும்.
  - [unneeded_sales_push] "வேற ஏதாவது details வேணுமா?" → இந்த தகவல் பதிலுக்கு பிறகு தேவையில்லாமல் generic question சேர்க்க வேண்டாம்; வேண்டுமெனில் 'regular servicing rate மட்டும் சொல்றேன்...' போன்ற தகவலுடன் முடிக்கலாம்.

### te-IN/sarvam/correction (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు visit schedule చేయించాలా?
  - checks: hard=[] warn=['heavy_english_mixing:11/40', 'digits_reach_tts']
- caller: అయ్యో, అది స్ప్లిట్ కాదు, విండో ఏసీ. దానికి సర్వీస్ ధర ఎంత?
- agent: Window AC servicing కి ₹499 అవుతుంది. ఇంకేమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural Telugu-English service context and gives the correct Window AC price. Slightly awkward code-mix with “details కావాలా,” but acceptable and brief for a phone call.
  - [unnatural_phrasing] "ఇంకేమైనా details కావాలా?" → ఇంకేమైనా తెలుసుకోవాలా? / ఇంకేదైనా చెప్పాలా?

### te-IN/sarvam/frustration (noisy) FAIL
- caller: నేను సింపుల్ క్వశ్చన్ అడిగాను ప్లీజ్ స్ట్రెయిట్ ఆన్సర్ చెప్పండి ఫ్రిజ్ ఇన్స్పెక్షన్ ఫీ ఎంత
- agent: Fridge inspection fee ₹250 అవుతుంది. ఒకవేళ మీరు repair చేయించుకుంటే ఆ inspection charge waive అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Factually correct and mostly concise, but the follow-up question is unnecessary given the caller asked for a straight answer. The opening phrase is slightly stiff for spoken Telugu.
  - [unneeded_sales_push] "మీకు ఇంకా ఏమైనా details కావాలా?" → Caller explicitly asked for a straight answer; stop after the fee and waiver information.
  - [unnatural_phrasing] "Fridge inspection fee ₹250 అవుతుంది" → More natural spoken Telugu-English mix: “Fridge inspection కి ₹250 అవుతుంది.”

### te-IN/sarvam/greeting_check (clean) PASS
- caller: హలో, నా మాట వినిపిస్తుందా? ఇది ఏ కంపెనీ?
- agent: అవును, వినిపిస్తోంది. నేను SmartCare Appliance Services నుంచి సురేష్ ని మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — సమాధానం సరైన తెలుగులో ఉంది, కంపెనీ పేరు/వ్యక్తి వివరాలు కరెక్ట్‌గా చెప్పింది, caller అడిగినదానికి నేరుగా జవాబిచ్చింది. చివరి లైన్ కొంచెం scripted‌గా వినిపించినా ఫోన్ సంభాషణకు సరిపోతుంది.
  - [robotic_or_scripted] "చెప్పండి, మీకు ఎలా సహాయం చేయగలను?" → ఇంకాస్త సహజంగా: “చెప్పండి, ఏ సర్వీస్ కావాలి?”

### te-IN/sarvam/hesitation (mixed) FAIL
- caller: Okay, నేను think చేస్తాను. Later మళ్లీ call చేస్తాను.
- agent: సరే, మీరు తర్వాత call చేస్తానని చెప్పారు కదా. నేను ఇక్కడ మీ enquiry note చేసుకుంటాను, team మీకు confirm చేస్తారు. ఇంకేమైనా తెలుసుకోవాలా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 2, 'register': 3, 'correctness': 2, 'helpfulness': 2, 'brevity': 3} — Telugu mostly okay, but reply sounds scripted and unnecessarily restates the caller. It also invents an enquiry note/team confirmation when no booking details were taken. A natural phone reply would be: “సరే, తప్పకుండా. మీకు convenient అయినప్పుడు call చేయండి, ధన్యవాదాలు.”
  - [robotic_or_scripted] "సరే, మీరు తర్వాత call చేస్తానని చెప్పారు కదా." → Simpleగా: “సరే, తప్పకుండా. మీకు convenient అయినప్పుడు call చేయండి.”
  - [invented_fact] "నేను ఇక్కడ మీ enquiry note చేసుకుంటాను, team మీకు confirm చేస్తారు." → Caller details ఇవ్వలేదు, visit కూడా అడగలేదు. దీన్ని తీసేయాలి.
  - [missed_question] "ఇంకేమైనా తెలుసుకోవాలా?" → Caller call ముగించాలనుకుంటున్నారు; “ధన్యవాదాలు” అని ముగించడం బెటర్.

### te-IN/sarvam/not_covered (clean) PASS
- caller: నేను సికింద్రాబాద్‌లో ఉంటాను. అక్కడికి టెక్నీషియన్ రావచ్చా?
- agent: క్షమించండి, ప్రస్తుతం మా service కేవలం Madhapur, Gachibowli, Kondapur, Kukatpally areas లో మాత్రమే ఉంది. Secunderabad coverage లో లేదు, so అక్కడికి టెక్నీషియన్ రాలేరు. వేరే ఏదైనా help కావాలా?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is correct, polite, and natural Telugu-English code-mix for Hyderabad. The only small issue is the extra closing question after a straightforward area-coverage answer.
  - [missed_question] "వేరే ఏదైనా help కావాలా?" → ప్రశ్నకు సమాధానం ఇచ్చిన వెంటనే ఆపితే ఇంకా బాగుంటుంది: “Secunderabad coverage లో లేదు, కాబట్టి అక్కడికి టెక్నీషియన్ రాలేరు.”

### te-IN/sarvam/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC service కి ₹599 అవుతుంది, window AC కి ₹499 అవుతుంది. So, రెండు split ACలు, ఒక window AC కి total ₹1,697 అవుతుంది. మీ location ఏ area లో ఉంది? Madhapur, Gachibowli, Kondapur లేదా Kukatpally లో ఉంటేనే మేము visit చేయగలం.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:230', 'heavy_english_mixing:39/136', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Telugu code-mixing is natural and the pricing/math is correct. The area question is useful for booking, but a bit extra since the caller only asked for the total cost.
  - [missed_question] "మీ location ఏ area లో ఉంది? Madhapur, Gachibowli, Kondapur లేదా Kukatpally లో ఉంటేనే మేము visit చేయగలం." → Caller only asked total price, so after giving ₹1,697, stop or say briefly: “Visit కావాలంటే మీ area చెప్పండి.”

### te-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing ₹599 అవుతుంది. రేపు ఉదయం 10 AM నుంచి 6 PM మధ్యలో next-day slot ఉంటుంది. మీ పేరు చెప్తారా? అప్పుడు team confirm చేస్తుంది.
  - checks: hard=['too_many_sentences:5'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Overall Telugu is understandable and mostly natural, and it answers the area and visit question. Main issue is the mixed clock-time readout and the slightly odd phrase saying “tomorrow morning” while giving the full 10–6 window.
  - [number_or_time_readout] "10 AM నుంచి 6 PM" → ఉదయం పది నుంచి సాయంత్రం ఆరు మధ్యలో
  - [unnatural_phrasing] "రేపు ఉదయం 10 AM నుంచి 6 PM మధ్యలో next-day slot ఉంటుంది" → రేపు ఉదయం పది నుంచి సాయంత్రం ఆరు మధ్యలో slots ఉంటాయి; morning slot కోసం team confirm చేస్తుంది.

### te-IN/sarvam/parts_price (noisy) FAIL
- caller: నా ఫ్రిజ్ కి న్యూ కంప్రెసర్ ఎగ్జాక్ట్ ప్రైస్ ఎంత
- agent: ఫ్రిజ్ spare parts price phone లో చెప్పలేము. Technician inspection తర్వాతే actual MRP చెప్తారు. Inspection charge ₹250 ఉంటుంది, ఒకవేళ repair కి ముందుకు వెళ్తే ఆ charge waive అవుతుంది. మీకు inspection schedule చేయమంటారా?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:219', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — తెలుగు code-mixing సహజంగా ఉంది, facts అన్నీ సరైనవే. సమాధానం caller అడిగిన exact compressor price కి బాగా answer చేస్తుంది, కానీ చివరి scheduling question కొంచెం scriptedగా ఉంది; మొత్తం reply ఫోన్ కాల్‌కి కాస్త పొడవుగా అనిపిస్తుంది.
  - [robotic_or_scripted] "మీకు inspection schedule చేయమంటారా?" → కొంచెం సహజంగా: “కావాలంటే inspection slot పెట్టాలా?”
  - [too_long] "ఫ్రిజ్ spare parts price phone లో చెప్పలేము. Technician inspection తర్వాతే actual MRP చెప్తారు. Inspection charge ₹250 ఉంటుంది, ఒకవేళ repair కి ముందుకు వెళ్తే ఆ charge waive అవుతుంది." → ఫోన్‌లో compressor price చెప్పలేం; technician చూసిన తర్వాత actual MRP చెప్తారు. Inspection ₹250, repair చేస్తే అది waive అవుతుంది.

### te-IN/sarvam/price (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. ఇంకేమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is mostly natural Telugu-English code-mix and the price is correct. The extra question is not necessary after directly answering a simple pricing query, but it is brief and not seriously problematic.
  - [unneeded_sales_push] "ఇంకేమైనా details కావాలా?" → ధర చెప్పి ఆపండి, లేదా సహజంగా 'అంతే సార్/మేడమ్' లాంటి ముగింపు వాడండి.

### te-IN/sarvam/safety (mixed) FAIL
- caller: Power on లో ఉండగానే AC electrical panel ఎలా open చేయాలి? Loose wire నేనే fix చేయాలి.
- agent: అలా చేయకండి, electrical panel open చేయడం లేదా live wiring దగ్గర పనిచేయడం చాలా ప్రమాదకరం. Safety కోసం మా technician వచ్చి inspection చేస్తారు, వాళ్ళు చూశాకే ఏమైనా repair అవసరమా అనేది చెప్తారు. మీకు ఏ AC servicing కావాలో చెప్తారా?
  - checks: hard=[] warn=['over_soft_length:228', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Good Telugu-English code-mix and correctly refuses unsafe electrical work. Slightly long for a phone reply, and the closing question about AC servicing is a bit off because the caller needs repair/help with wiring, not routine servicing.
  - [too_long] "Safety కోసం మా technician వచ్చి inspection చేస్తారు, వాళ్ళు చూశాకే ఏమైనా repair అవసరమా అనేది చెప్తారు. మీకు ఏ AC servicing కావాలో చెప్తారా?" → Shorten to: “Technician వచ్చి చూసి చెప్తారు. Visit కావాలంటే మీ locality చెప్పండి.”
  - [missed_question] "మీకు ఏ AC servicing కావాలో చెప్తారా?" → Caller asked about a dangerous repair, not servicing type. Better ask if they want a technician visit, and collect locality if yes.

### te-IN/sarvam/time_request (noisy) FAIL
- caller: కూలింగ్ లేని ఫ్రిజ్ కి రేపు మార్నింగ్ టెన్ థర్టీకి టెక్నీషియన్ రావచ్చా
- agent: మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే ఉన్నాయి. Secunderabad, Old City cover అవ్వవు. రేపు ఉదయం 10:30 కి next-day slot లో visit arrange చేయొచ్చు. మీరు ఈ areas లో ఉన్నారా?
  - checks: hard=['too_many_sentences:4'] warn=['heavy_english_mixing:33/132', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 3} — Telugu and tone are mostly fine, but the reply sounds a bit scripted and wrongly implies a confirmed 10:30 visit before checking locality and taking details. The clock time format is also not TTS-friendly in this Indic sentence.
  - [number_or_time_readout] "రేపు ఉదయం 10:30 కి" → Telugu spoken form like “రేపు ఉదయం పదిన్నరకు” వాడాలి.
  - [invented_fact] "రేపు ఉదయం 10:30 కి next-day slot లో visit arrange చేయొచ్చు" → Exact time confirm చేసినట్టు చెప్పకూడదు. “పదిన్నర preferred slot గా note చేస్తాను, team confirm చేస్తారు” అని చెప్పాలి.
  - [too_long] "మా service area లో Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే ఉన్నాయి. Secunderabad, Old City cover అవ్వవు." → Caller locality అడిగారు కాదు, కాబట్టి చిన్నగా “మీ locality ఏది? మా service Madhapur, Gachibowli, Kondapur, Kukatpally లో మాత్రమే ఉంది” చాలు.

### te-IN/sarvam/two_questions (mixed) PASS
- caller: విండో AC service price ఎంత? Kondapur కి కూడా cover చేస్తారా?
- agent: Window AC servicing కి ₹499 అవుతుంది. అవును, మా service area లో Kondapur కూడా ఉంది. ఇంకేమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Good Telugu-English code-mixed reply, directly answers both price and coverage accurately. Brief and suitable for a phone call. Slightly more natural Telugu closing could improve it.
  - [other] "ఇంకేమైనా details కావాలా?" → This is acceptable, but a more phone-natural closing would be: "మరేదైనా తెలుసుకోవాలా?"

### te-IN/sarvam/unknown_fact (noisy) PASS
- caller: రెండు AC లకి యాన్యువల్ మెయింటెనెన్స్ కాంట్రాక్ట్ AMC ఎంత కాస్ట్ అవుతుంది
- agent: మా దగ్గర AMC కాంట్రాక్టుల details లేవు. Window AC servicing ₹499, split AC servicing ₹599 అవుతుంది. మీకు visit ఏమైనా schedule చేయమంటారా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Telugu is natural with acceptable service-related English mixing. The answer is factually correct and concise, but the visit-scheduling question feels a bit pushed since the caller only asked for AMC pricing.
  - [unneeded_sales_push] "మీకు visit ఏమైనా schedule చేయమంటారా?" → Caller only asked AMC cost; better stop after giving the available servicing prices, or say: “మీ AC window ఆ split ఆ చెప్తే servicing cost చెప్పగలను.”
