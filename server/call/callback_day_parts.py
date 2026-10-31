"""Resolve vague callback times ("tomorrow evening", "రేపు ఈవెనింగ్", "शाम को") to a window.

Callers rarely give a clock time. Telecalling practice turns a day part into a
window and calls near the start of it:

==============  ==============  =====================================
Day part        Default window  Notes
==============  ==============  =====================================
morning         10:00 - 12:00   after people settle in, before lunch
after_lunch     14:00 - 15:00   "after lunch" starts at 14:00
afternoon       14:00 - 16:00   avoids the 12:30 - 14:00 lunch break
end_of_day      17:30 - 18:30   "end of day", "before closing"
evening         17:00 - 19:30
night           19:30 - 20:30   always capped at 21:00
==============  ==============  =====================================

Windows are evaluated in the tenant's follow-up timezone and clipped to the
legal calling hours (TRAI: 09:00 - 21:00 in India). Relative days ("today",
"tomorrow", "day after tomorrow", weekday names, "next week") are understood in
English, Hindi, Telugu and Tamil, in native script and romanised. A phrase with
an explicit clock time ("5 pm", "5 బజే", "மணிக்கு") is left to the exact-time
extractor; this module only handles the vague cases.

Pure functions, no I/O.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Final, Iterable
from zoneinfo import ZoneInfo

DAY_PART_ORDER: Final[tuple[str, ...]] = ("morning", "after_lunch", "afternoon", "end_of_day", "evening", "night")

DEFAULT_DAY_PARTS: Final[dict[str, dict[str, str]]] = {
    "morning": {"start": "10:00", "end": "12:00"},
    "after_lunch": {"start": "14:00", "end": "15:00"},
    "afternoon": {"start": "14:00", "end": "16:00"},
    "end_of_day": {"start": "17:30", "end": "18:30"},
    "evening": {"start": "17:00", "end": "19:30"},
    "night": {"start": "19:30", "end": "20:30"},
}

DAY_PART_LABELS: Final[dict[str, str]] = {
    "morning": "morning", "after_lunch": "after lunch", "afternoon": "afternoon",
    "end_of_day": "end of day", "evening": "evening", "night": "night",
}

#: Legal calling hours by timezone. India: TRAI / TCCCPR 09:00 - 21:00.
LEGAL_CALLING_HOURS: Final[dict[str, tuple[str, str]]] = {
    "Asia/Kolkata": ("09:00", "21:00"),
    "Asia/Calcutta": ("09:00", "21:00"),
}
DEFAULT_LEGAL_HOURS: Final[tuple[str, str]] = ("09:00", "21:00")

#: Minutes of headroom before a window closes for it to still count as "today".
_MIN_LEFT_MINUTES: Final = 20
#: Upper bound on the spread added to a window start so calls don't all fire at :00.
_MAX_SPREAD_MINUTES: Final = 15

# --- Lexicon ----------------------------------------------------------------------------
# Latin entries match on word boundaries; native-script entries are stems matched
# as substrings, so inflected forms (సాయంత్రానికి, शाम को, மாலையில்) still match.
# Ordered most specific first.

_DAY_PART_TERMS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("after_lunch", (
        "after lunch", "post lunch", "post-lunch", "lunch ke baad", "lunch ke bad", "khane ke baad",
        "lunch tarvata", "lunch taruvatha", "lunch taruvata", "bhojanam tarvata", "lunch ku apram", "lunch kku apram",
        "लंच के बाद", "खाने के बाद", "भोजन के बाद",
        "లంచ్ తర్వాత", "లంచ్ తరువాత", "భోజనం తర్వాత", "భోజనం తరువాత", "భోజనం అయ్యాక", "లంచ్ అయ్యాక",
        "மதிய உணவுக்குப் பிறகு", "சாப்பாட்டுக்கு அப்புறம்", "லஞ்ச் அப்புறம்", "லஞ்சுக்கு அப்புறம்",
    )),
    ("end_of_day", (
        "end of day", "end of the day", "eod", "before closing", "closing time", "end of business",
        "दिन खत्म", "दिन के अंत", "ఆఫీస్ అయ్యాక", "ఆఫీసు అయ్యాక",
    )),
    ("night", (
        "tonight", "night", "late evening", "raat", "rat ko", "ratri", "raatri", "rathri", "iravu", "nite",
        "रात", "రాత్రి", "నైట్", "இரவு", "ராத்திரி", "நைட்",
    )),
    ("evening", (
        "evening", "eve", "shaam", "sham", "saam", "sayantram", "saayantram", "sayankalam", "saayankaalam",
        "maalai", "malai", "evng", "evning",
        "शाम", "सायं", "ईवनिंग",
        "సాయంత్ర", "సాయంకాల", "ఈవెనింగ్", "ఈవినింగ్", "ఈవ్నింగ్",
        "மாலை", "சாயங்காலம்", "ஈவினிங்", "ஈவ்னிங்",
    )),
    ("afternoon", (
        "afternoon", "noon", "dopahar", "dopehar", "madhyahnam", "madhyanam", "madhyaanam", "madhiyam", "mathiyam",
        "दोपहर", "आफ्टरनून",
        "మధ్యాహ్న", "ఆఫ్టర్నూన్", "ఆఫ్టర్ నూన్",
        "மதியம்", "மத்தியானம்", "ஆஃப்டர்நூன்",
    )),
    ("morning", (
        "morning", "subah", "subha", "savere", "udayam", "poddunna", "podduna", "kaalai", "kalai",
        "सुबह", "सवेरे", "मॉर्निंग",
        "ఉదయ", "పొద్దున", "మార్నింగ్",
        "காலை", "மார்னிங்",
    )),
)

_DAY_TERMS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("day_after", (
        "day after tomorrow", "parso", "parson", "ellundi", "naalai marunaal", "nalanniki",
        "परसों", "ఎల్లుండి", "நாளை மறுநாள்", "நாளன்னைக்கு", "நாளை மறுதினம்",
    )),
    ("next_week", (
        "next week", "agle hafte", "agle week", "vachhe vaaram", "vache varam", "next vaaram", "adutha vaaram",
        "अगले हफ्ते", "अगले सप्ताह", "वचे वारम", "వచ్చే వారం", "నెక్స్ట్ వీక్", "అடుத்த வாரம்", "அடுத்த வாரம்",
    )),
    ("tomorrow", (
        "tomorrow", "tmrw", "tmr", "tomorow", "kal", "repu", "naalai", "nalai", "naalaikku", "naalaiku",
        "कल", "రేపు", "நாளை", "நாளைக்கு",
    )),
    ("today", (
        "today", "tonight", "aaj", "aj", "ee roju", "eeroju", "inniki", "innaikku", "indru",
        "आज", "ఈ రోజు", "ఈరోజు", "ఇవాళ", "இன்று", "இன்னைக்கு", "இன்னிக்கு",
    )),
)

_WEEKDAY_TERMS: Final[tuple[tuple[int, tuple[str, ...]], ...]] = (
    (0, ("monday", "mon", "somvar", "somvaar", "somavaram", "thingal", "सोमवार", "సోమవార", "திங்கள்")),
    (1, ("tuesday", "tue", "tues", "mangalvar", "mangalvaar", "mangalavaram", "sevvai", "मंगलवार", "మంగళవార", "செவ்வாய்")),
    (2, ("wednesday", "wed", "budhvar", "budhvaar", "budhavaram", "budhan", "बुधवार", "బుధవార", "புதன்")),
    (3, ("thursday", "thu", "thurs", "guruvar", "guruvaar", "guruvaram", "brihaspativar", "viyazhan",
         "गुरुवार", "बृहस्पतिवार", "గురువార", "வியாழன்")),
    (4, ("friday", "fri", "shukravar", "shukravaar", "sukravaram", "velli", "शुक्रवार", "శుక్రవార", "வெள்ளி")),
    (5, ("saturday", "sat", "shanivar", "shanivaar", "shanivaram", "sani", "शनिवार", "శనివార", "சனி")),
    (6, ("sunday", "sun", "ravivar", "ravivaar", "itvaar", "adivaram", "aadivaram", "nyayiru",
         "रविवार", "इतवार", "ఆదివార", "ஞாயிறு")),
)

_NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    "ek|do|teen|char|chaar|paanch|panch|chhe|chhah|saat|aath|nau|das|gyarah|barah|baarah"
)
_EXPLICIT_CLOCK = re.compile(
    r"(\b\d{1,2}[:.]\d{2}\b)"
    r"|(\b\d{1,2}\s*(?:am|pm|a\.m\.?|p\.m\.?|o'?clock|baje|bajey|bje|gantalaku|gantaki|manikku)\b)"
    rf"|(\b(?:{_NUMBER_WORDS})\s+(?:o'?clock|baje|bajey|gantalaku|manikku)\b)"
    r"|(\d{1,2}\s*(?:बजे|గంటలకు|గంటకు|గంటకి|மணிக்கு|மணிக்கு))"
    r"|((?:एक|दो|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस|ग्यारह|बारह)\s*बजे)"
    r"|((?:ఒక|రెండు|మూడు|నాలుగు|ఐదు|ఆరు|ఏడు|ఎనిమిది|తొమ్మిది|పది|పదకొండు|పన్నెండు)\s*గంట)"
    r"|(\b(?:in|after)\s+\d+\s*(?:min|mins|minutes|hour|hours|hrs|hr)\b)",
    re.I,
)


def _is_latin(term: str) -> bool:
    return all(ord(ch) < 0x0250 for ch in term)


def _find(text: str, term: str) -> int:
    """Position of ``term`` in ``text`` or -1. Latin terms need word boundaries."""
    if _is_latin(term):
        match = re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text)
        return match.start() if match else -1
    return text.find(term)


def _first_match(text: str, table: Iterable[tuple[Any, tuple[str, ...]]]) -> tuple[Any, str] | None:
    for key, terms in table:
        for term in terms:
            if _find(text, term) >= 0:
                return key, term
    return None


def has_explicit_clock(text: str) -> bool:
    """True when the caller named a clock time or a relative delay ("5 pm", "in 2 hours")."""
    return bool(_EXPLICIT_CLOCK.search(str(text or "")))


def detect(text: str) -> dict[str, Any] | None:
    """The day part and day a phrase refers to, or None when it names neither."""
    blob = " " + re.sub(r"\s+", " ", str(text or "").casefold()).strip() + " "
    if not blob.strip():
        return None
    part = _first_match(blob, _DAY_PART_TERMS)
    day = _first_match(blob, _DAY_TERMS)
    weekday = None if day else _first_match(blob, _WEEKDAY_TERMS)
    if day and day[1] == "tonight":
        day = ("today", "tonight")
    # "kal"/"aj"/"sat"/"sun" are short; keep them only when a day part or callback context backs them up.
    if day and day[1] in ("kal", "aj", "tmr") and part is None and not re.search(r"call|phone|baat|फोन|कॉल", blob):
        day = None
    if weekday and weekday[1] in ("sat", "sun", "mon", "tue", "wed", "thu", "fri", "sani", "velli") and part is None:
        weekday = None
    if part is None and day is None and weekday is None:
        return None
    return {
        "dayPart": part[0] if part else None,
        "day": day[0] if day else ("weekday" if weekday else None),
        "weekday": weekday[0] if weekday else None,
    }


def _hhmm(value: str) -> time:
    return time.fromisoformat(value)


def normalize_day_parts(day_parts: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    merged = {key: dict(val) for key, val in DEFAULT_DAY_PARTS.items()}
    for key, val in (day_parts or {}).items():
        if key in merged and isinstance(val, dict) and val.get("start") and val.get("end"):
            merged[key] = {"start": str(val["start"]), "end": str(val["end"])}
    return merged


def legal_hours(timezone_name: str) -> tuple[time, time]:
    start, end = LEGAL_CALLING_HOURS.get(timezone_name, DEFAULT_LEGAL_HOURS)
    return _hhmm(start), _hhmm(end)


def _fmt_clock(value: time) -> tuple[str, str]:
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d}", "am" if value.hour < 12 else "pm"


def format_window(day: date, start: time, end: time) -> str:
    """'Sat 31 Oct, 5:00–7:30 pm' / 'Mon 2 Nov, 10:00 am–12:00 pm'."""
    s_clock, s_mer = _fmt_clock(start)
    e_clock, e_mer = _fmt_clock(end)
    head = f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"
    span = f"{s_clock}–{e_clock} {e_mer}" if s_mer == e_mer else f"{s_clock} {s_mer}–{e_clock} {e_mer}"
    return f"{head}, {span}"


def _spread_minutes(key: str, window_minutes: int) -> int:
    cap = max(0, min(_MAX_SPREAD_MINUTES, window_minutes // 4))
    if cap == 0 or not key:
        return 0
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (cap + 1)


def resolve_callback_window(
    text: str,
    *,
    now: datetime,
    timezone_name: str = "Asia/Kolkata",
    day_parts: dict[str, Any] | None = None,
    weekdays: Iterable[int] | None = None,
    spread_key: str = "",
) -> dict[str, Any] | None:
    """A vague callback phrase -> concrete window in ``timezone_name``.

    Returns None when the phrase names no day or day part, names an explicit clock
    time (left to the exact-time extractor), or no legal window exists.
    """
    if not text or has_explicit_clock(text):
        return None
    found = detect(text)
    if not found:
        return None
    zone = ZoneInfo(timezone_name)
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    local_now = now_utc.astimezone(zone)
    parts = normalize_day_parts(day_parts)
    part_key = found["dayPart"] or "morning"
    window = parts[part_key]
    legal_start, legal_end = legal_hours(timezone_name)
    start_t = max(_hhmm(window["start"]), legal_start)
    end_t = min(_hhmm(window["end"]), legal_end)
    if start_t >= end_t:
        return None
    allowed_days = set(weekdays) if weekdays else set(range(7))
    today = local_now.date()
    day_kind = found["day"]
    explicit_day = day_kind in ("tomorrow", "day_after", "weekday", "next_week")

    def passed(on: date) -> bool:
        closes = datetime.combine(on, end_t, tzinfo=zone)
        return local_now >= closes - timedelta(minutes=_MIN_LEFT_MINUTES)

    if day_kind == "tomorrow":
        target = today + timedelta(days=1)
    elif day_kind == "day_after":
        target = today + timedelta(days=2)
    elif day_kind == "weekday":
        ahead = (found["weekday"] - today.weekday()) % 7
        target = today + timedelta(days=ahead)
        if ahead == 0 and passed(target):
            target += timedelta(days=7)
    elif day_kind == "next_week":
        target = today + timedelta(days=7 - today.weekday())
    else:  # "today" or no day: the next window that has not passed.
        target = today
        if passed(target):
            target += timedelta(days=1)
    if not explicit_day:
        for _ in range(7):
            if target.weekday() in allowed_days:
                break
            target += timedelta(days=1)
    elif day_kind == "next_week":
        for _ in range(7):
            if target.weekday() in allowed_days:
                break
            target += timedelta(days=1)

    start_local = datetime.combine(target, start_t, tzinfo=zone)
    end_local = datetime.combine(target, end_t, tzinfo=zone)
    earliest = start_local
    if target == today and local_now > start_local:
        # Already inside today's window: call soon, on a 5-minute boundary.
        bump = local_now + timedelta(minutes=10)
        earliest = bump.replace(minute=(bump.minute // 5) * 5, second=0, microsecond=0)
    window_minutes = int((end_local - earliest).total_seconds() // 60)
    scheduled = earliest + timedelta(minutes=_spread_minutes(spread_key, window_minutes))
    if scheduled >= end_local:
        scheduled = earliest

    day_label = {
        "today": "today", "tomorrow": "tomorrow", "day_after": "day after tomorrow",
        "next_week": "next week", "weekday": target.strftime("%A"),
    }.get(day_kind or "", "")
    if not day_label:
        day_label = "today" if target == today else "tomorrow" if target == today + timedelta(days=1) else target.strftime("%A")
    part_label = DAY_PART_LABELS[part_key] if found["dayPart"] else ""
    if part_key == "night" and day_label == "today" and found["dayPart"]:
        label = "tonight"
    elif day_label == "today" and part_key in ("morning", "afternoon", "evening") and found["dayPart"]:
        label = f"this {part_label}"
    else:
        label = " ".join(x for x in (day_label, part_label) if x).strip()
    display = format_window(target, start_t, end_t)
    return {
        "dayPart": found["dayPart"],
        "day": day_kind,
        "label": label,
        "timezone": timezone_name,
        "start": start_local.astimezone(timezone.utc).isoformat(),
        "end": end_local.astimezone(timezone.utc).isoformat(),
        "scheduledAt": scheduled.astimezone(timezone.utc).isoformat(),
        "display": display,
        "summary": f"{label} → {display}",
    }


def clamp_to_calling_window(
    due_at: datetime,
    *,
    timezone_name: str = "Asia/Kolkata",
    weekdays: Iterable[int] | None = None,
) -> datetime:
    """``due_at`` moved, if needed, to the next legal calling window on an allowed day.

    The last guard before a follow-up is stored: whatever computed the time (a
    window, an extractor, a retry delay), a dial is never queued for 08:04 or
    22:30 local. A time already inside the window is returned unchanged.
    """
    try:
        zone = ZoneInfo(timezone_name or "Asia/Kolkata")
    except Exception:  # noqa: BLE001 - an unknown zone falls back to the platform default.
        zone, timezone_name = ZoneInfo("Asia/Kolkata"), "Asia/Kolkata"
    due = due_at.astimezone(timezone.utc) if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
    start, end = legal_hours(timezone_name)
    allowed = {int(d) for d in weekdays} if weekdays else set(range(7))
    local = due.astimezone(zone)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        opens = datetime.combine(day, start, tzinfo=zone)
        closes = datetime.combine(day, end, tzinfo=zone)
        if offset == 0 and opens <= local < closes:
            return due
        if local < opens:
            return opens.astimezone(timezone.utc)
    return due


def resolve_from_texts(texts: Iterable[str], **kwargs: Any) -> dict[str, Any] | None:
    """First phrase that resolves wins. Pass the most specific text first."""
    for text in texts:
        if text and str(text).strip():
            if has_explicit_clock(text):
                return None
            resolved = resolve_callback_window(str(text), **kwargs)
            if resolved:
                resolved["phrase"] = str(text)[:200]
                return resolved
    return None
