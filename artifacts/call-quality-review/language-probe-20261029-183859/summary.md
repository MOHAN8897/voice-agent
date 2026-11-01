# Language probe language-probe-20261029-183859

Schema `sim_dad6f32e7abe4780a3b0ee8a2afcdb5f`. Caller gpt-5.6-luna, judge gpt-5.5.

| Language | TTS | Pass | Mean score | Lowest dimension |
|---|---|---|---|---|
| te-IN | sarvam | 2/2 | 4.33 | language_fit 4.00 |

## Transcripts

### te-IN/sarvam/numbers (mixed) PASS
- caller: రెండు split ACలు, ఒక window AC service చేస్తే total ఎంత అవుతుంది?
- agent: ఒక split AC కి five hundred ninety nine rupees, అలాగే ఒక window AC కి four hundred ninety nine rupees అవుతుంది. సో, రెండు split ACలు, ఒక window AC కి total one thousand six hundred ninety seven rupees అవుతుంది. మీకు మా team ని visit కి పంపించాలా?
  - checks: hard=[] warn=['over_soft_length:246', 'three_sentences', 'heavy_english_mixing:33/169', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 5, 'correctness': 5, 'helpfulness': 4, 'brevity': 4} — ధరలు, మొత్తం కరెక్ట్‌గా చెప్పారు, Telugu-English mix కూడా ఎక్కువగా సహజంగానే ఉంది. కానీ number readout కొంచెం TTS/English-scriptలా ఉంది, చివర్లో visit question కొద్దిగా sales pushలా వినిపిస్తుంది.
  - [number_or_time_readout] "five hundred ninety nine rupees... four hundred ninety nine rupees... one thousand six hundred ninety seven rupees" → Telugu phone speechలో ‘ఐదు వందల తొంభై తొమ్మిది రూపాయలు’, ‘నాలుగు వందల తొంభై తొమ్మిది’, ‘మొత్తం వెయ్యి ఆరు వందల తొంభై ఏడు’ అని చెప్పడం మరింత సహజం; లేదా ‘five ninety nine’ లాంటి compact readout వాడాలి.
  - [unneeded_sales_push] "మీకు మా team ని visit కి పంపించాలా?" → Caller కేవలం total అడిగారు, కాబట్టి price చెప్పి ఆపడం మంచిది; కావాలంటే చాలా సాఫ్ట్‌గా ‘booking కావాలంటే చెప్పండి’ అనవచ్చు.

### te-IN/sarvam/price (clean) PASS
- caller: స్ప్లిట్ ఏసీ సర్వీసింగ్‌కి ఎంత ఖర్చవుతుంది?
- agent: Split AC servicing కి five hundred ninety nine rupees అవుతుంది. మీకు visit schedule చేయమంటారా?
  - checks: hard=[] warn=['heavy_english_mixing:12/68', 'english_number_words_in_indic_reply']
- judge: {'language_fit': 4, 'human_naturalness': 4, 'register': 4, 'correctness': 5, 'helpfulness': 4, 'brevity': 5} — సమాధానం factually correct and brief. Telugu-English code-mix mostly natural, కానీ number readout కొంచెం TTS/Englishలా ఉంది, అలాగే caller అడగకముందే scheduling push కొద్దిగా అవసరం లేనిది.
  - [number_or_time_readout] "five hundred ninety nine rupees" → తెలుగు కాల్‌లో సహజంగా 'ఐదు వందల తొంభై తొమ్మిది రూపాయలు' లేదా 'ఫైవ్ నైన్టీ నైన్ రూపీస్' అనడం బాగుంటుంది.
  - [unneeded_sales_push] "మీకు visit schedule చేయమంటారా?" → ప్రశ్నకి ధర మాత్రమే అడిగారు; అవసరమైతే 'బుక్ చేయాలంటే చెప్పండి' లాంటి చిన్న optional line సరిపోతుంది, లేక ధర చెప్పి ఆగాలి.
