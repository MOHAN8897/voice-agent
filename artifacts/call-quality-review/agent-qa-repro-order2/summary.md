# Agent QA agent-qa-repro-order2

Sessions passed 0/1. Checks passed 16/17 (94.1%).

| Scenario | hi-IN |
|---|---|
| repro_order | FAIL: order_recorded |

## Session metrics

| Session | Dur s | Turns | Avg first chunk s | Max first chunk s | LLM calls/turn | Max sys prompt chars | Tools |
|---|---|---|---|---|---|---|---|
| hi-IN/repro_order | 92.4 | 6 | 2.04 | 2.88 | 5.0 | 22723 | - |

## Transcripts

### hi-IN/repro_order FAIL — 92.4s, disposition qualified ['order_recorded']
- opening: नमस्ते। मैं प्रिया हूँ NatureVeda Herbals से। क्या आप हमारे herbal products के बारे में कुछ जानकारी चाहते हैं?
- [13.7s] caller: नमस्ते प्रिया जी। हाँ, बताइए, आपके पास face cream के बारे में क्या है?
- agent [hi-IN, 2.39s]: हमारी NatureVeda Herbal Face Cream ₹599 की है 50 g के लिए, और इसमें Neem, Turmeric, और Aloe Vera होते हैं। यह moisturizing और routine skin care के लिए है। अगर आपको order करना हो तो बता दीजिए।
- [36.7s] caller: ठीक है, मैं 2 bottles hair oil और 1 face cream लेना चाहती हूँ, total price कितना हुआ?
- agent [hi-IN, 2.312s]: Hair oil ₹499 का है 200 ml के लिए, तो 2 bottles ₹998 की होंगी। Face cream ₹599 की है। क्या आप इसका order देना चाहेंगी?
- [52.6s] caller: ठीक है, फिर आप order confirm कर दीजिए, आगे क्या करना होगा?
- agent [hi-IN, 1.984s]: Order confirm करने के लिए मुझे आपका नाम और delivery address चाहिए होगा। वो बता दीजिए?
- [67.4s] caller: मेरा नाम लक्ष्मी रेड्डी है और मेरा एड्रेस है फ्लैट 302, साई रेसिडेंसी, कुकटपल्ली, हैदराबाद 500072।
- agent [hi-IN, 2.875s]: तो आपका नाम लक्ष्मी रेड्डी है और आपका पता फ्लैट 302, साई रेसिडेंसी, कुकटपल्ली, हैदराबाद 500072 है, ठीक है?
- [81.4s] caller: हाँ, सब सही है, order confirm कर दीजिए।
- agent [hi-IN, 1.719s]: तो मैं आपका order confirm कर दूँ, है ना?
- [88.0s] caller: ठीक है, धन्यवाद।
- agent [hi-IN, 0.954s]: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- FAILED server:order_recorded — None
