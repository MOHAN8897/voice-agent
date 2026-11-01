# Agent QA agent-qa-smoke

Sessions passed 1/4. Checks passed 71/76 (93.4%).

| Scenario | te-IN | kn-IN |
|---|---|---|
| language_switch | FAIL: pack_replaced_not_stacked | FAIL: no_runtime_error |
| integration | PASS | FAIL: no_runtime_error, min_duration_90s, tool_gmail_send_email_succeeded |

## Session metrics

| Session | Dur s | Turns | Avg first chunk s | Max first chunk s | LLM calls/turn | Max sys prompt chars | Tools |
|---|---|---|---|---|---|---|---|
| te-IN/language_switch | 245.5 | 6 | 1.71 | 2.19 | 4.5 | 26521 | - |
| te-IN/integration | 215.1 | 6 | 2.37 | 5.19 | 5.5 | 23279 | GMAIL_SEND_EMAIL |
| kn-IN/language_switch | 221.2 | 3 | 1.81 | 1.97 | 5.0 | 25721 | - |
| kn-IN/integration | 56.2 | 0 | 0.00 | 0.00 | 0.0 | 0 | - |

## Transcripts

### te-IN/language_switch FAIL — 245.5s, disposition interested ['pack_replaced_not_stacked']
- opening: నమస్కారం, నేను నేచర్‌వేద హెర్బల్స్ నుండి ప్రియను. మీరు మా హెర్బల్ ఉత్పత్తులు, వాటి పదార్థాలు, ధరలు లేదా డెలివరీ ఎంపికల గురించి తెలుసుకోవడానికి సహాయం చేయవచ్చా?
- [24.3s] caller: నమస్తే అండి. మీ దగ్గర అలోవెరా జ్యూస్ ఉందా? దాని ప్రైస్ మరియు సైజ్ ఎంత అండి?
- agent [te-IN, 2.188s]: అవును, మా దగ్గర అలోవెరా జ్యూస్ ఉంది. దీని ధర ₹399 మరియు సైజ్ 500 ml ఉంటుంది.
- [39.6s] caller: సరేనండి. ఈ అలోవెరా జ్యూస్ ఎలా తీసుకోవాలి? రోజుకి ఎంత డోసేజ్ వాడాలి?
- agent [te-IN, 2.032s]: రోజుకి ఎంత డోసేజ్ వాడాలి అనే సమాచారం మాకు అందుబాటులో లేదు. దయచేసి దీని వాడకం గురించి అర్హత కలిగిన ఆరోగ్య సంరక్షణ నిపుణులను సంప్రదించండి.
- [84.8s] caller: Okay, thank you. Actually, I would prefer to continue in English now. Could you please repeat the price of the aloe vera juice?
- agent [en-IN, 1.672s]: Sure, the aloe vera juice is priced at ₹399 for 500 ml.
- [101.5s] caller: Okay, got it. Can you also tell me about the ingredients in your hair oil?
- agent [en-IN, 1.734s]: Our Herbal Hair Oil contains Amla, Bhringraj, Hibiscus, and Coconut Oil. It is priced at ₹499 for 200 ml and is meant for routine hair and scalp care.
- [154.1s] caller: Thank you for that. So, what would be the total price if I order one aloe vera juice and one hair oil together?
- agent [en-IN, 1.922s]: The aloe vera juice is ₹399 and the hair oil is ₹499, so the total would be ₹898.
- [241.4s] caller: Alright, thank you so much for the details. That is all I needed to know today. Have a good evening!
- agent [en-IN, 0.703s]: (silent)
- farewell: Thank you for your time. Goodbye.
- FAILED server:pack_replaced_not_stacked — [[], [], [], ['te-IN', 'en-IN']]

### te-IN/integration PASS — 215.1s, disposition callback_required []
- opening: నమస్కారం, నేను నేచర్‌వేద హెర్బల్స్ నుండి ప్రియను. మీరు మా హెర్బల్ ఉత్పత్తులు, వాటి పదార్థాలు, ధరలు లేదా డెలివరీ ఎంపికల గురించి తెలుసుకోవడానికి సహాయం చేయవచ్చా?
- [23.5s] caller: నమస్తే అండి, నాకు మీ ఫేస్ క్రీమ్ మరియు హెయిర్ ఆయిల్ మీద ఆసక్తి ఉంది. ఈ రెండింటి price ఎంత అండి?
- agent [te-IN, 2.063s]: హెయిర్ ఆయిల్ 200 మి. లీ కి 499 రూపాయలు, ఫేస్ క్రీమ్ 50 గ్రాములకు 599 రూపాయలు అవుతుంది.
- [58.7s] caller: సరేనండి, ఈ product details మరియు prices నాకు ఒకసారి email చేస్తారా? నా email address mohansaiteja.99@gmail.com.
  - tool GMAIL_SEND_EMAIL -> {"status": "sent", "message_id": "1a19208a2885615a", "to": "mohansaiteja.99@gmail.com", "subject": "NatureVeda Product Details and Prices", "message": "Confirmation email sent to mohansaiteja.99@gmail
- agent [te-IN, 5.187s]: మీ email mohansaiteja.99@gmail. com కి details పంపించాను.
- [87.5s] caller: సరేనండి, ఫేస్ క్రీమ్ stock లో ఉందా? కూకట్‌పల్లికి delivery ఎప్పటికి అవుతుంది?
- agent [te-IN, 2.078s]: ఫేస్ క్రీమ్ స్టాక్ మరియు కూకట్‌పల్లికి డెలివరీ ఎప్పటికి అవుతుంది అనే వివరాలు ప్రస్తుతం మా దగ్గర అందుబాటులో లేవు. team దీన్ని confirm చేస్తారు.
- [110.4s] caller: అయితే రేపు ఉదయం 11 గంటలకి మీ team తో ఒక short call book చేస్తారా? నా order place చేయడానికి అనుకూలంగా ఉంటుంది.
- agent [te-IN, 2.062s]: సరే, రేపు ఉదయం 11 గంటలకి team తో ఒక short call కావాలని note చేసుకున్నాను.
- [135.4s] caller: సరేనండి, మరి ఆ call confirm గా book అయిపోయినట్లేనా అండి?
- agent [te-IN, 1.813s]: ఆ call ఇంకా confirm కాలేదు. team వాళ్లు దాన్ని confirm చేస్తారు.
- [207.2s] caller: సరేనండి, అర్థమైంది. రేపు మీ team నుండి call కోసం చూస్తాను. ధన్యవాదాలు అండి, బాయ్.
- agent [te-IN, 1.016s]: (silent)
- farewell: సరే, మీ callback note చేసుకున్నాను. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.

### kn-IN/language_switch FAIL — 221.2s, disposition None ['no_runtime_error']
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- [19.8s] caller: ಹೌದು, ಹೇಳಿ. ನಿಮ್ಮ aloe vera juice ಬಗ್ಗೆ ತಿಳಿದುಕೊಳ್ಳಬೇಕಿತ್ತು, ಅದರ price ಮತ್ತು size ಎಷ್ಟು?
- agent [kn-IN, 1.797s]: ಖಂಡಿತ, NatureVeda Aloe Vera Juice ಬೆಲೆ ₹399 ಮತ್ತು ಇದರ size 500 ml ಇದೆ. ಇದರ ಬಗ್ಗೆ ಇನ್ನು ಏನಾದರೂ details ಬೇಕಾ?
- [97.6s] caller: ಓಕೆ, ಇದನ್ನು daily ಹೇಗೆ consume ಮಾಡಬೇಕು? ಎಷ್ಟು quantity ತಗೋಬೇಕು?
- agent [kn-IN, 1.969s]: ಕ್ಷಮಿಸಿ, ಇದರ daily consumption quantity ಬಗ್ಗೆ exact details ನನ್ನ ಬಳಿ ಇಲ್ಲ. General ಆಗಿ wellness beverage ಆಗಿ ಬಳಸಬಹುದು, ಆದ್ರೆ ಎಷ್ಟು ತಗೋಬೇಕು ಅಂತ label ಮೇಲೆ ಇರೋ instructions ನೋಡಿ ಅಥವಾ doctor ಹತ್ರ ಕೇಳಿ confirm ಮಾಡ್ಕೊಳ್ಳಿ.
- [163.1s] caller: Okay, no problem. Actually, I would prefer to continue in English now. Could you please repeat the price of the aloe vera juice you mentioned earlier?
- agent [en-IN, 1.672s]: Sure, the NatureVeda Aloe Vera Juice is priced at ₹399 for 500 ml.
- FAILED server:no_runtime_error — RuntimeError: caller model failed: RuntimeError: Gemini request failed (HTTP 429)

### kn-IN/integration FAIL — 56.2s, disposition None ['no_runtime_error', 'min_duration_90s', 'tool_gmail_send_email_succeeded']
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- FAILED server:no_runtime_error — RuntimeError: caller model failed: RuntimeError: Gemini request failed (HTTP 429)
- FAILED server:min_duration_90s — 56.2s
- FAILED server:tool_gmail_send_email_succeeded — []
