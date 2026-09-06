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
_CURRENCY_PREFIX = re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)", re.I)
_UNIT_AMOUNT = re.compile(
    r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(paisa|rupees?|lakh|lakhs|crore|crores|rs)\b",
    re.I,
)
_OTP_NEAR = re.compile(
    r"(otp|pin|cvv|passcode|code)\b[^0-9]{0,16}(\d{4,6})(?!\d)",
    re.I,
)
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_LONG_ID = re.compile(r"(?<!\d)(\d{7,9})(?!\d)")
_CARDINAL_RUN = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")
_SKIP_NEAR_PLOT = re.compile(r"\b(plot|flat|unit|block|floor|phase)\s*$", re.I)


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
    hour = hour % 24
    if not ampm:
        ampm = "AM" if hour < 12 else "PM"
        hour12 = hour % 12 or 12
    else:
        hour12 = hour % 12 or 12
        ampm = ampm.upper()
    if minute == 0:
        return f"{cardinal_words(hour12)} {ampm}"
    return f"{cardinal_words(hour12)} {cardinal_words(minute)} {ampm}"


def expand_spoken_numbers(text: str) -> str:
    """Expand leftover digit tokens. Leave 'plot 2' and already-spoken words alone."""
    if not text or not any(ch.isdigit() for ch in text):
        return text

    out = _MOBILE.sub(lambda m: digit_words(m.group(1)), text)
    out = _OTP_NEAR.sub(lambda m: f"{m.group(1)} {digit_words(m.group(2))}", out)
    out = _CURRENCY_PREFIX.sub(lambda m: _decimal_words(m.group(1)), out)
    out = _UNIT_AMOUNT.sub(lambda m: f"{_decimal_words(m.group(1))} {m.group(2)}", out)
    out = _CLOCK.sub(
        lambda m: _clock_words(int(m.group(1)), int(m.group(2)), m.group(3) or ""),
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
