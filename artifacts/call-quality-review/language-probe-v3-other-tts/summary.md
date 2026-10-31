# Language probe language-probe-v3-other-tts

Schema `sim_af3b29fe01cb4735aff7ac0ae17ff7e0`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | cartesia | 3/6 | 4.42 | human_naturalness 3.50 |
| en-IN | gemini | 2/6 | 4.39 | human_naturalness 3.50 |
| en-IN | gnani | 1/6 | 4.25 | human_naturalness 3.50 |
| gu-IN | cartesia | 4/6 | 4.42 | human_naturalness 4.00 |
| gu-IN | gemini | 3/6 | 4.06 | human_naturalness 3.67 |
| gu-IN | gnani | 3/6 | 3.97 | human_naturalness 3.50 |
| hi-IN | cartesia | 4/6 | 4.31 | human_naturalness 3.83 |
| hi-IN | gemini | 4/6 | 4.22 | human_naturalness 3.83 |
| hi-IN | gnani | 3/6 | 3.92 | human_naturalness 3.50 |
| kn-IN | cartesia | 3/6 | 4.47 | human_naturalness 4.00 |
| kn-IN | gemini | 2/6 | 4.11 | human_naturalness 3.83 |
| kn-IN | gnani | 2/6 | 4.17 | human_naturalness 3.67 |
| ml-IN | cartesia | 3/6 | 4.25 | human_naturalness 3.67 |
| ml-IN | gemini | 4/6 | 4.53 | human_naturalness 4.00 |
| ml-IN | gnani | 0/6 | 4.17 | language_fit 4.00 |
| ta-IN | cartesia | 4/6 | 4.42 | human_naturalness 4.00 |
| ta-IN | gemini | 5/6 | 4.56 | helpfulness 4.00 |
| ta-IN | gnani | 3/6 | 4.25 | human_naturalness 4.00 |
| te-IN | cartesia | 3/6 | 4.28 | human_naturalness 3.83 |
| te-IN | gemini | 4/6 | 4.28 | human_naturalness 4.00 |
| te-IN | gnani | 3/6 | 4.19 | human_naturalness 3.83 |

## Transcripts

### en-IN/cartesia/frustration (mixed) FAIL
- caller: I am asking one simple thing, just tell me clearly what the fridge inspection charge is.
- agent: The fridge inspection costs 250 rupees. However, that charge is waived if you go ahead with the repair. Is there anything else you would like to know?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Correct answer in Indian English, but the closing question sounds scripted and unnecessary after the caller asked for one simple charge.
  - [robotic_or_scripted] "Is there anything else you would like to know?" → Drop this, or say more naturally: “That’s it.”
  - [too_formal] "However, that charge is waived if you go ahead with the repair." → Say: “If you go ahead with the repair, we’ll waive that charge.”

### en-IN/cartesia/greeting_check (mixed) FAIL
- caller: Hello, am I audible? What company are you calling from?
- agent: Yes, you are audible. I am calling from SmartCare Appliance Services. How can I help you today?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 5} — Clear and brief in Indian English, but a bit call-centre scripted and slightly incorrect because the agent is receiving the call, not calling from the company.
  - [robotic_or_scripted] "How can I help you today?" → Use a more natural line like, “Please tell me.” or just answer the company question without adding a scripted prompt.
  - [invented_fact] "I am calling from SmartCare Appliance Services." → Since the caller called the business, say “This is SmartCare Appliance Services” instead of “I am calling from…”

### en-IN/cartesia/numbers (mixed) PASS
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For two split ACs, that is 1,198 rupees, and one window AC is 499 rupees. So the total comes to 1,697 rupees.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct, concise, and in natural Indian English. Slightly itemised/calculator-like, but perfectly acceptable for a phone pricing answer.
  - [robotic_or_scripted] "that is 1,198 rupees" → Say it a bit more conversationally, e.g. “Two split ACs will be 1,198 rupees…”

### en-IN/cartesia/other_language (fixed) PASS
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: We do cover Kondapur, and next-day visits are available between 10 AM and 6 PM. Could you tell me your name so I can note this down?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Good Indian English reply, factually correct and concise. It answers coverage and next-day availability, but could handle the caller’s morning-slot request more directly before taking booking details.
  - [missed_question] "Could you tell me your name so I can note this down?" → Also ask for the preferred slot, since the caller asked for tomorrow morning and slots are only between 10 AM and 6 PM; e.g., “Sure, we cover Kondapur. Tomorrow slots are between 10 AM and 6 PM—what time works for you, and may I have your name?”

### en-IN/cartesia/price (mixed) PASS
- caller: What is the charge for split AC service, please?
- agent: The split AC servicing charge is five hundred and ninety nine rupees. Which area are you located in?
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The price is correct and the wording is natural for Indian English. The only issue is asking for the caller’s area when they only asked for the service charge.
  - [unneeded_sales_push] "Which area are you located in?" → Omit this unless the caller asks to book a visit, e.g. just say: “The split AC servicing charge is five hundred and ninety nine rupees.”

### en-IN/cartesia/time_request (mixed) FAIL
- caller: Can you send someone tomorrow morning at ten-thirty? The fridge is not cooling.
- agent: I can note that down for you. We do cover fridge inspections, which are 250 rupees, but the charge is waived if you go ahead with the repair. Before I record this, could you tell me your name and which area you are in? We serve Madhapur, Gachibowli, Kondapur, and Kukatpally only.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:280', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Correct and in suitable Indian English, but a bit scripted and longer than an ideal live phone response.
  - [unnatural_phrasing] "We do cover fridge inspections" → Say more naturally: “For fridge visits, inspection is 250 rupees…”
  - [too_long] "I can note that down for you. We do cover fridge inspections, which are 250 rupees, but the charge is waived if you go ahead with the repair. Before I record this, could you tell me your name and which area you are in? We serve Madhapur, Gachibowli, Kondapur, and Kukatpally only." → Make it shorter for a phone call: “Sure, I’ll note it. Fridge inspection is 250 rupees, waived if you repair; can I have your name and locality? We cover Madhapur, Gachibowli, Kondapur and Kukatpally.”

### en-IN/gemini/frustration (mixed) FAIL
- caller: I am asking one simple thing, just tell me clearly what the fridge inspection charge is.
- agent: The fridge inspection costs 250 rupees. If you go ahead with the repair, that inspection charge is waived. Is there anything else you would like to know?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — The price and waiver information are correct and in suitable Indian English. The closing question feels a bit call-centre scripted, especially after the caller asked for one simple clear answer.
  - [robotic_or_scripted] "Is there anything else you would like to know?" → Drop this or make it more natural, e.g. “That’s it for the inspection charge.”

### en-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, am I audible? What company are you calling from?
- agent: Yes, you are audible. I am Suresh calling from SmartCare Appliance Services. How can I help you today?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct Indian English, polite and brief. It answers the caller’s question accurately, though the closing line feels a bit scripted/repetitive after the initial greeting.
  - [robotic_or_scripted] "How can I help you today?" → Slightly more natural after repeating the company: “Yes, audible. This is SmartCare Appliance Services, Suresh speaking.”

### en-IN/gemini/numbers (mixed) PASS
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For one split AC servicing it is 599 rupees, and for a window AC it is 499 rupees. So for two split ACs and one window AC, the total comes to 1,697 rupees.
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Correct and clear Indian English, with the right total. Slightly wordy for a phone reply because it repeats the per-unit pricing, but it still sounds natural and helpful.

### en-IN/gemini/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: Yes, we cover Kondapur. For a split AC with cooling issue, servicing is five hundred ninety nine rupees. We can arrange a next-day visit between ten AM and six PM. Could you tell me your name so I can note this down?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:216']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Good Indian English and mostly natural. It answers the area and visit availability, but slightly overstates the price for a cooling fault and does not directly address the caller’s morning-slot request.
  - [invented_fact] "For a split AC with cooling issue, servicing is five hundred ninety nine rupees." → Say the servicing charge is ₹599, and any repair or spare parts will be quoted by the technician after inspection.
  - [missed_question] "We can arrange a next-day visit between ten AM and six PM." → Acknowledge the morning request: “Tomorrow morning may be possible, but the team will confirm; visits are between 10 AM and 6 PM.”

### en-IN/gemini/price (mixed) FAIL
- caller: What is the charge for split AC service, please?
- agent: Split AC servicing costs 599 rupees. Is there anything else you would like to know?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The price is correct and the reply is brief in Indian English. The follow-up sounds a bit scripted for a live receptionist; otherwise it fits the context.
  - [robotic_or_scripted] "Is there anything else you would like to know?" → Use a more natural phone phrasing like: “Anything else, sir/ma’am?” or simply stop after the price.

### en-IN/gemini/time_request (mixed) FAIL
- caller: Can you send someone tomorrow morning at ten-thirty? The fridge is not cooling.
- agent: I can note that for you. We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only, and visits are next-day slots between 10 AM and 6 PM. Could you tell me your name and locality so I can pass that along?
  - checks: hard=[] warn=['over_soft_length:207', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Correct and in Indian English, but a bit scripted and longer than needed for a live call. It should first acknowledge the requested 10:30 tomorrow slot, then quickly collect name/locality.
  - [robotic_or_scripted] "Could you tell me your name and locality so I can pass that along?" → More natural: “May I have your name and locality?”
  - [too_long] "We cover Madhapur, Gachibowli, Kondapur, and Kukatpally only, and visits are next-day slots between 10 AM and 6 PM." → Shorten for phone: “Tomorrow slots are between 10 AM and 6 PM, and we cover only Madhapur, Gachibowli, Kondapur and Kukatpally.”

### en-IN/gnani/frustration (mixed) FAIL
- caller: I am asking one simple thing, just tell me clearly what the fridge inspection charge is.
- agent: The fridge inspection costs two hundred and fifty rupees. However, that charge is waived if you go ahead with the repair. Is there anything else you would like to know?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Factually correct and in the right language, with numbers written suitably for the TTS. It answers the question, but the wording is a bit scripted and the extra closing question is unnecessary for such a direct pricing query.
  - [robotic_or_scripted] "However, that charge is waived if you go ahead with the repair." → Use a more spoken phrasing: "If you go ahead with the repair, we won’t charge the inspection separately."
  - [robotic_or_scripted] "Is there anything else you would like to know?" → Avoid the call-centre stock line after answering a direct question; say nothing more, or "That’s it."

### en-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, am I audible? What company are you calling from?
- agent: Yes, you are audible. I am calling from SmartCare Appliance Services. How can I help you today?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 5} — Clear and polite Indian English, but “I am calling from” is slightly incorrect because it’s an inbound call, and the closing line is a bit scripted.
  - [other] "I am calling from SmartCare Appliance Services" → Say “This is SmartCare Appliance Services” or “You’ve reached SmartCare Appliance Services,” since the customer called them.
  - [robotic_or_scripted] "How can I help you today?" → After answering the company question, a more natural phone reply would be “Tell me, how can I help?”

### en-IN/gnani/numbers (mixed) FAIL
- caller: For two split ACs and one window AC, what will the total come to?
- agent: For two split ACs, it is five hundred ninety nine rupees each, and one window AC is four hundred ninety nine rupees. So the total comes to one thousand seven hundred ninety seven rupees. Would you like to go ahead and book a visit?
  - checks: hard=[] warn=['over_soft_length:231', 'three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — The pricing and total are correct, and number words are appropriate since the TTS engine does not read digits. It’s polite and clear, but a bit wordy for a live call and adds a booking prompt after an information-only question.
  - [too_long] "For two split ACs, it is five hundred ninety nine rupees each, and one window AC is four hundred ninety nine rupees. So the total comes to one thousand seven hundred ninety seven rupees." → Shorten for a call: “Two split ACs at five ninety-nine each plus one window AC at four ninety-nine — total is one thousand seven hundred ninety-seven rupees.”
  - [unneeded_sales_push] "Would you like to go ahead and book a visit?" → Avoid appending a booking push unless the caller asks; or keep it softer: “If you’d like, I can help book a visit.”

### en-IN/gnani/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: We do cover Kondapur, but visits are only in next-day slots between 10 AM and 6 PM, so same-day service cannot be guaranteed. Could you tell me your name so I can note this down for the team?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Correct facts and acceptable Indian English, but a bit formal/scripted for a phone call and the time should not be written with digits for this TTS engine.
  - [number_or_time_readout] "10 AM and 6 PM" → Since digits are not read automatically, say “ten AM and six PM” or “ten in the morning to six in the evening.”
  - [robotic_or_scripted] "same-day service cannot be guaranteed" → Say more naturally: “same-day may not be possible.”
  - [too_long] "Could you tell me your name so I can note this down for the team?" → After answering, ask briefly: “May I take your name?”

### en-IN/gnani/price (mixed) FAIL
- caller: What is the charge for split AC service, please?
- agent: The charge for split AC servicing is five hundred ninety nine rupees. Which area are you located in?
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The price is correct and the reply is brief, but the added area question is unnecessary for a simple pricing query and makes it sound a bit like a script.
  - [robotic_or_scripted] "Which area are you located in?" → Don’t add a question unless the caller is trying to book; just answer the price, or say: “Split AC service is five hundred and ninety-nine rupees.”
  - [unnatural_phrasing] "five hundred ninety nine rupees" → In Indian English, “five hundred and ninety-nine rupees” sounds more natural when spoken.

### en-IN/gnani/time_request (mixed) FAIL
- caller: Can you send someone tomorrow morning at ten-thirty? The fridge is not cooling.
- agent: I can note that for you. Our visits are next-day slots between 10 AM and 6 PM, so tomorrow morning at ten thirty AM is possible. Could you share your name and locality so I can pass that along?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — The reply is polite and mostly natural Indian English, and it correctly handles the booking request. Main problems are TTS-unfriendly time formatting and a slightly long, scripted explanation for a phone call.
  - [number_or_time_readout] "10 AM and 6 PM" → Write it as “ten AM and six PM” for this TTS engine.
  - [number_or_time_readout] "ten thirty AM" → Say “ten-thirty in the morning” or just “ten-thirty”.
  - [too_long] "Our visits are next-day slots between 10 AM and 6 PM, so tomorrow morning at ten thirty AM is possible." → Shorten to: “Tomorrow around ten-thirty should be possible, subject to confirmation.”

### gu-IN/cartesia/frustration (mixed) PASS
- caller: મેં simple question પૂછ્યો છે, fridge inspection feeનો straight answer આપો.
- agent: Fridge inspectionની fee ₹250 છે. પણ જો તમે એનું repair કરાવશો, તો એ inspection charge માફ થઈ જશે. બીજું કંઈ પૂછવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Good Gujarati with natural code-mixing and correct pricing. The extra follow-up question is slightly unnecessary given the caller explicitly wanted a straight answer, but the main answer is clear and concise.
  - [missed_question] "બીજું કંઈ પૂછવું છે તમારે?" → Caller asked for a straight answer; better stop after the fee/waiver info, or say “બસ, આટલું જ.”

### gu-IN/cartesia/greeting_check (mixed) PASS
- caller: Hello, મારી voice આવે છે? આ કઈ company છે?
- agent: હા, અવાજ બરાબર આવે છે. હું SmartCare Appliance Services માંથી સુરેશ બોલું છું. કહો, તમારે શું help જોઈએ છે?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — સંદર્ભ મુજબ જવાબ સ્વાભાવિક, ટૂંકો અને સાચો છે. અવાજ આવવાની પુષ્ટિ અને કંપનીનું નામ સીધું જણાવે છે.

### gu-IN/cartesia/numbers (mixed) PASS
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service ₹599 અને window AC ની ₹499 છે. એટલે બે split અને એક window માટે total ₹1,797 થશે. બીજું કંઈ પૂછવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ ગુજરાતી અને સ્વાભાવિક કોડ-મિક્સિંગમાં છે, ભાવ અને ટોટલ સાચાં છે. છેલ્લો પ્રશ્ન થોડો સ્ક્રિપ્ટેડ લાગે છે અને માહિતીવાળા જવાબ પછી જરૂરી નથી.
  - [robotic_or_scripted] "બીજું કંઈ પૂછવું છે તમારે?" → માહિતી આપીને અટકી જવું, અથવા વધુ સ્વાભાવિક રીતે: “બસ, આટલું થશે.”

### gu-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC servicing નો ખર્ચ ₹599 થશે. કાલે સવારે visit માટે team confirm કરશે, તો તમારે કયો time ફાવશે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 4} — Gujarati is mostly natural and polite, but the reply doesn’t collect the customer’s name and is a bit loose about tomorrow morning slots. Pricing is not fully qualified for a cooling issue where repair or parts may be extra.
  - [missed_question] "તો તમારે કયો time ફાવશે?" → Preferred slot સાથે customer નું નામ પણ પૂછવું: “તમારું નામ અને કાલે 10 થી 6 વચ્ચે કયો slot ફાવશે?”
  - [invented_fact] "કાલે સવારે visit માટે team confirm કરશે" → Visits 10 AM થી 6 PM વચ્ચે જ છે, એટલે “કાલે 10 થી 6 વચ્ચે slot મળી શકે, team confirm કરશે” એવું કહો.
  - [other] "Split AC servicing નો ખર્ચ ₹599 થશે" → Caller ने not cooling કહ્યું છે, એટલે servicing charge સાથે “repair/parts extra હોય તો technician inspection પછી કહેશે” ઉમેરવું વધુ સાચું રહેશે.

### gu-IN/cartesia/price (mixed) PASS
- caller: Split AC servicingનો charge કેટલો આવે?
- agent: Split AC servicingનો charge ₹599 છે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Gujarati code-mixing is natural and the price is correct. The follow-up is acceptable, though a human might phrase it slightly softer like “બીજું કંઈ પૂછવું હોય તો કહો.”

### gu-IN/cartesia/time_request (mixed) FAIL
- caller: મારું fridge cooling નથી કરતું. Technician કાલે morningમાં 10:30 વાગ્યે આવી શકે?
- agent: Fridge cooling નથી કરતું એ જાણીને અફસોસ થયો. કાલે 10:30 વાગ્યે visit થઈ શકે, પણ એ next-day slot માં confirm થશે. તમારો area કયો છે? અમારી service Madhapur, Gachibowli, Kondapur અને Kukatpally માં જ available છે.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:211', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Reply mostly stays in Gujarati with natural service-area information, but it sounds a bit scripted and the clock time is not TTS-friendly for an Indic sentence.
  - [robotic_or_scripted] "Fridge cooling નથી કરતું એ જાણીને અફસોસ થયો." → આને વધુ સ્વાભાવિક રીતે કહો: “બરાબર, fridge cooling issue માટે કાલે slot જોઈ લઈએ.”
  - [number_or_time_readout] "10:30 વાગ્યે" → Gujarati TTS માટે સમય શબ્દોમાં લખો: “સાડા દસ વાગ્યે” અથવા “દસ-ત્રીસ વાગ્યે”.
  - [unnatural_phrasing] "એ next-day slot માં confirm થશે" → વધુ કુદરતી રીતે કહો: “એ team confirm કરશે” અથવા “કાલનો slot team confirm કરશે.”

### gu-IN/gemini/frustration (mixed) PASS
- caller: મેં simple question પૂછ્યો છે, fridge inspection feeનો straight answer આપો.
- agent: Fridge inspection નો charge ₹250 છે, પણ જો તમે repair કરાવો તો આ inspection charge માફ થઈ જશે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Gujarati with natural urban code-mixing, correct price and waiver, and concise. The extra follow-up question is unnecessary given the caller explicitly wanted only a straight answer.
  - [missed_question] "બીજું કંઈ જાણવું છે તમારે?" → Caller asked for just a straight answer; stop after the fee/waiver information.

### gu-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, મારી voice આવે છે? આ કઈ company છે?
- agent: હા, મારો અવાજ આવે છે. હું SmartCare Appliance Services માંથી સુરેશ બોલું છું. કહો, શું કામ હતું?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in Gujarati, answers both questions correctly, and is brief. Slightly blunt phrasing at the end for a receptionist, but otherwise natural and appropriate.
  - [unnatural_phrasing] "શું કામ હતું?" → થોડું વધુ સ્વાભાવિક/વિનમ્ર: “કહો, શું મદદ કરું?” અથવા “કહો, શું કામ છે?”

### gu-IN/gemini/numbers (mixed) FAIL
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service ₹599 અને window AC ની ₹499 છે. એટલે બે split અને એક window માટે total ₹1,797 થશે. બીજું કંઈ પૂછવું છે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — ભાષા અને ટોન સારી છે, પણ કુલ રકમ ખોટી ગણાઈ છે. ફોન પરના સીધા ભાવના જવાબમાં છેલ્લો વધારાનો પ્રશ્ન ટાળવો વધુ સારું.
  - [invented_fact] "total ₹1,797 થશે" → સાચો ટોટલ ₹1,697 છે: બે split AC ₹1,198 + એક window AC ₹499.
  - [missed_question] "બીજું કંઈ પૂછવું છે?" → જવાબને અહીં જ પૂરો કરો, અથવા બહુ સ્વાભાવિક રીતે કહો: “કુલ ₹1,697 થશે.”

### gu-IN/gemini/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC servicing નો charge ₹599 છે. આવતીકાલે સવારે 10 થી 6 ની વચ્ચે next-day visit માટે slot મળી શકે, પણ same-day ની guarantee નથી હોતી. તમારે visit માટે booking કરાવવું છે?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:219', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 4} — Mostly natural Gujarati with acceptable service-industry code-mixing, but it gives an awkward/incorrect time phrase, mentions same-day unnecessarily, and doesn’t move straight into collecting booking details.
  - [missed_question] "આવતીકાલે સવારે 10 થી 6 ની વચ્ચે" → Caller asked for tomorrow morning; say next-day slots are between 10 AM and 6 PM, and ask for a preferred morning slot/details.
  - [other] "સવારે 10 થી 6" → This sounds like 10 in the morning to 6 in the morning. Say “સવારે 10 થી સાંજે 6 વચ્ચે” or “10 AM થી 6 PM વચ્ચે”.
  - [missed_question] "same-day ની guarantee નથી હોતી" → Same-day guarantee is irrelevant because the caller asked for tomorrow; omit it here.
  - [missed_question] "તમારે visit માટે booking કરાવવું છે?" → Since the caller already asked for a technician, directly collect name, issue confirmation, locality, and preferred slot.

### gu-IN/gemini/price (mixed) PASS
- caller: Split AC servicingનો charge કેટલો આવે?
- agent: Split AC servicingનો charge ₹599 છે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Gujarati is natural with acceptable English service terms and the price is correct. The follow-up question is a bit unnecessary for a direct pricing answer on a phone call, but otherwise it sounds fine.
  - [missed_question] "બીજું કંઈ જાણવું છે તમારે?" → Caller asked only the price; better stop after the price or say: “Split AC servicingનો charge ₹599 છે.”

### gu-IN/gemini/time_request (mixed) FAIL
- caller: મારું fridge cooling નથી કરતું. Technician કાલે morningમાં 10:30 વાગ્યે આવી શકે?
- agent: Fridge cooling નથી કરતું એ સાંભળીને દુઃખ થયું. Fridge inspection નો charge ₹250 છે, પણ જો તમે repair કરાવો તો એ charge માફ થઈ જશે. અમારી service Madhapur, Gachibowli, Kondapur અને Kukatpallyમાં જ available છે. કાલે સવારે 10:30 વાગ્યાનો slot next-day visit માં આવી જશે.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:268', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 2, 'register': 3, 'correctness': 3, 'helpfulness': 3, 'brevity': 2} — Gujarati mostly fits, but the reply sounds scripted, is too long for a phone call, uses a digit clock time, and overstates the 10:30 visit instead of taking details for confirmation.
  - [robotic_or_scripted] "Fridge cooling નથી કરતું એ સાંભળીને દુઃખ થયું." → આ કાઢી નાખો; સીધું કહો: "Fridge inspection નો charge ₹250 છે..."
  - [number_or_time_readout] "10:30 વાગ્યાનો slot" → "સાડા દસનો slot" લખો.
  - [invented_fact] "કાલે સવારે 10:30 વાગ્યાનો slot next-day visit માં આવી જશે." → ખાતરી આપવાને બદલે કહો: "કાલે સાડા દસનો request લઈ શકું, team confirm કરશે."
  - [missed_question] "અમારી service Madhapur, Gachibowli, Kondapur અને Kukatpallyમાં જ available છે." → Caller appointment માંગે છે, એટલે locality પૂછો: "તમારી locality કઈ છે?"
  - [too_long] "Fridge cooling નથી કરતું એ સાંભળીને દુઃખ થયું. Fridge inspection નો charge ₹250 છે, પણ જો તમે repair કરાવો તો એ charge માફ થઈ જશે. અમારી service Madhapur, Gachibowli, Kondapur અને Kukatpallyમાં જ available છે. કાલે સવારે 10:30 વાગ્યાનો slot next-day visit માં આવી જશે." → એક-બે ટૂંકા વાક્યમાં કહો: "Fridge inspection ₹250 છે, repair કરાવશો તો waive થશે. કાલે સાડા દસનો request લઈ શકું; પહેલા તમારી locality કઈ છે?"

### gu-IN/gnani/frustration (mixed) FAIL
- caller: મેં simple question પૂછ્યો છે, fridge inspection feeનો straight answer આપો.
- agent: Fridge inspection નો ખર્ચ ₹250 છે, પણ જો તમે repair કરાવવાનું નક્કી કરો તો આ inspection charge માફ થઈ જશે. તમારે અત્યારે કોઈ service બુક કરાવવી છે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — જવાબ Gujaratiમાં અને factually સાચો છે, પણ TTS માટે રકમ શબ્દોમાં હોવી જોઈએ અને callerના 'straight answer' પછી service bookingનો સવાલ થોડો અનાવશ્યક લાગે છે.
  - [number_or_time_readout] "₹250" → Engine digits નથી વાંચતું, એટલે 'બસો પચાસ રૂપિયા' લખવું જોઈએ.
  - [unneeded_sales_push] "તમારે અત્યારે કોઈ service બુક કરાવવી છે?" → Callerએ straight answer માગ્યો છે, એટલે booking question વગર જવાબ પૂરો કરો.

### gu-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, મારી voice આવે છે? આ કઈ company છે?
- agent: હા, મારો અવાજ આવે છે. હું SmartCare Appliance Servicesમાંથી સુરેશ બોલું છું. કહો, તમારે શું help જોઈએ છે?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply Gujaratiમાં છે, સ્વાભાવિક code-mixing છે અને companyની ઓળખ સાચી આપે છે. થોડું અનાવશ્યક રીતે help પૂછે છે, પણ ફોન વાતચીતમાં અપ્રાકૃતિક નથી.
  - [other] "કહો, તમારે શું help જોઈએ છે?" → Callerએ company કઈ છે એ પૂછ્યું હતું, એટલે અહીં અટકવું કે 'SmartCare Appliance Services છે, ઘરનાં appliance repair કરીએ છીએ' કહેવું વધુ સીધું થાય.

### gu-IN/gnani/numbers (mixed) PASS
- caller: બે split AC અને એક window AC service કરાવું તો total કેટલું થશે?
- agent: Split AC ની service ₹599 અને window AC ની ₹499 છે. એટલે બે split અને એક window AC ના total ₹1,697 થશે. બીજું કંઈ જાણવું છે તમારે?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — જવાબનો ભાવ અને ગણતરી સાચી છે અને ગુજરાતી બોલચાલ સારી છે. મુખ્ય સમસ્યા એ છે કે આ TTS માટે આંકડા/₹ લખાણમાં નહીં, ગુજરાતી શબ્દોમાં હોવા જોઈએ.
  - [number_or_time_readout] "₹599 અને window AC ની ₹499 છે" → engine_reads_digits false હોવાથી રકમ ગુજરાતી શબ્દોમાં બોલાવો: “Split AC ની સર્વિસ પાંચસો નવ્વાણું રૂપિયા અને window AC ની ચારસો નવ્વાણું રૂપિયા છે.”
  - [number_or_time_readout] "₹1,697 થશે" → “કુલ એક હજાર છસો સત્તાણું રૂપિયા થશે.”
  - [missed_question] "બીજું કંઈ જાણવું છે તમારે?" → માહિતીનો જવાબ પૂરતો છે; ફોન પર વધુ સ્વાભાવિક રીતે “બસ, આટલું થશે.” પર અટકી શકાય.

### gu-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: હા, Kondapur અમારા service area માં આવે છે. Split AC servicing નો charge ₹599 છે. Technician આવતીકાલે સવારે આવી શકશે, પણ same-day visit ની guarantee નથી હોતી. તમારે સવારે કયો time ફાવશે?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 2} — Gujarati overall okay and polite, but it gives an over-certain tomorrow morning commitment, mentions irrelevant same-day policy, and uses digits despite the TTS setting.
  - [number_or_time_readout] "₹599" → engine_reads_digits false છે, એટલે 'પાંચસો નવ્વાણું રૂપિયા' લખવું.
  - [invented_fact] "Technician આવતીકાલે સવારે આવી શકશે" → આટલું definite ન કહો; 'આવતીકાલે 10 થી 6 વચ્ચે slot મળી શકે, team confirm કરશે' કહો.
  - [missed_question] "same-day visit ની guarantee નથી હોતી" → Caller એ tomorrow પૂછ્યું છે, same-day વાત જરૂરી નથી; next-day slot timing પર જવાબ આપો.
  - [missed_question] "તમારે સવારે કયો time ફાવશે?" → Visit માટે નામ, appliance/issue તો મળ્યું છે, હવે નામ, locality confirmation અને preferred slot પૂછો; અથવા 'તમારું નામ અને 10 પછીનો preferred slot કહેશો?' કહો.
  - [too_long] "હા, Kondapur અમારા service area માં આવે છે. Split AC servicing નો charge ₹599 છે. Technician આવતીકાલે સવારે આવી શકશે, પણ same-day visit ની guarantee નથી હોતી. તમારે સવારે કયો time ફાવશે?" → Phone call માટે 1-2 ટૂંકા વાક્યમાં રાખો.

### gu-IN/gnani/price (mixed) PASS
- caller: Split AC servicingનો charge કેટલો આવે?
- agent: Split AC servicingનો charge ₹599 છે. બીજું કંઈ પૂછવું છે?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — જવાબ સાચી ગુજરાતી code-mixમાં છે અને ભાવ પણ સાચો છે, પણ આ TTS માટે રકમ અંકોમાં ન લખવી જોઈએ. અંતે ઉમેરાયેલું પ્રશ્ન થોડું અનાવશ્યક લાગે છે.
  - [number_or_time_readout] "₹599" → engine_reads_digits false હોવાથી ગુજરાતીમાં બોલાય તે રીતે લખો: “પાંચસો નવ્વાણું રૂપિયા”
  - [missed_question] "બીજું કંઈ પૂછવું છે?" → જવાબ પછી needless question ટાળો અથવા વધુ સ્વાભાવિક રીતે કહો: “Split AC servicingનો charge પાંચસો નવ્વાણું રૂપિયા છે.”

### gu-IN/gnani/time_request (mixed) FAIL
- caller: મારું fridge cooling નથી કરતું. Technician કાલે morningમાં 10:30 વાગ્યે આવી શકે?
- agent: Fridge cooling નથી કરતું એ સાંભળીને અફસોસ થયો. હા, અમે કાલે સવારે 10:30 વાગ્યાનો next-day slot આપી શકીએ છીએ. તમારી locality કઈ છે, Madhapur, Gachibowli, Kondapur કે Kukatpally?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Gujarati mostly acceptable, but it wrongly confirms an exact appointment time and sounds a bit scripted. The time should be written in Gujarati words for this TTS setup.
  - [robotic_or_scripted] "Fridge cooling નથી કરતું એ સાંભળીને અફસોસ થયો." → આને બદલે સીધું કહો: “હા, fridge માટે inspection visit રાખી શકીએ.”
  - [invented_fact] "હા, અમે કાલે સવારે 10:30 વાગ્યાનો next-day slot આપી શકીએ છીએ." → Exact 10:30 confirm ન કરો; કહો: “કાલે દસથી છ વચ્ચે preferred slot તરીકે મૂકી દઈએ, team confirm કરશે.”
  - [number_or_time_readout] "10:30" → engine_reads_digits false હોવાથી સમય શબ્દોમાં લખો: “દસ ને ત્રીસ” અથવા વધુ સ્વાભાવિક રીતે “સાડા દસ”.
  - [missed_question] "તમારી locality કઈ છે, Madhapur, Gachibowli, Kondapur કે Kukatpally?" → Locality પૂછવી સાચી છે, પણ પહેલા visit confirm ન કરો. Covered area થયા પછી નામ, appliance issue અને preferred slot લેવું.

### hi-IN/cartesia/frustration (mixed) PASS
- caller: मैंने simple question पूछा था, fridge inspection fee का straight answer दीजिए।
- agent: Fridge inspection का charge ₹250 है। अगर आप repair के साथ आगे बढ़ते हैं, तो ये charge waive हो जाएगा। और कुछ जानना है आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply Hindi/Hinglish में natural है और facts सही हैं. बस caller की नाराज़गी और straight answer की मांग के बाद अंत में extra question थोड़ा unnecessary लगता है.
  - [missed_question] "और कुछ जानना है आपको?" → Caller ने straight answer मांगा था; यहीं रुकना बेहतर: “Fridge inspection का charge ₹250 है। Repair करवाते हैं तो ये waive हो जाएगा।”

### hi-IN/cartesia/greeting_check (mixed) PASS
- caller: Hello, मेरी आवाज़ clear आ रही है? और ये कौन-सी company है?
- agent: हाँ, आवाज़ बिल्कुल clear आ रही है। मैं SmartCare Appliance Services से सुरेश हूँ। बताइए, आज किस चीज़ में मदद चाहिए?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is in natural Hindi with common English code-mixing, confirms audibility and identifies the company correctly. It is brief and appropriate for a phone call. Slightly generic closing, but still human-sounding.

### hi-IN/cartesia/numbers (mixed) PASS
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing ₹599 और window AC की ₹499 है। तो दो split और एक window AC का total ₹1,697 आएगा। और कोई जानकारी चाहिए?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Hindi natural है, pricing और total सही हैं. आख़िर में अतिरिक्त सवाल थोड़ा unnecessary लगता है क्योंकि caller ने सिर्फ total पूछा था, पर overall reply phone call के लिए ठीक है.
  - [missed_question] "और कोई जानकारी चाहिए?" → सीधे जवाब पर खत्म करें, जैसे: “तो total ₹1,697 आएगा।”

### hi-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में आता है। Split AC servicing का charge ₹599 है। Technician inspection के बाद जो भी spare parts लगेंगे, वो actual MRP पर extra लगेंगे, उसकी price phone पर नहीं बताई जा सकती। कल सुबह का visit note कर लेता हूँ, team slot confirm करेगी।
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:267', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Hindi natural और facts mostly सही हैं, लेकिन reply booking के लिए जरूरी नाम नहीं मांगता और caller के सीधे visit सवाल पर थोड़ा ज़्यादा pricing detail दे देता है.
  - [missed_question] "कल सुबह का visit note कर लेता हूँ, team slot confirm करेगी।" → Visit request के लिए नाम भी पूछना चाहिए: “आपका नाम बता दीजिए, मैं Kondapur में split AC cooling issue के लिए कल 10 से 12 का request note कर देता हूँ; team confirm करेगी.”
  - [too_long] "Split AC servicing का charge ₹599 है। Technician inspection के बाद जो भी spare parts लगेंगे, वो actual MRP पर extra लगेंगे, उसकी price phone पर नहीं बताई जा सकती।" → Caller ने price नहीं पूछा था, इसलिए इसे छोटा रखें या booking details लेने के बाद ही बताएं.

### hi-IN/cartesia/price (mixed) PASS
- caller: स्प्लिट AC servicing का कितना charge है?
- agent: Split AC servicing का charge ₹599 है। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही भाषा में है, तथ्य सही है और फोन पर बोलने लायक छोटा है। बस कीमत बताने के बाद अतिरिक्त सवाल थोड़ा अनावश्यक लगता है।
  - [missed_question] "और कुछ जानकारी चाहिए आपको?" → Pricing answer के बाद यहीं रुकना बेहतर है, या बोलें: "जी, Split AC servicing का charge ₹599 है."

### hi-IN/cartesia/time_request (mixed) FAIL
- caller: मेरा fridge cooling नहीं कर रहा। क्या technician कल morning 10:30 पर आ सकता है?
- agent: Fridge cooling नहीं कर रहा, समझ गया। हमारे technician कल सुबह 10:30 के slot में visit कर सकते हैं, लेकिन same-day visit की guarantee नहीं होती। बस ये confirm करना था कि आप Madhapur, Gachibowli, Kondapur या Kukatpally में ही रहते हैं ना?
  - checks: hard=[] warn=['over_soft_length:236', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Hindi and tone are mostly okay, but it incorrectly makes the 10:30 visit sound confirmed, adds irrelevant same-day wording, and uses a clock-time format that is not TTS-friendly in a Hindi sentence.
  - [invented_fact] "हमारे technician कल सुबह 10:30 के slot में visit कर सकते हैं" → Exact slot confirm na karein; bolein: “कल सुबह साढ़े दस का preferred slot note कर लेता हूँ, team confirm कर देगी.”
  - [missed_question] "लेकिन same-day visit की guarantee नहीं होती" → Caller ne kal ke liye पूछा है, same-day वाली बात unnecessary है; इसकी जगह next-day confirmation की बात करें.
  - [number_or_time_readout] "10:30" → Hindi phone reply में time बोलकर लिखें: “साढ़े दस” या “सुबह साढ़े दस”.
  - [robotic_or_scripted] "Fridge cooling नहीं कर रहा, समझ गया।" → Restatement हटाकर सीधे जवाब दें: “जी, कल सुबह साढ़े दस का preferred slot note कर लेता हूँ…”

### hi-IN/gemini/frustration (mixed) PASS
- caller: मैंने simple question पूछा था, fridge inspection fee का straight answer दीजिए।
- agent: Fridge inspection का charge ₹250 है। अगर आप repair करवाते हैं, तो ये charge waive off हो जाएगा। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply Hindi-English natural code-mix में है, facts सही हैं और कीमत साफ बताई गई है. आख़िर का follow-up थोड़ा unnecessary है क्योंकि caller ने सिर्फ straight answer मांगा था.
  - [missed_question] "और कुछ जानकारी चाहिए आपको?" → Caller ने straight answer मांगा था, इसलिए बस कीमत बताकर रुकना बेहतर: “Fridge inspection का charge ₹250 है। Repair करवाते हैं तो ये charge waive off हो जाएगा.”

### hi-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, मेरी आवाज़ clear आ रही है? और ये कौन-सी company है?
- agent: हाँ, आवाज़ बिल्कुल clear आ रही है। मैं SmartCare Appliance Services से Suresh हूँ। बताइए, किस appliance में problem आ रही है?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply सही भाषा में है, आवाज़ और company का जवाब ठीक देता है, और facts सही हैं। आख़िर में appliance problem पूछना थोड़ा scripted/proactive लगता है, मगर call context में बहुत बड़ी गलती नहीं है।
  - [robotic_or_scripted] "बताइए, किस appliance में problem आ रही है?" → Caller ने सिर्फ आवाज़ और company पूछी थी; जवाब के बाद हल्का-सा 'जी, बोलिए' काफी होता।

### hi-IN/gemini/numbers (mixed) PASS
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing ₹599 और window AC की ₹499 है। तो दो split और एक window AC का total ₹1,797 आएगा। क्या आप visit book करवाना चाहेंगे?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Hindi code-mixing natural hai, pricing aur total सही हैं. बस जानकारी वाले सवाल के बाद booking push थोड़ा unnecessary लगता है.
  - [unneeded_sales_push] "क्या आप visit book करवाना चाहेंगे?" → Caller ने सिर्फ total पूछा है; जवाब यहीं खत्म करें, या बहुत हल्का विकल्प दें: “अगर visit चाहिए तो बता दीजिए.”

### hi-IN/gemini/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में है। Split AC servicing का charge ₹599 है। कल सुबह 10 AM से 6 PM के बीच visit schedule हो सकती है, पर same-day guarantee नहीं होती। आपकी booking के लिए अपना नाम बता दीजिए।
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:207', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Reply mostly सही है और Kondapur/price correctly बताता है, लेकिन time format TTS-friendly नहीं है, tomorrow morning के जवाब में पूरा 10–6 window बोलना थोड़ा awkward है, और same-day guarantee वाली बात अनावश्यक है।
  - [number_or_time_readout] "10 AM से 6 PM" → Hindi call में समय बोलकर लिखें: “सुबह दस बजे से शाम छह बजे के बीच”।
  - [other] "कल सुबह 10 AM से 6 PM के बीच visit schedule हो सकती है" → Caller ने tomorrow morning पूछा है; बेहतर: “कल सुबह का slot team confirm कर देगी” या “कल सुबह दस से बारह के बीच request डाल देता हूँ, team confirm करेगी।”
  - [missed_question] "पर same-day guarantee नहीं होती" → यहाँ same-day की बात relevant नहीं है, क्योंकि caller ने कल के लिए पूछा है। इसे हटाएँ।

### hi-IN/gemini/price (mixed) PASS
- caller: स्प्लिट AC servicing का कितना charge है?
- agent: स्प्लिट AC servicing का charge ₹599 है। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — सही और संक्षिप्त जवाब है। Hindi-English code-mix natural है, कीमत business facts से match करती है, और TTS digits/amount ठीक पढ़ेगा। हल्का सा scripted लग सकता है, लेकिन phone receptionist के लिए acceptable है।

### hi-IN/gemini/time_request (mixed) FAIL
- caller: मेरा fridge cooling नहीं कर रहा। क्या technician कल morning 10:30 पर आ सकता है?
- agent: Fridge inspection का charge ₹250 है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। हम Madhapur, Gachibowli, Kondapur और Kukatpally में service देते हैं, और कल सुबह 10:30 के slots available हैं। आप किस area से बोल रहे हैं?
  - checks: hard=[] warn=['over_soft_length:235', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Reply mostly natural Hindi-English mix है, लेकिन 10:30 slot available बताना business facts के खिलाफ है क्योंकि team confirmation चाहिए. Time format भी TTS phone call के लिए ठीक नहीं है.
  - [invented_fact] "कल सुबह 10:30 के slots available हैं" → Availability पक्की न बताएं; कहें: “कल के visits 10 बजे से 6 बजे के बीच होते हैं, 10:30 की preference मैं note कर देता हूँ, team confirm करेगी.”
  - [number_or_time_readout] "10:30" → Hindi call में clock time बोलने लायक लिखें: “साढ़े दस” या “सुबह साढ़े दस”.

### hi-IN/gnani/frustration (mixed) FAIL
- caller: मैंने simple question पूछा था, fridge inspection fee का straight answer दीजिए।
- agent: Fridge inspection की fee ₹250 है। अगर आप repair करवाते हैं, तो ये charge waive off हो जाएगा। और कुछ जानकारी चाहिए आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — जवाब तथ्यात्मक रूप से सही है और भाषा ठीक है, लेकिन TTS सेटिंग के हिसाब से रकम अंकों में नहीं होनी चाहिए। अंत में अतिरिक्त सवाल caller की मांग के हिसाब से थोड़ा अनावश्यक और scripted लगता है।
  - [number_or_time_readout] "₹250" → इसे 'ढाई सौ रुपये' या 'दो सौ पचास रुपये' बोलें, क्योंकि इस TTS में digits/amounts अपने-आप हिंदी में नहीं पढ़े जाते।
  - [missed_question] "और कुछ जानकारी चाहिए आपको?" → Caller ने straight answer मांगा था; सवाल जोड़ने की जरूरत नहीं। यहीं जवाब खत्म करें।

### hi-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, मेरी आवाज़ clear आ रही है? और ये कौन-सी company है?
- agent: हाँ, आवाज़ साफ़ आ रही है। मैं SmartCare Appliance Services से Suresh बात कर रहा हूँ। बताइए, आज किस चीज़ में मदद करूँ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही भाषा में, छोटा और तथ्यात्मक है। आवाज़ clear होने का जवाब देता है और कंपनी का नाम बताता है, लेकिन caller ने कौन-सी company है पूछा था—उसमें कंपनी का काम बताना ज़्यादा helpful होता।
  - [missed_question] "मैं SmartCare Appliance Services से Suresh बात कर रहा हूँ।" → कंपनी क्या करती है, यह भी संक्षेप में बताएं: “ये SmartCare Appliance Services है, हम Hyderabad में home appliance repair करते हैं।”
  - [unnatural_phrasing] "Suresh" → हिंदी TTS के लिए नाम देवनागरी में लिखें: “सुरेश”

### hi-IN/gnani/numbers (mixed) PASS
- caller: दो split AC और एक window AC की servicing का total कितना आएगा?
- agent: Split AC की servicing ₹599 और window AC की ₹499 है। तो दो split और एक window AC का total ₹1,697 आएगा। और कोई जानकारी चाहिए आपको?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब तथ्यात्मक और प्राकृतिक है, लेकिन इस TTS में अंकों/₹ को हिंदी में लिखना चाहिए। आख़िर में अतिरिक्त सवाल थोड़ा unnecessary लगता है।
  - [number_or_time_readout] "₹599 और window AC की ₹499" → engine digits नहीं पढ़ता, इसलिए बोलकर लिखें: “Split AC की servicing पाँच सौ निन्यानवे रुपये और window AC की चार सौ निन्यानवे रुपये है।”
  - [number_or_time_readout] "₹1,697" → “कुल एक हज़ार छह सौ सत्तानवे रुपये आएगा।”
  - [missed_question] "और कोई जानकारी चाहिए आपको?" → Price answer के बाद इसे हटाना बेहतर है; अगर रखना हो तो छोटा रखें: “बस इतना ही total होगा।”

### hi-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: हाँ, Kondapur हमारे service area में आता है। Split AC की servicing ₹599 में हो जाएगी। कल सुबह 10 AM से 6 PM के बीच visit schedule हो सकती है, पर same-day guarantee नहीं है। आप अपना नाम बता देंगे तो मैं team को note करवा देता हूँ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:229', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 2} — Reply mostly Hindi and polite, but it is too long for a phone turn, has TTS-unfriendly numbers/times, mentions irrelevant same-day guarantee, and slightly overpromises the AC issue as covered under servicing.
  - [number_or_time_readout] "₹599" → engine_reads_digits false है, इसलिए बोलकर लिखें: “पाँच सौ निन्यानवे रुपये”.
  - [number_or_time_readout] "10 AM से 6 PM" → हिंदी में बोलने लायक लिखें: “सुबह दस बजे से शाम छह बजे तक”.
  - [invented_fact] "कल सुबह 10 AM से 6 PM के बीच visit schedule हो सकती है" → Caller ने morning मांगा है; पूरा 10 से 6 window “सुबह” नहीं है. कहें: “कल के slots सुबह दस बजे से शाम छह बजे तक हैं; morning preference note कर देता हूँ.”
  - [missed_question] "पर same-day guarantee नहीं है" → Caller ने tomorrow पूछा है, same-day की बात गैर-ज़रूरी है. इसे हटाएँ.
  - [invented_fact] "Split AC की servicing ₹599 में हो जाएगी" → Not cooling repair में parts/extra repair लग सकते हैं. कहें: “Split AC servicing पाँच सौ निन्यानवे रुपये है; parts अगर लगे तो technician inspection के बाद बताएगा.”

### hi-IN/gnani/price (mixed) PASS
- caller: स्प्लिट AC servicing का कितना charge है?
- agent: Split AC servicing का charge ₹599 है। बताइए, और कुछ जानना है आपको?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — जवाब सही और संक्षिप्त है, लेकिन इस TTS में digits/₹ खुद सही नहीं पढ़े जाते, इसलिए रकम शब्दों में होनी चाहिए।
  - [number_or_time_readout] "₹599" → कहें: पाँच सौ निन्यानवे रुपये

### hi-IN/gnani/time_request (mixed) FAIL
- caller: मेरा fridge cooling नहीं कर रहा। क्या technician कल morning 10:30 पर आ सकता है?
- agent: Fridge inspection का charge ₹250 है, लेकिन अगर आप repair करवाते हैं तो ये charge waive हो जाएगा। कल सुबह 10:30 का slot note कर लेता हूँ team के लिए, बस area confirm कर दीजिए — क्या आप Madhapur, Gachibowli, Kondapur या Kukatpally में रहते हैं?
  - checks: hard=[] warn=['over_soft_length:242', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 4, 'brevity': 2} — जवाब ज़्यादातर सही और हिंदी-इंग्लिश mix natural है, लेकिन digits/TTS के लिए ठीक नहीं हैं, exact slot को ज़्यादा पक्का दिखा रहा है, और वाक्य फोन कॉल के लिए थोड़ा लंबा है।
  - [number_or_time_readout] "₹250" → engine_reads_digits false है, इसलिए बोलने लायक लिखें: 'ढाई सौ रुपये'.
  - [number_or_time_readout] "10:30" → समय बोलने लायक लिखें: 'साढ़े दस बजे'.
  - [invented_fact] "कल सुबह 10:30 का slot note कर लेता हूँ" → Business facts में visits next-day slots 10 AM से 6 PM के बीच हैं और team confirm करती है; exact 10:30 slot पक्का/नोट करने जैसा न कहें. कहें: 'साढ़े दस की preference team को बता दूँगा, confirmation वे देंगे'.
  - [too_long] "बस area confirm कर दीजिए — क्या आप Madhapur, Gachibowli, Kondapur या Kukatpally में रहते हैं?" → फोन पर छोटा रखें: 'आप कौन-से area में हैं?'

### kn-IN/cartesia/frustration (mixed) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ, please straight answer ಕೊಡಿ. Fridge inspection fee ಎಷ್ಟು?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ, ಆ inspection charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay? Fridge inspectionಗೆ exact fee ಎಷ್ಟು ಅಂತ straight ಆಗಿ ಹೇಳಿ.
- agent: ಕ್ಷಮಿಸಿ, ಸ್ವಲ್ಪ confusion ಆಯ್ತು ಅನ್ಸುತ್ತೆ. Fridge inspection-ಗೆ exact fee ₹250. ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಈ charge waive off ಆಗುತ್ತೆ. ಇನ್ನೇನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada code-mixing is natural and the ₹250 fee plus waiver is correct. But for an annoyed caller asking for a straight answer, the apology/confusion line and the follow-up question make it feel a bit scripted and less direct.
  - [robotic_or_scripted] "ಕ್ಷಮಿಸಿ, ಸ್ವಲ್ಪ confusion ಆಯ್ತು ಅನ್ಸುತ್ತೆ." → ಸರಿ, straight ಆಗಿ ಹೇಳ್ತೀನಿ.
  - [missed_question] "ಇನ್ನೇನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?" → Caller straight answer ಕೇಳಿದ್ದರಿಂದ ಇದನ್ನು ಬಿಡಿ; ಉತ್ತರದಲ್ಲೇ ಮುಗಿಸಿ.

### kn-IN/cartesia/greeting_check (mixed) PASS
- caller: Hello, ನನ್ನ voice ಕೇಳಿಸ್ತಿದೆಯಾ? ಇದು ಯಾವ company?
- agent: ಹೌದು, ನಿಮ್ಮ voice clear ಆಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್ ಮಾತಾಡ್ತಿದ್ದೀನಿ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: Hi, ನೀವು ನನ್ನನ್ನು hear ಮಾಡ್ತಿದ್ದೀರಾ? ನಿಮ್ಮ company name ಏನು?
- agent: ಹೌದು, ನಾನು ಹೇಳ್ತಿರೋದು ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನೀವು ಯಾವ service ಬಗ್ಗೆ ತಿಳ್ಕೊಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Kannada with natural English code-mixing, answers audibility and company name correctly. Slightly repetitive in context, but the judged reply itself is natural and brief.

### kn-IN/cartesia/numbers (mixed) PASS
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC service-ಗೆ ₹599 ಆಗುತ್ತೆ, window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So, ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Kannada-English code-mix and the total is correct. The only issue is the extra visit question after a simple pricing answer.
  - [unneeded_sales_push] "ನಿಮಗೆ visit ಬೇಕಾ?" → Caller only asked to repeat the total; stop after the price.

### kn-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicingಗೆ ₹599 ಆಗುತ್ತೆ. Technician ಬಂದು inspection ಮಾಡ್ತಾರೆ, ಆಮೇಲೆ spare parts ಏನಾದ್ರೂ ಬೇಕಿದ್ರೆ ಅದರ actual MRP ಹೇಳ್ತಾರೆ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ slot ಬೇಕು ಅಂದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ ಯಾವ time-ಗೆ ಬರೋದು ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:261', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Natural Kannada with normal English service-word mixing. It answers the area and pricing clearly, gives the parts caveat correctly, and asks for the next booking detail without inventing anything. Slightly long for a phone reply, but still acceptable.

### kn-IN/cartesia/price (mixed) PASS
- caller: ಸ್ಪ್ಲಿಟ್ AC servicing ಗೆ ಎಷ್ಟು cost ಆಗುತ್ತೆ?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ನನ್ನ split AC ಗೆ service ಮಾಡಿಸಬೇಕು, charges ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 charge ಆಗುತ್ತೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದ್ಯಾ?
  - checks: hard=[] warn=['heavy_english_mixing:17/79', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural Kannada-English code-mix, correct price, and a relevant follow-up to check service area before booking.

### kn-IN/cartesia/time_request (mixed) FAIL
- caller: Cooling ಆಗದ ನನ್ನ fridgeಗೆ ನಾಳೆ morning 10:30ಕ್ಕೆ technician ಬರಬಹುದಾ?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ inspection charge waive off ಆಗುತ್ತೆ. Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಈ areas-ನಲ್ಲಿ ಮಾತ್ರ ನಾವು service ಕೊಡ್ತೀವಿ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10:30ಕ್ಕೆ next-day slot ಲಭ್ಯ ಇರುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:266', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ. ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ?
- agent: ಹೌದು, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10:30ಕ್ಕೆ visit arrange ಮಾಡಬಹುದು. ಆದ್ರೆ ಮೊದಲು technician ಬಂದು inspection ಮಾಡ್ತಾರೆ, ಅದಕ್ಕೆ ₹250 ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['over_soft_length:206', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Natural Kannada-English phone style, but it incorrectly confirms an exact next-day visit without checking service area or saying the team must confirm the slot.
  - [invented_fact] "ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10:30ಕ್ಕೆ visit arrange ಮಾಡಬಹುದು" → Exact slot/visit should not be guaranteed; say it can be taken as a preferred slot and the team will confirm.
  - [missed_question] "visit arrange ಮಾಡಬಹುದು" → First check whether the caller is in Madhapur, Gachibowli, Kondapur or Kukatpally before saying a visit can be arranged.
  - [number_or_time_readout] "10:30ಕ್ಕೆ" → Write the time in Kannada-friendly spoken form, e.g. “ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ” or “ಬೆಳಿಗ್ಗೆ ಹತ್ತು-ಮೂವತ್ತಕ್ಕೆ”.

### kn-IN/gemini/frustration (mixed) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ, please straight answer ಕೊಡಿ. Fridge inspection fee ಎಷ್ಟು?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ, ಆ inspection charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay? Fridge inspectionಗೆ exact fee ಎಷ್ಟು ಅಂತ straight ಆಗಿ ಹೇಳಿ.
- agent: ಕ್ಷಮಿಸಿ, delay ಆಗಿದ್ದಕ್ಕೆ ಬೇಜಾರು. Fridge inspection fee exact ಆಗಿ ₹250 ಆಗುತ್ತೆ. Repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — ಉತ್ತರ factual ಆಗಿ ಸರಿಯಿದೆ ಮತ್ತು ಕನ್ನಡ-ಇಂಗ್ಲಿಷ್ ಮಿಕ್ಸ್ ಸಹಜವಾಗಿದೆ. ಆದರೆ caller straight answer ಕೇಳಿದ್ದಾಗ apology ಮತ್ತು ಕೊನೆಯ follow-up ಸ್ವಲ್ಪ unnecessary ಆಗಿದೆ; ಇನ್ನೂ ಚಿಕ್ಕದಾಗಿ ಹೇಳಬಹುದಿತ್ತು.
  - [unnatural_phrasing] "delay ಆಗಿದ್ದಕ್ಕೆ ಬೇಜಾರು" → ತಡವಾದಕ್ಕೆ ಕ್ಷಮಿಸಿ, ಅಥವಾ ಇದನ್ನೇ ಬಿಡಿ.
  - [missed_question] "ಬೇರೆ ಏನಾದ್ರೂ ಕೇಳ್ಬೇಕಾ?" → ಕಾಲರ್ straight answer ಕೇಳಿರುವುದರಿಂದ ಈ ಹೆಚ್ಚುವರಿ ಪ್ರಶ್ನೆ ಬೇಡ.

### kn-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, ನನ್ನ voice ಕೇಳಿಸ್ತಿದೆಯಾ? ಇದು ಯಾವ company?
- agent: ಹೌದು, voice clear ಆಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್ ಮಾತಾಡ್ತಿರೋದು. ನಿಮಗೆ ಯಾವ details ಬೇಕಿತ್ತು?
  - checks: hard=[] warn=['three_sentences']
- caller: Hi, ನೀವು ನನ್ನನ್ನು hear ಮಾಡ್ತಿದ್ದೀರಾ? ನಿಮ್ಮ company name ಏನು?
- agent: ಹೌದು, ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ನಿಮ್ಮ problem ಏನು ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is in natural Kannada-English code-mix, answers that the caller is audible and gives the company name correctly. The follow-up question is useful but a bit blunt/less receptionist-like.
  - [unnatural_phrasing] "ನಿಮ್ಮ problem ಏನು ಅಂತ ಹೇಳ್ತೀರಾ?" → ಯಾವ appliance issue ಇದೆ ಹೇಳ್ತೀರಾ? ಎಂದು ಸ್ವಲ್ಪ ಹೆಚ್ಚು ಸಹಜವಾಗಿ ಕೇಳಿ.

### kn-IN/gemini/numbers (mixed) PASS
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC service-ಗೆ ₹599 ಆಗುತ್ತೆ, ಮತ್ತೆ window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So ಎರಡು split ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ ನಮ್ಮ service area-ದಲ್ಲಿ visit ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada with natural service-related code-mixing is fine, and the price calculation is correct. The only issue is the extra booking prompt after a direct pricing question.
  - [unneeded_sales_push] "ನಿಮಗೆ visit book ಮಾಡ್ಬೇಕಾ?" → Caller only asked for the total; stop after saying the total, or say: “ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ.”

### kn-IN/gemini/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ spare parts ಏನಾದ್ರೂ ಬೇಕಿದ್ರೆ, ಅದರ actual MRP ಮೇಲೆ extra charge ಇರುತ್ತೆ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ slot ಬೇಕಂದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ ಯಾವ time-ಗೆ ಬರೋದು ಅಂತ ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:272', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Reply is mostly natural Kannada-English code-mix and factually correct. It answers the area and pricing well, but is a bit long for a live phone call and should mention the available slot window more tightly.
  - [too_long] "ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. Technician ಬಂದು inspection ಮಾಡಿದ ಮೇಲೆ spare parts ಏನಾದ್ರೂ ಬೇಕಿದ್ರೆ, ಅದರ actual MRP ಮೇಲೆ extra charge ಇರುತ್ತೆ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ slot ಬೇಕಂದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ ಯಾವ time-ಗೆ ಬರೋದು ಅಂತ ಹೇಳ್ತೀರಾ?" → ಇದನ್ನು ಎರಡು ಚಿಕ್ಕ ವಾಕ್ಯಗಳಲ್ಲಿ ಹೇಳಿ: “ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing ₹599; parts ಬೇಕಾದ್ರೆ technician inspection ನಂತರ MRP ಹೇಳ್ತಾರೆ. ನಾಳೆ 10ರಿಂದ 6ರೊಳಗೆ ಯಾವ slot ಬೇಕು, ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ?”
  - [unnatural_phrasing] "ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ ಯಾವ time-ಗೆ" → “ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಯಾವ time-ಗೆ” ಅಥವಾ ಮಾತುಕತೆಯಲ್ಲಿ “ನಿಮ್ಮ ಹೆಸರು, ಯಾವ time slot ಬೇಕು” ಹೆಚ್ಚು natural.

### kn-IN/gemini/price (mixed) FAIL
- caller: ಸ್ಪ್ಲಿಟ್ AC servicing ಗೆ ಎಷ್ಟು cost ಆಗುತ್ತೆ?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ನನ್ನ split AC ಗೆ service ಮಾಡಿಸಬೇಕು, charges ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 charge ಆಗುತ್ತೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ ಅಂತ ಒಂದು ಸಲ confirm ಮಾಡ್ತೀರಾ?
  - checks: hard=[] warn=['heavy_english_mixing:27/96', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Kannada-English code-mix is natural and the price is correct. Since the caller said they want service, asking area is relevant, but after a repeated pricing question it could be phrased less like a checklist and more conversationally.
  - [unneeded_sales_push] "ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally-ನಲ್ಲಿ ಇದೆಯಾ ಅಂತ ಒಂದು ಸಲ confirm ಮಾಡ್ತೀರಾ?" → Caller asked charges again; answer price first and ask area only if moving to booking. Better: “Split AC servicing ₹599. Service book ಮಾಡ್ಬೇಕಾದ್ರೆ ನಿಮ್ಮ area ಯಾವುದು ಹೇಳಿ.”

### kn-IN/gemini/time_request (mixed) FAIL
- caller: Cooling ಆಗದ ನನ್ನ fridgeಗೆ ನಾಳೆ morning 10:30ಕ್ಕೆ technician ಬರಬಹುದಾ?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally area-ದಲ್ಲಿ ಮಾತ್ರ ನಾಳೆ 10:30 AM ಇಂದ 6 PM ಒಳಗೆ next-day slot arrange ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['over_soft_length:237', 'three_sentences', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ. ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ?
- agent: ಹೌದು, ನಾಳೆ 10:30 AM slot-ಗೆ visit arrange ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 5} — Reply is short and mostly natural Kannada-English mix, but it wrongly confirms an exact 10:30 slot instead of taking it as a preference for confirmation, and the clock time format is not TTS-friendly in Kannada.
  - [invented_fact] "ಹೌದು, ನಾಳೆ 10:30 AM slot-ಗೆ visit arrange ಮಾಡಬಹುದು." → Exact 10:30 visit guarantee ಮಾಡಬೇಡಿ; preferred time ತೆಗೆದುಕೊಂಡು team confirm ಮಾಡುತ್ತಾರೆ ಅಂತ ಹೇಳಿ.
  - [number_or_time_readout] "10:30 AM" → Kannada phone speech-friendly ಆಗಿ “ಬೆಳಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತು” ಅಥವಾ “ಬೆಳಗ್ಗೆ ಹತ್ತೂವರೆ” ಎಂದು ಬರೆಯಿರಿ.
  - [missed_question] "ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?" → ಹೆಸರಿನ ಜೊತೆಗೆ locality ಕೂಡ ಬೇಕು, ಏಕೆಂದರೆ service areas limited: “ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು locality ಹೇಳ್ತೀರಾ?”

### kn-IN/gnani/frustration (mixed) FAIL
- caller: ನಾನು simple question ಕೇಳಿದ್ದೀನಿ, please straight answer ಕೊಡಿ. Fridge inspection fee ಎಷ್ಟು?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ. ಒಂದು ವೇಳೆ ನೀವು repair ಮಾಡಿಸಿದ್ರೆ ಆ inspection charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಯಾಕೆ ಇಷ್ಟು delay? Fridge inspectionಗೆ exact fee ಎಷ್ಟು ಅಂತ straight ಆಗಿ ಹೇಳಿ.
- agent: ಕ್ಷಮಿಸಿ, exact fee ಬಂದು ₹250. ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಈ charge waive off ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 3} — Correct factually and mostly in natural Kannada-English mix, but not ideal for this caller because it uses digits the TTS may not read, adds an unnecessary follow-up, and has slightly awkward phrasing.
  - [number_or_time_readout] "₹250" → Engine doesn't read digits, so say “ಎರಡು ನೂರು ಐವತ್ತು ರೂಪಾಯಿ”.
  - [unneeded_sales_push] "ಬೇರೆ ಏನಾದ್ರೂ ಮಾಹಿತಿ ಬೇಕಾ?" → Caller asked for a straight answer; don't append an extra question here.
  - [unnatural_phrasing] "exact fee ಬಂದು" → More natural: “Fridge inspection fee ಎರಡು ನೂರು ಐವತ್ತು ರೂಪಾಯಿ.”

### kn-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, ನನ್ನ voice ಕೇಳಿಸ್ತಿದೆಯಾ? ಇದು ಯಾವ company?
- agent: ಹೌದು, ನಿಮ್ಮ voice clear ಆಗಿ ಕೇಳಿಸ್ತಿದೆ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್ ಮಾತಾಡ್ತಾ ಇರೋದು. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಿತ್ತಾ?
  - checks: hard=[] warn=['three_sentences']
- caller: Hi, ನೀವು ನನ್ನನ್ನು hear ಮಾಡ್ತಿದ್ದೀರಾ? ನಿಮ್ಮ company name ಏನು?
- agent: ಹೌದು, ನಾನು ಕೇಳಿಸ್ತಾ ಇದೀನಿ. ನಾನು SmartCare Appliance Services ಇಂದ ಸುರೇಶ್. ಇವತ್ತು ನಿಮಗೆ ಯಾವ ರೀತಿ ಸಹಾಯ ಮಾಡಲಿ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — ಉತ್ತರ ಸರಿಯಾದ ಕನ್ನಡದಲ್ಲಿದೆ, ಕಂಪನಿ ಹೆಸರು ಮತ್ತು ಏಜೆಂಟ್ ಹೆಸರು ಸರಿಯಾಗಿದೆ, ಮತ್ತು caller ಕೇಳಿದುದಕ್ಕೆ ನೇರವಾಗಿ ಉತ್ತರಿಸಿದೆ. ಕೊನೆಯ ವಾಕ್ಯ ಸ್ವಲ್ಪ scripted receptionist phrasing ಅನಿಸುತ್ತದೆ, ಆದರೆ ಒಟ್ಟಾರೆ ಫೋನ್ ಕಾಲ್‌ಗೆ ಸರಿಯಾಗಿದೆ.
  - [robotic_or_scripted] "ಇವತ್ತು ನಿಮಗೆ ಯಾವ ರೀತಿ ಸಹಾಯ ಮಾಡಲಿ?" → ಸ್ವಲ್ಪ ಹೆಚ್ಚು ಸಹಜವಾಗಿ: “ಹೇಳಿ, ಏನ್ ಬೇಕಿತ್ತು?” ಅಥವಾ “ಹೇಳಿ, ಏನು ಮಾಹಿತಿ ಬೇಕಿತ್ತು?”

### kn-IN/gnani/numbers (mixed) FAIL
- caller: ಎರಡು split ACಗಳು ಮತ್ತು ಒಂದು window AC service ಮಾಡಿದರೆ total ಎಷ್ಟು?
- agent: Split AC service-ಗೆ ₹599 ಆಗುತ್ತೆ, ಮತ್ತೆ window AC-ಗೆ ₹499 ಆಗುತ್ತೆ. So ಎರಡು split AC ಮತ್ತೆ ಒಂದು window AC-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- caller: ಎರಡು split ಮತ್ತು ಒಂದು window ACಗಳ service charges ಸೇರಿಸಿ total ಹೇಳಿ.
- agent: ಎರಡು split AC ಮತ್ತು ಒಂದು window AC service-ಗೆ total ₹1,697 ಆಗುತ್ತೆ. ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ಉತ್ತರದ ಲೆಕ್ಕ ಸರಿಯಾಗಿದೆ ಮತ್ತು ಕನ್ನಡ-ಇಂಗ್ಲಿಷ್ ಮಿಕ್ಸ್ ಸಹಜವಾಗಿದೆ. ಆದರೆ TTSಗಾಗಿ ಮೊತ್ತವನ್ನು ಅಂಕಿಗಳಲ್ಲಿ ಬರೆದಿದೆ, ಮತ್ತು ಮರುಪ್ರಶ್ನೆಗೆ ಅನವಶ್ಯಕವಾಗಿ visit schedule push ಸೇರಿಸಿದೆ.
  - [number_or_time_readout] "₹1,697" → engine_reads_digits false ಆದ್ದರಿಂದ ಸಂಖ್ಯೆಯನ್ನು ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ: “ಒಟ್ಟು ಒಂದು ಸಾವಿರ ಆರು ನೂರು ತೊಂಬತ್ತೇಳು ರೂಪಾಯಿ ಆಗುತ್ತೆ.”
  - [unneeded_sales_push] "ನಿಮಗೆ visit schedule ಮಾಡ್ಬೇಕಾ?" → ಕಾಲರ್ ಕೇವಲ total ಮತ್ತೆ ಕೇಳಿದ್ದಾರೆ; ಇಲ್ಲಿ schedule ಪ್ರಶ್ನೆ ಬೇಡ. ದರವನ್ನು ಮಾತ್ರ ಸ್ಪಷ್ಟವಾಗಿ ಹೇಳಿ.

### kn-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. Technician inspection ಆದ್ಮೇಲೆ spare parts ಏನಾದ್ರೂ ಬೇಕಿದ್ರೆ ಅದರ MRP extra ಇರುತ್ತೆ, ಅದನ್ನ phone-ನಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ visit ಬೇಕಿದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:249', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Mostly natural Kannada-English code-mix and factually aligned, but the numeric amount is not TTS-safe for this engine, and it should handle the next-day slot window more clearly and more briefly.
  - [number_or_time_readout] "₹599" → engine_reads_digits is false, so say it in Kannada words, e.g. “ಐನೂರು ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ”.
  - [other] "ನಾಳೆ ಬೆಳಿಗ್ಗೆ visit ಬೇಕಿದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?" → Mention the actual visit window or ask for a slot within it, e.g. “ನಾಳೆ ಹತ್ತು ಗಂಟೆಯಿಂದ ಆರು ಗಂಟೆಯೊಳಗೆ ಯಾವ slot ಬೇಕು? ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ.”
  - [too_long] "ಹೌದು, Kondapur ನಮ್ಮ service area ಒಳಗಡೆ ಬರುತ್ತೆ. Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. Technician inspection ಆದ್ಮೇಲೆ spare parts ಏನಾದ್ರೂ ಬೇಕಿದ್ರೆ ಅದರ MRP extra ಇರುತ್ತೆ, ಅದನ್ನ phone-ನಲ್ಲಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. ನಾಳೆ ಬೆಳಿಗ್ಗೆ visit ಬೇಕಿದ್ರೆ, ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?" → Make it tighter for a phone call: “ಹೌದು, Kondapur cover ಆಗುತ್ತೆ. Split AC service ಐನೂರು ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ; parts ಬೇಕಾದ್ರೆ technician inspection ಆದ್ಮೇಲೆ MRP extra ಹೇಳ್ತಾರೆ. ನಾಳೆ ಹತ್ತುರಿಂದ ಆರು ಒಳಗೆ ಯಾವ slot ಬೇಕು, ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ?”

### kn-IN/gnani/price (mixed) PASS
- caller: ಸ್ಪ್ಲಿಟ್ AC servicing ಗೆ ಎಷ್ಟು cost ಆಗುತ್ತೆ?
- agent: Split AC servicing-ಗೆ ₹599 ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದ್ರೂ details ಬೇಕಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- caller: ನನ್ನ split AC ಗೆ service ಮಾಡಿಸಬೇಕು, charges ಎಷ್ಟು?
- agent: Split AC servicing-ಗೆ ₹599 charge ಆಗುತ್ತೆ. ನಿಮ್ಮ area Madhapur, Gachibowli, Kondapur ಅಥವಾ Kukatpally ಒಳಗಡೆ ಬರುತ್ತಾ?
  - checks: hard=[] warn=['heavy_english_mixing:19/81', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Reply is natural Kannada-English code-mix and correctly answers the service charge, then asks the needed service-area question. Only issue is the digit/rupee amount formatting for this TTS engine.
  - [number_or_time_readout] "₹599" → engine_reads_digits=false ಆದ್ದರಿಂದ 'ಐನೂರು ತೊಂಬತ್ತೊಂಬತ್ತು ರೂಪಾಯಿ' ಎಂದು ಬರೆಯಿರಿ.

### kn-IN/gnani/time_request (mixed) FAIL
- caller: Cooling ಆಗದ ನನ್ನ fridgeಗೆ ನಾಳೆ morning 10:30ಕ್ಕೆ technician ಬರಬಹುದಾ?
- agent: Fridge inspection-ಗೆ ₹250 ಆಗುತ್ತೆ, ಆದ್ರೆ ನೀವು repair ಮುಂದುವರಿಸಿದ್ರೆ ಆ charge waive off ಆಗುತ್ತೆ. ನಮ್ಮ service area Madhapur, Gachibowli, Kondapur ಮತ್ತೆ Kukatpally ಮಾತ್ರ ಇರೋದು. ನಾಳೆ morning 10:30ಕ್ಕೆ next-day slot available ಇದೆ. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:248', 'digits_reach_tts']
- caller: ನನ್ನ fridge cool ಆಗ್ತಿಲ್ಲ. ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡೋಕೆ ಆಗುತ್ತಾ?
- agent: ಹೌದು, ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡಬಹುದು. ನಿಮ್ಮ ಹೆಸರು ಹೇಳ್ತೀರಾ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 3, 'helpfulness': 4, 'brevity': 5} — Kannada is natural and brief, but it over-confirms the visit instead of saying the team will confirm the slot, and the numeric time is not TTS-friendly for this engine.
  - [invented_fact] "ನಾಳೆ ಬೆಳಗ್ಗೆ 10:30ಕ್ಕೆ visit ಮಾಡಬಹುದು" → ನಾಳೆ ಬೆಳಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ slot request ಹಾಕಬಹುದು; team confirm ಮಾಡ್ತಾರೆ.
  - [number_or_time_readout] "10:30ಕ್ಕೆ" → ಹತ್ತು ಮೂವತ್ತಕ್ಕೆ

### ml-IN/cartesia/frustration (mixed) PASS
- caller: ഞാൻ simple question ആണ് ചോദിച്ചത്. Fridge inspection fee എത്രയെന്ന് straight ആയി പറയൂ.
- agent: Fridge inspection-ന് ₹250 ആണ് charge വരുന്നത്. പക്ഷെ, നിങ്ങൾ പിന്നീട് repair ചെയ്യാൻ തീരുമാനിക്കുകയാണെങ്കിൽ ഈ inspection charge ഒഴിവാക്കി തരുന്നതാണ്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Malayalam with natural service-call code-mixing, correct price and waiver, and concise. The closing question is a little unnecessary given the caller explicitly wanted a straight answer, but it is not a major problem.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Caller asked for a straight answer; better to stop after the fee/waiver, or say “അത്രേയുള്ളൂ.”

### ml-IN/cartesia/greeting_check (mixed) FAIL
- caller: Hello, എന്റെ voice കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് company ആണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് വിളിക്കുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 3, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 5} — Malayalam is correct and concise, and it answers audibility and company name. But “വിളിക്കുന്നത്” is slightly wrong for an inbound call and the closing question sounds a bit scripted.
  - [robotic_or_scripted] "വേറെ എന്തെങ്കിലും അറിയണോ?" → കൂടുതൽ സ്വാഭാവികമായി: “SmartCare Appliance Services ആണ്.” എന്നിട്ട് നിർത്താം, അല്ലെങ്കിൽ “എന്ത് കാര്യമാണെന്ന് പറയൂ.”
  - [invented_fact] "ഞാൻ SmartCare Appliance Services-ൽ നിന്നാണ് വിളിക്കുന്നത്." → കോൾ സ്വീകരിക്കുന്ന സാഹചര്യത്തിൽ “SmartCare Appliance Services ആണ്” അല്ലെങ്കിൽ “ഞാൻ SmartCare Appliance Services-ലെ സുരേഷ് ആണ്” എന്ന് പറയുക.

### ml-IN/cartesia/numbers (mixed) PASS
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് ₹599-ഉം window AC-ക്ക് ₹499-ഉം ആണ് വരുന്നത്. അപ്പോൾ രണ്ട് split AC-യും ഒരു window AC-യും ചേർത്ത് total ₹1,697 ആകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — മലയാളം സ്വാഭാവികമാണ്, code-mixing okay ആണ്, കണക്കും business facts-ഉം ശരിയാണ്. അവസാനത്തെ follow-up ചോദ്യം ചെറിയൊരു needless add-on പോലെ തോന്നുന്നു, പക്ഷേ മൊത്തത്തിൽ phone call-ിന് നല്ല മറുപടിയാണ്.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Pricing answer നൽകിയ ശേഷം ഇത് ഒഴിവാക്കാം, അല്ലെങ്കിൽ വളരെ സ്വാഭാവികമായി 'ഇതാണ് total.' എന്ന് അവസാനിപ്പിക്കാം.

### ml-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. നാളെ രാവിലെ ഒരു visit വേണമെങ്കിൽ 10 AM-നും 6 PM-നും ഇടയിൽ slot നോക്കാം. ഏത് സമയമാണ് സൗകര്യം?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 3} — Overall Malayalam is natural with normal English code-mixing, and the facts are correct. Main issue is the clock time written as AM/PM inside Malayalam, which is not TTS-friendly; the reply is also a little longer than needed for a live call.
  - [number_or_time_readout] "10 AM-നും 6 PM-നും" → Malayalam spoken form ആയി പറയുക: “രാവിലെ പത്ത് മുതൽ വൈകിട്ട് ആറുവരെ”.
  - [too_long] "അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. നാളെ രാവിലെ ഒരു visit വേണമെങ്കിൽ 10 AM-നും 6 PM-നും ഇടയിൽ slot നോക്കാം. ഏത് സമയമാണ് സൗകര്യം?" → ഫോണിൽ കുറച്ച് ചുരുക്കി: “അതെ, Kondapur cover ചെയ്യും. Split AC servicing ₹599 ആണ്; നാളെ രാവിലെ പത്ത് കഴിഞ്ഞ് slot നോക്കാം, ഏത് സമയം സൗകര്യം?”

### ml-IN/cartesia/price (mixed) PASS
- caller: Split AC servicing-ന് എത്ര cost വരും?
- agent: Split AC servicing-ന് ₹599 ആണ് വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct Malayalam code-mixed reply, accurate price, and brief. The follow-up is acceptable but a bit generic/script-like; otherwise it fits a phone receptionist well.
  - [other] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Slightly more natural on a call: “മറ്റെന്തെങ്കിലും അറിയണോ?” or simply omit it.

### ml-IN/cartesia/time_request (mixed) FAIL
- caller: Cooling ഇല്ലാത്ത fridge-ന് നാളെ morning 10:30-ന് technician വരാമോ?
- agent: Fridge-ന്റെ cooling issue-വിന് നാളെ 10:30-ന് visit ചെയ്യാൻ പറ്റും. Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally എവിടെയാണ് നിങ്ങളുടെ സ്ഥലം?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 4} — Malayalam code-mixing is mostly natural and brief, but it wrongly confirms an exact appointment time and doesn’t mention confirmation/slot constraints. The numeric time is also not ideal for spoken Malayalam.
  - [invented_fact] "നാളെ 10:30-ന് visit ചെയ്യാൻ പറ്റും" → Business fact says next-day slots are between 10 AM and 6 PM, and team should confirm; don’t confirm an exact 10:30 visit before checking area/details. Say: “നാളെ 10 മുതൽ 6 വരെ slot നോക്കാം; team confirm ചെയ്യും.”
  - [number_or_time_readout] "10:30-ന്" → In a Malayalam spoken sentence, clock time should be TTS-friendly, e.g. “പത്ത് മുപ്പതിന്” or “രാവിലെ പത്ത് മുപ്പതിന്”.
  - [missed_question] "Fridge-ന്റെ cooling issue-വിന് നാളെ 10:30-ന് visit ചെയ്യാൻ പറ്റും." → Should first clarify availability is not guaranteed/confirmation needed, then ask locality. Example: “നാളെ morning slot നോക്കാം, confirm ചെയ്യണം; നിങ്ങളുടെ സ്ഥലം Madhapur, Gachibowli, Kondapur, Kukatpally ഇതിലേതാണ്?”

### ml-IN/gemini/frustration (mixed) PASS
- caller: ഞാൻ simple question ആണ് ചോദിച്ചത്. Fridge inspection fee എത്രയെന്ന് straight ആയി പറയൂ.
- agent: Fridge inspection-ന് ₹250 ആണ് charge വരുന്നത്. പക്ഷെ, repair ചെയ്യാൻ തീരുമാനിച്ചാൽ ഈ inspection charge ഞങ്ങൾ waive off ചെയ്തു തരും. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good Malayalam with natural service-context code-mixing and correct pricing. The final follow-up question is a bit unnecessary because the caller explicitly wanted a straight answer, but the main answer is accurate and concise.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?" → Caller asked for a straight answer; stop after the fee and waiver info, or say simply: "അത്രേ."

### ml-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, എന്റെ voice കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് company ആണ്?
- agent: അതെ, കേൾക്കുന്നുണ്ട്. ഇത് SmartCare Appliance Services ആണ്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Good natural Malayalam reply, answers both whether the voice is audible and which company it is. Slightly generic follow-up, but acceptable and brief for a phone call.

### ml-IN/gemini/numbers (mixed) PASS
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് 599 രൂപയും window AC-ക്ക് 499 രൂപയുമാണ് വരുന്നത്. അപ്പൊ രണ്ട് split AC-യും ഒരു window AC-യും ചേരുമ്പോൾ total 1,697 രൂപ ആകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural Malayalam with common AC/service English mixing, and the calculation is correct: 599+599+499 = 1,697. Digits and rupee amounts are acceptable for this TTS. The only minor issue is the unnecessary generic add-on question, which makes it a bit scripted.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → The price answer is complete; avoid adding a generic extra question unless needed. End after the total.

### ml-IN/gemini/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC servicing-ന് ₹599 ആകും. Spare parts-ന് actual MRP വേറെ വരും, അത് technician inspection കഴിഞ്ഞിട്ടേ പറയൂ. നാളെ രാവിലെ ഒരു slot നോക്കാൻ, പേരും ഏത് സമയമാണ് സൗകര്യം എന്നും ഒന്ന് പറയാമോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:242', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Natural Malayalam with common service-related English mixing. It answers the area and pricing, explains parts correctly, and asks for the needed booking details without adding unnecessary sales talk. Slightly long for a phone response, but still acceptable.

### ml-IN/gemini/price (mixed) PASS
- caller: Split AC servicing-ന് എത്ര cost വരും?
- agent: Split AC servicing-ന് ₹599 ആണ് വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Malayalam code-mix natural ആണ്, price fact ശരിയാണ്, ₹599 engine വായിക്കുമെന്നതിനാൽ പ്രശ്നമില്ല. അവസാനം appended question അല്പം needless ആയി തോന്നുന്നു; phone receptionist ആയാൽ direct answer മാത്രം മതിയാകും.
  - [missed_question] "വേറെ എന്തെങ്കിലും അറിയണോ?" → Price answer-ന് ശേഷം ഇങ്ങനെ ചേർക്കാതെ അവസാനിപ്പിക്കാം, അല്ലെങ്കിൽ വളരെ സ്വാഭാവികമായി 'ഇതിൽ service charge മാത്രം ആണ്' പോലുള്ള relevant detail പറയാം.

### ml-IN/gemini/time_request (mixed) FAIL
- caller: Cooling ഇല്ലാത്ത fridge-ന് നാളെ morning 10:30-ന് technician വരാമോ?
- agent: Fridge-ന് cooling ഇല്ലാത്ത issue ആണല്ലേ. ഞങ്ങൾ Madhapur, Gachibowli, Kondapur, Kukatpally എന്നീ areas-ൽ മാത്രമേ service ചെയ്യുന്നുള്ളൂ. ഈ സ്ഥലങ്ങളിൽ ഏതാണ് നിങ്ങളുടെ location?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — Malayalam code-mixing is mostly natural and the service-area fact is correct, but it doesn’t directly address the requested next-day 10:30 visit and starts with a slightly robotic restatement.
  - [robotic_or_scripted] "Fridge-ന് cooling ഇല്ലാത്ത issue ആണല്ലേ." → ഇത് ഒഴിവാക്കി നേരിട്ട് മറുപടി പറയാം.
  - [missed_question] "ഈ സ്ഥലങ്ങളിൽ ഏതാണ് നിങ്ങളുടെ location?" → നാളത്തെ 10:30 slot team confirm ചെയ്യാം; ആദ്യം നിങ്ങളുടെ location Madhapur, Gachibowli, Kondapur, അല്ലെങ്കിൽ Kukatpally-ലാണോ എന്ന് ചോദിക്കുക.

### ml-IN/gnani/frustration (mixed) FAIL
- caller: ഞാൻ simple question ആണ് ചോദിച്ചത്. Fridge inspection fee എത്രയെന്ന് straight ആയി പറയൂ.
- agent: Fridge inspection-ന് 250 രൂപയാണ് charge വരുന്നത്. പക്ഷെ ഒരു കാര്യം ശ്രദ്ധിക്കുക, repair ചെയ്യാൻ തീരുമാനിച്ചാൽ ഈ inspection charge ഒഴിവാക്കി തരുന്നതാണ്. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']

### ml-IN/gnani/greeting_check (mixed) FAIL
- caller: Hello, എന്റെ voice കേൾക്കുന്നുണ്ടോ? ഇത് ഏത് company ആണ്?
- agent: കേൾക്കുന്നുണ്ട്. ഞാൻ SmartCare Appliance Services-ൽ നിന്ന് സുരേഷ് ആണ്. എന്താണ് അറിയേണ്ടത്?
  - checks: hard=[] warn=['three_sentences']

### ml-IN/gnani/numbers (mixed) FAIL
- caller: രണ്ട് split AC-യും ഒരു window AC-യും service ചെയ്യാൻ total എത്ര വരും?
- agent: Split AC-ക്ക് 599 രൂപയും window AC-ക്ക് 499 രൂപയുമാണ് വരുന്നത്. അപ്പോൾ രണ്ട് split AC-യും ഒരു window AC-യും ചേർത്ത് total 1,697 രൂപയാകും. വേറെ എന്തെങ്കിലും അറിയണോ?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ഉത്തരം ശരിയായ Malayalam code-mix-ലാണ്, കണക്ക് ശരിയാണ്. പക്ഷേ TTS digits വായിക്കാത്തതിനാൽ രൂപ തുകകൾ വാക്കുകളായി വേണം; അവസാനം ചേർത്ത ചോദ്യം അല്പം അനാവശ്യമാണ്.
  - [number_or_time_readout] "599 രൂപയും ... 499 രൂപയും ... 1,697 രൂപയാകും" → engine_reads_digits=false ആയതിനാൽ തുകകൾ മലയാളത്തിൽ വാക്കുകളാക്കി പറയുക: “അഞ്ഞൂറ്റി തൊണ്ണൂറ്റൊൻപത് രൂപ”, “നാനൂറ്റി തൊണ്ണൂറ്റൊൻപത് രൂപ”, “ആയിരത്തി അറുനൂറ്റി തൊണ്ണൂറ്റിയേഴ് രൂപ”.
  - [unneeded_sales_push] "വേറെ എന്തെങ്കിലും അറിയണോ?" → ചോദിച്ച തുക പറഞ്ഞ് നിർത്തുക, അല്ലെങ്കിൽ “ഇതാണ് service charge” പോലൊരു ചെറു വാചകം മതി.

### ml-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: അതെ, Kondapur ഞങ്ങളുടെ service area-യിൽ വരുന്നതാണ്. Split AC servicing-ന് ₹599 ആണ് charge വരുന്നത്. Technician വന്ന് നോക്കുമ്പോൾ എന്തെങ്കിലും spare parts വേണ്ടി വന്നാൽ അതിന്റെ actual MRP മാത്രമേ extra ആയിട്ട് വരൂ. നാളെ രാവിലെ ഒരു visit വേണമെങ്കിൽ സമയം ഏതാണെന്ന് പറയാമോ?
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:269', 'digits_reach_tts']

### ml-IN/gnani/price (mixed) FAIL
- caller: Split AC servicing-ന് എത്ര cost വരും?
- agent: Split AC servicing-ന് ₹599 ആണ് വരുന്നത്. വേറെ എന്തെങ്കിലും അറിയണമെന്നുണ്ടോ?
  - checks: hard=[] warn=['digits_reach_tts']

### ml-IN/gnani/time_request (mixed) FAIL
- caller: Cooling ഇല്ലാത്ത fridge-ന് നാളെ morning 10:30-ന് technician വരാമോ?
- agent: Fridge-ന്റെ inspection charge 250 രൂപയാണ്. പക്ഷെ നിങ്ങൾ repair ചെയ്യാൻ തീരുമാനിച്ചാൽ ആ charge ഒഴിവാക്കാം. നാളെ 10:30-ന് visit വേണമെങ്കിൽ Madhapur, Gachibowli, Kondapur അല്ലെങ്കിൽ Kukatpally എവിടെയാണെന്ന് പറയാമോ?
  - checks: hard=[] warn=['over_soft_length:211', 'three_sentences', 'digits_reach_tts']

### ta-IN/cartesia/frustration (mixed) PASS
- caller: நான் ஒரு simple question தான் கேட்டேன், please straight answer சொல்லுங்க. Fridge inspection fee எவ்வளவு?
- agent: Fridge inspection-க்கு ₹250 ஆகும். ஆனா, நீங்க repair பண்ணிக்கிட்டீங்கன்னா அந்த inspection charge waive ஆகிடும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Tamil is natural and the pricing/waiver facts are correct. The final extra question is slightly unnecessary given the caller asked for a straight answer, but otherwise it sounds like a normal receptionist.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Caller specifically asked for a straight answer; end after the fee/waiver info, or say nothing extra.

### ta-IN/cartesia/greeting_check (mixed) PASS
- caller: Hello, என் voice கேட்கிறதா? இது என்ன company?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். சொல்லுங்க, என்ன உதவி வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural spoken Tamil with light English brand use, directly confirms audibility and answers which company it is. Brief and phone-appropriate.

### ta-IN/cartesia/numbers (mixed) PASS
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599, window AC-க்கு ₹499 ஆகும். So, ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total ₹1,697 வரும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Tamil code-mixing natural-ஆ இருக்கு, pricing மற்றும் total சரியாக உள்ளது. கடைசிலுள்ள extra follow-up கேள்வி மட்டும் தேவையில்லாமல் சேர்க்கப்பட்டுள்ளது.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Information answer முடிந்ததும் இந்த extra கேள்வியை விடலாம்; “Total ₹1,697 வரும்.” என்று முடிக்கலாம்.

### ta-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing-க்கு ₹599 ஆகும். நாளைக்கு காலைல visit வேணும்னா, உங்க பேரும், எந்த time-க்கு வரணும்னு மட்டும் சொல்லுங்க. அப்போ team-கிட்ட சொல்லி confirm பண்ணிடலாம்.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:218', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 4, 'helpfulness': 4, 'brevity': 4} — Good spoken Tamil with natural code-mixing and correct area/pricing, but it should constrain the visit to the official 10 AM–6 PM slots and clarify that parts/repair costs may be extra after inspection.
  - [missed_question] "நாளைக்கு காலைல visit வேணும்னா, உங்க பேரும், எந்த time-க்கு வரணும்னு மட்டும் சொல்லுங்க." → Tomorrow slots 10 AM to 6 PM only, so say: “நாளைக்கு காலை 10 மணிக்குப் பிறகு slot பார்க்கலாம்; உங்க பேரும் preferred slot-உம் சொல்லுங்க.”
  - [invented_fact] "Split AC servicing-க்கு ₹599 ஆகும்." → For a not-cooling complaint, avoid implying this is the full repair cost. Say: “Split AC servicing ₹599; parts ஏதாவது தேவைப்பட்டா technician inspection-க்கு பிறகுதான் quote பண்ணுவார்.”

### ta-IN/cartesia/price (mixed) PASS
- caller: Split AC service பண்ண எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct Tamil reply with natural code-mixing and accurate price. Brief and phone-friendly; the follow-up is acceptable but a little scripted.
  - [robotic_or_scripted] "வேற ஏதாச்சும் details வேணுமா?" → Slightly more natural: "இன்னும் ஏதாவது தெரிஞ்சுக்கணுமா?" or omit it.

### ta-IN/cartesia/time_request (mixed) FAIL
- caller: Cooling இல்லாத fridge-க்கு நாளைக்கு morning 10:30-க்கு technician வர முடியுமா?
- agent: நாளைக்கு காலைல 10:30-க்கு visit பண்ணலாம். Madhapur, Gachibowli, Kondapur இல்ல Kukatpally, இந்த areas-ல தான் நம்ம service இருக்கு. நீங்க எந்த area-ல இருக்கீங்க?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Tamil is mostly natural and the area check is relevant, but the agent wrongly confirms an exact 10:30 visit even though visits are only next-day slots and confirmation is needed. It should keep the slot tentative and gather details.
  - [invented_fact] "நாளைக்கு காலைல 10:30-க்கு visit பண்ணலாம்." → Exact 10:30 slot should not be confirmed; only next-day slots between 10 AM and 6 PM, subject to team confirmation. Say: "நாளைக்கு 10 மணிக்குப் பிறகு slot try பண்ணலாம்; team confirm பண்ணுவாங்க."
  - [number_or_time_readout] "10:30-க்கு" → For Tamil TTS, clock time in digits may be awkward. Say "பத்தரை மணிக்கு" or avoid exact time: "காலை slot".
  - [missed_question] "நீங்க எந்த area-ல இருக்கீங்க?" → Should also mention fridge inspection charge and collect booking details if proceeding: name, issue, locality, preferred slot.

### ta-IN/gemini/frustration (mixed) PASS
- caller: நான் ஒரு simple question தான் கேட்டேன், please straight answer சொல்லுங்க. Fridge inspection fee எவ்வளவு?
- agent: Fridge inspection fee ₹250 வரும். நீங்க repair பண்ணிக்கிறதா இருந்தா அந்த charge waive ஆகிடும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Tamil-English phone style and factually correct. The only issue is the extra follow-up question despite the caller asking for a straight answer.
  - [missed_question] "வேற ஏதாவது details வேணுமா?" → Caller explicitly asked for a straight answer; stop after the fee/waiver information, or say nothing further.

### ta-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, என் voice கேட்கிறதா? இது என்ன company?
- agent: ஆமா, clear-ஆ கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். சொல்லுங்க, என்ன help வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Natural spoken Tamil with normal English code-mixing, directly confirms audibility and identifies the company without adding unnecessary details.

### ta-IN/gemini/numbers (mixed) PASS
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599, window AC-க்கு ₹499 வரும். அப்போ ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total-ஆ ₹1,697 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 5, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Tamil-English code-mix, correct pricing and total, and concise for a phone call. The final follow-up is acceptable but slightly unnecessary after a direct pricing answer; adding parts-extra context would be more useful if anything is added.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → Answer can simply end after the total, or say “இது service charge மட்டும்; parts இருந்தா extra.” if adding useful pricing context.

### ta-IN/gemini/other_language (fixed) PASS
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing-க்கு ₹599 ஆகும். நாளைக்கு காலைல visit வேணும்னா, உங்க பேரும், exact address-உம் கொஞ்சம் சொல்லுங்க, அப்போ team slot confirm பண்ணுவாங்க.
  - checks: hard=[] warn=['over_soft_length:204', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural Tamil with typical service-call code mixing. It answers the area and price correctly and asks for details to confirm the visit. Slightly long for a phone reply, but acceptable.

### ta-IN/gemini/price (mixed) PASS
- caller: Split AC service பண்ண எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — தமிழ் code-mix இயல்பாக இருக்கிறது, விலை சரியாக சொல்லப்பட்டுள்ளது, ₹599 TTSக்கு ஏற்றது. கடைசியில் கூடுதல் கேள்வி தேவையில்லாததால் சிறிய குறை.
  - [other] "வேற ஏதாவது details வேணுமா?" → Information answerக்கு அப்படியே நிறுத்தலாம், அல்லது 'Parts தேவைப்பட்டா technician inspectionக்கு பிறகு சொல்வாங்க' போன்ற relevant clarification மட்டும் சொல்லலாம்.

### ta-IN/gemini/time_request (mixed) FAIL
- caller: Cooling இல்லாத fridge-க்கு நாளைக்கு morning 10:30-க்கு technician வர முடியுமா?
- agent: நாளைக்கு காலைல 10:30-க்கு நம்ம team வந்து பாக்க முடியும். ஆனா நம்ம service Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally area-ல மட்டும் தான் இருக்கு. உங்க area இதுல வருதா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 4} — Tamil is mostly natural and polite, but it over-confirms a specific appointment time that the business facts only allow as a next-day slot subject to confirmation. The numeric time format is not ideal for spoken Tamil TTS.
  - [invented_fact] "நாளைக்கு காலைல 10:30-க்கு நம்ம team வந்து பாக்க முடியும்." → Exact visit time should not be confirmed before locality and booking confirmation; say: “நாளைக்கு 10 முதல் 6க்குள் slot பார்க்கலாம், team confirm பண்ணுவாங்க.”
  - [number_or_time_readout] "10:30-க்கு" → For Tamil TTS, write the clock time in spoken form: “பத்தரை மணிக்கு” or avoid the exact time and say “காலை slot”.
  - [missed_question] "உங்க area இதுல வருதா?" → Good to ask locality, but also mention fridge inspection charge if pricing is relevant only when asked; here the main missing part is collecting name, appliance issue, locality and preferred slot if the caller wants a visit.

### ta-IN/gnani/frustration (mixed) PASS
- caller: நான் ஒரு simple question தான் கேட்டேன், please straight answer சொல்லுங்க. Fridge inspection fee எவ்வளவு?
- agent: Fridge inspection-க்கு ₹250 ஆகும். நீங்க repair பண்ணிக்கிறதா இருந்தா இந்த charge waive ஆகிடும். வேற ஏதாவது details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Tamil code-mixing natural-ஆ இருக்கு, pricing fact சரி. ஆனால் TTS digits படிக்காது என்பதால் தொகையை தமிழில் வார்த்தைகளாக எழுத வேண்டும்; கூடுதல் கேள்வி caller கேட்ட ‘straight answer’ tone-க்கு தேவையில்லை.
  - [number_or_time_readout] "₹250" → engine_reads_digits=false என்பதால், ‘இருநூற்றி ஐம்பது ரூபாய்’ என்று எழுதவும்.
  - [missed_question] "வேற ஏதாவது details வேணுமா?" → Caller straight answer கேட்டதால் இதை விடலாம்; முதல் இரண்டு வாக்கியங்கள் போதும்.

### ta-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, என் voice கேட்கிறதா? இது என்ன company?
- agent: ஆமா, தெளிவா கேக்குது. நான் SmartCare Appliance Services-லிருந்து Suresh பேசுறேன். சொல்லுங்க, என்ன details வேணும்?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Tamil is natural and matches the caller’s question. It directly confirms audibility and identifies the company. Minor issue: “என்ன details வேணும்” is understandable urban code-mix, but a bit receptionist-script-like/less natural than a smoother Tamil phrasing.
  - [robotic_or_scripted] "சொல்லுங்க, என்ன details வேணும்?" → சொல்லுங்க, என்ன தெரிஞ்சுக்கணும்? / சொல்லுங்க, என்ன தகவல் வேணும்?

### ta-IN/gnani/numbers (mixed) FAIL
- caller: ரெண்டு split AC-யும் ஒரு window AC-யும் service பண்ணினா total எவ்வளவு?
- agent: Split AC servicing-க்கு ₹599, window AC-க்கு ₹499 வரும். So, ரெண்டு split AC அப்புறம் ஒரு window AC-க்கு total-ஆ ₹1,697 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — பதில் இயல்பான spoken Tamil code-mix-ல் உள்ளது, கணக்கும் சரி. ஆனால் இந்த TTS engine எண்களைத் தமிழில் படிக்காது என்பதால் தொகைகளை இலக்கங்களில் எழுதுவது பொருத்தமில்லை; கடைசி கேள்வியும் தேவையற்றது.
  - [number_or_time_readout] "₹599, window AC-க்கு ₹499" → engine_reads_digits false என்பதால், தமிழில் சொல்லவும்: “Split AC servicing-க்கு ஐநூற்று தொண்ணூற்று ஒன்பது ரூபாய், window AC-க்கு நானூற்று தொண்ணூற்று ஒன்பது ரூபாய்.”
  - [number_or_time_readout] "₹1,697" → “மொத்தம் ஆயிரத்து அறுநூற்று தொண்ணூற்று ஏழு ரூபாய்” என்று எழுதவும்.
  - [missed_question] "வேற ஏதாச்சும் details வேணுமா?" → தகவல் பதிலுக்கு பின் தேவையில்லாத கேள்வியை தவிர்க்கலாம்; “மொத்தம் ஆயிரத்து அறுநூற்று தொண்ணூற்று ஏழு ரூபாய் வரும்.” என்று முடிக்கலாம்.

### ta-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: கண்டிப்பா, Kondapur நம்ம service area-ல தான் வருது. Split AC servicing-க்கு ₹599 ஆகும். நாளைக்கு morning 10 AM-ல இருந்து 6 PM-க்குள்ள slot இருக்கு. உங்க பேரும், exact address-உம் கொஞ்சம் சொல்ல முடியுமா? அப்போதான் team-அ confirm பண்ண சொல்ல முடியும்.
  - checks: hard=['too_many_sentences:5'] warn=['over_soft_length:248', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — Reply is mostly natural Tamil with acceptable code-mixing and answers the area/pricing question. Main problems are digit/time readout for this TTS setup and slightly over-confirming slot availability before team confirmation.
  - [number_or_time_readout] "₹599" → engine_reads_digits false என்பதால் தமிழில் சொல்ல வேண்டும்: “ஐநூற்று தொண்ணூற்று ஒன்பது ரூபாய்”.
  - [number_or_time_readout] "10 AM-ல இருந்து 6 PM-க்குள்ள" → தமிழில் இயல்பாக எழுதவும்: “காலை பத்து மணிலிருந்து மாலை ஆறு மணிக்குள்ள”.
  - [other] "நாளைக்கு morning 10 AM-ல இருந்து 6 PM-க்குள்ள slot இருக்கு" → Availability உறுதி செய்த மாதிரி சொல்லாமல்: “நாளைக்கு காலை பத்து முதல் மாலை ஆறு மணிக்குள்ள slots இருக்கும்; team confirm பண்ணுவாங்க” என்று சொல்லலாம்.

### ta-IN/gnani/price (mixed) PASS
- caller: Split AC service பண்ண எவ்வளவு ஆகும்?
- agent: Split AC servicing-க்கு ₹599 ஆகும். வேற ஏதாச்சும் details வேணுமா?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Correct price and concise, with natural Tamil-English mix overall. Main issue is the digit amount for this TTS setting; it should be written out in Tamil words.
  - [number_or_time_readout] "₹599" → engine_reads_digits false, so say it in Tamil words: “ஐநூற்று தொண்ணூற்று ஒன்பது ரூபாய்”
  - [unnatural_phrasing] "details" → More natural Tamil phone phrasing: “வேற ஏதாவது தெரிஞ்சுக்கணுமா?”

### ta-IN/gnani/time_request (mixed) FAIL
- caller: Cooling இல்லாத fridge-க்கு நாளைக்கு morning 10:30-க்கு technician வர முடியுமா?
- agent: Sorry, நம்ம service Madhapur, Gachibowli, Kondapur அப்புறம் Kukatpally-ல மட்டும் தான் இருக்கு. Fridge inspection charge ₹250 வரும், ஆனா நீங்க repair பண்ணிக்கிறீங்கன்னா அந்த charge waive ஆயிடும். நீங்க எந்த area-ல இருக்கீங்க?
  - checks: hard=[] warn=['over_soft_length:224', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 4, 'helpfulness': 3, 'brevity': 3} — Reply mostly natural Tamil-English code-mix and facts are broadly correct, but it doesn’t directly address the requested next-day 10:30 visit before asking locality, and the rupee amount is written in digits even though this TTS engine will not read digits in Tamil.
  - [number_or_time_readout] "₹250" → Engine digits படிக்காது என்பதால், “இருநூற்று ஐம்பது ரூபாய்” என்று எழுத வேண்டும்.
  - [missed_question] "நீங்க எந்த area-ல இருக்கீங்க?" → முதலில் “நாளைக்கு slot team confirm பண்ணும்; visits 10 AM முதல் 6 PMக்குள் தான்” என்று சொல்லி, பிறகு area கேட்கலாம்.

### te-IN/cartesia/frustration (mixed) PASS
- caller: నేను simple question అడిగాను, please straight answer చెప్పండి. Fridge inspection fee ఎంత?
- agent: Fridge inspection కి ₹250 అవుతుంది. ఒకవేళ మీరు repair కి ముందుకు వెళితే ఆ inspection charge waive off అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Natural Telugu-English code-mix and the price/waiver facts are correct. The only issue is the extra follow-up question despite the caller asking for a direct answer.
  - [missed_question] "మీకు ఇంకా ఏమైనా details కావాలా?" → Caller specifically asked for a straight answer, so stop after the fee and waiver information.

### te-IN/cartesia/greeting_check (mixed) PASS
- caller: Hello, నా voice వినిపిస్తుందా? ఇది ఏ company?
- agent: అవును, నా voice clear గా వినిపిస్తోంది. నేను సురేష్ ని, SmartCare Appliance Services నుంచి మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — తెలుగు code-mixing సహజంగా ఉంది, caller అడిగిన company ప్రశ్నకు నేరుగా సరైన సమాధానం ఇచ్చింది. చివరి వాక్యం కొంచెం call-centre/scripted గా వినిపిస్తుంది, కానీ పెద్ద సమస్య కాదు.
  - [robotic_or_scripted] "చెప్పండి, మీకు ఎలా సహాయం చేయగలను?" → కొంచెం సహజంగా: “చెప్పండి, ఏ appliance service కావాలి?”

### te-IN/cartesia/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: Split AC service కి ₹599, window AC కి ₹499 అవుతుంది. సో, రెండు split ACలు, ఒక window AC కలిపి total ₹1,697 అవుతుంది. మీ area ఏది? Madhapur, Gachibowli, Kondapur లేదా Kukatpally లోనే service చేస్తాం.
  - checks: hard=['too_many_sentences:4'] warn=['heavy_english_mixing:29/118', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural Telugu-English service-call style and the pricing/math are correct. The area question is relevant for booking, though the caller only asked the total, so it’s slightly more than necessary.

### te-IN/cartesia/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లోకే వస్తుంది. Split AC servicing కి ₹599 అవుతుంది. Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది. రేపు morning 10 AM నుంచి 6 PM మధ్యలో next-day slot లో visit arrange చేయగలను.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:259', 'heavy_english_mixing:49/165', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 2} — Telugu is mostly natural and answers area/pricing, but it incorrectly applies the fridge inspection waiver to a split AC visit and gives a clunky/contradictory time window. It should be shorter and ask for the caller’s name and preferred slot to proceed.
  - [invented_fact] "Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది." → ₹250 inspection waiver fridge కోసం మాత్రమే ఉంది; split AC గురించి చెప్పేటప్పుడు దీన్ని చెప్పకూడదు. చెప్పాలి: “Spare parts ఉంటే technician inspection తర్వాత quote చేస్తారు.”
  - [number_or_time_readout] "10 AM నుంచి 6 PM" → Telugu TTS కోసం clock times మాటల్లో రాయాలి: “ఉదయం పది నుంచి సాయంత్రం ఆరు మధ్య”.
  - [other] "రేపు morning 10 AM నుంచి 6 PM మధ్యలో" → Caller ‘tomorrow morning’ అడిగారు; business facts ప్రకారం slots 10 AM–6 PM మాత్రమే. “ఉదయం పది తర్వాత slot చూసి confirm చేస్తాం” అని చెప్పడం మంచిది.
  - [too_long] "అవును, Kondapur మా service area లోకే వస్తుంది. Split AC servicing కి ₹599 అవుతుంది. Technician వచ్చి inspection చేశాక, అవసరమైతే repair చేస్తే ఆ ₹250 inspection charge waive అవుతుంది. రేపు morning 10 AM నుంచి 6 PM మధ్యలో next-day slot లో visit arrange చేయగలను." → ఒకటి-రెండు చిన్న వాక్యాలు చాలు; visit కోసం name/preferred slot అడగాలి.

### te-IN/cartesia/price (mixed) PASS
- caller: స్ప్లిట్ AC servicing కి ఎంత cost అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు వేరే ఏమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — Correct Telugu-English code-mix and the price matches the facts. It directly answers the caller and is brief. The follow-up is acceptable, though a bit scripted for a natural phone receptionist.
  - [robotic_or_scripted] "మీకు వేరే ఏమైనా details కావాలా?" → Slightly more natural: “ఇంకేమైనా తెలుసుకోవాలా?” or just end after the price.

### te-IN/cartesia/time_request (mixed) FAIL
- caller: Cooling లేని fridge కి రేపు morning 10:30కి technician రావచ్చా?
- agent: Fridge inspection కి ₹250 అవుతుంది, కానీ మీరు repair చేయిస్తే ఆ charge waive అవుతుంది. మా service area Madhapur, Gachibowli, Kondapur, Kukatpally కి మాత్రమే ఉంది. మీరు ఈ areas లో ఉన్నారా?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:34/119', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 3, 'brevity': 4} — Telugu with natural service-call code-mixing is mostly fine, and the pricing/area facts are correct. But it doesn’t directly answer the caller’s specific request for a next-day 10:30 technician visit before asking the area.
  - [missed_question] "మీరు ఈ areas లో ఉన్నారా?" → Caller అడిగిన రేపు 10:30 slot గురించి ముందుగా చెప్పాలి: “రేపు 10:30 slot team confirm చేస్తారు; ముందుగా మీ locality చెప్పండి.”

### te-IN/gemini/frustration (mixed) PASS
- caller: నేను simple question అడిగాను, please straight answer చెప్పండి. Fridge inspection fee ఎంత?
- agent: Fridge inspection కి ₹250 అవుతుంది. ఒకవేళ మీరు repair తో ముందుకు వెళితే, ఆ inspection charge waive అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Good natural Telugu-English mix and the price/waiver facts are correct. The extra follow-up question is unnecessary given the caller asked for a straight answer.
  - [missed_question] "మీకు ఇంకా ఏమైనా details కావాలా?" → Caller specifically asked for a straight answer; stop after the fee and waiver information.

### te-IN/gemini/greeting_check (mixed) PASS
- caller: Hello, నా voice వినిపిస్తుందా? ఇది ఏ company?
- agent: అవును, clearly వినిపిస్తోంది. నేను Suresh ని, SmartCare Appliance Services నుంచి మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 5, 'brevity': 4} — Reply is in natural Telugu with common English mixing, confirms audibility and company correctly. Slightly scripted ending, but overall appropriate and helpful.
  - [robotic_or_scripted] "చెప్పండి, మీకు ఎలా సహాయం చేయగలను?" → ఇది కొంచెం call-centreలా ఉంది; 'చెప్పండి, ఏ service కావాలి?' లాంటి సహజమైన మాట బెటర్.

### te-IN/gemini/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC servicing ₹599, window AC ₹499 అవుతుంది. So, రెండు split ACలు, ఒక window AC కి total ₹1,696 అవుతుంది. మీకు మా team ని visit కి పంపించాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Telugu with natural service-context code-mixing is fine, and the total is correct. The final booking prompt is slightly pushy after a direct pricing question but not a major issue.
  - [unneeded_sales_push] "మీకు మా team ని visit కి పంపించాలా?" → ధర మాత్రమే అడిగారు కాబట్టి: “మొత్తం ₹1,696 అవుతుంది.” దగ్గరే ఆపండి, లేదా “బుక్ చేయాలంటే చెప్పండి” అని మృదువుగా చెప్పండి.

### te-IN/gemini/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing ₹599 అవుతుంది. Technician వచ్చి inspection చేశాక, అవసరమైతే repair కూడా చేస్తారు, అప్పుడు inspection charge పడదు. రేపు ఉదయం slot కావాలంటే మీ పేరు, అలాగే exact time ఏంటో చెప్పండి.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:237', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 4, 'correctness': 2, 'helpfulness': 3, 'brevity': 3} — Telugu is natural and mostly phone-friendly, but it wrongly applies the fridge inspection-waiver rule to a split AC visit and asks for an exact time instead of a preferred slot to be confirmed.
  - [invented_fact] "Technician వచ్చి inspection చేశాక, అవసరమైతే repair కూడా చేస్తారు, అప్పుడు inspection charge పడదు." → AC కోసం inspection charge/waiver చెప్పకండి; అది fridgeకి మాత్రమే ఉంది. Split AC servicing ₹599, parts extra at actual MRP అని చెప్పండి.
  - [invented_fact] "exact time ఏంటో చెప్పండి" → Exact time promise చేయకుండా, available next-day slot/preferred time window అడగండి; team confirm చేస్తారని చెప్పండి.
  - [missed_question] "మీ పేరు, అలాగే exact time ఏంటో చెప్పండి" → Caller ఇప్పటికే appliance, issue, locality చెప్పాడు. పేరు మరియు preferred slot మాత్రమే అడగండి, లేదా అవసరమైతే address/contact కూడా తర్వాత తీసుకోవచ్చు.

### te-IN/gemini/price (mixed) PASS
- caller: స్ప్లిట్ AC servicing కి ఎంత cost అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు booking కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Telugu code-mixing is natural and the price is correct. The follow-up booking question is a bit pushy for a simple pricing question, though still plausible on a service call.
  - [unneeded_sales_push] "మీకు booking కావాలా?" → Asked price only; better stop after the price, or say “సర్వీసింగ్ ఛార్జ్ ₹599.”

### te-IN/gemini/time_request (mixed) PASS
- caller: Cooling లేని fridge కి రేపు morning 10:30కి technician రావచ్చా?
- agent: Fridge inspection కి ₹250 అవుతుంది, కానీ మీరు repair చేయిస్తే ఆ charge waive అవుతుంది. మా service area Madhapur, Gachibowli, Kondapur, Kukatpally మాత్రమే. మీరు ఈ areas లో ఉన్నారా?
  - checks: hard=[] warn=['three_sentences', 'heavy_english_mixing:31/116', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Natural Telugu-English code-mix and facts are correct. It answers cost and area, but doesn’t directly address the requested tomorrow 10:30 visit timing before asking the area.
  - [missed_question] "మీరు ఈ areas లో ఉన్నారా?" → Caller asked for tomorrow 10:30; first say tomorrow slots are between 10 AM and 6 PM and 10:30 can be requested, then ask locality.

### te-IN/gnani/frustration (mixed) PASS
- caller: నేను simple question అడిగాను, please straight answer చెప్పండి. Fridge inspection fee ఎంత?
- agent: Fridge inspection కి ₹250 అవుతుంది. ఒకవేళ మీరు repair చేయిస్తే ఆ inspection charge waive అవుతుంది. మీకు ఇంకా ఏమైనా details కావాలా?
  - checks: hard=[] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — సమాధానం నిజాలు కరెక్ట్‌గా చెబుతోంది, Telugu-English code-mix సహజంగా ఉంది. కానీ TTS digits చదవదు కాబట్టి ₹250 సమస్య, అలాగే caller అడిగింది straight answer మాత్రమే కాబట్టి చివరి follow-up కొంచెం unnecessary.
  - [number_or_time_readout] "₹250" → engine_reads_digits false కాబట్టి 'రెండు వందల యాభై రూపాయలు' అని రాయాలి.
  - [missed_question] "మీకు ఇంకా ఏమైనా details కావాలా?" → Caller straight answer అడిగారు కాబట్టి చివర్లో అదనపు ప్రశ్న లేకుండా ఆపాలి.

### te-IN/gnani/greeting_check (mixed) PASS
- caller: Hello, నా voice వినిపిస్తుందా? ఇది ఏ company?
- agent: అవును, వినిపిస్తోంది. నేను సురేష్, SmartCare Appliance Services నుంచి మాట్లాడుతున్నాను. చెప్పండి, మీకు ఎలా సహాయం చేయగలను?
  - checks: hard=[] warn=['three_sentences']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 5, 'brevity': 5} — సమాధానం సహజమైన తెలుగులో ఉంది, caller అడిగిన voice వినిపిస్తుందా మరియు company ఏది అన్న రెండింటికీ నేరుగా జవాబు ఇచ్చింది. కొంచెం generic receptionist phrasing ఉన్నా phone context‌లో బాగానే సరిపోతుంది.

### te-IN/gnani/numbers (mixed) FAIL
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC servicing ₹599, window AC ₹499 అవుతుంది. రెండు split ACలకు కలిపి ₹1,198, plus window AC ₹499, total ₹1,697 అవుతుంది. మీ area ఏది? Madhapur, Gachibowli, Kondapur లేదా Kukatpally లోనే service చేస్తాం.
  - checks: hard=['too_many_sentences:4'] warn=['over_soft_length:210', 'heavy_english_mixing:27/122', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — సమాధానం factual గా సరైంది, Telugu-English code-mix సహజంగానే ఉంది. కానీ ఈ TTS engine digits/₹ amounts సరిగా చదవదు, కాబట్టి amounts మాటల్లో ఉండాలి. అలాగే pricing questionకి చివర area question కొంచెం అవసరం లేనట్టుంది.
  - [number_or_time_readout] "₹599, window AC ₹499" → Engine digits చదవదు కాబట్టి ఇలా చెప్పాలి: “ఒక split AC servicing ఐదు వందల తొంభై తొమ్మిది రూపాయలు, window AC నాలుగు వందల తొంభై తొమ్మిది రూపాయలు.”
  - [number_or_time_readout] "₹1,198, plus window AC ₹499, total ₹1,697" → “రెండు split ACలకు కలిపి వెయ్యి నూట తొంభై ఎనిమిది రూపాయలు, window AC కలిపి total వెయ్యి ఆరు వందల తొంభై ఏడు రూపాయలు.”
  - [unneeded_sales_push] "మీ area ఏది? Madhapur, Gachibowli, Kondapur లేదా Kukatpally లోనే service చేస్తాం." → Caller కేవలం total అడిగారు; ముందు ధర మాత్రమే చెప్పాలి. Visit కావాలంటే ఆ తర్వాత area అడగచ్చు.

### te-IN/gnani/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing ₹599 అవుతుంది. మా team next-day slots లో 10 AM నుంచి 6 PM మధ్యలో visit చేయగలరు. మీకు ఏ time వీలవుతుందో చెప్తారా?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Overall Telugu is natural and facts are correct, but the numeric price/time format is not suitable for this TTS setting, and it misses collecting the caller’s name for a visit request.
  - [number_or_time_readout] "₹599" → engine_reads_digits=false కాబట్టి ‘ఐదు వందల తొంభై తొమ్మిది రూపాయలు’ అని రాయాలి.
  - [number_or_time_readout] "10 AM నుంచి 6 PM" → ‘ఉదయం పది నుంచి సాయంత్రం ఆరు వరకు’ అని రాయాలి.
  - [missed_question] "మీకు ఏ time వీలవుతుందో చెప్తారా?" → విజిట్ బుక్ చేయాలంటే పేరు కూడా అడగాలి: ‘రేపు ఉదయం పది తర్వాత slot చూసి చెప్తాం; మీ పేరు చెప్పండి?’

### te-IN/gnani/price (mixed) PASS
- caller: స్ప్లిట్ AC servicing కి ఎంత cost అవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు మా team ని visit కి పంపించాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం సరైన ధర చెబుతోంది, తెలుగు-ఇంగ్లీష్ మిక్స్ సహజంగానే ఉంది. కానీ TTS digits చదవదు కాబట్టి మొత్తం మాటల్లో ఉండాలి, అలాగే caller కేవలం cost అడిగినప్పుడు visit question అవసరం లేదు.
  - [number_or_time_readout] "₹599" → engine_reads_digits false కాబట్టి 'ఐదు వందల తొంభై తొమ్మిది రూపాయలు' అని రాయాలి.
  - [unneeded_sales_push] "మీకు మా team ని visit కి పంపించాలా?" → కేవలం ధర అడిగారు కాబట్టి, 'Split AC servicing కి ఐదు వందల తొంభై తొమ్మిది రూపాయలు అవుతుంది.' అని ఆపితే సరిపోతుంది.

### te-IN/gnani/time_request (mixed) FAIL
- caller: Cooling లేని fridge కి రేపు morning 10:30కి technician రావచ్చా?
- agent: Fridge inspection కి ₹250 అవుతుంది, కానీ మీరు repair చేయిస్తే ఆ inspection charge waive అవుతుంది. మా service area లో రేపు ఉదయం 10:30 కి slot దొరకవచ్చు, కానీ same-day visit guarantee ఉండదు. మీ locality ఏంటో చెప్తారా?
  - checks: hard=[] warn=['over_soft_length:215', 'three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 3, 'register': 4, 'correctness': 3, 'helpfulness': 3, 'brevity': 2} — Mostly understandable Telugu-English mix, but not fully phone-natural and has TTS-unfriendly digits. It also assumes the area before asking locality and mentions same-day unnecessarily.
  - [number_or_time_readout] "₹250" → engine_reads_digits=false కాబట్టి “రెండు వందల యాభై రూపాయలు” అని చెప్పాలి.
  - [number_or_time_readout] "10:30" → “పది ముప్పైకి” లేదా “పది నరకి” అని రాయాలి.
  - [invented_fact] "మా service area లో రేపు ఉదయం 10:30 కి slot దొరకవచ్చు" → caller locality ఇంకా తెలియదు; “మీ locality మా service area లో ఉంటే రేపు పది ముప్పై slot check చేయొచ్చు” అని చెప్పాలి.
  - [invented_fact] "same-day visit guarantee ఉండదు" → caller రేపటి slot అడిగారు, so this is irrelevant; instead say next-day slots are between ten and six and team will confirm.
  - [too_long] "Fridge inspection కి ₹250 అవుతుంది, కానీ మీరు repair చేయిస్తే ఆ inspection charge waive అవుతుంది. మా service area లో రేపు ఉదయం 10:30 కి slot దొరకవచ్చు, కానీ same-day visit guarantee ఉండదు. మీ locality ఏంటో చెప్తారా?" → Shorten: “Fridge inspection రెండు వందల యాభై రూపాయలు; repair చేస్తే waive అవుతుంది. మీ locality చెప్తారా? మా area లో ఉంటే రేపు పది ముప్పై slot check చేసి confirm చేస్తాం.”
