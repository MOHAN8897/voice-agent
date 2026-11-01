# Language probe language-probe-smoke-v3

Schema `sim_8ca1eeee98744fadb0a2c1772908cf04`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| en-IN | sarvam | 0/2 | 3.25 | language_fit 1.00 |
| te-IN | sarvam | 1/2 | 4.42 | human_naturalness 4.00 |

## Transcripts

### en-IN/sarvam/other_language (fixed) FAIL
- caller: भैया, कल सुबह Kondapur में technician आ सकता है क्या? Split AC की cooling बंद है।
- agent: Kondapur ನಮ್ಮ service area ಒಳಗೆ ಬರುತ್ತದೆ, ಆದರೆ same-day visits guarantee ಇಲ್ಲ. ನಾವು next-day slots ಮಾತ್ರ ಕೊಡುತ್ತೇವೆ, ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ ಸಂಜೆ 6 PM ವರೆಗೆ. ನಿಮ್ಮ visit book ಮಾಡಲು, ನಿಮ್ಮ ಹೆಸರು ಹೇಳಬಹುದಾ?
  - checks: hard=['indic_script_in_english_call'] warn=['three_sentences', 'digits_reach_tts']
- judge: {'language_fit': 1, 'human_naturalness': 3, 'register': 3, 'correctness': 4, 'helpfulness': 4, 'brevity': 3} — The reply is mostly factually aligned and tries to collect booking details, but it is in Kannada instead of the configured Indian English, and it answers with an unnecessary same-day caveat rather than directly addressing tomorrow morning.
  - [wrong_language] "Kondapur ನಮ್ಮ service area ಒಳಗೆ ಬರುತ್ತದೆ" → Use Indian English, e.g. “Yes, Kondapur is in our service area.”
  - [wrong_language] "ನಾವು next-day slots ಮಾತ್ರ ಕೊಡುತ್ತೇವೆ" → Say it in Indian English: “We have next-day slots between 10 AM and 6 PM.”
  - [number_or_time_readout] "ಬೆಳಿಗ್ಗೆ 10 AM ಇಂದ ಸಂಜೆ 6 PM ವರೆಗೆ" → Since this is an Indic sentence with clock times, avoid this format; in the required Indian English reply, say “between 10 AM and 6 PM.”
  - [missed_question] "same-day visits guarantee ಇಲ್ಲ" → The caller asked for tomorrow morning, not same-day. Better: “Tomorrow can be requested, but the team will confirm the exact slot.”

### en-IN/sarvam/price (clean) FAIL
- caller: How much does split AC servicing cost?
- agent: Split AC servicing ಗೆ 599 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದರೂ ಮಾಹಿತಿ ಬೇಕಿತ್ತಾ?
  - checks: hard=['indic_script_in_english_call'] warn=['digits_reach_tts']
- caller: How much does split AC servicing cost?
- agent: Split AC servicing ಗೆ 599 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕಾ?
  - checks: hard=['indic_script_in_english_call'] warn=['digits_reach_tts']
- judge: {'language_fit': 1, 'human_naturalness': 3, 'register': 3, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — The price is correct and the reply is brief, but the configured language is Indian English while the agent replied in Kannada code-mix.
  - [wrong_language] "Split AC servicing ಗೆ 599 rupees ಆಗುತ್ತೆ. ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕಾ?" → Use Indian English: “Split AC servicing is ₹599. Anything else you’d like to know?”

### te-IN/sarvam/other_language (fixed) FAIL
- caller: Hi, can a technician come to Kondapur tomorrow morning? My split AC is not cooling.
- agent: అవును, Kondapur మా service area లో ఉంది. Split AC servicing ₹599 అవుతుంది. మా team next-day visit కోసం 10 AM నుంచి 6 PM మధ్యలో slot ఇస్తారు. మీకు ఏ time వీలవుతుందో చెప్తారా?
  - checks: hard=['too_many_sentences:4'] warn=['digits_reach_tts']
- judge: {'language_fit': 5, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — Reply is mostly natural Telugu-English code-mix and factually correct. Main issues: clock times written in AM/PM inside Telugu are TTS-unfriendly, and it could respond more directly to the requested tomorrow morning visit before asking for time.
  - [number_or_time_readout] "10 AM నుంచి 6 PM" → Spoken Teluguలో timeని naturalగా 'ఉదయం పది నుంచి సాయంత్రం ఆరు మధ్య' అని చెప్పండి.
  - [missed_question] "మీకు ఏ time వీలవుతుందో చెప్తారా?" → Caller 'tomorrow morning' అన్నాడు కాబట్టి ముందుగా morning requestని acknowledge చేసి, 'రేపు morning slot కోసం note చేస్తాను; మీ పేరు చెప్పండి' లాగా details అడగాలి.

### te-IN/sarvam/price (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి ₹599 అవుతుంది. మీకు వేరే ఏమైనా details కావాలా?
  - checks: hard=[] warn=['digits_reach_tts']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — Reply is mostly natural Telugu-English code-mix and the price is correct. It’s brief and phone-friendly. The extra follow-up question is not needed for a straightforward pricing answer, though it is not very harmful.
  - [unneeded_sales_push] "మీకు వేరే ఏమైనా details కావాలా?" → ధర చెప్పి ఆపేయండి, లేదా సహజంగా ‘అంతే’ వంటి ముగింపు సరిపోతుంది.
