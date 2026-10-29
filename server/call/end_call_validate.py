"""Server-side hangup gate — LLM may propose end_call; this decides."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from server.call.call_end_policy import HANGUP_REASONS as POLICY_REASONS
from server.call.call_end_policy import allowed_reasons_for
from server.call.caller_intent import (
    callback_scope_only,
    caller_declined_callback,
    caller_revoked_callback,
    caller_will_contact,
    has_future_interest,
    is_negated_end,
    is_wait_or_continue,
)
from server.call.close_decision import (
    contact_preference_for,
    evidence_matches,
    meaningful_remaining_request,
    opt_out_evidence,
    parse_close_proposal,
)
from server.call.hangup_judge import (
    agent_spoke_closing,
    agent_spoke_disqualification_close,
    agent_spoke_terminal_farewell,
    agent_still_collecting_lead,
    caller_complains_about_repeated_calls,
    caller_negated_refusal,
    caller_polite_thanks_only,
    caller_wants_to_continue,
    default_farewell_for,
    user_short_close_ack,
)
from server.prompts.agent_voice_rules import normalize_compile_language
from server.utils.logger import logger

END_CALL_REASONS = frozenset({"none", *POLICY_REASONS})
HANGUP_REASONS = frozenset(POLICY_REASONS)

_QUESTION_RE = re.compile(
    r"(\?|^(what|why|how|when|where|who|which|can you|could you|would you|"
    r"please tell|tell me|will you|do you|does|did you|are you|is there|"
    r"was there|were you|have you|has your|am i|may i|should i)\b"
    r"|\b(what|why|how|when|where|who|which|price|cost|charges?|fees?)\b"
    r"|^(?:do|does|did|are|is|was|were|will|would|could|should|can|have|has|"
    r"am|may|might)\s+(?:you|your|i|we|they|there|it|this|that|he|she|the|any)\b"
    r"|ఏమిటి|ఎలా|ఎందుకు|కదా\s*\?|ఎంత|ధర|ప్రైసింగ్|ఉన్నాయా|ఉందా|"
    r"చేస్తారా|ఇస్తారా|అవుతుందా|చెప్పగలరా|ఏంటి|ఎప్పుడు|ఎక్కడ|ఎవరు|తీసుకుంటారా|పంపుతారా|చెప్తారా|"
    r"\b(?:enta|entha|ekkada|emiti|enti|enduku|evaru|unda|unnaya|avutunda|chestaara|chestara|cheptara|cheppagalara|tisukuntara)\b|"
    r"क्या|कैसे|क्यों|कितना|कीमत"
    r"|என்ன(?![\u0BBE-\u0BCD])|எப்படி|ஏன்|எப்போது|எங்கே|யார்|எவ்வளவு|"
    r"வேண்டுமா|தெரியுமா|விலை|செய்வீர்களா|உண்டா)",
    re.I,
)
_GOODBYE = re.compile(
    r"\b(bye|goodbye|good night|hang up|hangup|stop calling|"
    r"stop the calls|alvida|call cheyoddu|call cheyaku|call cheyakandi|"
    r"sare\s+unta(?:nu)?|untan(?:u|andi)|unta|"
    r"குட்\s*பை|விடைபெறுகிறேன்|போய்\s*வருகிறேன்|போகிறேன்)\b|"
    r"సరే\s*ఉంటాన(?:ు|ండి)|సరే\s*ఉంటా|ఉంటాన(?:ు|ండి)|ఉంటా\b|"
    r"వద్దు\s*call|కాల్\s*చేయొద్దు|call\s*చేయక|(?:இனி|மீண்டும்).{0,12}(?:அழைக்க|தொடர்பு).{0,12}వేண்டாம்|"
    r"மீண்டும்\s*அழைக்காதீர்கள்|இனி\s*அழைக்காதீர்கள்|இனிமேல்\s*அழைக்காதீர்கள்|இனி\s*call|"
    r"బై(?!క)|బాయ్",  # transliterated bye; never the "బైక్" (bike) prefix
    re.I,
)
# Do not match లేదు inside నచ్చలేదు / కాలేదు, or bare వద్దు in "ఇంకేమీ వద్దు".
_REFUSAL = re.compile(
    r"\b(not interested|no thanks|don't want|do not want|nahi chahiye|"
    r"mat karo|no interest|not for me|no need|remove me|"
    r"don'?t (?:want|need) (?:this|it|any)|stop (?:this|the) call)\b|"
    # Negated identification ("this isn't something I want to pursue") reads as
    # "I want" to the positive-request pattern, so name it as a refusal here.
    r"\b(?:isn'?t|is not|wasn'?t|was not|'s not)\s+(?:really\s+|exactly\s+)?"
    r"(?:something|anything|what)\s+(?:that\s+)?(?:i|we)(?:'m|'re)?\s+"
    r"(?:want|need|like|pursue|interested)\b|"
    r"\b(vaddu|ledu)\b.{0,48}interest|interest.{0,24}\b(vaddu|ledu)\b|"
    r"interest\s*లేదు|ఇంట్రెస్ట్\s*లేదు|"
    r"ఇంట్రెస్ట్(?:\s+\S+){0,2}\s+లేద(?:ు|ండి)|interested\s*nahi|"
    r"లేదు.{0,32}ఇంట్రెస్ట్|ఇంట్రెస్ట్.{0,32}లేదు|"
    r"(?:వద్దు.{0,48}(?:interest|call|ఇంట్రెస్ట్)|(?:interest|call|ఇంట్రెస్ట్).{0,24}వద్దు)|"
    r"दिलचस्पी\s*नहीं|रुचि\s*नहीं|मुझे\s+नहीं\s+चाहिए|नहीं\s*चाहिए|"
    r"விருப்பமில்லை|ஆர்வம்\s*இல்லை|எனக்கு.{0,16}(?:வேண்டாம்|தேவையில்லை)|"
    r"(?:அழைப்பு|கால்).{0,20}(?:வேண்டாம்|தேவையில்லை)|(?:வேண்டாம்|தேவையில்லை).{0,20}(?:அழைப்பு|கால்)|"
    r"(?:இனி|மீண்டும்).{0,16}(?:அழைக்க|தொடர்பு).{0,16}வேண்டாம்",
    re.I | re.S,
)
_ABUSE = re.compile(
    r"\b(kill you|rape|bomb|terrorist)\b",
    re.I,
)
_GOAL_DONE = re.compile(
    r"\b(booked|scheduled|ticket[_ ]?id|order[_ ]?id|confirmed slot|visit booked|"
    r"lead[_ ]?captured|callback[_ ]?scheduled)\b",
    re.I,
)
_STAY_ON_LINE = re.compile(
    r"\b(frustrated|frustrating|explained this|taking too long|"
    r"maybe|think about it|not now|busy|in a meeting|email me|text me|"
    r"call (me )?later|i'll decide|will think|don't have time for (a )?pitch|"
    r"not looking|not in the market|not looking for|"
    r"இன்னும்.{0,16}(?:சொல்லு|விளக்கு|தகவல்)|மேலும்.{0,16}(?:சொல்லு|விளக்கு|தகவல்)|"
    r"தொடர்ந்து.{0,12}சொல்லு|இன்னும்\s*கேட்க|"
    r"और\s*बताइए|आगे\s*बताइए|थोड़ा\s*और\s*बताइए|"
    r"ఇంకా\s*చెప్పండి|మరింత\s*వివరించండి)\b",
    re.I,
)
# Refusing one product while asking about another is a scoped preference, not
# an overall refusal. The contrast marker or the later ask proves the scope.
_CONTRAST = re.compile(
    r"\b(?:but|however|though|although|instead|except)\b|"
    r"(?:किंतु|लेकिन|परन्तु|పర్|కానీ|అయితే|ஆனால்|என்றாலும்)",
    re.I,
)
# Positive asks that keep the conversation open: pricing, details, or wanting
# a named product/service. A refusal next to one of these is not a refusal of
# the call.
_POSITIVE_REQUEST = re.compile(
    r"\b(?:tell|show|send|share|explain|give|quote|provide)\s+(?:me\s+)?"
    r"(?:the\s+)?(?:price|pricing|cost|rate|rates|details?|info|information|"
    r"more|quote|sample|samples)\b|"
    r"\b(?:what(?:'s| is)|how\s+much\s+is)\s+(?:the\s+)?(?:price|cost|rate)\b|"
    r"\b(?:i|we)\s+(?:want|need|would\s+like|'d\s+like)\b|"
    r"\bgo\s+ahead\b|"
    r"(?:చెప్పండి|చెప్పు|వివరాలు|వివరం|ధర|ఎంత|కావాలి|ఇవ్వండి|పంపండి)|"
    r"(?:बताइए|बताओ|विवरण|कीमत|कितना|चाहिए|भेजिए)|"
    r"(?:சொல்லுங்கள்|சொல்லுங்க|விவரம்|விலை|எவ்வளவு|வேண்டும்|அனுப்புங்கள்)",
    re.I,
)
_DONE_WORDS = re.compile(
    r"\b(?:that'?s (?:all|it)|that(?:'s| is) enough|nothing (?:else|more)|"
    r"no more questions|i(?:'m| am) done|we(?:'re| are) done|all good|all set)\b|"
    r"(?:అంతే|ఇంకేమీ\s*లేదు|ఇక\s*చాలు|चाहिए\s*नहीं|और\s*कुछ\s*नहीं|बस\s*इतना|"
    r"அவ்வளவுதான்|இதுவே\s*போதும்|போதும்)",
    re.I,
)
_AFFIRMATIVE_TURN = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|correct|right|ok(?:ay)?|sure|fine|alright|"
    r"అవును|అవునండి|సరే|ओके|हाँ|हां|ठीक|சரி|ஆம்|ஆமாம்)(?:\s*[,.!?]|\s|$)",
    re.I,
)
_THANKS_ONLY = re.compile(
    r"^\s*(?:(?:yeah|yes|ok|okay|sure|fine|alright)[,.]?\s+)?"
    r"(?:thanks?|thank you)(?:\s+so much)?[.!]?\s*$",
    re.I,
)
_CALLER_DONE = re.compile(
    r"^\s*(?:thanks|thank you)[,.]?\s+that'?s (?:all|it)(?:\s+for now)?\b.*"
    r"(?:\bbye\b|\bgoodbye\b)?\s*[.!]?\s*$|"
    r"^\s*that'?s (?:all|it)(?:\s+for now)?(?:[,.]?\s*(?:thanks|thank you))?"
    r"(?:[,.]?\s*(?:bye|goodbye))?\s*[.!]?\s*$|"
    r"^\s*(?:அவ்வளவுதான்|அதுவே\s*போதும்|இதுதான்\s*போதும்)"
    r"(?:\s*[,.]?\s*(?:நன்றி|குட்\s*பை|போகிறேன்|விடைபெறுகிறேன்))?\s*[.!]?\s*$",
    re.I,
)
# Backup hangup (Pass 3): golden substrings + tight negation-near-call/need.
# Not a phrase catalog — add a named pytest when you add a line.
_BACKUP_GOLDEN = (
    "కాల్ అవసరం లేదు",
    "मुझे इसकी जरूरत नहीं है",
    "मुझे इसकी ज़रूरत नहीं है",
)
_BACKUP_STRUCT = re.compile(
    r"కాల్.{0,40}(?:అవసరం|అవసరము).{0,16}లేదు|"
    r"కాల్.{0,16}వద్దు|"
    r"వద్దు.{0,16}కాల్|"
    r"(?:इसकी|इसको|कॉल).{0,16}(?:जरूरत|ज़रूरत).{0,12}नहीं|"
    r"(?:जरूरत|ज़रूरत).{0,12}नहीं.{0,16}(?:कॉल|इसकी)",
    re.I | re.S,
)
_GOAL_COMPLETE_USER = re.compile(
    r"\b(that answers (?:it|my question)|that(?:'s| is) (?:sorted|resolved)|"
    r"i (?:have|got) (?:the|my) answer|i know .{1,40} now|"
    r"that is all i needed|that(?:'s| is) what i needed|"
    r"(?:yes|yeah|ok|okay|sure|fine|please).{0,40}"
    r"(?:call me(?: back)?|team (?:will |can )?call|callback|reach out)|"
    r"(?:call me(?: back)?|callback).{0,20}(?:please|yes|ok|okay)|"
    r"(?:yes|yeah|ok|okay).{0,24}(?:team (?:will |can )?contact|have (?:them|the team) call))\b",
    re.I,
)
_OPT_OUT = re.compile(
    # "Don't call me at night" is a preference, not an opt-out; require finality.
    r"(?:please\s+)?(?:don'?t|do not)\s+(?:ever\s+)?(?:call|contact)(?:\s+me)?"
    r"(?:\s+(?:again|anymore|ever|at\s+all))?\s*[.!]?\s*$|"
    r"(?:please\s+)?(?:don'?t|do not)\s+(?:ever\s+)?(?:call|contact)\s+me\s+(?:again|anymore|ever|at\s+all)\b|"
    r"stop calling|stop the calls|never (?:call|contact)|please stop calling|"
    r"\b(?:you\s+)?(?:don['’]?t|do not)\s+(?:have|need)\s+to\s+(?:call|contact)\s+me\b|"
    r"\b(?:cancel|forget)\s+(?:the |my |that )?callback\b|"
    r"(?:ఈ\s+)?(?:నంబర్|నెంబర్|నంబరు|నెంబరు)(?:కి|కు)?\s*(?:మళ్లీ|మళ్ళీ)?\s*(?:కాల్|ఫోన్)\s*(?:చేయకండి|చేయొద్దు|చేయవద్దు)|"
    r"(?:మళ్లీ|మళ్ళీ|ఇకపై|ఇకమీదట)\s*(?:కాల్|ఫోన్)\s*(?:చేయకండి|చేయొద్దు|చేయవద్దు)|"
    r"(?:నా\s+)?(?:నంబర్|నెంబర్|వివరాలు).{0,20}(?:తీసేయండి|డిలీట్\s*చేయండి|లిస్ట్\s*నుండి\s*తీసేయండి)|"
    r"(?:నన్ను\s+)?(?:మళ్లీ|మళ్ళీ)\s*సంప్రదించ(?:కండి|వద్దు)|"
    r"இனி.{0,16}(?:அழைக்க|தொடர்பு).{0,16}வேண்டாம்|"
    r"(?:இனி|மீண்டும்)\s*அழைக்காதீர்கள்",
    re.I,
)

# Polite requests are grammatically questions, but explicitly end this call.
# "call this call" is a common ASR swap for "cut this call".
_END_REQUEST = re.compile(
    r"\b(?:hang\s*up|hangup)\b|"
    r"\b(?:please\s+)?(?:cut|end|disconnect|stop|close|drop|terminate)\s+"
    r"(?:the |this |our )?(?:call|conversation|line)\b|"
    r"\b(?:can|could|would)\s+you\s+(?:please\s+)?"
    r"(?:cut|end|hang\s*up|disconnect|stop|close|drop)\s+"
    r"(?:the |this |our )?(?:call|conversation|line)?\b|"
    r"\b(?:call|cut)\s+(?:the |this |our )?call\b|"
    r"\bcall\s+(?:cut|band|end)\s*(?:karo|kar do|chey|cheyyi|cheyandi)?\b|"
    # Mixed speech is normal: Latin "call" with a native end verb, sometimes
    # with an adverb between them ("this call, end it now" in the caller's
    # language). The negation guard in caller_explicit_end_request keeps
    # "don't end this call" out.
    r"\bcall\b.{0,20}(?:ముగించండి|ముగించు|కట్\s*చేయండి|ఆపండి|ఆపేయండి)|"
    r"\bcall\b.{0,20}(?:समाप्त\s*(?:कीजिए|करें|करो|कर\s*दीजिए)|बंद\s*(?:कीजिए|करें|करो)|"
    r"काट\s*(?:दीजिए|दें|दो)|खत्म\s*(?:कीजिए|करें|करो))|"
    r"\bcall\b.{0,20}(?:முடிச்சிடுங்க|முடிக்கவும்|முடியுங்க|நிறுத்துங்க|நிறுத்து|முடி)|"
    r"\bcall\b.{0,20}(?:ಮುಗಿಸಿ|ಮುಗಿಸುವುದು|ನಿಲ್ಲಿಸಿ|ಕಡಿತ\s*ಮಾಡಿ|ಮುಗಿಸು)|"
    r"(?:కాల్|ఫోన్)\s*కట్\s*(?:చేయండి|చేసెయ్యండి|చేయి|చెయ్|చేస్తారా|చేస్తావా)|కట్\s*(?:చేయండి|చేసెయ్యండి|చేయి|చెయ్|చేస్తారా|చేస్తావా)\s*(?:కాల్|ఫోన్)|"
    r"(?<!సోది\s)(?<!మాటలు\s)(?:కట్\s*(?:చేయండి|చేసెయ్యండి|చేయి|చెయ్|చేస్తారా|చేస్తావా))|"
    r"(?:కాల్|ఫోన్)\s*.{0,16}(?:కట్|ఆపండి|ఆపేయండి|ముగించండి|ముగించు|పెట్టేయండి)|"
    r"ఫోన్\s*పెట్టేయండి|కాల్\s*పెట్టేయండి|కాల్\s*ఆపేయండి|ఫోన్\s*ఆపేయండి|"
    r"(?:कॉल|फोन)\s*.{0,16}(?:काट|बंद|समाप्त|खत्म\s*कर)|"
    r"(?:कॉल|फोन)\s*.{0,12}(?:समाप्त|खत्म|बंद\s*कर)|"
    r"அழைப்பை\s*.{0,16}(?:முடி|முடிக்கவும்|முடியுங்கள்|முடிங்க|நிறுத்து|நிறுத்தவும்|நிறுத்துங்கள்|நிறுத்துங்க|துண்டிக்கவும்)|"
    r"காலை?\s*.{0,16}(?:கட்\s*பண்ணுங்க|முடி|முடிக்கவும்|நிறுத்து|நிறுத்துங்க)|"
    r"(?:கால்|அழைப்பு).{0,16}(?:முடிச்சிடுங்க|முடிக்கவும்|நிறுத்துங்க)|"
    r"(?:ಕರೆ|ಫೋನ್|ಕಾಲ್).{0,20}(?:ಮುಗಿಸಿ|ಮುಗಿಸುವುದು|ನಿಲ್ಲಿಸಿ|ಕಡಿತ\s*ಮಾಡಿ|ಮುಗಿಸು)",
    re.I,
)
# Caller cannot continue now — close politely (not a callback unless they also asked).
_UNAVAILABLE_NOW = re.compile(
    r"\b(?:i(?:'m| am)\s+(?:going\s+to\s+|gonna\s+|about\s+to\s+)?sleep(?:ing)?(?:\s+now)?|"
    r"going\s+to\s+(?:sleep|bed)|"
    r"i\s+(?:need|have|want|got)\s+to\s+(?:sleep|go\s+to\s+bed)|"
    r"i(?:'m| am)\s+in\s+bed|"
    r"(?:i\s+)?(?:gotta|have\s+to|need\s+to|got\s+to)\s+go(?:\s+now)?"
    r"(?!\s+(?:over|through|into|to\s+(?:the|a|my)))|"
    r"i(?:'ve| have)\s+got\s+to\s+go)\b",
    re.I,
)
_NEGATED_END = re.compile(
    r"\b(?:don'?t|do not|never)\s+(?:hang\s*up|end|cut|disconnect)\b|"
    r"அழைப்பை\s*(?:முடிக்காதீங்க|முடிக்காதீர்கள்|நிறுத்தாதீங்க|நிறுத்தாதீர்கள்)|"
    r"காலை?\s*(?:முடிக்காதீங்க|முடிக்காதீர்கள்|நிறுத்தாதீங்க|நிறுத்தாதீர்கள்)|"
    r"கட்\s*பண்ணாதீங்க",
    re.I,
)
_CALLBACK_REQUEST = re.compile(
    r"\b(?:call|phone|ring)\s+me\s+(?:(?:back|again)\b(?:\s+(?:later|tomorrow))?|"
    r"later\b|tomorrow\b|after\b|next\b|at\s+\d)|"
    r"\b(?:call|phone|ring)\s+me\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
    r"\b(?:contact|reach(?:\s+out)?(?:\s+to)?)\s+me\b(?:\s+(?:back|again|later|tomorrow|tonight|today|after|next|please|on\s+\w+))|"
    r"\bget\s+back\s+to\s+me\b|"
    r"\bfollow\s+up\b(?:\s+with\s+me)?(?:\s+(?:later|tomorrow|next|please))?"
    r"|\bcallback\b(?:\s+(?:later|tomorrow|please|me))?"
    r"|\b(?:repu|tarvata|malli)\b.{0,24}\b(?:call|phone|cheyandi|matladandi)\b|"
    r"(?:రేపు|తర్వాత|మళ్ళీ|మళ్లీ|సాయంత్రం|ఉదయం|మధ్యాహ్నం|రాత్రి).{0,24}(?:కాల్|call|contact|చేయండి|మాట్లాడండి)|"
    r"(?:కాల్|call).{0,24}(?:సాయంత్రం|ఉదయం|మధ్యాహ్నం|రాత్రి)|"
    r"\b(?:saayantram|sayantram|evening|tonight)\s+(?:call|phone)\b|"
    r"(?:कल|बाद में).{0,16}(?:कॉल|फोन|संपर्क)|"
    r"(?:நாளை|பிறகு|பின்னர்|அடுத்த\s*(?:வாரம்|மாதம்)|மாலையில்).{0,20}(?:கால்|அழைக்க|தொடர்பு)|"
    r"(?:கால்|அழைக்க|தொடர்பு).{0,20}(?:நாளை|பிறகு|பின்னர்|அடுத்த\s*(?:வாரம்|மாதம்))",
    re.I,
)
_NEGATED_CALLBACK = re.compile(
    r"\b(?:don'?t|do not|never|cannot|can'?t)\s+(?:you\s+)?(?:call|phone|ring|contact)\s+me|"
    r"\b(?:can|could|should|will)\s+i\s+call\b|"
    r"\bhow\s+(?:can|do|should)\s+i\s+contact\b|"
    r"\bwhat(?:'s| is)\s+(?:your|the)\s+contact\b|"
    r"\b(?:if|whether)\s+you\s+(?:can\s+)?(?:call|contact)\s+me|"
    r"\b(?:before|first).{0,20}(?:tell|explain|answer)|\b(?:tell|explain|answer).{0,30}\bfirst\b|"
    r"(?:callback|call\s*back|కాల్\s*బ్యాక్|కాల్బ్యాక్)\s*(?:వద్దు|వద్దండి|అవసరం\s*లేదు|చేయొద్దు|చేయవద్దు|చేయకండి|అక్కర్లేదు|కాదు)|"
    r"(?:వద్దు|వద్దండి|అవసరం\s*లేదు|అక్కర్లేదు).{0,20}(?:callback|call\s*back|కాల్\s*బ్యాక్|కాల్బ్యాక్)|"
    r"(?:నేను|నేనే|మేము|మేమే).{0,30}(?:call|కాల్|ఫోన్).{0,20}(?:చేస్తాను|చేస్తాం|చేస్తాము|చేసుకుంటాను)|"
    r"(?:ఇది\s+|idi\s+)?(?:callback|కాల్\s*బ్యాక్).{0,20}(?:కాదు|అడగడం\s*లేదు|అడగటం\s*లేదు|అడగడం\s*కాదు|అడగట్లేదు|kaadu|adagadam\s*kaadu)|"
    r"(?:அழைக்க|தொடர்பு\s*கொள்ள).{0,12}வேண்டாம்|அழைக்காதீர்கள்|தொடர்பு\s*கொள்ளாதீர்கள்",
    re.I,
)
_RECORD_DETAILS = re.compile(
    r"\b(?:please\s+)?(?:record|note|save|take|collect|capture|write\s*down|note\s*down)\s+"
    r"(?:down\s+)?(?:my\s+)?(?:name|number|phone|mobile|details|contact|info)\b|"
    r"\b(?:my\s+)?(?:name|phone|number|details)\b.{0,48}\b(?:record|note|save|take|collect)\b|"
    r"(?:పేరు|నంబర్|వివరాలు).{0,24}(?:రాయ|నోట్|తీసుకో)|"
    r"(?:नाम|नंबर|विवरण).{0,24}(?:लिख|नोट|ले\s*लो)|"
    r"(?:என்|என்னுடைய).{0,16}(?:பெயர்|போன்|நம்பர்|எண்).{0,24}(?:பதிவு|குறித்து|எழுதி|சேமி)|"
    r"(?:பெயர்|போன்|நம்பர்|எண்).{0,24}(?:பதிவு|குறித்து|எழுதி|சேமி)",
    re.I,
)
_BARE_NAME_BLOCKLIST = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "no",
        "bye",
        "goodbye",
        "tomorrow",
        "today",
        "tonight",
        "later",
        "please",
        "thanks",
        "thank you",
        "hello",
        "hi",
        "sleeping",
        "sleep",
        "guessing",
        "understood",
        "going",
        "done",
    }
)


def caller_asked_to_record_details(user_text: str) -> bool:
    """Caller asked the agent to take name/phone/details — collect, then close."""
    return bool(_RECORD_DETAILS.search(user_text or ""))


def looks_like_bare_name(user_text: str) -> bool:
    text = re.sub(r"^(?:my name is|this is|i am|i'm|name is)\s+", "", user_text or "", flags=re.I)
    cleaned = text.strip(" .,!?:;")
    if not cleaned or re.search(r"\d", cleaned):
        return False
    if cleaned.lower() in _BARE_NAME_BLOCKLIST:
        return False
    words = cleaned.split()
    return 1 <= len(words) <= 4 and not looks_like_question(cleaned)


def _lead_name_and_phone(user_text: str, memory_snapshot: dict[str, Any] | None) -> tuple[str, str]:
    from server.call.caller_detail_capture import (
        extract_caller_name,
        extract_caller_phone,
        is_usable_lead_name,
        is_usable_lead_phone,
    )

    facts = memory_snapshot.get("facts") if isinstance((memory_snapshot or {}).get("facts"), dict) else {}
    facts = facts or {}
    name = str(
        facts.get("caller_name")
        or facts.get("name")
        or facts.get("customer_name")
        or extract_caller_name(user_text)
        or ""
    ).strip()
    if name and not is_usable_lead_name(name):
        name = ""
    if not name and looks_like_bare_name(user_text):
        stripped = re.sub(
            r"^(?:my name is|this is|i am|i'm|name is)\s+",
            "",
            user_text or "",
            flags=re.I,
        )
        candidate = stripped.strip(" .,!?:;")
        if is_usable_lead_name(candidate):
            name = candidate
    phone = str(
        facts.get("callback_phone")
        or facts.get("phone")
        or facts.get("phone_number")
        or extract_caller_phone(user_text)
        or ""
    ).strip()
    if phone and not is_usable_lead_phone(phone):
        phone = ""
    return name, phone


def memory_with_live_lead(
    memory_snapshot: dict[str, Any] | None, latest_text: str
) -> dict[str, Any]:
    """Copy snapshot facts plus name/phone extracted from the latest utterance."""
    base = dict(memory_snapshot or {})
    facts = dict(base.get("facts") or {}) if isinstance(base.get("facts"), dict) else {}
    name, phone = _lead_name_and_phone(latest_text, {"facts": facts})
    if name:
        facts.setdefault("caller_name", name)
        facts.setdefault("name", name)
    if phone:
        facts.setdefault("callback_phone", phone)
        facts.setdefault("phone", phone)
    base["facts"] = facts
    return base


def callback_ready_to_close(
    user_text: str,
    memory_snapshot: dict[str, Any] | None = None,
    latest_text: str = "",
) -> bool:
    """True when a callback/lead-close can hang up now (details already in, or none were requested)."""
    if not caller_requested_callback(user_text):
        return False
    if not caller_asked_to_record_details(user_text):
        return True
    snap = memory_with_live_lead(memory_snapshot, latest_text or user_text)
    name, phone = _lead_name_and_phone(latest_text or user_text, snap)
    return bool(name and phone)


def caller_requested_callback(user_text: str) -> bool:
    """A direct request to move this conversation to a later call, not a question about callbacks."""
    text = user_text or ""
    if (
        caller_revoked_callback(text)
        or is_negated_end(text)
        or caller_declined_callback(text)
        or callback_scope_only(text)
        or caller_will_contact(text)
    ):
        return False
    if _NEGATED_CALLBACK.search(text) or opt_out_evidence(text):
        return False
    return bool(_CALLBACK_REQUEST.search(text) or _RECORD_DETAILS.search(text))


def caller_explicit_end_request(user_text: str) -> bool:
    text = user_text or ""
    return bool(_END_REQUEST.search(text) and not is_negated_end(text))


def caller_unavailable_now(user_text: str) -> bool:
    """True when the caller is clearly leaving the line (sleeping, have to go)."""
    text = user_text or ""
    if not text.strip() or _NEGATED_END.search(text):
        return False
    if caller_requested_callback(text):
        return False
    return bool(_UNAVAILABLE_NOW.search(text))


@dataclass(frozen=True)
class EndCallDecision:
    accepted: bool
    should_end: bool
    reason: str
    farewell: str
    reject_code: str | None = None
    contact_preference: str = "none"
    #: False only when the model proposed a close without a real caller quote;
    #: such a proposal is a continuation, not a counted close attempt.
    evidence_valid: bool = True


def parse_end_call_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "should_end": False,
            "reason": "none",
            "farewell": "",
            "decision": "continue",
            "evidence": "",
            "remaining_request": "",
            "contact_preference": "",
            "conflict": False,
        }
    proposal = parse_close_proposal(raw)
    reason = str(raw.get("reason") or "none").strip().lower()
    if reason not in END_CALL_REASONS:
        reason = "none"
    return {
        "should_end": proposal.should_end,
        "reason": reason,
        "farewell": proposal.farewell,
        "decision": proposal.decision,
        "evidence": proposal.evidence,
        "remaining_request": proposal.remaining_request,
        "contact_preference": proposal.contact_preference,
        "conflict": proposal.conflict,
    }


_COURTEOUS_CLOSING_CONFIRMATION = re.compile(
    r"^(?:ok(?:ay)?|all\s*right|sure|thanks?|thank\s*you|bye|goodbye|sare(?:na)?|theek\s*hai(?:\s*na)?|alvida|"
    r"ధన్యవాదాలు|సరే(?:నా)?|ఓకే(?:నా)?|ఉంటానండి|వెళ్లొస్తా|சரி|ஆமாம்|ஆம்|நன்றி|விடைபெறுகிறேன்)[\s\?,.!]*$",
    re.I,
)


def looks_like_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # Courteous closing check-ins with question marks (e.g. "సరేనా?", "okay?", "theek hai?")
    # must not be treated as substantive questions that veto hanging up.
    if _COURTEOUS_CLOSING_CONFIRMATION.match(t):
        return False
    return bool(_QUESTION_RE.search(t))


_SUBSTANTIVE_Q = re.compile(
    r"\b(how|what|when|where|why|which|who|price|cost|much)\b",
    re.I,
)


_CB_FULL_REGEX = re.compile(
    r"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:call|phone|ring|contact)(?:\s+me)?(?:\s+back)?(?:\s+(?:again|later|tomorrow|tonight|today|next\s+\w+))?\b|"
    r"\b(?:please\s+)?(?:call|phone|ring|contact|reach\s+out\s+to)\s+me(?:\s+back)?(?:\s+(?:again|later|tomorrow|after|next\b|at\s+\d))?\b|"
    r"(?:రేపు|తర్వాత|మళ్ళీ|మళ్లీ|సాయంత్రం|ఉదయం|నెక్స్ట్\s*(?:మంత్|వీక్)).{0,30}"
    r"(?:కాల్|call|ఫోన్)\s*(?:చేయండి|చేస్తారా|చేస్తావా|చేయగలరా|చేయవచ్చా|చేయొచ్చా|contact)?|"
    r"(?:కాల్|call|ఫోన్)\s*(?:చేస్తారా|చేస్తావా|చేయగలరా|చేయవచ్చా|చేయొచ్చా|చేయండి)|"
    r"\b(?:repu|tarvata|malli)\b.{0,30}\b(?:call|phone|cheyandi|matladandi|chestaara|chestara|cheyagalara)\b|"
    r"\b(?:call|phone|ring)\s+(?:me\s+)?(?:back\s+)?(?:again|later|tomorrow)?\b",
    re.I,
)


def _caller_has_non_callback_question(text: str) -> bool:
    if not looks_like_question(text):
        return False
    stripped = _CB_FULL_REGEX.sub("", text)
    if not re.search(r"\w", stripped):
        return False
    return looks_like_question(stripped)


def _substantive_user_question(text: str) -> bool:
    """True for a real information question — not a short close fragment with a '?'."""
    if caller_wants_to_continue(text):
        return True
    if not looks_like_question(text):
        return False
    return bool(_SUBSTANTIVE_Q.search(text or ""))


def memory_has_goal_complete(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    blobs: list[str] = []
    facts = snapshot.get("facts") or {}
    prefs = snapshot.get("preferences") or {}
    if isinstance(facts, dict):
        for k, v in facts.items():
            blobs.append(f"{k} {v}")
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            blobs.append(f"{k} {v}")
    blobs.append(str(snapshot.get("summary") or ""))
    blobs.append(str(snapshot.get("important_context") or ""))
    joined = " ".join(blobs)
    return bool(_GOAL_DONE.search(joined))


def _evidence_ok(
    reason: str,
    user_text: str,
    *,
    language: str,
    completed_turns: int = 0,
    memory_snapshot: dict[str, Any] | None = None,
    spoken_text: str = "",
) -> bool:
    text = user_text or ""
    spoken = spoken_text or ""
    if reason == "goodbye":
        return bool(
            _GOODBYE.search(text)
            or _OPT_OUT.search(text)
            or caller_complains_about_repeated_calls(text)
            or _CALLER_DONE.search(text)
            or caller_explicit_end_request(text)
            or caller_unavailable_now(text)
        )
    if reason == "firm_refusal":
        return caller_firm_refusal(text)
    if reason == "not_interested":
        return caller_not_interested(text)
    if reason == "abuse":
        return bool(_ABUSE.search(text))
    if reason == "goal_complete":
        if caller_requested_callback(text) and callback_ready_to_close(text, memory_snapshot):
            return True
        if caller_requested_callback(text) and not caller_asked_to_record_details(text):
            return True
        if looks_like_question(text) and _substantive_user_question(text):
            return False
        if looks_like_question(text) and not agent_spoke_closing(spoken):
            return False
        if _GOAL_COMPLETE_USER.search(text) or memory_has_goal_complete(memory_snapshot):
            return True
        # Objective closed only when they confirmed the next step — not okay/thanks, not turn count.
        if (
            agent_spoke_closing(spoken)
            and not caller_wants_to_continue(text)
            and caller_confirmed_goal_complete(text)
        ):
            return True
        if agent_spoke_disqualification_close(spoken) and agent_spoke_closing(spoken):
            return True
        return False
    if reason == "out_of_scope":
        return bool(text.strip()) and not looks_like_question(text) and completed_turns >= 1
    return False


def _trust_live_tool_evidence(
    reason: str,
    user_text: str,
    *,
    memory_snapshot: dict[str, Any] | None = None,
    completed_turns: int = 0,
    spoken_text: str = "",
) -> bool:
    """Accept Live API hangup tool intent; regex evidence is repair-only."""
    text = (user_text or "").strip()
    spoken = spoken_text or ""
    if not text:
        if reason in {"goodbye", "firm_refusal", "not_interested", "abuse"}:
            return True
        if reason == "goal_complete":
            return bool(memory_has_goal_complete(memory_snapshot))
        if reason == "out_of_scope":
            return completed_turns >= 1
        return False
    if caller_negated_refusal(text) and reason in {
        "goodbye", "firm_refusal", "not_interested", "goal_complete",
    }:
        return False
    if caller_wants_to_continue(text):
        if reason == "goal_complete" and agent_spoke_disqualification_close(spoken):
            return True
        return False
    if reason in {"goodbye", "firm_refusal", "not_interested"} and caller_engaged_in_turn(text):
        # A tool call is not consent. An affirmative answer, a question or a
        # request for another product keeps the conversation open.
        return False
    if reason in {"firm_refusal", "not_interested"}:
        return not (user_short_close_ack(text) and not caller_firm_refusal(text))
    if reason == "goodbye":
        return True
    if reason == "abuse":
        return True
    if reason == "goal_complete":
        if agent_spoke_disqualification_close(spoken):
            return True
        if looks_like_question(text) and _substantive_user_question(text):
            return False
        return True
    if reason == "out_of_scope":
        return bool(text) and not looks_like_question(text) and completed_turns >= 1
    return False


def caller_requested_hangup(user_text: str) -> bool:
    """True when the caller explicitly asked to stop / said goodbye."""
    return _user_wants_hangup(user_text)


def caller_backup_end_intent(user_text: str) -> bool:
    """STT-final backup when Live omits request_end_call. Goldens + tight structure only."""
    text = user_text or ""
    if not text.strip() or looks_like_question(text):
        return False
    if _STAY_ON_LINE.search(text):
        return False
    compact = re.sub(r"\s+", " ", text)
    if any(golden in compact for golden in _BACKUP_GOLDEN):
        return True
    return bool(_BACKUP_STRUCT.search(compact))


def caller_stop_contact(user_text: str) -> bool:
    """True only when the caller asked to stop being contacted at all."""
    text = user_text or ""
    if not text.strip():
        return False
    if is_negated_end(text):
        # "Do not cut this call" and "I am not asking you to call me" both
        # contain a call word plus a negative, and mean the opposite.
        return False
    from server.call.close_decision import opt_out_evidence

    matched = _OPT_OUT.search(text)
    if matched and not caller_revoked_callback(matched.group()):
        # "Don't call me again; I'll call you" contains both an explicit
        # opt-out and a withdrawn callback. The independent opt-out still wins.
        return True
    return bool(not caller_revoked_callback(text) and opt_out_evidence(text))


def _scoped_refusal(text: str) -> bool:
    """Refusing one thing while asking for another is not refusing the call."""
    refusal = _REFUSAL.search(text)
    if not refusal or not _POSITIVE_REQUEST.search(text):
        return False
    return bool(_CONTRAST.search(text) or _POSITIVE_REQUEST.search(text[refusal.end():]))


def caller_not_interested(user_text: str) -> bool:
    """A clear refusal that is not an opt-out, an end request, or a deferral."""
    text = user_text or ""
    if not text.strip() or looks_like_question(text):
        return False
    if caller_stop_contact(text) or caller_explicit_end_request(text):
        return False
    if (
        _STAY_ON_LINE.search(text)
        or caller_wants_to_continue(text)
        or caller_negated_refusal(text)
        or caller_revoked_callback(text)
        or has_future_interest(text)
        or _scoped_refusal(text)
    ):
        return False
    return bool(_REFUSAL.search(text) or caller_backup_end_intent(text))


def caller_engaged_in_turn(user_text: str) -> bool:
    """True when the caller's own turn keeps the conversation open.

    A tool call or a model quote is not consent: an affirmative answer, a
    question, or a request for another product's details must not authorize a
    close. Genuine close words, done phrases and polite thanks still do.
    """
    text = (user_text or "").strip()
    if not text:
        return False
    if (
        caller_stop_contact(text)
        or caller_explicit_end_request(text)
        or _user_wants_hangup(text)
        or caller_not_interested(text)
        or _OPT_OUT.search(text)
        or _CALLER_DONE.search(text)
        or _DONE_WORDS.search(text)
        or _THANKS_ONLY.search(text)
    ):
        return False
    if looks_like_question(text) or caller_wants_to_continue(text):
        return True
    if caller_negated_refusal(text):
        return True
    return bool(_POSITIVE_REQUEST.search(text) or _AFFIRMATIVE_TURN.match(text))


def caller_firm_refusal(user_text: str) -> bool:
    """Any clear refusal (not interested or stop-contact); reason choice is separate."""
    return caller_stop_contact(user_text) or caller_not_interested(user_text)


def caller_close_reason(user_text: str) -> str | None:
    """The close reason the caller's own words justify, most specific first."""
    if caller_stop_contact(user_text):
        return "firm_refusal"
    if _user_wants_hangup(user_text):
        return "goodbye"
    if caller_not_interested(user_text):
        return "not_interested"
    return None


def caller_confirmed_goal_complete(user_text: str) -> bool:
    text = user_text or ""
    if not text.strip() or looks_like_question(text):
        return False
    if _STAY_ON_LINE.search(text):
        return False
    return bool(_GOAL_COMPLETE_USER.search(text) or _CALLER_DONE.search(text))


def _user_wants_hangup(user_text: str) -> bool:
    text = user_text or ""
    # Holding the line open outranks every close phrase in the same turn.
    if is_negated_end(text) or is_wait_or_continue(text) or caller_revoked_callback(text):
        return False
    if caller_explicit_end_request(text):
        return True
    if _OPT_OUT.search(text) or _CALLER_DONE.search(text):
        return True
    if caller_complains_about_repeated_calls(text):
        return True
    if caller_requested_callback(text):
        return False
    if caller_unavailable_now(text):
        return True
    if caller_wants_to_continue(text) or caller_negated_refusal(text):
        return False
    if looks_like_question(text):
        return False
    return bool(_GOODBYE.search(text))


def _force_end(
    reason: str,
    farewell: str,
    spoken: str,
    language: str,
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = (farewell or spoken or "").strip() or default_farewell_for(language)
    merged = dict(parsed or {})
    merged.update({"should_end": True, "reason": reason, "farewell": text[:240]})
    return merged


def validate_end_call(
    raw: Any,
    *,
    user_text: str,
    language: str = "te-IN",
    call_status: str | None = "active",
    already_armed: bool = False,
    allowed_reasons: frozenset[str] | None = None,
    barge_in_flight: bool = False,
    last_stt_partial_at: float | None = None,
    now: float | None = None,
    completed_turns: int = 0,
    memory_snapshot: dict[str, Any] | None = None,
    call_end_policy: dict[str, Any] | None = None,
    spoken_text: str = "",
    callback_close_phase: str | None = None,
    tool_sourced: bool = False,
    agent_farewell_ends_call: bool = False,
    classifier_sourced: bool = False,
    pending_tool_result: bool = False,
    action_outcome_unconfirmed: bool = False,
) -> EndCallDecision:
    parsed = parse_end_call_payload(raw)
    user = user_text or ""
    spoken = spoken_text or ""
    lang = normalize_compile_language(language)
    wants_hangup = _user_wants_hangup(user)
    stop_contact = caller_stop_contact(user)
    not_interested = False if (wants_hangup or stop_contact) else caller_not_interested(user)
    firm_refusal = stop_contact or not_interested
    hard_end = wants_hangup or firm_refusal
    agent_concluded = bool(
        agent_farewell_ends_call and parsed.get("should_end")
        and parsed.get("reason") in {"goal_complete", "goodbye"}
        and agent_spoke_terminal_farewell(spoken)
    )
    # Whether this proposal carries proof the server can verify. A close the
    # server established (caller intent, tool call, already-spoken farewell)
    # needs no model quote; a model-proposed close needs one from this turn.
    quoted = bool(
        hard_end
        or agent_concluded
        or tool_sourced
        or evidence_matches(parsed.get("evidence") or "", user)
    )
    if parsed.get("conflict") and not hard_end:
        logger.info("[END_CALL] rejected code=decision_conflict")
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "decision_conflict", evidence_valid=quoted
        )
    if (
        parsed["should_end"]
        and parsed.get("reason") != "abuse"
        and not (wants_hangup or stop_contact)
        and meaningful_remaining_request(parsed.get("remaining_request") or "")
    ):
        # A model note does not outrank the caller's own stop/end request: a
        # rejected close that keeps talking is worse than one leftover note.
        logger.info("[END_CALL] rejected code=remaining_request reason=%s", parsed.get("reason"))
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "remaining_request", evidence_valid=quoted
        )
    if parsed["should_end"] and pending_tool_result and not hard_end:
        # A result the server is still fetching is an unfinished task. A caller's
        # own explicit end still wins; a proposed close waits for the result.
        logger.info("[END_CALL] rejected code=tool_result_pending")
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "tool_result_pending", evidence_valid=quoted
        )
    if parsed["should_end"] and parsed.get("reason") == "goal_complete" and action_outcome_unconfirmed and not hard_end:
        logger.info("[END_CALL] rejected code=action_unconfirmed")
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "action_unconfirmed", evidence_valid=quoted
        )

    # True when the server, not the model, established this close from the
    # caller's own words. Those closes need no model evidence span.
    server_forced = False
    # The caller's own words win over a wrong model reason. Stop-contact stays
    # firm_refusal; a plain decline is not a permanent opt-out.
    if stop_contact:
        parsed = _force_end("firm_refusal", parsed.get("farewell") or "", spoken, lang, parsed)
        server_forced = True
    elif wants_hangup:
        parsed = _force_end("goodbye", parsed.get("farewell") or "", spoken, lang, parsed)
        server_forced = True
    elif not_interested:
        parsed = _force_end("not_interested", parsed.get("farewell") or "", spoken, lang, parsed)
        server_forced = True
    elif agent_still_collecting_lead(spoken) and not (
        (
            (tool_sourced or classifier_sourced)
            and parsed.get("should_end")
            and (
                parsed.get("reason") in {"goodbye", "firm_refusal", "abuse"}
                or classifier_sourced
            )
        )
        or caller_firm_refusal(user)
        or _user_wants_hangup(user)
    ):
        logger.info("[END_CALL] rejected code=lead_details_missing spoken_collecting=1")
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "lead_details_missing", evidence_valid=quoted
        )
    elif caller_requested_callback(user) or callback_close_phase in {
        "collecting_name",
        "collecting_phone",
        "closing_allowed",
    }:
        collecting = callback_close_phase in {"collecting_name", "collecting_phone"}
        if collecting:
            if parsed["should_end"]:
                logger.info("[END_CALL] rejected code=lead_details_missing")
                return EndCallDecision(
                    False, False, "none", parsed.get("farewell") or "", "lead_details_missing", evidence_valid=quoted
                )
        elif callback_close_phase == "closing_allowed" or callback_ready_to_close(user, memory_snapshot):
            if (
                not _caller_has_non_callback_question(user)
                and not meaningful_remaining_request(parsed.get("remaining_request") or "")
                and not caller_wants_to_continue(user)
            ):
                parsed = _force_end("goal_complete", parsed.get("farewell") or "", spoken, lang, parsed)
                server_forced = True
        elif parsed["should_end"] and caller_asked_to_record_details(user):
            logger.info("[END_CALL] rejected code=lead_details_missing")
            return EndCallDecision(
                False, False, "none", parsed.get("farewell") or "", "lead_details_missing", evidence_valid=quoted
            )
    elif parsed["should_end"] and _STAY_ON_LINE.search(user) and not caller_requested_callback(user):
        logger.info("[END_CALL] rejected code=stay_on_line reason=%s", parsed.get("reason"))
        return EndCallDecision(
            False, False, "none", parsed.get("farewell") or "", "stay_on_line", evidence_valid=quoted
        )
    elif (
        parsed["should_end"]
        and caller_wants_to_continue(user)
        and parsed.get("reason") in {"firm_refusal", "not_interested", "goal_complete", "goodbye"}
        and not looks_like_question(user)
        and not caller_firm_refusal(user)
        and not caller_confirmed_goal_complete(user)
        and not _user_wants_hangup(user)
        and not agent_concluded
        and not (
            tool_sourced
            and parsed.get("reason") in {"goal_complete", "firm_refusal", "not_interested", "goodbye"}
            and (
                agent_spoke_disqualification_close(spoken)
                or agent_spoke_closing(spoken)
            )
        )
    ):
        logger.info("[END_CALL] rejected code=caller_engaged reason=%s", parsed.get("reason"))
        return EndCallDecision(False, False, "none", "", "caller_engaged", evidence_valid=quoted)
    elif not parsed["should_end"]:
        if callback_close_phase in {"collecting_name", "collecting_phone"}:
            return EndCallDecision(False, False, "none", "", "lead_details_missing")
        # Repair missed end_call tool when the turn already closed the conversation.
        if (
            (caller_confirmed_goal_complete(user) or _user_wants_hangup(user) or caller_explicit_end_request(user) or caller_firm_refusal(user))
            and (agent_spoke_closing(spoken) or agent_spoke_terminal_farewell(spoken) or parsed.get("farewell"))
        ):
            end_reason = caller_close_reason(user) or (
                "goal_complete" if caller_confirmed_goal_complete(user) else "goodbye"
            )
            parsed = _force_end(end_reason, parsed.get("farewell") or "", spoken, lang, parsed)
            server_forced = True
        # Do not repair hangup from a spoken goodbye plus okay/thanks or turn count.

    if not parsed["should_end"]:
        return EndCallDecision(False, False, "none", "", None)

    reason = parsed["reason"]
    # firm_refusal is reserved for a stop-contact request; any other clear
    # refusal is recorded as not_interested so DNC and reporting stay separate.
    if reason == "firm_refusal" and user.strip() and not caller_stop_contact(user):
        reason = "not_interested"
        parsed["reason"] = reason
    farewell = parsed["farewell"] or spoken or default_farewell_for(lang)

    def _reject(code: str) -> EndCallDecision:
        logger.info("[END_CALL] rejected code=%s reason=%s lang=%s", code, reason, lang)
        return EndCallDecision(
            False, False, reason, farewell, code, evidence_valid=bool(server_forced or quoted)
        )

    if already_armed:
        return _reject("already_armed")
    if barge_in_flight:
        return _reject("barge_in_flight")
    if call_status and call_status != "active":
        return _reject("call_not_active")
    clock = now if now is not None else time.monotonic()
    if (
        not tool_sourced
        and last_stt_partial_at
        and (clock - last_stt_partial_at) < 0.4
    ):
        return _reject("caller_still_talking")
    if reason not in HANGUP_REASONS:
        return _reject("reason_invalid")
    allowed = allowed_reasons if allowed_reasons is not None else allowed_reasons_for(call_end_policy)
    if reason not in allowed:
        return _reject("policy_overlay")
    if not user.strip() and not (tool_sourced and parsed.get("should_end")):
        return _reject("empty_user_turn")
    if user.strip() and looks_like_question(user) and reason != "abuse" and not _user_wants_hangup(user):
        skip_question = (
            agent_concluded
            or (tool_sourced and reason == "goal_complete" and agent_spoke_disqualification_close(spoken))
            or (caller_requested_callback(user) and not _caller_has_non_callback_question(user))
        )
        if not skip_question and not (_OPT_OUT.search(user) or _CALLER_DONE.search(user)
                or caller_explicit_end_request(user)
                or caller_unavailable_now(user)):
            return _reject("user_asked_question")
    if (
        looks_like_question(spoken)
        and reason == "goal_complete"
        and not classifier_sourced
        and not _user_wants_hangup(user)
        and not caller_firm_refusal(user)
    ):
        return _reject("open_question")
    if not (server_forced or quoted):
        # Evidence proves intent; it is not decoration. A proposal that does not
        # quote the caller's current turn is a continuation, not a close attempt.
        logger.info("[END_CALL] rejected code=evidence_not_quoted reason=%s", reason)
        return EndCallDecision(False, False, "none", "", "evidence_not_quoted", evidence_valid=False)
    # The model's evidence span is semantic evidence: it must be the caller's own
    # words and must not contain a request to keep talking. This is what lets a
    # valid refusal in an unlisted phrasing close without a phrase-list match.
    semantic_close = bool(
        reason in {"firm_refusal", "not_interested", "goodbye"}
        and parsed.get("evidence")
        and evidence_matches(parsed.get("evidence") or "", user)
        and not caller_wants_to_continue(user)
        and not caller_negated_refusal(user)
        and not caller_polite_thanks_only(user)
        and not caller_engaged_in_turn(user)
        and not meaningful_remaining_request(parsed.get("remaining_request") or "")
    )
    # The dedicated close step reads meaning in any language and quotes the
    # caller. The server still requires that quote to be present in this turn
    # and every factual veto above to pass; no phrase list is consulted.
    classifier_close = bool(
        classifier_sourced
        and parsed["should_end"]
        and reason in {"goal_complete", "goodbye", "not_interested", "firm_refusal", "abuse"}
        and evidence_matches(parsed.get("evidence") or "", user)
        and not caller_wants_to_continue(user)
        and not caller_negated_refusal(user)
        and not meaningful_remaining_request(parsed.get("remaining_request") or "")
        and not (
            caller_polite_thanks_only(user)
            and not agent_concluded
            and not agent_spoke_closing(spoken)
            and not caller_confirmed_goal_complete(user)
        )
    )
    evidence_ok = agent_concluded or classifier_close or semantic_close or (
        _trust_live_tool_evidence(
            reason,
            user,
            memory_snapshot=memory_snapshot,
            completed_turns=completed_turns,
            spoken_text=spoken,
        )
        if tool_sourced and parsed.get("should_end")
        else _evidence_ok(
            reason,
            user,
            language=lang,
            completed_turns=completed_turns,
            memory_snapshot=memory_snapshot,
            spoken_text=spoken,
        )
    )
    if not evidence_ok:
        return _reject("no_evidence")
    if len(farewell) > 240:
        return _reject("farewell_too_long")

    contact_preference = contact_preference_for(
        parsed.get("contact_preference") or "",
        reason=reason,
        user_text=user,
        evidence=parsed.get("evidence") or "",
        # caller_stop_contact already applies the negation/scoped-refusal guards
        # and reads the native opt-out phrases, so a server-forced close keeps
        # the caller's real do-not-call request.
        opt_out_matched=stop_contact,
        callback_requested=caller_requested_callback(user),
    )
    return EndCallDecision(True, True, reason, farewell, None, contact_preference)
