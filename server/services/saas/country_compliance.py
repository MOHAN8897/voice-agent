"""India telephony compliance checklist for the tenant agent settings screen.

The console presents one India checklist because the platform's commercial
calling route is Indian. This catalogue records operator acknowledgements; it
does not certify compliance or substitute for consent/recipient-preference
verification.

Deliberately advisory only. Nothing here is consulted by the live PSTN path —
turning a toggle off must not change how a call is placed, which is why the
call path does not import this module at all.
"""
from __future__ import annotations

from typing import Any

#: The tenant-facing checklist. Keys are stable so acknowledgements saved by
#: earlier releases survive an update to the wording.
INDIA_COMPLIANCE: dict[str, Any] = {
    "country": "IN",
    "countryName": "India",
    "regulation": "TRAI TCCCPR · DPDP Act 2023",
    "summary": "Commercial calls need a documented consent basis, sender identity, recipient-preference checks and a privacy notice.",
    "obligations": {
        "consent_disclosure": "I have documented consent or another lawful basis for these calls and can produce it on request.",
        "do_not_call_registry": "I check the recipient's DND/consent preferences through an authorised process before calling and honour opt-outs.",
        "identify_sender": "My agent identifies my business and the purpose of the call, and discloses that it is an AI assistant.",
        "recording_disclosure": "My agent tells the caller when the call is recorded or transcribed and provides the privacy notice.",
        "commercial_registration": "My business uses an approved commercial calling route and completes sender/KYC registration.",
        "data_retention": "I limit caller data to its stated purpose and maintain retention, deletion and grievance-handling processes.",
    },
    "notes": [
        "TRAI's TCCCPR framework governs commercial calls, consent, recipient preferences and the 140/1600/1601 numbering series. The Third Amendment (18 September 2026) phases in AI-based spam detection, A2P termination charges and KYC re-verification; confirm the provisions and number series applicable to your business before launch.",
        "The DPDP Rules, 2025 were notified on 13 November 2025. Consent Manager registration begins 13 November 2026, and the main notice, consent and data-principal duties (with penalties) apply from 13 May 2027. Prepare your privacy processes; this checklist is not a certification.",
        "The workspace Do Not Call list records your own opt-outs. It does not establish that a recipient was checked against the national preference or consent registers.",
    ],
    "sources": [
        {"label": "TRAI commercial calling regulations", "url": "https://trai.gov.in/release-publication/regulations/amendments-page/7617"},
        {"label": "TRAI Third Amendment press note (2026)", "url": "https://www.trai.gov.in/sites/default/files/2026-09/PR_No119of2026.pdf"},
        {"label": "DPDP commencement notification", "url": "https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf"},
        {"label": "DPDP Rules, 2025", "url": "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf"},
    ],
}


def compliance_for_country(raw: str | None = None) -> dict[str, Any]:
    """Return the tenant checklist.

    The argument is retained for the existing query surface; the tenant
    checklist is India-only and does not vary by the agent's number.
    """
    del raw
    return {
        "country": INDIA_COMPLIANCE["country"],
        "countryName": INDIA_COMPLIANCE["countryName"],
        "regulation": INDIA_COMPLIANCE["regulation"],
        "summary": INDIA_COMPLIANCE["summary"],
        "obligations": [
            {"key": key, "label": label}
            for key, label in INDIA_COMPLIANCE["obligations"].items()
        ],
        "notes": list(INDIA_COMPLIANCE["notes"]),
        "sources": list(INDIA_COMPLIANCE["sources"]),
    }


def compliance_catalog() -> list[dict[str, Any]]:
    """The tenant checklist; India is the only market the console presents."""
    return [{**compliance_for_country(), "dial": "+91"}]


def merge_agent_compliance(
    saved: dict[str, Any] | None, country: str | None = None
) -> dict[str, Any]:
    """Stored India acknowledgements over the checklist defaults.

    Acknowledgements saved under a former non-India checklist are discarded so
    an operator must re-confirm the Indian obligations. A newly added obligation
    remains unconfirmed until it is explicitly acknowledged.
    """
    del country
    base = compliance_for_country()
    stored = saved if isinstance(saved, dict) else {}
    toggles = {item["key"]: False for item in base["obligations"]}
    saved_market = str(stored.get("country") or "").strip().upper()[:2]
    acknowledgements = stored.get("acknowledged") if saved_market in {"", "IN"} else None
    for key, value in (acknowledgements if isinstance(acknowledgements, dict) else {}).items():
        if key in toggles:
            toggles[key] = bool(value)
    return {
        **base,
        "acknowledged": toggles,
    }
