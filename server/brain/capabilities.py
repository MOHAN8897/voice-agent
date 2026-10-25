"""Compiled capability contract — permissions come from typed evidence, not prose.

The audit (F10) found that a Telugu quote-only brief offered order confirmation
because its minimum-order sentence contains the noun "ఆర్డర్". Scanning the whole
compiled prompt for an order noun cannot distinguish "take orders" from "we
cannot confirm an order", so the compiler now derives a small explicit section
from the business script and every runtime consumer reads only that section:

    --- CALL CAPABILITIES ---
    order_confirmation: not_allowed

Classification is fail-closed: a positive order-taking signal, the fields a real
order needs, and the absence of a global order prohibition must all hold. The
section is recomputed at render time, so a stored publication cannot keep a
permission its script no longer supports.
"""
from __future__ import annotations

import re

CAPABILITIES_HEADER = "--- CALL CAPABILITIES ---"
_CAPABILITIES_HEADER_RE = re.compile(r"(?m)^---\s*CALL CAPABILITIES\s*---[ \t]*$")
_ORDER_CAP_LINE = re.compile(r"(?m)^order_confirmation:\s*(allowed|not_allowed)\s*$")
_BUSINESS_END = re.compile(
    r"(?m)^--- (?:CALL CAPABILITIES|PLATFORM CALL RULES|CALL END POLICY|STATIC OUTPUT RULES) ---"
)

# Positive order-taking evidence. English phrases name the act explicitly; the
# Indic forms are imperatives/infinitives for taking an order, not the generic
# "ఆర్డర్ చేయాలి" (must order) that a minimum-order condition uses.
_ORDER_TAKING = re.compile(
    r"\b(?:take|taking|accept|accepting|place|placing|record|recording|handle|process)"
    r"\b[^.\n]{0,40}\borders?\b|"
    r"\b(?:order|purchase)\b[^.\n]{0,40}\b(?:quantity|delivery address|shipping address)\b|"
    r"ఆర్డర్\s*(?:తీసుకో|తీసుకోండి|పెట్టుకో)|"
    r"ऑर्डर\s*(?:ले|लें|लूँ|बुक कर)|"
    r"ஆர்டர்\s*(?:எடு|எடுங்கள்|பெறு)|"
    r"ಆರ್ಡರ್\s*(?:ತಗೊ|ತೆಗೆದುಕೊ)|"
    r"ഓർഡർ\s*(?:എടു|എടുക്ക)|"
    r"অর্ডার\s*(?:নিন|নেব|গ্রহণ)|"
    r"ઓર્ડર\s*(?:લો|લેલો|સ્વીકાર)|"
    r"ਆਰਡਰ\s*(?:ਲਓ|ਲੈ|ਲਵੋ)",
    re.I,
)

# A negative statement about confirming/claiming an order. Both word orders are
# present across the Indic scripts, so each direction is checked.
_ORDER_PROHIBITION = re.compile(
    r"\b(?:do not|don't|never|cannot|can't|can not|unable to|not able to|not permitted to|"
    r"must not|should not)\b[^.\n]{0,60}\b(?:confirm|claim|promise|guarantee|place|process|take|accept|record|handle)\b"
    r"[^.\n]{0,40}\b(?:orders?|purchases?)\b|"
    r"\b(?:orders?|purchases?)\b[^.\n]{0,40}\b(?:cannot|can't|can not|is not|are not|won't|will not)\b"
    r"[^.\n]{0,20}\b(?:be\s+)?(?:confirmed|placed|processed|claimed)\b|"
    r"(?:ఆర్డర్|ఆర్డరు)[^.\n]{0,40}(?:కన్ఫర్మ్|నిర్ధార|క్లెయిమ్)[^.\n]{0,20}(?:లేరు|లేదు|కాదు|వద్దు)|"
    r"(?:కన్ఫర్మ్|నిర్ధార|క్లెయిమ్)[^.\n]{0,40}(?:ఆర్డర్|ఆర్డరు)[^.\n]{0,20}(?:లేరు|లేదు|కాదు|వద్దు)|"
    r"ऑर्डर[^.\n]{0,40}(?:पुष्टि|कन्फर्म)[^.\n]{0,20}(?:नहीं|मत)|"
    r"(?:पुष्टि|कन्फर्म)[^.\n]{0,40}ऑर्डर[^.\n]{0,20}(?:नहीं|मत)|"
    r"ஆர்டர்[^.\n]{0,40}(?:உறுதி|கன்ஃபர்ம்)[^.\n]{0,20}(?:இல்லை|வேண்டாம்|முடியாது)|"
    r"ಆರ್ಡರ್[^.\n]{0,40}(?:ದೃಢೀಕರಿಸ|ಕನ್ಫರ್ಮ್)[^.\n]{0,20}(?:ಇಲ್ಲ|ಬೇಡ|ಸಾಧ್ಯವಿಲ್ಲ)|"
    r"ഓർഡർ[^.\n]{0,40}(?:സ്ഥിരീകര|കൺഫേം)[^.\n]{0,20}(?:ഇല്ല|വേണ്ട|കഴിയില്ല)|"
    r"অর্ডার[^.\n]{0,40}(?:নিশ্চিত|কনফার্ম)[^.\n]{0,20}(?:নয়|না|নেই)|"
    r"ઓર્ડર[^.\n]{0,40}(?:પુષ્ટિ|કન્ફર્મ)[^.\n]{0,20}(?:નથી|ના|નહીં)|"
    r"ਆਰਡਰ[^.\n]{0,40}(?:ਪੁਸ਼ਟੀ|ਕਨਫਰਮ)[^.\n]{0,20}(?:ਨਹੀਂ|ਨਾ)",
    re.I,
)

# The fields a confirmed order actually needs. A brief that never mentions any
# of them is describing a sale, quote or enquiry, not an order workflow.
_ORDER_PROOF_FIELDS = re.compile(
    r"\b(?:delivery address|shipping address|delivery|dispatch|shipment)\b|"
    r"(?:డెలివరీ|చిరునామా)|(?:डिलीवरी|पता)|(?:டெலிவரி|முகவரி)|"
    r"(?:ಡೆಲಿವರಿ|ವಿಳಾಸ)|(?:ഡെലിവറി|വിലാസം)|(?:ডেলিভারি|ঠিকানা)|"
    r"(?:ડિલિવરી|સરનામું)|(?:ਡਿਲਿਵਰੀ|ਪਤਾ)",
    re.I,
)


def business_text(compiled_text: str | None) -> str:
    """The authored business script, without platform-owned sections."""
    raw = (compiled_text or "").strip()
    start = re.search(r"(?m)^--- CALLING SCRIPT ---[ \t]*$", raw)
    if start:
        body = raw[start.end():]
        end = _BUSINESS_END.search(body)
        return (body[:end.start()] if end else body).strip()
    return raw


def order_confirmation_evidence(compiled_text: str | None) -> tuple[bool, bool, bool]:
    """(takes_orders, names_proof_fields, prohibits_confirmation) from the script."""
    business = business_text(compiled_text)
    return (
        bool(_ORDER_TAKING.search(business)),
        bool(_ORDER_PROOF_FIELDS.search(business)),
        bool(_ORDER_PROHIBITION.search(business)),
    )


def order_confirmation_allowed_from_script(compiled_text: str | None) -> bool:
    takes_orders, proof_fields, prohibited = order_confirmation_evidence(compiled_text)
    return takes_orders and proof_fields and not prohibited


def render_capabilities_section(compiled_text: str | None) -> str:
    allowed = order_confirmation_allowed_from_script(compiled_text)
    return (
        f"{CAPABILITIES_HEADER}\n"
        f"order_confirmation: {'allowed' if allowed else 'not_allowed'}"
    )


def capabilities_section_present(compiled_text: str | None) -> bool:
    return bool(_CAPABILITIES_HEADER_RE.search(compiled_text or ""))


def order_confirmation_allowed(compiled_text: str | None) -> bool:
    """Fail-closed runtime permission read from the compiled section."""
    text = compiled_text or ""
    match = _ORDER_CAP_LINE.search(text)
    if match:
        return match.group(1) == "allowed"
    # A publication stored before the capability section existed carries no
    # permission marker; classify its business script once at render time
    # rather than trusting platform safety text that also mentions orders.
    if capabilities_section_present(text):
        return False
    return order_confirmation_allowed_from_script(text)
