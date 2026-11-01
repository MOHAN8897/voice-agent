# Agent QA agent-qa-repro-order3

Sessions passed 0/1. Checks passed 17/18 (94.4%).

| Scenario | hi-IN |
|---|---|
| repro_order | FAIL: totals_consistent |

## Session metrics

| Session | Dur s | Turns | Avg first chunk s | Max first chunk s | LLM calls/turn | Max sys prompt chars | Tools |
|---|---|---|---|---|---|---|---|
| hi-IN/repro_order | 114.7 | 6 | 2.07 | 3.42 | 5.2 | 22064 | - |

## Transcripts

### hi-IN/repro_order FAIL — 114.7s, disposition converted ['totals_consistent']
- opening: नमस्ते। मैं प्रिया बोल रही हूँ नेचरवेदा हर्बल्स से। क्या आप हमारे हर्बल प्रोडक्ट्स, जैसे कि हेयर ऑयल, एलोवेरा जूस, फेस क्रीम, या अश्वगंधा कैप्सूल के बारे में जानकारी चाहेंगे?
- [18.0s] caller: नमस्ते प्रिया जी। हाँ, बताइए, आपके पास face cream के बारे में क्या है?
- agent [hi-IN, 2.047s]: हमारी NatureVeda Herbal Face Cream ₹599 में 50 ग्राम की आती है। इसमें Neem, Turmeric, और Aloe Vera हैं, जो moisturizing और routine skin care के लिए अच्छी है। बताइए, आपको इसका order करना है या delivery के बारे में जानना है?
- [41.9s] caller: ठीक है, मैं 2 bottles hair oil और 1 face cream लेना चाहती हूँ, total price कितना हुआ?
- agent [hi-IN, 2.156s]: देखिए, 2 bottles hair oil और 1 face cream का total ₹1497 होगा। Hair oil 499 रुपये per bottle है और face cream 599 रुपये की है। बताइए, order place करना है या delivery details जाननी हैं?
- [61.9s] caller: ठीक है, फिर आप order confirm कर दीजिए, आगे क्या करना होगा?
- agent [hi-IN, 2.125s]: order confirm करने के लिए मुझे आपका नाम और delivery address चाहिए होगा। आप details बता दीजिए, फिर आगे process कर देते हैं।
- [79.3s] caller: मेरा नाम लक्ष्मी रेड्डी है और मेरा एड्रेस है फ्लैट 302, साई रेसिडेंसी, कुकटपल्ली, हैदराबाद 500072।
- agent [hi-IN, 3.422s]: मैंने note कर लिया है। तो confirm कर दूँ — 2 bottles NatureVeda Herbal Hair Oil और 1 NatureVeda Herbal Face Cream, total ₹1497, delivery address flat 302, Sai Residency, Kukatpally, Hyderabad 500072। क्या मैं order place कर दूँ?
- [100.8s] caller: हाँ, सब सही है, order confirm कर दीजिए।
- agent [hi-IN, 2.063s]: आपका order confirm हो गया है। अब बस delivery के लिए team आपसे जल्दी ही संपर्क करेगी।
- [110.7s] caller: ठीक है, धन्यवाद।
- agent [hi-IN, 0.625s]: (silent)
- farewell: समय देने के लिए धन्यवाद। नमस्कार।
- FAILED server:totals_consistent — turns [2]
