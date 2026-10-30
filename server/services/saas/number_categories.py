"""Classify catalog phone numbers as mobile, landline, toll-free or other.

Vobiz's inventory API has no number-type field (see the PhoneNumber object:
https://www.vobiz.ai/docs/account-phone-number/account-phone-number-object.md).
Each row carries only ``e164``, ``country``, a free-text ``region`` and the
``aadhaar_verification_required`` flag. The type therefore comes from the
national numbering plan applied to the E.164 number, with Vobiz's ``region``
as a tie-breaker:

* India geographic (landline) numbers are an STD area code followed by the
  subscriber number, 10 digits in all: +91 80 xxxx xxxx is Bengaluru (STD 080),
  +91 79 xxxx xxxx is Ahmedabad (STD 079). Vobiz labels these with the state
  name in ``region`` ("Karnataka", "Gujarat").
* India mobile-series numbers are 10 digits starting 6-9. Vobiz stocks these as
  a series and says so in ``region`` ("92 Series").
* India toll-free numbers start 1800 after the country code. Shared-cost 1860
  and the regulated 140 / 1600 series are listed as "other".

Nothing here is a guess dressed up as fact: a number that matches no rule is
"other", and a landline whose STD code is not in the table keeps the carrier's
region as its area instead of an invented city.
"""
from __future__ import annotations

import re
from typing import Any

CATEGORIES: tuple[str, ...] = ("mobile", "landline", "toll_free", "other")

CATEGORY_LABELS: dict[str, str] = {
    "mobile": "Mobile",
    "landline": "Landline",
    "toll_free": "Toll-free",
    "other": "Other",
}

# STD code (without the trunk 0) -> (city, state). Longest prefix wins, so a
# 3-digit code is checked before the 2-digit metro codes.
INDIA_STD_CODES: dict[str, tuple[str, str]] = {
    "11": ("Delhi", "Delhi"),
    "20": ("Pune", "Maharashtra"),
    "22": ("Mumbai", "Maharashtra"),
    "33": ("Kolkata", "West Bengal"),
    "40": ("Hyderabad", "Telangana"),
    "44": ("Chennai", "Tamil Nadu"),
    "79": ("Ahmedabad", "Gujarat"),
    "80": ("Bengaluru", "Karnataka"),
    "120": ("Noida and Ghaziabad", "Uttar Pradesh"),
    "124": ("Gurugram", "Haryana"),
    "129": ("Faridabad", "Haryana"),
    "135": ("Dehradun", "Uttarakhand"),
    "141": ("Jaipur", "Rajasthan"),
    "160": ("Mohali", "Punjab"),
    "161": ("Ludhiana", "Punjab"),
    "172": ("Chandigarh", "Chandigarh"),
    "175": ("Patiala", "Punjab"),
    "181": ("Jalandhar", "Punjab"),
    "183": ("Amritsar", "Punjab"),
    "191": ("Jammu", "Jammu and Kashmir"),
    "194": ("Srinagar", "Jammu and Kashmir"),
    "212": ("Nashik", "Maharashtra"),
    "231": ("Kolhapur", "Maharashtra"),
    "240": ("Aurangabad", "Maharashtra"),
    "253": ("Nashik", "Maharashtra"),
    "261": ("Surat", "Gujarat"),
    "265": ("Vadodara", "Gujarat"),
    "281": ("Rajkot", "Gujarat"),
    "291": ("Jodhpur", "Rajasthan"),
    "294": ("Udaipur", "Rajasthan"),
    "353": ("Siliguri", "West Bengal"),
    "361": ("Guwahati", "Assam"),
    "413": ("Puducherry", "Puducherry"),
    "416": ("Vellore", "Tamil Nadu"),
    "422": ("Coimbatore", "Tamil Nadu"),
    "431": ("Tiruchirappalli", "Tamil Nadu"),
    "452": ("Madurai", "Tamil Nadu"),
    "471": ("Thiruvananthapuram", "Kerala"),
    "484": ("Kochi", "Kerala"),
    "487": ("Thrissur", "Kerala"),
    "495": ("Kozhikode", "Kerala"),
    "512": ("Kanpur", "Uttar Pradesh"),
    "522": ("Lucknow", "Uttar Pradesh"),
    "532": ("Prayagraj", "Uttar Pradesh"),
    "542": ("Varanasi", "Uttar Pradesh"),
    "562": ("Agra", "Uttar Pradesh"),
    "612": ("Patna", "Bihar"),
    "641": ("Bhagalpur", "Bihar"),
    "651": ("Ranchi", "Jharkhand"),
    "657": ("Jamshedpur", "Jharkhand"),
    "661": ("Rourkela", "Odisha"),
    "671": ("Cuttack", "Odisha"),
    "674": ("Bhubaneswar", "Odisha"),
    "712": ("Nagpur", "Maharashtra"),
    "731": ("Indore", "Madhya Pradesh"),
    "751": ("Gwalior", "Madhya Pradesh"),
    "755": ("Bhopal", "Madhya Pradesh"),
    "761": ("Jabalpur", "Madhya Pradesh"),
    "771": ("Raipur", "Chhattisgarh"),
    "821": ("Mysuru", "Karnataka"),
    "824": ("Mangaluru", "Karnataka"),
    "831": ("Belagavi", "Karnataka"),
    "836": ("Hubballi-Dharwad", "Karnataka"),
    "861": ("Nellore", "Andhra Pradesh"),
    "863": ("Guntur", "Andhra Pradesh"),
    "866": ("Vijayawada", "Andhra Pradesh"),
    "870": ("Warangal", "Telangana"),
    "877": ("Tirupati", "Andhra Pradesh"),
    "883": ("Rajahmundry", "Andhra Pradesh"),
    "891": ("Visakhapatnam", "Andhra Pradesh"),
}

# North American toll-free area codes.
_NANP_TOLL_FREE = {"800", "833", "844", "855", "866", "877", "888"}
_DIGITS = re.compile(r"\D+")


def _norm(value: Any) -> str:
    return re.sub(r"[\s_-]+", " ", str(value or "").strip().lower())


def _std_lookup(nsn: str) -> tuple[str, str, str] | None:
    for length in (3, 2):
        code = nsn[:length]
        if code in INDIA_STD_CODES:
            city, state = INDIA_STD_CODES[code]
            return code, city, state
    return None


def _classify_india(nsn: str, region: str) -> dict[str, Any]:
    region_norm = _norm(region)
    if nsn.startswith("1800"):
        return {"category": "toll_free", "detail": "Free for callers in India"}
    if nsn.startswith("1860"):
        return {"category": "other", "detail": "Shared-cost number (1860)"}
    if nsn.startswith("140"):
        return {"category": "other", "detail": "140 series (promotional calls)"}
    if nsn.startswith("1600"):
        return {"category": "other", "detail": "160 series (service and transactional calls)"}
    if len(nsn) != 10:
        return {"category": "other", "detail": ""}
    if "series" in region_norm and nsn[0] in "6789":
        # Vobiz names mobile-range stock by its series, e.g. "92 Series".
        return {"category": "mobile", "detail": f"{nsn[:2]} series"}
    std = _std_lookup(nsn)
    if std is not None:
        code, city, state = std
        subscriber_lead = nsn[len(code)] if len(nsn) > len(code) else ""
        names_state = bool(region_norm) and region_norm in (_norm(state), _norm(city))
        # STD codes starting 6-9 (Ahmedabad 79, Bengaluru 80, ...) share leading
        # digits with the mobile range, so those count as landline only when the
        # carrier's region names the code's state. Other codes cannot be mobiles.
        region_ok = names_state if code[0] in "6789" else (not region_norm or names_state or "series" not in region_norm)
        # Landline subscriber numbers begin 2-6 after the STD code.
        if subscriber_lead in "23456" and region_ok:
            return {
                "category": "landline",
                "stdCode": f"0{code}",
                "city": city,
                "state": state,
                "detail": f"{city} (STD 0{code})",
            }
    if nsn[0] in "6789":
        return {"category": "mobile", "detail": ""}
    if nsn[0] in "12345":
        # Geographic range whose STD code is not in our table: keep the carrier's
        # region as the area rather than inventing a city.
        return {"category": "landline", "state": region or "", "detail": region or ""}
    return {"category": "other", "detail": ""}


def classify_number(e164: str, *, country: str | None = None, region: str | None = None) -> dict[str, Any]:
    """Category, display label and area for one catalog number."""
    digits = _DIGITS.sub("", str(e164 or ""))
    cc = str(country or "").strip().upper()
    region_text = str(region or "").strip()
    info: dict[str, Any]
    if digits.startswith("91") and (cc in ("", "IN")):
        info = _classify_india(digits[2:], region_text)
    elif digits.startswith("1") and len(digits) == 11:
        area = digits[1:4]
        if area in _NANP_TOLL_FREE:
            info = {"category": "toll_free", "detail": f"Toll-free ({area})"}
        else:
            info = {"category": "other", "detail": f"Local number, area code {area}"}
    elif digits.startswith("44") and digits[2:5] in ("800", "808"):
        info = {"category": "toll_free", "detail": "Freephone"}
    else:
        info = {"category": "other", "detail": region_text}
    category = info.get("category") or "other"
    detail = info.get("detail") or ""
    return {
        "category": category,
        "categoryLabel": CATEGORY_LABELS[category],
        "areaLabel": detail,
        "city": info.get("city") or "",
        "stdCode": info.get("stdCode") or "",
        "state": info.get("state") or (region_text if category == "landline" else ""),
    }


def number_requirements(row: dict[str, Any]) -> list[str]:
    """Extra steps the carrier states for this number, from its documented fields only."""
    reqs: list[str] = []
    if str(row.get("aadhaar_verification_required") or "").strip().lower() in {"1", "true", "yes"}:
        reqs.append("Aadhaar verification of the account holder is required by the phone network for this number.")
    try:
        months = int(row.get("minimum_commitment_months") or 0)
    except (TypeError, ValueError):
        months = 0
    if months > 0:
        reqs.append(f"Minimum rental commitment of {months} month{'s' if months != 1 else ''}.")
    return reqs


def normalize_category(raw: str | None) -> str | None:
    """Accept the API filter in the spellings a client may send; None means all."""
    value = _norm(raw).replace(" ", "_")
    if not value or value == "all":
        return None
    aliases = {
        "tollfree": "toll_free",
        "toll_free": "toll_free",
        "toll": "toll_free",
        "freephone": "toll_free",
        "mobile": "mobile",
        "cell": "mobile",
        "landline": "landline",
        "fixed": "landline",
        "fixed_line": "landline",
        "geographic": "landline",
        "local": "landline",
        "other": "other",
    }
    if value not in aliases:
        raise ValueError("invalid_category")
    return aliases[value]


def matches_area(row: dict[str, Any], classified: dict[str, Any], area: str | None) -> bool:
    """City, state or STD/area-code filter. Digits match the number's area code."""
    needle = str(area or "").strip()
    if not needle:
        return True
    digits = _DIGITS.sub("", needle)
    if digits and digits == needle.replace(" ", "").lstrip("+"):
        std = classified.get("stdCode") or ""
        e164_digits = _DIGITS.sub("", str(row.get("e164") or ""))
        national = e164_digits[2:] if e164_digits.startswith("91") else e164_digits[1:] if e164_digits.startswith("1") else e164_digits
        return std == digits or std.lstrip("0") == digits.lstrip("0") or national.startswith(digits.lstrip("0"))
    text = _norm(needle)
    haystack = " ".join(
        _norm(v) for v in (classified.get("city"), classified.get("state"), classified.get("areaLabel"), row.get("region"))
    )
    return text in haystack


def provider_search_hint(category: str | None, area: str | None, country: str) -> str | None:
    """Substring the carrier's inventory ``search`` param can narrow on (E.164 digits)."""
    if str(country or "").upper() != "IN":
        return None
    digits = _DIGITS.sub("", str(area or ""))
    if digits:
        return "91" + digits.lstrip("0")
    if area:
        wanted = _norm(area)
        for code, (city, state) in INDIA_STD_CODES.items():
            if _norm(city) == wanted:
                return "91" + code
    if category == "toll_free":
        return "911800"
    return None
