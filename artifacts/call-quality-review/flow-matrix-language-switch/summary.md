# Flow matrix flow-matrix-language-switch

Schema `sim_cd18b655b1784c92a8725117b3229a36`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | hi-IN | ta-IN | te-IN |
|---|---|---|---|---|
| language_switch | shop | PASS | FAIL: judge:offered_language_callback_and_closed | FAIL: judge:offered_language_callback_and_closed |

Passed 1/3.

## Transcripts

### hi-IN/language_switch/shop PASS — disposition callback_required []
- opening: नमस्ते, मैं अर्जुन हूं FreshCart से। मैं आपकी क्या मदद कर सकता हूं?
- caller: 300 रुपये के order की delivery fee कितनी है?
- agent: देखिए, 499 रुपये से कम के orders पर ₹30 की delivery fee लगती है। तो आपके 300 रुपये के order पर ₹30 charge लगेगा।
- caller: Can you please speak in English? I want to talk in English.
- agent: (silent)
- farewell: ज़रूर, हम आपको English में वापस call करेंगे। समय देने के लिए धन्यवाद। नमस्कार।
- judge answered_question_with_facts: True — देखलीं, 499 रुपये से कम के orders पर ₹30 की delivery fee लगती है।
- judge offered_language_callback_and_closed: True — (silent)

### ta-IN/language_switch/shop FAIL — disposition callback_required ['judge:offered_language_callback_and_closed']
- opening: வணக்கம். நான் FreshCart நிறுவனத்தின் அர்ஜுன் பேசுகிறேன். உங்களுக்கு எப்படி உதவ முடியும்?
- caller: 300 ரூவா order-க்கு delivery fee எவ்ளோ?
- agent: நானூற்று தொண்ணூறு ரூபாய்க்கு குறைவான ஆர்டர்களுக்கு முப்பது ரூபாய் delivery fee வரும்.
- caller: Can you please speak in English? I want to talk in English.
- agent: (silent)
- farewell: கண்டிப்பா, உங்களுக்கு Englishல மறுபடியும் call பண்றோம். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.
- judge answered_question_with_facts: True — நானூற்று தொண்ணூறு ரூபாய்க்கு குறைவான ஆர்டர்களுக்கு முப்பது ரூபாய் delivery fee வரும்.
- judge offered_language_callback_and_closed: False — (silent)

### te-IN/language_switch/shop FAIL — disposition callback_required ['judge:offered_language_callback_and_closed']
- opening: నమస్కారం, ఫ్రెష్‌కార్ట్‌కి స్వాగతం. నేను అర్జున్. నేను మీకు ఎలా సహాయం చేయగలను?
- caller: 300 rupees order కి delivery fee ఎంత?
- agent: మీ 300 రూపాయల ఆర్డర్‌కి డెలివరీ ఫీజు 30 రూపాయలు ఉంటుంది.
- caller: Can you please speak in English? I want to talk in English.
- agent: (silent)
- farewell: తప్పకుండా, మీకు English లో మళ్ళీ call చేస్తాం. సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.
- judge answered_question_with_facts: True — మీ 300 రూపాయల ఆర్డర్‌కి డెలివరీ ఫీజు 30 రూపాయలు ఉంటుంది.
- judge offered_language_callback_and_closed: False — AGENT (silent)
