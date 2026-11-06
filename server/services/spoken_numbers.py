"""Conservative pre-TTS number expander — leftover digits only, not a rewrite."""
from __future__ import annotations

import re

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

_MOBILE = re.compile(r"(?<!\d)(?:\+91[-\s]?)?(\d{10})(?!\d)")
_CURRENCY_PREFIX = re.compile(r"(?:₹|(?<!\w)(?:rs\.?|inr|రూ\.?))\s*(\d[\d,]*(?:\.\d+)?)", re.I)
_CURRENCY_SUFFIX = re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(?:/[-–—]|రూపాయలు|రూ\b)", re.I)
_USD_PREFIX = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_LAKH_CRORE = re.compile(
    r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(lakh|lakhs|crore|crores)\b",
    re.I,
)
_UNIT_AMOUNT = re.compile(
    r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(paisa|rupees?|rs)\b",
    re.I,
)
_OTP_NEAR = re.compile(
    r"(otp|pin|cvv|passcode|code)\b[^0-9]{0,16}(\d{4,6})(?!\d)",
    re.I,
)
_CLOCK = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?:[ \t]*(am|pm)(?![a-z]))?(?!\d)", re.I)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_LONG_ID = re.compile(r"(?<!\d)(\d{7,9})(?!\d)")
_CARDINAL_RUN = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")
_SKIP_NEAR_PLOT = re.compile(r"\b(plot|flat|unit|block|floor|phase)\s*$", re.I)
# Phone-shaped numbers only: +country formats, 0-prefixed STD landlines and bare
# 10-13 digit runs. The old pattern removed every 5-12 digit run, so order IDs
# ("FC10234" became "FC"), PIN codes and plain amounts ("15000") vanished from
# speech; shorter ids are read digit by digit by _space_id_digits instead.
_PHONE_SPOKEN = re.compile(
    r"(?<![\w-])(?:"
    r"\+\d{1,3}[\s.-]?\(?\d{2,5}\)?(?:[\s.-]?\d{2,5}){1,3}"
    r"|\(?0\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
    r"|\d{10,13}"
    r")(?![\w-])"
)
_PHONE_PHRASE = re.compile(
    r"\b(?:call|phone|mobile|whatsapp|reach)(?:\s+us)?\s+at\s+[\d\s\-+().]{8,}",
    re.I,
)
_BARE_DECIMAL = re.compile(r"(?<!\d)(\d[\d,]*)\.(\d{1,4})(?!\d)")
_ELLIPSIS = re.compile(r"\.{2,}")
_INITIALISM_DOTS = re.compile(r"(?<=\b[A-Za-z])\.(?=[A-Za-z]\b)")
_ABBREV_DOTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bRs\.", re.I), "rupees"),
    (re.compile(r"\bNo\.", re.I), "number"),
    (re.compile(r"\bDr\.", re.I), "Doctor"),
    (re.compile(r"\bMr\.", re.I), "Mister"),
    (re.compile(r"\bMrs\.", re.I), "Missus"),
    (re.compile(r"\bMs\.", re.I), "Miss"),
    (re.compile(r"\bLtd\.", re.I), "Limited"),
    (re.compile(r"\bInc\.", re.I), "Incorporated"),
    (re.compile(r"\bvs\.", re.I), "versus"),
    (re.compile(r"\be\.g\.", re.I), "for example"),
    (re.compile(r"\betc\.", re.I), "etcetera"),
)
_TERMINAL_PUNCT = frozenset(".?!।!?")


def _cardinal_under_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} {_ONES[ones]}"


def cardinal_words(n: int) -> str:
    if n < 0:
        return "minus " + cardinal_words(-n)
    if n < 100:
        return _cardinal_under_100(n)
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        if rest == 0:
            return f"{_ONES[hundreds]} hundred"
        return f"{_ONES[hundreds]} hundred {_cardinal_under_100(rest)}"
    if n < 100_000:
        thousands, rest = divmod(n, 1000)
        head = cardinal_words(thousands) + " thousand"
        return head if rest == 0 else f"{head} {cardinal_words(rest)}"
    if n < 10_000_000:
        lakhs, rest = divmod(n, 100_000)
        head = cardinal_words(lakhs) + " lakh"
        return head if rest == 0 else f"{head} {cardinal_words(rest)}"
    crores, rest = divmod(n, 10_000_000)
    head = cardinal_words(crores) + " crore"
    return head if rest == 0 else f"{head} {cardinal_words(rest)}"


def _decimal_words(raw: str) -> str:
    cleaned = raw.replace(",", "")
    if "." in cleaned:
        whole_s, frac_s = cleaned.split(".", 1)
        whole = int(whole_s or "0")
        frac_s = frac_s[:2]
        if not frac_s or int(frac_s) == 0:
            return cardinal_words(whole)
        return f"{cardinal_words(whole)} point {' '.join(_ONES[int(d)] for d in frac_s)}"
    return cardinal_words(int(cleaned or "0"))


def digit_words(digits: str) -> str:
    return " ".join(_ONES[int(ch)] for ch in digits if ch.isdigit())


def _year_words(year: int) -> str:
    if 2000 <= year <= 2099:
        rest = year - 2000
        if rest == 0:
            return "two thousand"
        if rest < 10:
            return f"two thousand {_ONES[rest]}"
        return f"twenty {_cardinal_under_100(rest)}"
    if 1900 <= year <= 1999:
        rest = year - 1900
        if rest == 0:
            return "nineteen hundred"
        if rest < 10:
            return f"nineteen oh {_ONES[rest]}"
        return f"nineteen {_cardinal_under_100(rest)}"
    return cardinal_words(year)


def _clock_words(hour: int, minute: int, ampm: str) -> str:
    # A bare 8:00 does not specify morning. Preserve that ambiguity; only
    # unmistakable 24-hour values or an explicit suffix determine AM/PM.
    ampm = ampm.upper() or ("PM" if hour > 12 else "AM" if hour == 0 else "")
    hour12 = hour % 12 or 12
    if minute == 0:
        return f"{cardinal_words(hour12)} {ampm}".strip()
    return f"{cardinal_words(hour12)} {cardinal_words(minute)} {ampm}".strip()


def strip_spoken_phone_numbers(text: str) -> str:
    """Remove phone numbers from text before TTS — agents must not speak them."""
    if not text:
        return text
    out = _PHONE_PHRASE.sub("", text)
    out = _MOBILE.sub("", out)
    out = _PHONE_SPOKEN.sub("", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    return out.strip()


def expand_spoken_numbers(text: str) -> str:
    """Expand leftover digit tokens. Leave 'plot 2' and already-spoken words alone."""
    if not text or not any(ch.isdigit() for ch in text):
        return text

    out = _USD_PREFIX.sub(lambda m: f"dollars {_decimal_words(m.group(1))}", text)
    out = _CURRENCY_PREFIX.sub(lambda m: f"rupees {_decimal_words(m.group(1))}", out)
    out = _CURRENCY_SUFFIX.sub(lambda m: f"{_decimal_words(m.group(1))} rupees", out)
    out = _LAKH_CRORE.sub(
        lambda m: f"{_decimal_words(m.group(1))} {'lakh' if m.group(2).lower().startswith('lakh') else 'crore'}",
        out,
    )
    out = _OTP_NEAR.sub(lambda m: f"{m.group(1)} {digit_words(m.group(2))}", out)
    out = _UNIT_AMOUNT.sub(lambda m: f"{_decimal_words(m.group(1))} {m.group(2)}", out)
    out = _CLOCK.sub(
        lambda m: _clock_words(int(m.group(1)), int(m.group(2)), m.group(3) or "")
        + (" " if m.end() < len(out) and out[m.end()].isalpha() else ""),
        out,
    )
    out = _YEAR.sub(lambda m: _year_words(int(m.group(1))), out)
    out = _LONG_ID.sub(lambda m: digit_words(m.group(1)), out)

    def _cardinal_run(m: re.Match[str]) -> str:
        prefix = out[: m.start()]
        if _SKIP_NEAR_PLOT.search(prefix[-24:] if len(prefix) >= 24 else prefix):
            return m.group(1)
        raw = m.group(1)
        if len(raw) == 4 and raw.startswith(("19", "20")):
            return _year_words(int(raw))
        return _decimal_words(raw)

    return _CARDINAL_RUN.sub(_cardinal_run, out)


def sanitize_tts_punctuation(text: str, *, ensure_terminal: bool = True, expand_decimals: bool = True) -> str:
    """
    Prep text for Cartesia Sonic + Sarvam Bulbul.

    Keep sentence punctuation (. ? ! ,) — both engines use it for pacing.
    Only neutralize TTS-hostile dots: ellipses, abbreviations, bare decimals,
    and letter.letter initialism separators.
    """
    if not text:
        return text
    out = _ELLIPSIS.sub(",", text)
    for pat, repl in _ABBREV_DOTS:
        out = pat.sub(repl, out)
    if expand_decimals:
        out = _BARE_DECIMAL.sub(lambda m: _decimal_words(f"{m.group(1)}.{m.group(2)}"), out)
    out = _INITIALISM_DOTS.sub(" ", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.!?।])", r"\1", out)
    out = out.strip(" ,")
    return ensure_terminal_punctuation(out) if ensure_terminal else out


def ensure_terminal_punctuation(text: str) -> str:
    """Cartesia/Sarvam need a terminal . ? or ! for natural end-of-phrase prosody."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    if cleaned[-1] in _TERMINAL_PUNCT:
        return cleaned
    if "?" in cleaned[:-1] and cleaned[-1] not in _TERMINAL_PUNCT:
        # Already asked mid-line — still close the phrase.
        pass
    return cleaned + "."


def provider_normalizes_numbers(provider: str | None, model: str | None) -> bool:
    """Engines that read digits, currency and clock times in the call language themselves.

    Sarvam Bulbul v3/v4 always preprocess numbers and their guide says not to hand-expand
    them; Gemini TTS and Cartesia Sonic (normalization "auto") read digits in-language too.
    """
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip().lower()
    if provider == "sarvam":
        return model.startswith(("bulbul:v3", "bulbul:v4"))
    return provider in {"gemini", "cartesia"}


# --- Entities a digit-reading engine still misreads ------------------------------------
# Measured on Gnani Timbre v3.0 (te-IN, call CC1627 and a direct probe on 6 Nov 2026):
#   "₹85 Lakhs"    -> "85 rupees lakhs"         "₹85,00,000"    -> "85 lakh rupees"
#   "₹1.10 Crore"  -> "1 rupee 10 paise crore"  "₹1,10,00,000"  -> "1 crore 10 lakh rupees"
#   "1,850 Sq.ft." -> unintelligible            "1,850 square feet" -> read correctly
#   "10:30 AM"     -> "10 hours 30 minutes A M" "ఉదయం 10:30"    -> read correctly
# Gnani's and Sarvam's guides both document Indian digit grouping (₹2,40,000), so a
# lakh/crore amount is sent to them as the full grouped number.
_INDIAN_GROUPING_ENGINES = frozenset({"gnani", "sarvam"})
_SCALE_AMOUNT = re.compile(
    r"(?<![\w.])(₹\s*)?(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr)(?![A-Za-z])"
    # "1 crore 10 lakh", "2 lakh 50 thousand": one amount, not two.
    r"(?:\s+(\d[\d,]*)\s*(lakhs?|lacs?|thousand)(?![A-Za-z]))?",
    re.I,
)
_SCALE = {"lakh": 100_000, "lac": 100_000, "crore": 10_000_000, "cr": 10_000_000, "thousand": 1_000}
_UNIT_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])sq\.?\s?(?:ft|feet)(?![A-Za-z])(\.)?", re.I), "square feet"),
    (re.compile(r"(?<=\d)\s?s(?:q)?ft(?![A-Za-z])(\.)?", re.I), " square feet"),
    (re.compile(r"(?<![A-Za-z])sq\.?\s?(?:yds?|yards?)(?![A-Za-z])(\.)?", re.I), "square yards"),
    (re.compile(r"(?<![A-Za-z])sq\.?\s?(?:mtrs?|metres?|meters?|m)(?![A-Za-z])(\.)?", re.I), "square metres"),
)
_AMPM_TIME = re.compile(r"(?<![\d:])(1[0-2]|0?[1-9])(?::([0-5]\d))?\s?([ap])\.?\s?m\.?(?![A-Za-z])", re.I)
#: Morning / afternoon / evening / night as said before a clock time.
_DAY_PART_WORDS: dict[str, tuple[str, str, str, str]] = {
    "te": ("ఉదయం", "మధ్యాహ్నం", "సాయంత్రం", "రాత్రి"),
    "hi": ("सुबह", "दोपहर", "शाम", "रात"),
    "ta": ("காலை", "மதியம்", "மாலை", "இரவு"),
    "kn": ("ಬೆಳಿಗ್ಗೆ", "ಮಧ್ಯಾಹ್ನ", "ಸಂಜೆ", "ರಾತ್ರಿ"),
    "ml": ("രാവിലെ", "ഉച്ചയ്ക്ക്", "വൈകുന്നേരം", "രാത്രി"),
    "mr": ("सकाळी", "दुपारी", "संध्याकाळी", "रात्री"),
    "bn": ("সকাল", "দুপুর", "সন্ধ্যা", "রাত"),
    "gu": ("સવારે", "બપોરે", "સાંજે", "રાત્રે"),
    "pa": ("ਸਵੇਰੇ", "ਦੁਪਹਿਰ", "ਸ਼ਾਮ", "ਰਾਤ"),
}
#: Stems that already name the part of day, so none is added (సాయంత్రానికి, रात को ...).
_DAY_PART_STEMS: dict[str, tuple[str, ...]] = {
    "te": ("ఉదయ", "పొద్దున", "మధ్యాహ్న", "సాయంత్ర", "రాత్రి"),
    "hi": ("सुबह", "सवेरे", "दोपहर", "शाम", "रात"),
    "ta": ("காலை", "மதிய", "மாலை", "இரவு", "ராத்திரி"),
    "kn": ("ಬೆಳಿಗ್ಗೆ", "ಬೆಳಗ್ಗೆ", "ಮಧ್ಯಾಹ್ನ", "ಸಂಜೆ", "ರಾತ್ರಿ"),
    "ml": ("രാവിലെ", "ഉച്ച", "വൈകുന്നേര", "രാത്രി"),
    "mr": ("सकाळ", "दुपार", "संध्याकाळ", "रात्र"),
    "bn": ("সকাল", "দুপুর", "সন্ধ্যা", "বিকেল", "রাত"),
    "gu": ("સવાર", "બપોર", "સાંજ", "રાત"),
    "pa": ("ਸਵੇਰ", "ਦੁਪਹਿਰ", "ਸ਼ਾਮ", "ਰਾਤ"),
}


def indian_grouping(value: int) -> str:
    """12345678 -> "1,23,45,678"."""
    digits = str(abs(int(value)))
    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        grouped = ",".join(([head] if head else []) + parts + [tail])
    return f"-{grouped}" if value < 0 else grouped


def _expand_scale_amounts(text: str) -> str:
    """"₹1.10 Crore" -> "₹1,10,00,000"; a fraction of a rupee keeps the scale word, lower-cased."""
    from decimal import Decimal, InvalidOperation

    def repl(m: re.Match[str]) -> str:
        rupee = "₹" if m.group(1) else ""
        word = m.group(3).lower().rstrip("s")
        try:
            value = Decimal(m.group(2).replace(",", "")) * _SCALE[word]
            if m.group(4):
                second = m.group(5).lower().rstrip("s")
                if _SCALE[second] >= _SCALE[word]:
                    return m.group(0)
                value += Decimal(m.group(4).replace(",", "")) * _SCALE[second]
        except (InvalidOperation, KeyError):
            return m.group(0)
        if value != value.to_integral_value() or m.group(4) and "." in m.group(2):
            return m.group(0) if m.group(4) else f"{rupee}{m.group(2)} {'crore' if word in ('crore', 'cr') else 'lakh'}"
        return f"{rupee}{indian_grouping(int(value))}"

    return _SCALE_AMOUNT.sub(repl, text)


def expand_unit_abbreviations(text: str) -> str:
    """Dotted area units are not read by Indic voices; their English words are."""
    out = text
    for pattern, words in _UNIT_WORDS:
        def repl(m: re.Match[str], words: str = words) -> str:
            # A consumed dot that ends the sentence must still end it.
            tail = "." if m.group(1) and (m.end() >= len(m.string) or m.string[m.end()].isspace()) else ""
            return words + tail
        out = pattern.sub(repl, out)
    return out


def localize_clock_times(text: str, language: str | None) -> str:
    """"10:30 AM" inside an Indic sentence -> "ఉదయం 10:30" (or just "10:30" after సాయంత్రం)."""
    lang = str(language or "").split("-")[0].lower()
    words = _DAY_PART_WORDS.get(lang)
    if not words:
        return text

    def repl(m: re.Match[str]) -> str:
        hour = int(m.group(1))
        clock = f"{hour}:{m.group(2)}" if m.group(2) else str(hour)
        if m.group(3).lower() == "a":
            part = words[0] if 5 <= hour <= 11 else words[3]
        else:
            part = words[1] if hour == 12 or hour <= 3 else words[2] if hour <= 6 else words[3]
        before = m.string[max(0, m.start() - 24):m.start()]
        if any(stem in before for stem in _DAY_PART_STEMS[lang]):
            return clock
        return f"{part} {clock}"

    return _AMPM_TIME.sub(repl, text)


def _space_id_digits(text: str) -> str:
    """OTPs and long reference ids are read digit by digit, never as one big amount."""
    out = _OTP_NEAR.sub(lambda m: f"{m.group(1)} {' '.join(m.group(2))}", text)
    return _LONG_ID.sub(lambda m: " ".join(m.group(1)), out)


def prepare_spoken_reply(
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
    ensure_terminal: bool = True,
) -> str:
    """
    Final pass before TTS: strip phones, then make numbers speakable, keep grammar punctuation.

    English number words are only inserted where nothing better reads them: an engine
    that normalizes digits gets digits, and an Indic call never gets English words
    spliced into its sentence. Only documented cues for Gnani v3 may survive.
    """
    from server.prompts.tts_delivery_rules import sanitize_tts_tags

    cleaned = sanitize_tts_tags(strip_spoken_phone_numbers(text or ""), provider=provider, model=model)
    cleaned = expand_unit_abbreviations(cleaned)
    indic_call = bool(language) and not str(language).lower().startswith("en")
    engine = str(provider or "").strip().lower()
    if provider_normalizes_numbers(provider, model) or (provider and indic_call):
        # "Rs.599" would otherwise become "rupees599" once the abbreviation is spelled out.
        prepared = re.sub(r"\bRs\.?\s*(?=\d)", "₹", cleaned, flags=re.I)
        if indic_call:
            # "599 rupees" makes an Indic voice say the number natively and "rupees" in English;
            # ₹599 is read entirely in the call language.
            prepared = re.sub(r"(?<![\d₹])(\d[\d,]*(?:\.\d+)?)\s*(?:rupees?|rs\b|inr\b)", r"₹\1", prepared, flags=re.I)
        if engine in _INDIAN_GROUPING_ENGINES:
            prepared = _expand_scale_amounts(prepared)
        if indic_call and engine == "gnani":
            prepared = localize_clock_times(prepared, language)
        prepared = _space_id_digits(prepared)
        return sanitize_tts_punctuation(prepared, ensure_terminal=ensure_terminal, expand_decimals=False)
    expanded = expand_spoken_numbers(cleaned)
    return sanitize_tts_punctuation(expanded, ensure_terminal=ensure_terminal)
