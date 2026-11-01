# Agent QA agent-qa-v5

Sessions passed 23/24. Checks passed 467/468 (99.8%).

| Scenario | en-IN | hi-IN | ta-IN | kn-IN | gu-IN | ml-IN |
|---|---|---|---|---|---|---|
| language_switch | - | PASS | PASS | PASS | PASS | PASS |
| integration | - | PASS | - | PASS | - | - |
| dnd | PASS | - | - | PASS | - | - |
| callback_language | PASS | PASS | - | - | - | PASS |
| interested | PASS | FAIL: speech_clean | PASS | PASS | PASS | PASS |
| partially_interested | PASS | - | - | - | PASS | - |
| callback | - | - | PASS | - | PASS | - |
| not_interested | - | - | PASS | - | - | PASS |

## Session metrics

| Session | Dur s | Turns | Avg first chunk s | Max first chunk s | LLM calls/turn | Max sys prompt chars | Tools |
|---|---|---|---|---|---|---|---|
| hi-IN/language_switch | 133.3 | 7 | 1.57 | 2.00 | 4.6 | 25216 | - |
| hi-IN/integration | 197.8 | 10 | 1.99 | 5.09 | 4.7 | 21795 | GMAIL_SEND_EMAIL |
| en-IN/dnd | 116.3 | 5 | 1.44 | 1.89 | 4.4 | 22306 | - |
| en-IN/callback_language | 140.3 | 7 | 1.69 | 2.88 | 4.6 | 22597 | - |
| en-IN/interested | 238.9 | 13 | 1.70 | 2.66 | 4.8 | 22680 | - |
| en-IN/partially_interested | 137.8 | 6 | 1.51 | 1.92 | 4.5 | 22409 | - |
| ta-IN/interested | 155.5 | 8 | 2.11 | 2.69 | 5.2 | 22528 | - |
| ta-IN/language_switch | 161.2 | 8 | 1.55 | 2.19 | 4.6 | 26227 | - |
| kn-IN/dnd | 115.2 | 7 | 1.56 | 2.02 | 3.9 | 21969 | - |
| kn-IN/language_switch | 122.1 | 7 | 1.82 | 2.39 | 4.9 | 26470 | - |
| kn-IN/integration | 182.1 | 11 | 2.20 | 4.91 | 5.2 | 22167 | GMAIL_SEND_EMAIL |
| gu-IN/callback | 120.9 | 8 | 1.57 | 2.78 | 3.6 | 22440 | - |
| gu-IN/interested | 164.8 | 8 | 2.08 | 2.64 | 5.6 | 22482 | - |
| gu-IN/partially_interested | 97.4 | 4 | 2.23 | 2.56 | 4.8 | 22858 | - |
| gu-IN/language_switch | 150.7 | 7 | 2.37 | 3.88 | 5.3 | 26268 | - |
| ml-IN/callback_language | 108.8 | 7 | 1.58 | 1.88 | 4.6 | 22542 | - |
| hi-IN/callback_language | 104.9 | 6 | 1.86 | 3.39 | 4.2 | 22134 | - |
| ta-IN/callback | 109.5 | 6 | 1.76 | 2.38 | 4.3 | 22594 | - |
| ta-IN/not_interested | 115.2 | 6 | 1.60 | 2.34 | 4.0 | 22729 | - |
| ml-IN/not_interested | 102.2 | 7 | 1.45 | 1.91 | 4.0 | 22696 | - |
| ml-IN/language_switch | 121.6 | 7 | 1.66 | 2.33 | 4.0 | 26647 | - |
| kn-IN/interested | 181.9 | 12 | 2.01 | 3.38 | 4.7 | 22600 | - |
| ml-IN/interested | 229.2 | 17 | 1.95 | 3.12 | 4.6 | 23129 | - |
| hi-IN/interested | 210.8 | 14 | 1.67 | 2.45 | 4.3 | 21812 | - |

## Transcripts

### hi-IN/language_switch PASS — 133.3s, disposition interested []
- opening: नमस्ते, मैं प्रिया हूँ NatureVeda Herbals से। क्या आप हमारे हर्बल प्रोडक्ट्स के बारे में जानना चाहते हैं?
- [17.8s] caller: नमस्ते प्रिया, हाँ मुझे हमारे products के बारे में जानना है। ये aloe vera juice का price क्या है और इसकी size क्या-क्या आती है?
- agent [hi-IN, 1.485s]: NatureVeda Aloe Vera Juice ₹399 का है और इसकी size 500 ml आती है।
- [30.0s] caller: ठीक है, 500 ml के लिए ₹399। और इसको लेना कैसे सही रहेगा?
- agent [hi-IN, 1.265s]: ये general wellness beverage के लिए है, तो आप इसे daily routine में drink कर सकते हैं। अगर आप इसे लेना चाहें तो बता दीजिए।
- [50.7s] caller: ठीक है, daily drink करने का idea अच्छा है। वैसे, क्या आपको पता है कि हमारे यहाँ Kukatpally, Hyderabad में delivery कितने दिन में हो जाएगी?
- agent [hi-IN, 1.687s]: माफ़ कीजिए, Kukatpally, Hyderabad में delivery कितने दिन में हो जाएगी, इसकी जानकारी मेरे पास उपलब्ध नहीं है। अगर आप order place करना चाहें तो बता दीजिए।
- [73.4s] caller: Actually प्रिया, I think we should continue in English now. Could you please repeat the price of the aloe vera juice you told me earlier?
- agent [en-IN, 1.656s]: Sure, the NatureVeda Aloe Vera Juice is priced at ₹399 for 500 ml.
- [88.8s] caller: Okay, 500 ml for 399 rupees. अब मुझे उस hair oil के ingredients के बारे में बताइए जो आप बेचते हैं।
- agent [en-IN, 1.375s]: The NatureVeda Herbal Hair Oil contains Amla, Bhringraj, Hibiscus, and Coconut Oil, and it comes in 200 ml for ₹499. It is meant for routine hair and scalp care. Would you like to place an order for it?
- [113.1s] caller: Amla, Bhringraj, Hibiscus, and Coconut Oil, that sounds good. One juice and one hair oil, what will be the total amount?
- agent [en-IN, 2.0s]: One Aloe Vera Juice at ₹399 and one Herbal Hair Oil at ₹499 will come to a total of ₹898.
- [127.7s] caller: Okay, 898 rupees for both. That sounds reasonable. Thank you for the information Priya.
- agent [en-IN, 1.5s]: You're welcome. Let me know if you'd like to place an order.

> infra: GMAIL_SEND_EMAIL connection unavailable: The Gmail connection needs to be re-authorized by the business. Nothing was sent.
### hi-IN/integration PASS — 197.8s, disposition callback_required []
- opening: नमस्ते, मैं प्रिया हूँ NatureVeda Herbals से। क्या आप हमारे हर्बल प्रोडक्ट्स के बारे में जानना चाहते हैं?
- [15.5s] caller: हाँ, मुझे उनके बारे में जानना है। आपका face cream और hair oil का price क्या है?
- agent [hi-IN, 1.61s]: देखिए, Herbal Hair Oil ₹499 में 200 ml मिलता है, और Herbal Face Cream ₹599 में 50 g का है। इसके अलावा हमारे पास Aloe Vera Juice ₹399 और Ashwagandha Capsules ₹699 में भी उपलब्ध हैं। क्या आप इनमें से किसी प्रोडक्ट के बारे में और जानना चाहेंगे?
- [37.8s] caller: ठीक है, details और price मुझे email कर दीजिए। मेरा email ID है mohansaiteja.99@gmail.com।
  - tool GMAIL_SEND_EMAIL -> {"status": "error", "message": "The Gmail connection needs to be re-authorized by the business. Nothing was sent."}
- agent [hi-IN, 5.094s]: Email भेजने का try किया था, पर अभी connection issue की वजह से नहीं हो पाया। मैं अपनी team को बोल देती हूँ कि वो आपको directly contact करके details भेज दें। क्या मैं ये request note कर लूँ?
- [62.5s] caller: ठीक है, फिर वो details मुझे email कर दीजिए। क्या आपने email भेज दिया है?
- agent [hi-IN, 1.344s]: नहीं, अभी तक email नहीं भेजा जा सका क्योंकि connection issue आ रहा है। मैं ये request note कर लूँ?
- [78.6s] caller: अच्छा, ठीक है। क्या face cream अभी stock में है? और Kukatpally में delivery कब तक हो जाएगी?
- agent [hi-IN, 2.266s]: Face cream का stock और Kukatpally में delivery कब तक होगी, इसकी जानकारी मेरे पास अभी उपलब्ध नहीं है। मैं आपकी ये request note कर लेती हूँ ताकि team confirm कर सके। क्या मैं इसे save कर दूँ?
- [102.5s] caller: ठीक है, इसे note कर लीजिए। क्या face cream अभी stock में है और Kukatpally में delivery कब तक होगी?
- agent [hi-IN, 2.235s]: Face cream का stock और Kukatpally में delivery का समय, यह जानकारी मेरे पास अभी उपलब्ध नहीं है। आपकी request save हो गई है, team आपसे संपर्क करके details confirm कर लेगी।
- [128.4s] caller: ठीक है, team से बात हो जाएगी। एक काम कीजिए, कल सुबह 11 बजे के लिए एक short call book कर दीजिए order place करने के लिए। क्या ये time book हो गया?
- agent [hi-IN, 2.046s]: आपकी request save हो गई है। कल सुबह 11 बजे की callback request भी मैंने team के लिए note कर ली है, वो आपसे संपर्क करके details confirm कर लेंगे।
- [146.7s] caller: ठीक है, तो कल 11 बजे का call book हो गया है, है ना?
- agent [hi-IN, 1.454s]: हाँ, कल सुबह 11 बजे की callback request मैंने note कर ली है। Team आपसे संपर्क करके order details confirm कर लेगी।
- [161.5s] caller: ठीक है, तो कल 11 बजे का call confirm हो गया है।
- agent [hi-IN, 1.188s]: क्या आप अभी कोई order place करना चाहते हैं?
- [173.8s] caller: नहीं, अभी order place नहीं करना है। बस कल 11 बजे का call confirm हो गया है ना?
- agent [hi-IN, 1.688s]: हाँ, कल सुबह 11 बजे की callback request मैंने note कर ली है। Team आपसे संपर्क करके details confirm कर लेगी।
- [190.8s] caller: ठीक है, सब कुछ note हो गया है। मैं कल 11 बजे team के call का wait करूँगी।
- agent [hi-IN, 0.969s]: (silent)
- farewell: ठीक है, आपका callback note कर लिया है। समय देने के लिए धन्यवाद। नमस्कार।

### en-IN/dnd PASS — 116.3s, disposition not_interested []
- opening: Hello, my name is Priya from NatureVeda Herbals. I am calling to help you discover our herbal products, ingredients, prices, usage instructions, and delivery options. Is this a good time to talk?
- [19.2s] caller: Yes, tell me. Who are you calling from and what do you sell?
- agent [en-IN, 1.812s]: I am calling from NatureVeda Herbals. We offer herbal products like Hair Oil, Aloe Vera Juice, Face Cream, and Ashwagandha Capsules. Which one would you like to know about today?
- [38.5s] caller: Hair oil sounds interesting. What is the price for that one?
- agent [en-IN, 1.344s]: NatureVeda Herbal Hair Oil costs 499 rupees for 200 ml. It contains Amla, Bhringraj, Hibiscus, and Coconut Oil, and is intended for routine hair and scalp care. Would you like to place an order today?
- [61.0s] caller: 499 rupees? That is a bit costly na. Do you have any discount for first time buyers?
- agent [en-IN, 1.89s]: I don't have any discount details for first time buyers right now. The Hair Oil is priced at 499 rupees for 200 ml. Would you still like to go ahead with an order, or would you prefer to check the details later?
- [83.5s] caller: No discount? Okay, I will think about it. What other products do you have?
- agent [en-IN, 1.11s]: We also have Aloe Vera Juice at 399 rupees for 500 ml, Herbal Face Cream at 599 rupees for 50 g, and Ashwagandha Capsules at 699 rupees for 60 capsules. Which one would you like to explore?
- [108.9s] caller: Okay, these prices are too much. I do not want any products right now. Please remove my number from your list and never call this number again.
- agent [en-IN, 1.032s]: (silent)
- farewell: Understood, we won't call this number again. Thank you for your time. Goodbye.

### en-IN/callback_language PASS — 140.3s, disposition callback_required []
- opening: Hello, my name is Priya from NatureVeda Herbals. I am calling to help you discover our herbal products, ingredients, prices, usage instructions, and delivery options. Is this a good time to talk?
- [16.6s] caller: Yes, tell me. I am listening.
- agent [en-IN, 1.36s]: Great. Which herbal product or category would you like to explore today?
- [33.2s] caller: Actually, can you tell me what products you have? I am especially interested in the aloe vera juice, what is the price for that?
- agent [en-IN, 1.937s]: Our NatureVeda Aloe Vera Juice costs 399 rupees for 500 ml. It contains Aloe Vera and is marketed as a general wellness beverage. Would you like to know more about it?
- [53.0s] caller: 399 rupees is okay. Does it have any added sugar or preservatives in it?
- agent [en-IN, 1.406s]: I’m sorry, I don’t have that detail right now.
- [64.6s] caller: Ah, that is okay. Is it available for delivery to my address in Kukatpally, Hyderabad?
- agent [en-IN, 2.875s]: I’m sorry, but I currently don’t have the delivery availability for Kukatpally, Hyderabad. Would you like me to note this enquiry for you?
- [84.5s] caller: No need to note it right now. What other products do you have, maybe something for hair?
- agent [en-IN, 1.375s]: We have NatureVeda Herbal Hair Oil for 499 rupees for 200 ml. It contains Amla, Bhringraj, Hibiscus, and Coconut Oil, and is intended for routine hair and scalp care. Which details would you like to know?
- [107.0s] caller: 499 rupees is a bit high for me. Do you have anything cheaper for hair growth?
- agent [en-IN, 1.844s]: Our NatureVeda Aloe Vera Juice is 399 rupees for 500 ml, which is our lower-priced option. For hair growth specifically, I don’t have a cheaper product in that category right now. Would you like to explore the Aloe Vera Juice instead?
- [133.7s] caller: No, let us just stop here for now. I am more comfortable speaking in Hindi, so can you call me back tomorrow morning around 11?
- agent [en-IN, 1.063s]: (silent)
- farewell: Okay, I've noted your callback. Thank you for your time. Goodbye.

### en-IN/interested PASS — 238.9s, disposition converted []
- opening: Hello, my name is Priya from NatureVeda Herbals. I am calling to help you discover our herbal products, ingredients, prices, usage instructions, and delivery options. Is this a good time to talk?
- [19.2s] caller: Yes, yes, this is a good time. Please tell me about your products.
- agent [en-IN, 1.547s]: We have four main products. Would you like to know about our Herbal Hair Oil, Aloe Vera Juice, Face Cream, or Ashwagandha Capsules?
- [35.0s] caller: Can you tell me what ingredients are in the face cream?
- agent [en-IN, 1.25s]: The Herbal Face Cream contains Neem, Turmeric, and Aloe Vera, and it costs 599 rupees for 50 g. It is meant for moisturizing and routine skin care. Which product would you like to explore today?
- [55.5s] caller: Neem and turmeric, good for skin. How do I use this face cream?
- agent [en-IN, 1.297s]: The usage instructions for the Herbal Face Cream are currently unavailable. Would you like to know about any of our other products?
- [75.3s] caller: Oh, usage instructions are not available? That is a bit difficult. Anyway, tell me about the hair oil, how much is it?
- agent [en-IN, 1.328s]: The Herbal Hair Oil costs 499 rupees for 200 ml. It contains Amla, Bhringraj, Hibiscus, and Coconut Oil, and is intended for routine hair and scalp care. Would you like to place an order today?
- [100.7s] caller: Okay, the ingredients sound very natural. I want to order 2 bottles of the hair oil and 1 face cream. What is the total price?
- agent [en-IN, 2.312s]: The total comes to 1,597 rupees. 2 bottles of the hair oil at 499 rupees each, and 1 face cream at 599 rupees. Would you like to place this order today?
- [118.0s] caller: 1597 rupees, okay. How long will the delivery take?
- agent [en-IN, 1.547s]: The delivery time is currently unavailable. Would you like to place the order today?
- [133.4s] caller: Delivery time is not available? Hmm, that is not very good. Is there any discount on this order?
- agent [en-IN, 1.547s]: I don't have any discount details for this order. The information is currently unavailable. Would you like to place it today?
- [152.7s] caller: No discount and no delivery time, I am not sure. But I will go ahead with the order. What happens next?
- agent [en-IN, 2.266s]: Great. To proceed, I will need your name and delivery address. Could you share those with me?
- [164.4s] caller: My name is Lakshmi Reddy.
- agent [en-IN, 1.625s]: Thank you, Lakshmi Reddy. Could you share your delivery address?
- [175.1s] caller: It is Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- agent [en-IN, 1.156s]: Lakshmi Reddy. I have noted your address as Flat 302, Sai Residency, Kukatpally, Hyderabad 500072. Would you like to place this order today?
- [191.8s] caller: Yes, yes, I want to place the order. My mobile number is mohansaiteja.99@gmail.com.
- agent [en-IN, 2.656s]: Your order for 2 bottles of Herbal Hair Oil and 1 Herbal Face Cream has been confirmed. I have noted your email as mohansaiteja.99@gmail.com for the confirmation.
- [210.5s] caller: Okay, email noted. So my order is confirmed now, correct?
- agent [en-IN, 1.781s]: Yes, your order is confirmed. It is for 2 bottles of Herbal Hair Oil and 1 Herbal Face Cream for Lakshmi Reddy, delivered to Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- [231.4s] caller: Okay, so it is confirmed. What happens now? Do I need to pay now itself?
- agent [en-IN, 1.781s]: The payment timing is currently unavailable. Would you like to place the order today?

### en-IN/partially_interested PASS — 137.8s, disposition interested []
- opening: Hello, my name is Priya from NatureVeda Herbals. I am calling to help you discover our herbal products, ingredients, prices, usage instructions, and delivery options. Is this a good time to talk?
- [18.1s] caller: Yes, now is fine. What is this product for exactly?
- agent [en-IN, 1.219s]: That depends on which product you are looking at. Could you tell me which one interests you today?
- [34.1s] caller: I heard about your Ashwagandha capsules for stress and sleep. Can you tell me the price for those?
- agent [en-IN, 1.515s]: The Ashwagandha Capsules cost 699 rupees for 60 capsules. They are an herbal wellness supplement, and for stress or sleep concerns, I would recommend consulting a qualified healthcare professional. Would you like to place an order today?
- [61.2s] caller: 699 rupees for 60 capsules, okay. But I am already taking blood pressure medicine, so is this safe for me to take? I am a little worried.
- agent [en-IN, 1.547s]: I understand your concern. Since you are already taking blood pressure medicine, I would strongly recommend consulting a qualified healthcare professional before starting this supplement.
- [84.6s] caller: Haan, I will definitely ask my doctor first. Is it guaranteed to cure stress completely? And are there any side effects?
- agent [en-IN, 1.797s]: These products do not cure diseases or guarantee side-effect-free results, so I cannot confirm that. For medical conditions or possible interactions, please consult a qualified healthcare professional.
- [107.6s] caller: Arre, no guarantee? Then what is the use? Is there any discount available if I buy it?
- agent [en-IN, 1.922s]: There is no discount available right now. Also, these products do not guarantee to cure stress completely and I cannot confirm there are no side effects.
- [130.8s] caller: No discount at all? That is too much for 699 rupees then. I will think about it and maybe talk to my doctor before deciding.
- agent [en-IN, 1.046s]: I understand, take your time. Just let me know if you would like to place an order later.

### ta-IN/interested PASS — 155.5s, disposition converted []
- opening: வணக்கம், என் பெயர் ப்ரியா, நேச்சர்வேதா ஹெர்பல்ஸ் நிறுவனத்திலிருந்து பேசுகிறேன். எங்களின் மூலிகை தயாரிப்புகள் மற்றும் அதன் விவரங்களை தெரிந்து கொள்ள உங்களுக்கு இப்போது சிறிது நேரம் கிடைக்குமா?
- [17.4s] caller: வணக்கம் பிரியா, கொஞ்சம் time இருக்கு. சொல்லுங்க, என்ன products இருக்கு?
- agent [ta-IN, 2.203s]: சரி, எங்களோட products விவரம் சொல்றேன். நேச்சர்வேதா ஹெர்பல் ஹேர் ஆயில் 200 ml விலை 499 ரூபாய், இதுல ஆம்லா, பிரிங்கராஜ், செம்பருத்தி மற்றும் தேங்காய் எண்ணெய் இருக்கு.
- [36.8s] caller: Hair oil நல்லா இருக்கு போல. இந்த face cream-ல என்னென்ன ingredients இருக்குன்னு சொல்ல முடியுமா?
- agent [ta-IN, 1.484s]: நேச்சர்வேதா ஹெர்பல் ஃபேஸ் கிரீம் 50 கிராம் விலை 599 ரூபாய். இதுல வேப்பிலை, மஞ்சள் மற்றும் அலோ வேரா இருக்கு, இது மாய்ஸ்சரைசிங் மற்றும் வழக்கமான தோல் பராமரிப்புக்காகப் பயன்படுகிறது.
- [58.7s] caller: Super, இந்த ingredients எல்லாம் natural-ஆ இருக்கறது நல்லா இருக்கு. நான் 2 bottles hair oil-உம் 1 face cream-உம் order பண்ணிக்கிறேன்.
- agent [ta-IN, 2.688s]: சரி, order பண்றதுக்கு உங்க பேரும் delivery address-உம் கொஞ்சம் சொல்லுங்க. நான் details பதிவு பண்றேன்.
- [75.2s] caller: சரி பிரியா, என் பேரு லட்சுமி ரெட்டி. Address வந்து Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- agent [ta-IN, 2.547s]: சரி லட்சுமி ரெட்டி, உங்க address Flat 302, Sai Residency, Kukatpally, Hyderabad 500072-ன்னு note பண்ணிக்கிட்டேன். இப்போ order-அ confirm பண்றதுக்கு முன்னாடி, total-அ ஒரு தடவ சொல்றேன். எல்லாம் correct-தானே?
- [98.2s] caller: ஆமா, correct தான். ஆனா total price எவ்ளோ வரும்னு சொல்ல முடியுமா?
- agent [ta-IN, 2.016s]: சரி, 2 hair oil 499 ரூபாய் வீதம் மொத்தம் 998 ரூபாய் வரும், அப்புறம் 1 face cream 599 ரூபாய். So, total-ஆ 1,597 ரூபாய் வரும்.
- [114.0s] caller: சரி, 1,597 rupees ஆச்சு. இதுக்கு ஏதாவது discount இருக்கா பிரியா?
- agent [ta-IN, 1.875s]: தள்ளுபடி பத்தின விவரங்கள் இப்போ எங்ககிட்ட கிடைக்கலைங்க. எங்க குழு அதை உறுதி செய்வாங்க. இப்போதைக்கு இந்த order-அ proceed பண்ணலாமா?
- [129.6s] caller: சரி, discount இல்லன்னாலும் பரவாயில்லை. Delivery எப்போ வரும்னு சொல்ல முடியுமா?
- agent [ta-IN, 1.672s]: மன்னிக்கவும், delivery எப்போது வரும் என்ற விவரங்கள் இப்போ எங்ககிட்ட கிடைக்கலைங்க. எங்கள் குழு அதை உறுதி செய்வாங்க.
- [145.2s] caller: சரி, delivery time தெரியலன்னா பரவாயில்ல. அப்படியே order-அ confirm பண்ணிடுங்க. அடுத்து என்ன பண்ணனும்னு சொல்லுங்க.
- agent [ta-IN, 2.406s]: உங்க order confirm ஆயிடுச்சு. அடுத்ததா எங்க குழு இத process பண்ணுவாங்க, delivery details-அ அவங்க confirm பண்ணுவாங்க.

### ta-IN/language_switch PASS — 161.2s, disposition interested []
- opening: வணக்கம், என் பெயர் ப்ரியா, நேச்சர்வேதா ஹெர்பல்ஸ் நிறுவனத்திலிருந்து பேசுகிறேன். எங்களின் மூலிகை தயாரிப்புகள் மற்றும் அதன் விவரங்களை தெரிந்து கொள்ள உங்களுக்கு இப்போது சிறிது நேரம் கிடைக்குமா?
- [22.5s] caller: வணக்கம் பிரியா. எனக்கு கொஞ்சம் time இருக்கு. அந்த aloe vera juice பத்தி சொல்லுங்க, என்ன விலை, எந்த size-ல வர்றது, எப்படி குடிக்கணும்னு கொஞ்சம் details வேணும்.
- agent [ta-IN, 1.86s]: சரி, நேச்சர்வேதா அலோ வேரா ஜூஸ் 500 ml பாட்டில் விலை 399 ரூபாய். இதுல அலோ வேரா மட்டும் தான் இருக்கு, பொதுவான wellness beverage-ஆ குடிக்கலாம். உங்களுக்கு இந்த product வேணுமா?
- [43.3s] caller: சரி, 399 rupees-னா கொஞ்சம் அதிகம் தான். 500 ml size ஓகே, ஆனா தினமும் எப்படி குடிக்கணும்னு கொஞ்சம் சொல்லுங்க.
- agent [ta-IN, 1.829s]: புரியுது, விலை கொஞ்சம் அதிகம் தான். ஆனா இந்த அலோ வேரா ஜூஸ் எப்படி குடிக்கணும்ங்கிற exact daily usage details இப்போதைக்கு எங்ககிட்ட இல்லைங்க, எங்க team அதை confirm பண்ணுவாங்க.
- [69.2s] caller: Okay, I will think about that. Actually, from now on can we speak in plain English? I am more comfortable in that.
- agent [en-IN, 1.469s]: Of course, we can continue in English. Just let me know whenever you decide if you would like to place an order for the Aloe Vera Juice.
- [88.3s] caller: Actually, since some time has passed, can we continue in plain English now? I am more comfortable with that.
- agent [en-IN, 1.219s]: Of course, we can continue in plain English.
- [99.6s] caller: Okay. Can you repeat the price of that aloe vera juice you told me earlier?
- agent [en-IN, 1.391s]: The Aloe Vera Juice is ₹399 for 500 ml. Just let me know if you would like to place an order.
- [114.3s] caller: Right, 399 rupees. Tell me one thing, what are the ingredients in your hair oil?
- agent [en-IN, 1.296s]: Our Herbal Hair Oil contains Amla, Bhringraj, Hibiscus, and Coconut Oil. It comes in 200 ml for ₹499. Would you like to place an order for that?
- [134.2s] caller: Okay, got it. If I take one aloe vera juice and one hair oil, what will be the total amount?
- agent [en-IN, 2.188s]: One Aloe Vera Juice at ₹399 and one Herbal Hair Oil at ₹499 makes a total of ₹898. Just let me know if you would like to place an order.
- [154.2s] caller: 898 rupees is okay. I will think about it and let you know later. Thank you for the information.
- agent [en-IN, 1.125s]: You're welcome. Just let me know whenever you decide if you'd like to place the order.

### kn-IN/dnd PASS — 115.2s, disposition not_interested []
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- [8.5s] caller: ನಮಸ್ಕಾರ, ಹೇಳಿ. ಯಾರು ಮಾತಾಡ್ತಿದ್ದೀರಾ, ಏನು ಸೇಲ್ ಮಾಡ್ತೀರಾ?
- agent [kn-IN, 1.344s]: ನಾನು NatureVeda Herbals ಇಂದ Priya ಮಾತಾಡ್ತಿದ್ದೀನಿ. ನಮ್ಮ ಹತ್ರ herbal products ಇದೆ — like hair oil, aloe vera juice, face cream, ಮತ್ತೆ ashwagandha capsules. ಇದರ ಬಗ್ಗೆ details ತಿಳ್ಕೊಬೇಕಾ?
- [26.8s] caller: ಆ hair oil price ಎಷ್ಟಿದೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.688s]: NatureVeda Herbal Hair Oil price ₹499 ಇದೆ, 200 ml bottle ಗೆ. ಇದರಲ್ಲಿ Amla, Bhringraj, Hibiscus, ಮತ್ತೆ Coconut Oil ಇರುತ್ತೆ, routine hair ಮತ್ತೆ scalp care ಗೆ ಒಳ್ಳೇದು. ಇದರ ಬಗ್ಗೆ ಇನ್ನು ಏನಾದ್ರೂ ತಿಳ್ಕೊಬೇಕಾ?
- [47.5s] caller: ₹499 ಅಂದ್ರೆ ಸ್ವಲ್ಪ ಜಾಸ್ತಿ ಆಯ್ತು. ಆ ಮುಖದ ಕ್ರೀಮ್ ಬಗ್ಗೆ ಏನು ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.328s]: ಖಂಡಿತ, ಅರ್ಥ ಆಗುತ್ತೆ. NatureVeda Herbal Face Cream ಬೆಲೆ ₹599 ಇದೆ, 50 g ಗೆ. ಇದರ ಬಗ್ಗೆ ಇನ್ನು details ಬೇಕಾ?
- [63.0s] caller: ಮುಖದ ಕ್ರೀಮ್ ಬೆಲೆ ₹599 ಅಂದ್ರೆ ತುಂಬಾನೇ ಜಾಸ್ತಿ ಆಯ್ತು ನೋಡಿ. ಇದರಲ್ಲಿ ಏನೇನು ingredients ಇದೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 2.016s]: ಹೌದು, ಇದು ಸ್ವಲ್ಪ ಜಾಸ್ತಿ ಅನ್ಸಬಹುದು. ಈ face cream ನಲ್ಲಿ Neem, Turmeric, ಮತ್ತೆ Aloe Vera ಇರುತ್ತೆ. ಇದರ ಬಗ್ಗೆ ಇನ್ನು ಏನಾದ್ರೂ ತಿಳ್ಕೊಬೇಕಾ?
- [81.2s] caller: Neem ಮತ್ತೆ Turmeric ಇದ್ರೆ ಸರಿ, ಆದ್ರೆ ಈ price ಸ್ವಲ್ಪ ಜಾಸ್ತಿ ಅನ್ಸುತ್ತೆ. Ashwagandha capsules ಬಗ್ಗೆ ಏನಾದ್ರೂ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.391s]: NatureVeda Ashwagandha Capsules ಬೆಲೆ ₹699 ಇದೆ, 60 capsules ಗೆ.
- [91.6s] caller: ₹699 ಅಂದ್ರೆ ತುಂಬಾನೇ ಜಾಸ್ತಿ ಆಯ್ತು. ಈ ಬೆಲೆಗೆ ನಾನು ತಗೊಳಲ್ಲ.
- agent [kn-IN, 1.172s]: ಸರಿ, ಅರ್ಥ ಆಯ್ತು. ನಿಮಗೆ interest ಇಲ್ಲ ಅಂದ್ರೆ ಪರವಾಗಿಲ್ಲ, ಸಮಯ ಕೊಟ್ಟಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು.
- [107.4s] caller: ನೋಡಿ, ನಂಗೆ ಈ ತರಹದ ತುಂಬಾ calls ಬರ್ತಾ ಇದೆ. ದಯವಿಟ್ಟು ಈ number-ಗೆ ಮತ್ತೆ ಯಾವತ್ತೂ call ಮಾಡ್ಬೇಡಿ, ನನ್ನ number-ನ ತಕ್ಷಣ remove ಮಾಡಿ.
- agent [kn-IN, 1.984s]: (silent)
- farewell: ಸರಿ, ಈ ನಂಬರ್‌ಗೆ ಮತ್ತೆ ಕಾಲ್ ಮಾಡಲ್ಲ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### kn-IN/language_switch PASS — 122.1s, disposition interested []
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- [14.9s] caller: ನಮಸ್ಕಾರ, ನಾನು Lakshmi ಮಾತಾಡ್ತಿರೋದು. ನಾನು first time call ಮಾಡ್ತಿದ್ದೀನಿ. ನಿಮ್ಮ aloe vera juice ಬಗ್ಗೆ ಸ್ವಲ್ಪ details ಬೇಕಿತ್ತು, ಅದರ price ಮತ್ತೆ size ಎಷ್ಟಿದೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.703s]: ಖಂಡಿತ ಹೇಳ್ತೀನಿ. ನಮ್ಮ NatureVeda Aloe Vera Juice price ₹399 ಇರುತ್ತೆ, ಮತ್ತೆ ಅದು 500 ml size-ಅಲ್ಲಿ ಬರುತ್ತೆ.
- [29.2s] caller: ಸರಿ, 500 ml-ಗೆ ₹399 ಆಗ್ತದಾ. ಇದನ್ನ ದಿನಾ ಎಷ್ಟು ಕುಡೀಬೇಕು ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.625s]: ಆ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ. General wellness beverage ಆಗಿ ಇದನ್ನ use ಮಾಡ್ತಾರೆ, ಆದ್ರೆ ದಿನಕ್ಕೆ ಎಷ್ಟು ಕುಡೀಬೇಕು ಅನ್ನೋದು ಖಚಿತವಾಗಿ ಹೇಳೋಕೆ ಆಗಲ್ಲ. Medical conditions ಅಥವಾ ಬೇರೆ ಏನಾದ್ರೂ concerns ಇದ್ರೆ ದಯವಿಟ್ಟು healthcare professional ಹತ್ರ ಒಮ್ಮೆ ಕೇಳಿ.
- [52.6s] caller: ಸರಿ, ಅರ್ಥ ಆಯ್ತು. ಈಗ ನಂಗೆ ಸ್ವಲ್ಪ ಬೇರೆ language-ಅಲ್ಲಿ ಮಾತಾಡೋಕೆ ಇಷ್ಟ ಇದೆ, ದಯವಿಟ್ಟು ಅದೇ details-ನ ಕನ್ನಡದಲ್ಲಿ continue ಮಾಡಿ.
- agent [kn-IN, 1.391s]: ಖಂಡಿತ, ನಾನು ಕನ್ನಡದಲ್ಲೇ continue ಮಾಡ್ತೀನಿ.
- [67.2s] caller: Okay, so earlier you said the aloe vera juice is 399 rupees, right? Can you tell me what ingredients are in your hair oil?
- agent [kn-IN, 2.031s]: ಹೌದು, aloe vera juice price ₹399. ನಮ್ಮ Herbal Hair Oil-ಅಲ್ಲಿ Amla, Bhringraj, Hibiscus, ಮತ್ತೆ Coconut Oil ಇರುತ್ತೆ. ನಿಮಗೆ ಇದರ ಬಗ್ಗೆ ಇನ್ನು ಏನಾದ್ರೂ details ಬೇಕಾ?
- [86.4s] caller: Okay, Amla and Bhringraj are good. How much does that hair oil cost?
- agent [en-IN, 1.704s]: Our Herbal Hair Oil costs ₹499 for 200 ml. Would you like to know more about any of our products?
- [102.4s] caller: Okay, so one aloe vera juice and one hair oil, how much will it come to together?
- agent [en-IN, 1.922s]: One aloe vera juice and one hair oil will come to ₹898 together.
- [113.3s] caller: Okay, 898 rupees total. That is fine for me.
- agent [en-IN, 2.391s]: Got it, Lakshmi. Since the total comes to ₹898, would you like to go ahead and place the order?

> infra: GMAIL_SEND_EMAIL connection unavailable: The Gmail connection needs to be re-authorized by the business. Nothing was sent.
### kn-IN/integration PASS — 182.1s, disposition callback_required []
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- [11.9s] caller: ಹೌದು ಪ್ರಿಯಾ, ಹೇಳಿ. ನಿಮ್ಮ ಹತ್ರ face cream ಮತ್ತೆ hair oil ಇದೆ ಅಂತ ಕೇಳಿದ್ದೆ, ಅದರ price ಎಷ್ಟಾಗುತ್ತೆ?
- agent [kn-IN, 1.594s]: ಖಂಡಿತ ಹೇಳ್ತೀನಿ. ನಮ್ಮ Herbal Hair Oil 200 ml ಗೆ ₹499 ಆಗುತ್ತೆ, ಮತ್ತೆ Herbal Face Cream 50 g ಗೆ ₹599 ಇದೆ. ನಿಮಗೆ ಬೇರೆ ಯಾವುದಾದ್ರೂ details ಬೇಕಾ?
- [32.8s] caller: ಸರಿ, price ಕೇಳಿ ತುಂಬಾ ಖುಷಿ ಆಯ್ತು. ಇದನ್ನ ಎಲ್ಲಾ details ಮತ್ತೆ price list ನ ನನ್ನ email ಗೆ ಕಳಿಸ್ತೀರಾ? ನನ್ನ email ID mohansaiteja.99@gmail.com, ದಯವಿಟ್ಟು ಕಳಿಸಿ.
  - tool GMAIL_SEND_EMAIL -> {"status": "error", "message": "The Gmail connection needs to be re-authorized by the business. Nothing was sent."}
- agent [kn-IN, 4.906s]: ಕ್ಷಮಿಸಿ, ಈಗ email ಕಳಿಸೋಕೆ ಆಗಿಲ್ಲ, connection issue ಇದೆ. ನೀವು ಸ್ವಲ್ಪ ಹೊತ್ತಿನ ನಂತರ try ಮಾಡಬಹುದು, ಅಥವಾ ಬೇಕಿದ್ರೆ ನಾನು ಈ details ನ enquiry ಆಗಿ save ಮಾಡ್ತೀನಿ. ಹಾಗೆ ಮಾಡ್ಲಾ?
- [53.9s] caller: ಸರಿ, ತೊಂದರೆ ಇಲ್ಲ, ಹಾಗೇ ಮಾಡಿ save ಮಾಡಿ. ಆಮೇಲೆ email ಕಳಿಸ್ತೀರಾ?
- agent [kn-IN, 2.453s]: ಆಯ್ತು, ನಿಮ್ಮ enquiry save ಆಗಿದೆ. ಆಮೇಲೆ email ಕಳಿಸೋ ಬಗ್ಗೆ ನಮ್ಮ team ನಿಮ್ಮನ್ನ contact ಮಾಡ್ತಾರೆ.
- [67.0s] caller: ಸರಿ, email ಕಳಿಸಿದ್ರಾ ಅಂತ ಒಂದು ಸಲ confirm ಮಾಡ್ತೀರಾ?
- agent [kn-IN, 3.203s]: ಇಲ್ಲ, ಈಗ email ಕಳಿಸೋಕೆ ಆಗ್ತಿಲ್ಲ. ಆದ್ರೆ ನಿಮ್ಮ enquiry ಖಂಡಿತ save ಆಗಿದೆ, ನಮ್ಮ team ಆಮೇಲೆ ನಿಮ್ಮನ್ನ contact ಮಾಡ್ತಾರೆ.
- [84.1s] caller: ಸರಿ, team ಕಡೆಯಿಂದ ಯಾವಾಗ call ಬರುತ್ತೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.516s]: ನಾನು ನಿಮ್ಮ callback time ನ note ಮಾಡ್ಕೊಳ್ತೀನಿ. ನಿಮಗೆ ಯಾವ time ಅನುಕೂಲ ಆಗುತ್ತೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- [99.8s] caller: ನಾಳೆ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ ಒಂದು short call arrange ಮಾಡ್ತೀರಾ order place ಮಾಡೋಕೆ? ಅದನ್ನ book ಮಾಡಿದ್ರಾ ಅಂತ confirm ಮಾಡ್ತೀರಾ?
- agent [kn-IN, 1.812s]: ಆಯ್ತು, ನಿಮ್ಮ callback request ನಾಳೆ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ note ಮಾಡಿದ್ದೀನಿ. ನಮ್ಮ team order place ಮಾಡೋಕೆ ನಿಮಗೆ call ಮಾಡ್ತಾರೆ.
- [116.3s] caller: ಸರಿ, face cream stock ಅಲ್ಲಿ ಇದೆಯಾ? ಮತ್ತೆ Kukatpally ಗೆ ಯಾವಾಗ delivery ಆಗುತ್ತೆ ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.828s]: Face cream stock ಬಗ್ಗೆ ಮಾಹಿತಿ ಸದ್ಯಕ್ಕೆ ಲಭ್ಯವಿಲ್ಲ. Kukatpally ಗೆ delivery ಯಾವಾಗ ಆಗುತ್ತೆ ಅನ್ನೋದು ಕೂಡ ಈಗ ತಿಳಿದಿಲ್ಲ.
- [133.9s] caller: ಅಯ್ಯೋ, stock details ಇಲ್ಲ ಅಂದ್ರೆ ಹೇಗೆ? ನಂಗೆ order ಮಾಡೋಕೆ ಮುಂಚೆ ಇದು ಬೇಕಾಗುತ್ತೆ ಅಲ್ವಾ. ದಯವಿಟ್ಟು team ಹತ್ರ ಕೇಳಿ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 2.266s]: ಸರಿ, ನಾನು ನಮ್ಮ team ಗೆ stock details ಬಗ್ಗೆ ಕೇಳಿ ತಿಳಿಸ್ತೀನಿ. ಅವರು ನಿಮಗೆ ವಾಪಸ್ ತಿಳಿಸ್ತಾರೆ.
- [148.3s] caller: ಸರಿ, ಹಾಗಾದ್ರೆ team ಹತ್ರ ಕೇಳಿ ನನಗೆ stock ಮತ್ತೆ delivery ಬಗ್ಗೆ confirm ಮಾಡ್ತೀರಾ ಅಲ್ವಾ?
- agent [kn-IN, 1.703s]: ಹೌದು, ಖಂಡಿತ. ನಾನು team ಹತ್ರ ಕೇಳಿ ನಿಮಗೆ stock ಮತ್ತೆ delivery ಬಗ್ಗೆ confirm ಮಾಡಿಸ್ತೀನಿ.
- [160.4s] caller: ಸರಿ, ತುಂಬಾ ಧನ್ಯವಾದಗಳು. ದಯವಿಟ್ಟು team ಕಡೆಯಿಂದ ನನಗೆ confirm ಮಾಡಿಸಿ.
- agent [kn-IN, 1.813s]: ನಾನು note ಮಾಡ್ಕೊಂಡಿದ್ದೀನಿ. ನಮ್ಮ team ನಿಮ್ಮನ್ನ contact ಮಾಡಿ stock ಮತ್ತೆ delivery ಬಗ್ಗೆ confirm ಮಾಡ್ತಾರೆ.
- [175.6s] caller: ಸರಿ, ತುಂಬಾ ಧನ್ಯವಾದಗಳು ಪ್ರಿಯಾ. ನಾನು wait ಮಾಡ್ತೀನಿ, team ಕಡೆಯಿಂದ ನನಗೆ ಖಂಡಿತ update ಕೊಡಿ.
- agent [kn-IN, 1.109s]: ಖಂಡಿತ, ನಾನು ಎಲ್ಲವನ್ನೂ note ಮಾಡ್ಕೊಂಡಿದ್ದೀನಿ. ನಮ್ಮ team ನಿಮ್ಮನ್ನ contact ಮಾಡ್ತಾರೆ.

### gu-IN/callback PASS — 120.9s, disposition callback_required []
- opening: નમસ્તે, હું NatureVeda Herbals માંથી Priya. એક મિનિટ વાત થઈ શકે?
- [7.8s] caller: હા, કહો ને. હું સાંભળું છું.
- agent [gu-IN, 0.984s]: સરસ. આજે તમે કયો herbal product જોવા માંગો છો? અમારી પાસે Hair Oil, Aloe Vera Juice, Face Cream અને Ashwagandha Capsules છે.
- [22.6s] caller: Hair oil વિશે જણાવશો? મારા વાળ બહુ dry થઈ ગયા છે.
- agent [gu-IN, 2.282s]: હા ચોક્કસ. અમારી NatureVeda Herbal Hair Oil 200 ml માટે ₹499 ની છે. order કરવો છે આજે?
- [36.2s] caller: ₹499? આટલી price છે? એમાં શું ingredients નાખ્યા છે એ જણાવશો?
- agent [gu-IN, 1.562s]: હા, આ Hair Oil ની price ₹499 જ છે. એમાં Amla, Bhringraj, Hibiscus અને Coconut Oil નાખેલા છે, જે routine hair અને scalp care માટે સારા છે.
- [52.5s] caller: આ ingredients સારા છે. આ oil કેટલી વાર use કરવાનું હોય?
- agent [gu-IN, 2.781s]: એ માહિતી મારી પાસે નથી. Usage કેટલી વાર કરવાનું એ product label પર લખેલું હોય છે, એટલે એકવાર check કરી લેજો.
- [69.2s] caller: અચ્છા, તો label પર જોઈ લઈશ. આ oil માં ખરેખર સારા ingredients લાગે છે.
- agent [gu-IN, 0.922s]: સારું. જો તમારે order કરવો હોય તો કહેજો.
- [79.1s] caller: હા, order તો કરવો છે પણ મને આની delivery ક્યારે મળશે એ જણાવશો?
- agent [gu-IN, 1.875s]: એ information મારી પાસે અત્યારે ઉપલબ્ધ નથી. જો તમે order place કરવા માંગતા હોવ, તો હું તે કરી શકું છું. શું આપણે order place કરીએ?
- [96.0s] caller: Delivery ની details અત્યારે ખબર નથી? તો કંઈ વાંધો નહીં, હું પછીથી વિચારીશ.
- agent [gu-IN, 0.938s]: કંઈ વાંધો નહીં, તમે આરામથી વિચારી લો. જ્યારે પણ order કરવો હોય ત્યારે જણાવી દેજો.
- [114.0s] caller: સારુ, હું વિચારીને કાલે જણાવીશ. અત્યારે હું કામમાં છું ને થોડો busy છું, તો કાલે સાંજે 6:30 વાગ્યે આ જ number પર મને પાછો call કરી લેજો.
- agent [gu-IN, 1.25s]: (silent)
- farewell: સારું, તમારો callback note કરી લીધો છે. તમારા સમય માટે આભાર. આવજો.

### gu-IN/interested PASS — 164.8s, disposition converted []
- opening: નમસ્તે, હું NatureVeda Herbals માંથી Priya. એક મિનિટ વાત થઈ શકે?
- [8.2s] caller: હા, બોલો ને. હું Lakshmi બોલું છું.
- agent [gu-IN, 1.797s]: આભાર Lakshmi. આજે તમે કયો herbal product જોવા માંગો છો? અમારી પાસે Hair Oil, Aloe Vera Juice, Face Cream અને Ashwagandha Capsules ઉપલબ્ધ છે.
- [29.5s] caller: મને hair oil અને face cream માં interest છે. આ face cream માં કયા ingredients છે? અને એને કેવી રીતે use કરવાનું છે?
- agent [gu-IN, 1.719s]: Face cream માં Neem, Turmeric અને Aloe Vera છે, અને એ moisturizing અને routine skin care માટે છે. એને કેવી રીતે use કરવાનું છે, એ માહિતી મારી પાસે નથી.
- [69.4s] caller: સારું, કોઈ વાંધો નહીં. તો હું 2 bottles hair oil અને 1 face cream નો order કરું છું. આનો total price કેટલો થશે?
- agent [gu-IN, 2.187s]: Hair oil ની એક bottle ₹499 ની છે અને face cream ₹599 ની છે. એટલે 2 bottles અને 1 face cream નો total ₹1,597 થશે. Order place કરવો છે તમારે?
- [87.7s] caller: હા, order place કરી દઉં છું. પણ આમાં કોઈ discount જેવી સુવિધા છે ખરી?
- agent [gu-IN, 2.422s]: માફ કરશો, અત્યારે અમારી પાસે કોઈ discount ની માહિતી ઉપલબ્ધ નથી. તો શું આપણે આ order આગળ વધારીએ?
- [103.7s] caller: ઠીક છે, discount નથી તો ચાલશે. તો મારો order confirm કરી દો ને.
- agent [gu-IN, 2.64s]: સારું, હું order confirm કરી દઉં છું. બસ તમારું પૂરું delivery address કહી દો ને, એટલે હું બધું record કરી લઉં.
- [118.9s] caller: સારું, address છે Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- agent [gu-IN, 2.156s]: મેં address note કરી લીધું છે. તો એકવાર confirm કરી દઉં, 2 x Hair Oil અને 1 x Face Cream, total ₹1,597, delivery address Flat 302, Sai Residency, Kukatpally, Hyderabad 500072 સાથે. આ બરાબર છે ને?
- [139.0s] caller: હા, બરાબર છે. આ delivery માં કેટલો time લાગશે?
- agent [gu-IN, 1.875s]: આ delivery માં કેટલો સમય લાગશે, એની માહિતી મારી પાસે અત્યારે ઉપલબ્ધ નથી. Order place કરવો છે તો હું આગળ વધારી શકું છું.
- [157.6s] caller: Delivery નો time ખબર નથી? તો ચાલશે, order place કરી દો. હવે આગળ શું કરવાનું છે એ મને જણાવો.
- agent [gu-IN, 1.875s]: તમારો order confirm થઈ ગયો છે. હવે અમારી team તરફથી તમને આગળની details મળી જશે.

### gu-IN/partially_interested PASS — 97.4s, disposition interested []
- opening: નમસ્તે, હું NatureVeda Herbals માંથી Priya. એક મિનિટ વાત થઈ શકે?
- [10.9s] caller: હા Priya, બોલો. આ Ashwagandha capsules શેના માટે છે? અને એની price કેટલી છે?
- agent [gu-IN, 1.61s]: આ Ashwagandha Capsules એક herbal wellness supplement છે. એની price ₹699 છે 60 capsules માટે. જો તમને કોઈ medical condition હોય કે medications ચાલતા હોય, તો એકવાર healthcare professional ને consult કરી લેવું સારું રહેશે.
- [36.7s] caller: હું blood pressure ની દવા લઉં છું, તો આ મારા માટે safe રહેશે ને? આનાથી stress સાવ મટી જશે? કોઈ guarantee છે ખરી?
- agent [gu-IN, 2.562s]: તમે blood pressure ની દવા લો છો, તો એકવાર તમારા doctor ને પૂછી લેવું સૌથી safe રહેશે. આ capsules થી stress સાવ મટી જશે એવી કોઈ guarantee નથી, અને આ products કોઈ disease cure નથી કરતા કે side effects વગર ના રહેશે એવી ખાતરી પણ નથી આપતાં.
- [61.9s] caller: સારું, સમજી ગઈ. આમાં કોઈ side effects તો નથી ને? અને અત્યારે કોઈ discount કે offer ચાલે છે ખરું?
- agent [gu-IN, 2.328s]: આ products થી કોઈ side effects નથી એવી કોઈ ખાતરી નથી આપી શકાતી, અને medical conditions માટે healthcare professional ની સલાહ લેવી સારી રહેશે. અત્યારે કોઈ discount કે offer ચાલે છે કે નહીં, એની માહિતી મારી પાસે ઉપલબ્ધ નથી.
- [88.4s] caller: અચ્છા, તો અત્યારે કોઈ discount નથી તો કાઈ વાંધો નહીં. હું આ details વિચારીને મારા doctor સાથે વાત કરીશ, પછી જ decide કરીશ.
- agent [gu-IN, 2.422s]: ચોક્કસ, એ જ સૌથી સારું રહેશે. તમે શાંતિથી વિચારીને decide કરી લેજો. પછી કોઈ પણ help જોઈએ તો કહેજો.

### gu-IN/language_switch PASS — 150.7s, disposition not_interested []
- opening: નમસ્તે, હું NatureVeda Herbals માંથી Priya. એક મિનિટ વાત થઈ શકે?
- [14.8s] caller: હા, બોલો ને. મેં તમારું aloe vera juice વિશે સાંભળ્યું હતું, એનું price અને size શું છે? અને એ કેવી રીતે લેવાનું હોય છે?
- agent [gu-IN, 1.719s]: જુઓ, NatureVeda Aloe Vera Juice ની વાત કરું તો, એ 500 ml ની bottle માટે ₹399 માં આવે છે. એમાં ફક્ત Aloe Vera છે અને એને general wellness beverage તરીકે લેવામાં આવે છે. એનો ઉપયોગ કેવી રીતે કરવો એની details અત્યારે મારી પાસે નથી.
- [40.6s] caller: બરાબર, 500 ml માટે 399 rupees. તો આના સિવાય તમારી પાસે કોઈ hair oil છે ખરી? એમાં શું ingredients છે એ જરા કહેશો?
- agent [gu-IN, 1.578s]: હા, અમારી પાસે NatureVeda Herbal Hair Oil પણ છે. એ 200 ml માટે ₹499 માં આવે છે અને એમાં Amla, Bhringraj, Hibiscus અને Coconut Oil છે. તમારે આ order કરવું છે?
- [61.4s] caller: Actually, I would prefer to continue in English now. Can you repeat the aloe vera juice price for me?
- agent [en-IN, 3.875s]: Sure, the NatureVeda Aloe Vera Juice is ₹399 for 500 ml. Which product would you like to explore today?
- [81.5s] caller: Okay, got it. So if I take one aloe vera juice and one hair oil, what will be the total amount?
- agent [en-IN, 2.141s]: One Aloe Vera Juice is ₹399 and one Herbal Hair Oil is ₹499, so the total comes to ₹898. Would you like to place an order today?
- [97.3s] caller: 898 rupees is okay. Do you deliver to Kukatpally, Hyderabad?
- agent [en-IN, 2.5s]: I have noted your enquiry for delivery to Kukatpally, Hyderabad. Regarding delivery, that information is currently unavailable. If you would like to place the order now, just let me know your full delivery address and I will confirm it.
- [122.8s] caller: My address is Flat 302, Sai Residency, Kukatpally, Hyderabad 500072. Can you please check once if you can deliver there?
- agent [en-IN, 2.734s]: I have noted your address as Flat 302, Sai Residency, Kukatpally, Hyderabad 500072. Regarding delivery to that location, that information is currently unavailable.
- [142.9s] caller: Delivery ની કોઈ details નથી? તો પછી અત્યારે order નથી કરવો, thank you.
- agent [en-IN, 2.031s]: I understand. Since the delivery details are currently unavailable, no problem at all.

### ml-IN/callback_language PASS — 108.8s, disposition callback_required []
- opening: നമസ്കാരം, ഞാൻ NatureVeda Herbals-ൽ നിന്ന് Priya. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- [8.2s] caller: അതെ, ഒന്ന് സംസാരിക്കാമല്ലോ. എന്താണ് details?
- agent [ml-IN, 1.266s]: ശരി. ഇന്ന് ഞങ്ങളുടെ കയ്യിൽ herbal products ഉണ്ട്. Hair oil, Aloe Vera Juice, Face Cream, അതോ Ashwagandha Capsules ആണോ?
- [21.4s] caller: ആ aloe vera juice-ന്റെ price എത്രയാണ്?
- agent [ml-IN, 1.375s]: NatureVeda Aloe Vera Juice-ന് 500 ml-ന് ₹399 ആണ് വില. അതൊരു general wellness beverage ആണ്. ഇന്ന് order ചെയ്യണോ?
- [36.6s] caller: 500 ml-ന് 399 രൂപയോ? കുറെ നാളായിട്ട് ഇത് കുടിക്കാൻ നോക്കുന്നുണ്ടായിരുന്നു. ഇതിൽ എന്തെങ്കിലും discount ഉണ്ടോ?
- agent [ml-IN, 1.875s]: ആ വിവരം എനിക്കറിയില്ല.
- [45.9s] caller: ഓ, അങ്ങനെയെങ്കിൽ discount ഒന്നും ഇല്ലാതെ എനിക്കിത് എടുക്കാൻ ബുദ്ധിമുട്ടാകും. വേറെ എന്തെങ്കിലും offers ഉണ്ടോ?
- agent [ml-IN, 1.688s]: നിലവിൽ വേറെ offers ഒന്നും എനിക്ക് പറയാൻ കഴിയില്ല. ആ വിവരം എനിക്കറിയില്ല.
- [57.2s] caller: അങ്ങനെയെങ്കിൽ എനിക്ക് ഇത് വാങ്ങാൻ ബുദ്ധിമുട്ടാണ്. വേറെ products എന്തെങ്കിലും ഉണ്ടോ?
- agent [ml-IN, 1.485s]: തീർച്ചയായും, വേറെ products ഉണ്ട്. ഞങ്ങളുടെ കയ്യിൽ 499 രൂപയുടെ Herbal Hair Oil, 599 രൂപയുടെ Face Cream, പിന്നെ 699 രൂപയുടെ Ashwagandha Capsules എന്നിവയുണ്ട്. ഇതിൽ ഏതാണ് കൂടുതൽ അറിയേണ്ടത്?
- [74.7s] caller: Hair oil-ന്റെ details കൂടി ഒന്ന് പറയാമോ?
- agent [ml-IN, 1.641s]: NatureVeda Herbal Hair Oil-ന് 200 ml-ന് 499 രൂപയാണ് വില. ഇതിൽ Amla, Bhringraj, Hibiscus, പിന്നെ Coconut Oil എന്നിവ അടങ്ങിയിട്ടുണ്ട്. ഇത് routine hair, scalp care-ന് വേണ്ടിയുള്ളതാണ്.
- [100.1s] caller: ശരി, hair oil-ന്റെ details എനിക്ക് കിട്ടി. പക്ഷെ ഇപ്പോൾ എനിക്ക് ഇംഗ്ലീഷിൽ സംസാരിക്കാൻ വലിയ കംഫർട്ടബിൾ അല്ല. ഹിന്ദിയിൽ സംസാരിക്കാൻ കൂടുതൽ എളുപ്പമാണ്. അതുകൊണ്ട് നാളെ രാവിലെ 11 മണിക്ക് എന്നെ ഒന്ന് call ചെയ്യാമോ?
- agent [ml-IN, 1.75s]: തീർച്ചയായും, ഹിന്ദി ഭാഷയിൽ നിങ്ങളെ വീണ്ടും call ചെയ്യാം. നാളെ രാവിലെ 11 മണിക്ക് ഞാൻ ഇത് note ചെയ്തോളാം.

### hi-IN/callback_language PASS — 104.9s, disposition callback_required []
- opening: नमस्ते, मैं प्रिया हूँ NatureVeda Herbals से। क्या आप हमारे हर्बल प्रोडक्ट्स के बारे में जानना चाहते हैं?
- [11.6s] caller: हाँ, बताइए। आपके पास कौन से products हैं?
- agent [hi-IN, 3.391s]: हमारे पास NatureVeda Herbal Hair Oil ₹499 में 200 ml, Aloe Vera Juice ₹399 में 500 ml, Herbal Face Cream ₹599 में 50 g, और Ashwagandha Capsules ₹699 में 60 capsules हैं। क्या आप इनमें से किसी के बारे में और जानना चाहेंगे?
- [34.9s] caller: Aloe Vera Juice का price ठीक है। इसका delivery charge कितना लगेगा?
- agent [hi-IN, 1.328s]: इसकी जानकारी मेरे पास उपलब्ध नहीं है। बाकी products के बारे में कुछ पूछना है?
- [49.6s] caller: ठीक है, कोई बात नहीं। क्या इन products की कोई offer या discount चल रहा है?
- agent [hi-IN, 1.329s]: अभी कोई offer या discount चल रहा है, इसकी जानकारी मेरे पास नहीं है।
- [63.3s] caller: अच्छा, तो अभी कोई offer नहीं है। क्या इन products के ingredients की details मिल सकती हैं?
- agent [hi-IN, 1.516s]: NatureVeda Aloe Vera Juice ₹399 में 500 ml मिलता है और इसमें सिर्फ Aloe Vera है। बाकी products के ingredients की details भी बता दूँ?
- [78.1s] caller: हाँ, बाकी products के ingredients भी बता दीजिए।
- agent [hi-IN, 1.859s]: ठीक है। NatureVeda Herbal Hair Oil में Amla, Bhringraj, Hibiscus और Coconut Oil हैं। क्या आप इनमें से कोई order करना चाहेंगे?
- [96.9s] caller: देखिए, मुझे Telugu ज़्यादा comfortable आती है। क्या आप मुझे कल सुबह 11 बजे call back कर सकते हैं?
- agent [hi-IN, 1.75s]: ज़रूर, हम आपको तेलुगु में वापस call करेंगे। मैंने कल सुबह 11 बजे का callback note कर लिया है।

### ta-IN/callback PASS — 109.5s, disposition callback_required []
- opening: வணக்கம், என் பெயர் ப்ரியா, நேச்சர்வேதா ஹெர்பல்ஸ் நிறுவனத்திலிருந்து பேசுகிறேன். எங்களின் மூலிகை தயாரிப்புகள் மற்றும் அதன் விவரங்களை தெரிந்து கொள்ள உங்களுக்கு இப்போது சிறிது நேரம் கிடைக்குமா?
- [15.8s] caller: ஆமா, சொல்லுங்க. என்ன details இருக்கு?
- agent [ta-IN, 1.562s]: சரி. எங்களோட Herbal Hair Oil 200 ml, விலை 499 ரூபாய்.
- [26.5s] caller: ஓ, 499 rupees ஆ? சரி, இதுல என்னென்ன ingredients இருக்குன்னு சொல்ல முடியுமா?
- agent [ta-IN, 1.453s]: ஆமா, இதுல Amla, Bhringraj, செம்பருத்தி மற்றும் தேங்காய் எண்ணெய் இருக்கு.
- [39.8s] caller: ஓகே, ingredients எல்லாம் நல்லா இருக்கு. இத எப்படி use பண்ணனும்னு கொஞ்சம் சொல்ல முடியுமா?
- agent [ta-IN, 1.844s]: இந்த hair oil-அ வழக்கமா முடி மற்றும் scalp care-க்காக use பண்ணலாம். Exact-ஆ எப்படி apply பண்ணனும்னு எங்க team confirm பண்ணி சொல்லுவாங்க. உங்களுக்கு இந்த product வேணும்னா சொல்லுங்க.
- [58.4s] caller: சரி, அப்போ இத எப்படி use பண்ணனும்னு கொஞ்சம் detail-ஆ சொல்லுங்க.
- agent [ta-IN, 2.375s]: மன்னிக்கவும், இதை எப்படி சரியாக apply பண்ணனும்னு எங்க team தான் confirm பண்ணி சொல்ல முடியும். தற்போதைய விவரப்படி, இது வழக்கமான முடி மற்றும் scalp care-க்காகப் பயன்படுகிறது. இந்த product-க்கு order பதிவு செய்ய வேண்டுமா?
- [80.4s] caller: சரி, அப்போ order பண்ணலாம்னு நினைக்கிறேன். இதோட delivery எப்போ வரும்னு சொல்ல முடியுமா?
- agent [ta-IN, 2.234s]: மன்னிக்கவும், delivery எப்போது வரும் என்ற விவரம் இப்போதைக்கு எங்களிடம் இல்லை. எங்க team அதை confirm பண்ணுவாங்க. Order பண்ணனும்னா சொல்லுங்க, details பதிவு பண்றேன்.
- [102.4s] caller: Sorry, நான் இப்போ work-ல இருக்கேன், ரொம்ப busy-ஆ இருக்கேன். நாளைக்கு evening 6:30-க்கு இதே number-க்கு திரும்ப call பண்ணுங்க. என் பேரு Lakshmi Reddy.
- agent [ta-IN, 1.062s]: (silent)
- farewell: சரி, உங்க callback-ஐ note பண்ணிட்டேன். உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ta-IN/not_interested PASS — 115.2s, disposition not_interested []
- opening: வணக்கம், என் பெயர் ப்ரியா, நேச்சர்வேதா ஹெர்பல்ஸ் நிறுவனத்திலிருந்து பேசுகிறேன். எங்களின் மூலிகை தயாரிப்புகள் மற்றும் அதன் விவரங்களை தெரிந்து கொள்ள உங்களுக்கு இப்போது சிறிது நேரம் கிடைக்குமா?
- [17.5s] caller: சரி, என்ன details-னு சொல்லுங்க. நீங்க என்ன மாதிரி products விக்கிறீங்க?
- agent [ta-IN, 2.344s]: எங்ககிட்ட நேச்சர்வேதா ஹெர்பல் ஹேர் ஆயில் 200 ml வந்து 499 ரூபாய், அலோ வேரா ஜூஸ் 500 ml 399 ரூபாய், ஹெர்பல் ஃபேஸ் கிரீம் 50 கிராம் 599 ரூபாய், அப்புறம் அஸ்வகந்தா காப்ஸ்யூல்கள் 60 எண்ணிக்கை 699 ரூபாய் இருக்கு.
- [40.1s] caller: ஓ, hair oil அப்புறம் face cream-னு சொல்றீங்க. இதெல்லாம் எங்க manufacture ஆகுது? Hyderabad-ல தானா?
- agent [ta-IN, 1.594s]: மன்னிக்கவும், எங்க products எங்க manufacture ஆகுதுன்ற விவரம் எங்களுக்குத் தெரியலை. எங்க team அதை confirm பண்ணுவாங்க. உங்களுக்கு எந்த தயாரிப்பு வேணும்னு சொல்ல முடியுமா?
- [59.4s] caller: ஓ, அவங்க confirm பண்ணுவாங்கனா... சரி. இந்த hair oil-ல என்னென்ன ingredients இருக்குன்னு சொல்ல முடியுமா?
- agent [ta-IN, 1.516s]: அந்த ஹேர் ஆயில்ல ஆம்லா, பிரிங்கராஜ், செம்பருத்தி மற்றும் தேங்காய் எண்ணெய் இருக்கு. இது வழக்கமான முடி மற்றும் தோல் பராமரிப்புக்காக தயாரிக்கப்பட்டது. உங்களுக்கு இதுல எது வேணும்னு சொல்ல முடியுமா?
- [79.3s] caller: சரி, ingredients எல்லாம் நல்லா இருக்க மாதிரி தான் இருக்கு. இதெல்லாம் natural-ஆ தானே?
- agent [ta-IN, 1.203s]: ஆமா, அந்த ingredients எல்லாம் natural-ஆ தான் இருக்கு.
- [89.2s] caller: சரி, natural-ஆ இருந்தா தான் நல்லது. இதோட delivery-க்கு எவ்வளவு time ஆகும்?
- agent [ta-IN, 1.578s]: மன்னிக்கவும், delivery-க்கு எவ்வளவு நேரம் ஆகும்ன்ற விவரம் எங்களுக்குத் தெரியலை. எங்க team அதை confirm பண்ணுவாங்க. உங்களுக்கு எந்த தயாரிப்பு வேணும்னு சொல்ல முடியுமா?
- [110.4s] caller: சரி, அப்போ நான் இப்போதைக்கு எதுவும் வாங்கல. நான் ஏற்கனவே வேற products use பண்ணிட்டு இருக்கேன், so எனக்கு interest இல்ல. நன்றி.
- agent [ta-IN, 1.359s]: (silent)
- farewell: உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.

### ml-IN/not_interested PASS — 102.2s, disposition not_interested []
- opening: നമസ്കാരം, ഞാൻ NatureVeda Herbals-ൽ നിന്ന് Priya. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- [8.9s] caller: ഞാൻ സംസാരിക്കാം. എന്താണ് ഈ NatureVeda Herbals വിൽക്കുന്നത്?
- agent [ml-IN, 1.907s]: ഞങ്ങൾ herbal products ആണ് വിൽക്കുന്നത്. Hair care, wellness juice, face cream, പിന്നെ Ashwagandha capsules ഒക്കെ ഞങ്ങളുടെ കയ്യിലുണ്ട്. ഇതിൽ ഏത് product-നെ കുറിച്ചാണ് കൂടുതൽ അറിയേണ്ടത്?
- [27.5s] caller: Hair care products ആണല്ലേ. ഇത് എവിടെയാണ് manufacture ചെയ്യുന്നത്?
- agent [ml-IN, 1.359s]: ആ വിവരം എനിക്കറിയില്ല. ഇന്ന് ഏതെങ്കിലും product-നെ കുറിച്ച് കൂടുതൽ അറിയണോ?
- [38.2s] caller: ശരി, ഈ hair oil-ൽ എന്തൊക്കെയാണ് അടങ്ങിയിരിക്കുന്നത് എന്ന് പറയാമോ?
- agent [ml-IN, 1.422s]: ഈ NatureVeda Herbal Hair Oil-ൽ Amla, Bhringraj, Hibiscus, പിന്നെ Coconut Oil എന്നിവയാണ് അടങ്ങിയിരിക്കുന്നത്. ഇത് routine hair, scalp care-ന് വേണ്ടിയുള്ളതാണ്. ഇതിന്റെ വില 200 ml-ന് ₹499 ആണ്.
- [56.6s] caller: 499 രൂപയോ? ഇത്രയും വിലയുണ്ടോ ഇതിന്? ഇതിന്റെ delivery എങ്ങനെയാണ്?
- agent [ml-IN, 1.859s]: അതെ, 200 ml-ന് ₹499 ആണ് ഇതിന്റെ വില. Delivery എങ്ങനെയാണ് എന്ന് എനിക്ക് ഇപ്പോൾ പറയാൻ കഴിയില്ല, ആ വിവരം നിലവിൽ ലഭ്യമല്ല.
- [71.2s] caller: Delivery details ഇല്ലാതെ എങ്ങനെയാ വിൽക്കുന്നത്? എനിക്ക് അത്ര വിശ്വാസം വരുന്നില്ല.
- agent [ml-IN, 1.609s]: ആ ബുദ്ധിമുട്ട് എനിക്ക് മനസ്സിലാകുന്നുണ്ട്. നിലവിൽ delivery details എനിക്ക് ലഭ്യമായിട്ടില്ല.
- [83.7s] caller: Delivery details ഇല്ലാതെ എനിക്ക് ഇത് വാങ്ങാൻ പറ്റില്ലല്ലോ. എന്തായാലും കൊള്ളാം.
- agent [ml-IN, 1.344s]: ശരി, മനസ്സിലായി. പിന്നീട് details നോക്കുമ്പോൾ വിളിച്ചാൽ മതിയോ, അതോ ഇപ്പോൾ വേറെ എന്തെങ്കിലും അറിയണോ?
- [98.0s] caller: ഇപ്പോൾ എനിക്ക് ഇതിൽ താല്പര്യമില്ല, കാരണം ഞാൻ ഇതിനകം വേറെ products ഉപയോഗിക്കുന്നുണ്ട്. അതുകൊണ്ട് വേണ്ട കേട്ടോ.
- agent [ml-IN, 0.672s]: (silent)
- farewell: നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.

### ml-IN/language_switch PASS — 121.6s, disposition interested []
- opening: നമസ്കാരം, ഞാൻ NatureVeda Herbals-ൽ നിന്ന് Priya. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- [9.8s] caller: ഒരു മിനിറ്റ് സംസാരിക്കാം. ഈ aloe vera juice-ന്റെ price എത്രയാണ്?
- agent [ml-IN, 1.75s]: NatureVeda Aloe Vera Juice-ന് 500 ml-ന് ₹399 ആണ് വില. ഇതിൽ Aloe Vera ആണ് ഉള്ളത്, ഒരു general wellness beverage ആയിട്ടാണ് ഇത് ഉപയോഗിക്കുന്നത്.
- [25.7s] caller: ശരി, 500 ml-ന് 399 രൂപയോ. ഇതിന്റെ size വേറെ ഉണ്ടോ?
- agent [ml-IN, 1.422s]: ക്ഷമിക്കണം, അതിന്റെ മറ്റ് size options ഇപ്പോൾ എനിക്ക് അറിയില്ല.
- [36.6s] caller: ഓ, ശരി. എങ്കിൽ കുപ്പി കുടിച്ചാൽ എങ്ങനെ ഉപയോഗിക്കണം എന്ന് ഒന്ന് പറയാമോ?
- agent [ml-IN, 1.281s]: Aloe Vera Juice ഒരു general wellness beverage ആയിട്ടാണ് ഉപയോഗിക്കുന്നത്. ഇതിന്റെ കൃത്യമായ usage instructions ഇപ്പോൾ എനിക്ക് അറിയില്ല. ഏത് details ആണ് വേണ്ടത്?
- [58.9s] caller: Actually, I would prefer to continue in English now. Could you please repeat the price of the aloe vera juice you told me earlier?
- agent [en-IN, 2.328s]: Sure, the NatureVeda Aloe Vera Juice is priced at ₹399 for 500 ml. It contains Aloe Vera and is marketed as a general wellness beverage.
- [78.9s] caller: Got it, 399 rupees for 500 ml. Now, could you tell me what ingredients are in your hair oil?
- agent [en-IN, 1.953s]: The NatureVeda Herbal Hair Oil costs ₹499 for 200 ml. It contains Amla, Bhringraj, Hibiscus, and Coconut Oil, and is intended for routine hair and scalp care. Would you like to place an order today?
- [104.2s] caller: Okay, so the hair oil is 499 rupees. What would be the total if I take one juice and one hair oil together?
- agent [en-IN, 1.938s]: One Aloe Vera Juice and one Herbal Hair Oil together would come to ₹898.
- [118.7s] caller: Okay, 898 rupees total. That sounds fine. Thank you for the details, I will think about it.
- agent [en-IN, 0.968s]: Of course — please go ahead.

### kn-IN/interested PASS — 181.9s, disposition converted []
- opening: ನಮಸ್ಕಾರ, ನಾನು NatureVeda Herbals ಇಂದ Priya. ಒಂದು ನಿಮಿಷ ಮಾತನಾಡಬಹುದಾ?
- [10.0s] caller: ನಮಸ್ಕಾರ, ನಾನು ಮಾತಾಡಬಹುದು. ಫಸ್ಟ್ ಟೈಮ್ ಕಾಲ್ ಮಾಡ್ತಿದ್ದೀನಿ, ಇದರ ಬಗ್ಗೆ ಸ್ವಲ್ಪ ತಿಳಿಸಿ.
- agent [kn-IN, 1.516s]: ಖಂಡಿತ, ನಮ್ಮ ಹತ್ರ ನಾಲ್ಕು main products ಇದೆ. Herbal Hair Oil ₹499-ಗೆ 200 ml ಸಿಗುತ್ತೆ, ಅದರಲ್ಲಿ Amla, Bhringraj, Hibiscus ಮತ್ತೆ Coconut Oil ಇದೆ. ನಿಮಗೆ ಯಾವುದರ ಬಗ್ಗೆ ಜಾಸ್ತಿ details ಬೇಕು?
- [28.3s] caller: ಫೇಸ್ ಕ್ರೀಮ್ ಬಗ್ಗೆ ಹೇಳಿ. ಅದರಲ್ಲಿ ಏನೇನಿದೆ ingredients ಅಂತ?
- agent [kn-IN, 3.141s]: ನಮ್ಮ Herbal Face Cream ₹599-ಗೆ 50 g ಸಿಗುತ್ತೆ. ಅದರಲ್ಲಿ Neem, Turmeric, ಮತ್ತೆ Aloe Vera ಇದೆ, ಇದು skin moisturize ಮಾಡೋಕೆ ಮತ್ತೆ routine skin care-ಗೆ ಚೆನ್ನಾಗಿರುತ್ತೆ.
- [48.7s] caller: ಸರಿ, ಈ ingredients ಚೆನ್ನಾಗಿದೆ. ಇದನ್ನ ಹೇಗೆ use ಮಾಡ್ಬೇಕು ಅಂತ ಸ್ವಲ್ಪ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 2.125s]: ಈ Face Cream-ನ ದಿನಾ ಮುಖಕ್ಕೆ ಹಚ್ಚಿಕೊಳ್ಳಬಹುದು, ಇದು moisturizing ಮತ್ತೆ routine skin care-ಗೆ ಸಹಾಯ ಮಾಡುತ್ತೆ.
- [65.3s] caller: ಸರಿ, ಮುಖಕ್ಕೆ ಹಚ್ಚಿಕೊಳ್ಳೋದು ಸುಲಭನೇ. ನಾನು ಒಂದು ಫೇಸ್ ಕ್ರೀಮ್ ತಗೋತೀನಿ, ಜೊತೆಗೆ ಎರಡು ಬಾಟಲ್ ಹೇರ್ ಆಯಿಲ್ ಕೂಡ ಬೇಕಿತ್ತು.
- agent [kn-IN, 2.062s]: ಒಂದು Face Cream ಮತ್ತೆ ಎರಡು Hair Oil bottles. Total ಆಗಿ ₹1497 ಆಗುತ್ತೆ. Order confirm ಮಾಡ್ಲಾ?
- [77.1s] caller: ಓಕೆ, ಟೋಟಲ್ price ಎಷ್ಟು ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.594s]: ಒಂದು Face Cream ಮತ್ತೆ ಎರಡು Hair Oil bottles-ಗೆ total ಆಗಿ ₹1497 ಆಗುತ್ತೆ. Order confirm ಮಾಡ್ಲಾ?
- [92.0s] caller: ಓಕೆ, 1497 rupees ಆ? ತುಂಬಾ thanks. ನನ್ನ order ನ proceed ಮಾಡೋಕೆ details ಬೇಕಾಗುತ್ತೆ, ನಾನು ಹೇಳ್ತೀನಿ.
- agent [kn-IN, 1.562s]: ಹೌದು, total ₹1497 ಆಗುತ್ತೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಹೆಸರು ಮತ್ತೆ delivery address ಹೇಳ್ತೀರಾ? Order place ಮಾಡೋಕೆ ಇದು ಬೇಕಾಗುತ್ತೆ.
- [107.7s] caller: ನನ್ನ ಹೆಸರು Lakshmi Reddy. Address ಬಂದು Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- agent [kn-IN, 3.375s]: ಸರಿ, Lakshmi Reddy ಅವರೇ, ನಿಮ್ಮ address Flat 302, Sai Residency, Kukatpally, Hyderabad 500072. ನಾನು order details ಒಮ್ಮೆ confirm ಮಾಡ್ತೀನಿ. Proceed ಮಾಡ್ಲಾ?
- [126.0s] caller: ಸರಿ, delivery-ಗೆ ಎಷ್ಟು ದಿನ ಆಗುತ್ತೆ? ಏನಾದ್ರೂ discount ಇದ್ರೆ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.765s]: Delivery-ಗೆ ಎಷ್ಟು ದಿನ ಆಗುತ್ತೆ ಅನ್ನೋ ಮಾಹಿತಿ ಸದ್ಯಕ್ಕೆ ಲಭ್ಯವಿಲ್ಲ. Discount ಬಗ್ಗೆ ಕೂಡ ಮಾಹಿತಿ ಇಲ್ಲ.
- [141.8s] caller: ಓಹೋ, delivery time ಅಥವಾ discount details ಇಲ್ಲ ಅಂದ್ರೆ ಸ್ವಲ್ಪ ಕಷ್ಟ ಆಗುತ್ತೆ. ಆದರೂ ಪರವಾಗಿಲ್ಲ, order proceed ಮಾಡೋಣ.
- agent [kn-IN, 3.047s]: ನಿಮ್ಮ order confirm ಆಗಿದೆ. ಸ್ವಲ್ಪ ಹೊತ್ತಲ್ಲೇ ನಿಮಗೆ confirmation details ಬರುತ್ತೆ.
- [154.6s] caller: ಸರಿ, confirmation details ಬಂದ್ಮೇಲೆ ಏನು ಮಾಡ್ಬೇಕು ಅಂತ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 2.125s]: Confirmation details ಬಂದ್ಮೇಲೆ ಅದರಲ್ಲಿ ಇರೋ instructions follow ಮಾಡಿ.
- [166.5s] caller: ಓಕೆ, instructions follow ಮಾಡ್ತೀನಿ. ಅಷ್ಟೇನಾ ಅಥವಾ ಬೇರೆ ಏನಾದ್ರೂ ಇದ್ರೆ ಹೇಳ್ತೀರಾ?
- agent [kn-IN, 1.14s]: ಇವತ್ತು ಬೇರೆ ಏನಾದ್ರೂ products ಬಗ್ಗೆ details ಬೇಕಾ? ಅಥವಾ ಅಷ್ಟೇನಾ?
- [177.7s] caller: ಇಲ್ಲ, ಅಷ್ಟೇ ಸಾಕು. ನೀವು ಬೇರೆ ಏನು ಹೇಳೋದು ಬೇಡ, ನಾನು order confirm ಮಾಡ್ತೀನಿ.
- agent [kn-IN, 0.719s]: (silent)
- farewell: ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.

### ml-IN/interested PASS — 229.2s, disposition converted []
- opening: നമസ്കാരം, ഞാൻ NatureVeda Herbals-ൽ നിന്ന് Priya. ഒരു മിനിറ്റ് സംസാരിക്കാമോ?
- [8.6s] caller: ശരി, പറയൂ. ഞാൻ എന്തായാലും വാങ്ങാൻ നോക്കുന്നുണ്ട്.
- agent [ml-IN, 1.109s]: ഇന്ന് ഏത് product ആണ് നോക്കുന്നത്? ഞങ്ങളുടെ Herbal Hair Oil, Aloe Vera Juice, Face Cream, അതോ Ashwagandha Capsules ആണോ?
- [22.2s] caller: ഫേസ് ക്രീം ഒന്ന് നോക്കാം. ഇതിൽ എന്തൊക്കെ ഇൻഗ്രീഡിയന്റ്സ് ആണുള്ളത്?
- agent [ml-IN, 2.906s]: NatureVeda Herbal Face Cream-ൽ Neem, Turmeric, പിന്നെ Aloe Vera എന്നിവയാണ് ഉള്ളത്. ഇത് moisturizing-നും routine skin care-നും വേണ്ടിയുള്ളതാണ്. ഇന്ന് തന്നെ order ചെയ്യണോ?
- [40.8s] caller: ശരി, ingredients ഒക്കെ നല്ലതാണല്ലോ. ഇത് എങ്ങനെയാണ് use ചെയ്യേണ്ടത്?
- agent [ml-IN, 1.187s]: ക്ഷമിക്കണം, ഈ ഉപയോഗിക്കേണ്ട രീതിയുടെ details ഇപ്പോൾ എന്റെ പക്കൽ ലഭ്യമല്ല. കൂടുതൽ അറിയണമെങ്കിൽ ഒരു healthcare professional-നോട് ചോദിക്കുന്നത് നന്നായിരിക്കും.
- [62.1s] caller: അത് കുഴപ്പമില്ല, ഞാൻ വേറെ എവിടെയെങ്കിലും നോക്കാം. എനിക്ക് ഇപ്പോൾ hair oil കൂടി വേണം, 2 bottles എടുക്കാം, ഒപ്പം ഒരു face cream കൂടി തരൂ.
- agent [ml-IN, 3.125s]: ശരി. അപ്പോൾ 200 ml Herbal Hair Oil രണ്ട് എണ്ണയും, 50 g Herbal Face Cream ഒരു എണ്ണയും എടുക്കുന്നു. ഞാൻ order proceed ചെയ്യട്ടെ?
- [77.3s] caller: ശരി, total price എത്രയാകും എന്ന് പറയാമോ?
- agent [ml-IN, 1.875s]: Herbal Hair Oil-ന് ₹499 ആണ് വില, അപ്പോൾ രണ്ട് എണ്ണയ്ക്ക് ₹998 ആകും. Face Cream-ന് ₹599 ആണ്. Order place ചെയ്യണോ?
- [91.4s] caller: ശരി, അപ്പൊ total ₹1597 ആകും അല്ലേ? ഞാൻ order ചെയ്യാം.
- agent [ml-IN, 2.515s]: അതെ, total ₹1597 ആണ് വരുന്നത്. Order confirm ചെയ്യാൻ നിങ്ങളുടെ പേരും delivery address-ഉം ഒന്ന് പറയാമോ?
- [104.2s] caller: ശരി, പേര് Lakshmi Reddy എന്നാണ്.
- agent [ml-IN, 1.906s]: Lakshmi Reddy. ഇനി delivery address ഒന്ന് പറയാമോ?
- [114.5s] caller: എന്റെ address Flat 302, Sai Residency, Kukatpally, Hyderabad 500072 എന്നാണ്.
- agent [ml-IN, 1.797s]: ശരി, address Flat 302, Sai Residency, Kukatpally, Hyderabad 500072 എന്ന് ഞാൻ note ചെയ്തിട്ടുണ്ട്. അപ്പോൾ 2 Herbal Hair Oil-ഉം 1 Face Cream-ഉം, total ₹1597, Lakshmi Reddy-യുടെ address-ലേക്ക് അയക്കുന്നു. ഞാൻ order confirm ചെയ്യട്ടെ?
- [134.6s] caller: Delivery വരാൻ എത്ര സമയം എടുക്കും? എന്തെങ്കിലും discount ഉണ്ടോ?
- agent [ml-IN, 2.875s]: ആ വിവരം എനിക്കറിയില്ല. Order place ചെയ്യണോ?
- [146.5s] caller: അപ്പൊ discount എന്തെങ്കിലും ഉണ്ടെങ്കിൽ ഒന്ന് നോക്കാമോ? മിക്ക കമ്പനികളും എന്തെങ്കിലും offer കൊടുക്കാറില്ലേ.
- agent [ml-IN, 2.922s]: ആ വിവരം എനിക്കറിയില്ല. Order place ചെയ്യണോ?
- [156.3s] caller: ഓ, മനസ്സിലായി. ശരി, എന്നാൽ order place ചെയ്യാം.
- agent [ml-IN, 2.187s]: Order confirm ആയിട്ടുണ്ട്. ഇനി കുറച്ചു സമയത്തിനുള്ളിൽ details നിങ്ങൾക്ക് കിട്ടും.
- [168.3s] caller: ശരി, അടുത്തത് എന്താ സംഭവിക്കുക എന്ന് ഒന്ന് clear ആക്കാമോ?
- agent [ml-IN, 1.235s]: Order confirm ആയിട്ടുണ്ട്. ഇനി കുറച്ചു സമയത്തിനുള്ളിൽ details നിങ്ങൾക്ക് കിട്ടും.
- [180.3s] caller: ശരി, അപ്പോൾ details എപ്പോഴാ കിട്ടുക എന്ന് കൃത്യമായി ഒന്ന് പറയാമോ?
- agent [ml-IN, 2.313s]: ക്ഷമിക്കണം, കൃത്യമായ സമയം ഇപ്പോൾ പറയാൻ കഴിയില്ല. കുറച്ചു സമയത്തിനുള്ളിൽ details നിങ്ങൾക്ക് കിട്ടും.
- [192.9s] caller: ശരി, അപ്പോൾ ഫോൺ നമ്പർ mohansaiteja.99@gmail.com എന്നാണ്.
- agent [ml-IN, 1.266s]: email mohansaiteja.99@gmail.com എന്ന് ഞാൻ note ചെയ്തിട്ടുണ്ട്.
- [202.5s] caller: ശരി, അപ്പോൾ order എപ്പോഴാ delivery ആവുക?
- agent [ml-IN, 1.453s]: ക്ഷമിക്കണം, കൃത്യമായ സമയം ഇപ്പോൾ പറയാൻ കഴിയില്ല. കുറച്ചു സമയത്തിനുള്ളിൽ details നിങ്ങൾക്ക് കിട്ടും.
- [216.1s] caller: ശരി, മനസ്സിലായി. അപ്പൊ order confirm ആയല്ലോ അല്ലേ? എനിക്ക് വേറെ എന്തെങ്കിലും അറിയാനുണ്ടോ?
- agent [ml-IN, 1.359s]: അതെ, order confirm ആയിട്ടുണ്ട്.
- [225.9s] caller: ശരി, അപ്പൊ order confirm ആയി എന്ന് ഉറപ്പല്ലേ? എനിക്ക് വേറെ എന്തെങ്കിലും അറിയാനുണ്ടോ എന്ന് ചോദിച്ചതാണ്.
- agent [ml-IN, 1.125s]: അതെ, order confirm ആയിട്ടുണ്ട്.

### hi-IN/interested FAIL — 210.8s, disposition converted ['speech_clean']
- opening: नमस्ते, मैं प्रिया हूँ NatureVeda Herbals से। क्या आप हमारे हर्बल प्रोडक्ट्स के बारे में जानना चाहते हैं?
- [16.3s] caller: हाँ प्रिया जी, मुझे हमारे hair oil और face cream के बारे में जानना है। face cream में क्या ingredients हैं?
- agent [hi-IN, 2.203s]: हमारी NatureVeda Herbal Face Cream में Neem, Turmeric और Aloe Vera हैं, और यह ₹599 में 50 g मिलती है moisturizing और routine skin care के लिए। Hair oil के बारे में जानना है तो बताइए।
- [38.8s] caller: Neem और turmeric तो अच्छे हैं, पर face cream को कैसे use करना है, वो भी बता दीजिए।
- agent [hi-IN, 1.391s]: Face cream को कैसे use करना है, इसकी जानकारी मेरे पास नहीं है। बाकी products के बारे में जानना है तो बताइए।
- [54.4s] caller: अरे, ये तो अजीब है। ठीक है, मैं hair oil के बारे में पूछती हूँ।
- agent [hi-IN, 1.922s]: कोई बात नहीं। हमारा NatureVeda Herbal Hair Oil 200 ml का है और इसकी कीमत ₹499 है। इसमें Amla, Bhringraj, Hibiscus और Coconut Oil हैं, जो routine hair and scalp care के लिए अच्छे हैं।
- [80.5s] caller: Amla और bhringraj तो hair के लिए बहुत अच्छे होते हैं। मैं 2 bottles hair oil और 1 face cream order करना चाहती हूँ। Total price कितना होगा?
- agent [hi-IN, 1.968s]: 2 bottles hair oil और 1 face cream का total ₹1,497 बनेगा। क्या मैं order place कर दूँ?
- [94.5s] caller: ठीक है, ₹1,497 ठीक लग रहा है। पर delivery में कितना time लगेगा?
- agent [hi-IN, 1.187s]: इसकी जानकारी मेरे पास उपलब्ध नहीं है। Booking करनी हो तो बता दीजिए।
- [106.3s] caller: Delivery का time नहीं पता? ठीक है, कोई discount वगैरह है क्या?
- agent [hi-IN, 2.453s]: Delivery time की जानकारी मेरे पास नहीं है। Discount के बारे में भी मुझे कोई जानकारी नहीं है। कोई और सवाल हो तो बताइए।
- [123.3s] caller: अच्छा, ठीक है। तो मैं order confirm कर देती हूँ। आगे क्या करना होगा?
- agent [hi-IN, 1.718s]: Order confirm करने के लिए मुझे आपका नाम और delivery address चाहिए होगा। वो बता दीजिए।
- [134.7s] caller: ठीक है, मेरा नाम लक्ष्मी रेड्डी है।
- agent [hi-IN, 1.782s]: ठीक है लक्ष्मी रेड्डी, noted। अब अपना delivery address बता दीजिए।
- [145.6s] caller: Address है Flat 302, Sai Residency, Kukatpally, Hyderabad 500072.
- agent [hi-IN, 1.235s]: address note कर लिया है। तो 2 bottles hair oil और 1 face cream का total ₹1,497 है। क्या मैं order place कर दूँ?
- [157.9s] caller: हाँ, आप order place कर दीजिए।
- agent [hi-IN, 1.609s]: आपका order confirm हो गया है। Team जल्दी ही आपसे contact करेगी।
- [168.5s] caller: ठीक है। मेरे number पर confirmation message आएगा क्या?
- agent [hi-IN, 1.75s]: इसकी जानकारी मेरे पास उपलब्ध नहीं है। Team जल्दी ही आपसे contact करेगी। और कुछ पूछना है तो बताइए।
- [186.2s] caller: ठीक है, confirmation message की जानकारी नहीं है तो कोई बात नहीं। Team जब call करेगी तो मैं details पूछ लूँगी।
- agent [hi-IN, 1.328s]: noted।
- [193.0s] caller: ठीक है प्रिया जी, तो आगे का process क्या रहेगा?
- agent [hi-IN, 1.703s]: Team जल्दी ही आपसे contact करके order की details confirm कर देगी। और कुछ जानकारी चाहिए तो बताइए।
- [206.3s] caller: ठीक है प्रिया जी, process clear है। मैं wait करूँगी।
- agent [hi-IN, 1.078s]: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- FAILED server:speech_clean — t12:no_native_script
