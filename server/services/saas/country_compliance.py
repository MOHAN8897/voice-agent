"""Per-country telephony compliance rules, for the agent settings screen.

The product is sold to English-speaking markets, so the obligations an operator
has to answer for differ by where the number sits. This module is a reference
catalogue: it states which regulation applies to each country and what each one
obliges them to do.

Deliberately advisory only. Nothing here is consulted by the live PSTN path —
turning a toggle off must not change how a call is placed, which is why the
call path does not import this module at all.
"""
from __future__ import annotations

from typing import Any

#: Regulation catalogue keyed by ISO-3166 alpha-2.
#:
#: `obligations` are the things an operator genuinely has to decide for that
#: market. Each maps to a per-agent toggle so the settings screen can ask a
#: yes/no question rather than making them read legislation.
COUNTRY_COMPLIANCE: dict[str, dict[str, Any]] = {
    "US": {
        "regulation": "TCPA / TIA",
        "summary": "Automated calls need prior consent; recorded calls must be disclosed.",
        "obligations": {
            "consent_disclosure": "Announce that the call is automated at the start",
            "recording_disclosure": "Tell the caller the call is recorded",
            "do_not_call_registry": "Honour the national Do-Not-Call registry",
        },
    },
    "GB": {
        "regulation": "UK GDPR / PECR",
        "summary": "Lawful basis for processing, plus recorded-call notice to callers.",
        "obligations": {
            "lawful_basis": "Record the lawful basis you rely on (consent or legitimate interest)",
            "recording_disclosure": "Tell the caller the call is recorded",
            "data_retention": "Set and document a retention period for transcripts",
        },
    },
    "CA": {
        "regulation": "CASL / PIPEDA",
        "summary": "Commercial electronic messages need consent or a stated exception.",
        "obligations": {
            "consent_disclosure": "Confirm you have consent to message this number",
            "recording_disclosure": "Tell the caller the call is recorded",
            "identify_sender": "Identify your organisation on the call",
        },
    },
    "AU": {
        "regulation": "ACMA Spam Act / Privacy Act",
        "summary": "Consent-based messaging, and a clear sender identity.",
        "obligations": {
            "consent_disclosure": "Confirm you have consent to message this number",
            "identify_sender": "Identify your organisation on the call",
            "recording_disclosure": "Tell the caller the call is recorded",
        },
    },
    "IE": {
        "regulation": "ePrivacy Regulations",
        "summary": "Direct marketing restrictions and recorded-call notice.",
        "obligations": {
            "consent_disclosure": "Confirm you have consent to message this number",
            "recording_disclosure": "Tell the caller the call is recorded",
        },
    },
    "NZ": {
        "regulation": "Privacy Act 2020",
        "summary": "Privacy principles and recorded-call notice.",
        "obligations": {
            "recording_disclosure": "Tell the caller the call is recorded",
            "data_retention": "Set and document a retention period for transcripts",
        },
    },
    "SG": {
        "regulation": "PDPA",
        "summary": "Consent or contract for collection, disclosure, and purpose limitation.",
        "obligations": {
            "consent_disclosure": "Record the consent or contractual basis you rely on",
            "recording_disclosure": "Tell the caller the call is recorded",
            "data_retention": "Set and document a retention period for transcripts",
        },
    },
    "ZA": {
        "regulation": "POPIA",
        "summary": "Explicit consent for direct marketing; processing notice.",
        "obligations": {
            "consent_disclosure": "Confirm you have consent to message this number",
            "recording_disclosure": "Tell the caller the call is recorded",
        },
    },
    "PH": {
        "regulation": "NPC / Data Privacy Act",
        "summary": "Consent for processing and clear privacy notice.",
        "obligations": {
            "consent_disclosure": "Confirm you have consent to message this number",
            "recording_disclosure": "Tell the caller the call is recorded",
        },
    },
    "IN": {
        "regulation": "TRAI DND / IT Act",
        "summary": "Registration and DND-category consent before commercial calls.",
        "obligations": {
            "consent_disclosure": "Confirm DND-category consent before a commercial call",
            "identify_sender": "Identify your organisation on the call",
            "recording_disclosure": "Tell the caller the call is recorded",
        },
    },
}

#: Shown when a country has no specific catalogue entry, so the settings screen
#: never implies a jurisdiction is unregulated.
DEFAULT_COUNTRY = {
    "regulation": "Local privacy law",
    "summary": "Tell callers who you are and that the call may be recorded.",
    "obligations": {
        "identify_sender": "Identify your organisation on the call",
        "recording_disclosure": "Tell the caller the call is recorded",
    },
}


def normalize_country(raw: str | None) -> str:
    return (raw or "US").strip().upper()[:2]


def _humanize(key: str) -> str:
    """consent_disclosure -> "consent disclosure".

    `str.replace` takes literals, not a regex — writing `/_/g` here silently
    matched nothing and left every label as a raw snake_case key.
    """
    return str(key).replace("_", " ")


def compliance_for_country(raw: str | None) -> dict[str, Any]:
    """The obligations and whether they are on by default."""
    code = normalize_country(raw)
    entry = COUNTRY_COMPLIANCE.get(code, DEFAULT_COUNTRY)
    return {
        "country": code,
        "regulation": entry["regulation"],
        "summary": entry["summary"],
        "obligations": [
            {"key": key, "label": _humanize(key), "enabled": True}
            for key in entry["obligations"]
        ],
    }


def compliance_catalog() -> list[dict[str, Any]]:
    """Every country the console offers, with its obligations."""
    from server.services.saas.telephony_countries import BUY_COUNTRIES

    return [
        {**compliance_for_country(c["code"]), "countryName": c["name"], "dial": c["dial"]}
        for c in BUY_COUNTRIES
    ]


def merge_agent_compliance(
    saved: dict[str, Any] | None, country: str | None
) -> dict[str, Any]:
    """Stored toggles over the catalogue defaults.

    Stored `false` is honoured, but a key the catalogue has since added defaults
    to `true` — so a new obligation is visible rather than silently off.
    """
    base = compliance_for_country(country)
    stored = saved if isinstance(saved, dict) else {}
    toggles = {t["key"]: bool(t.get("enabled", True)) for t in base["obligations"]}
    for key, value in (stored.get("acknowledged") or {}).items():
        if key in toggles:
            toggles[key] = bool(value)
    return {
        "country": base["country"],
        "regulation": base["regulation"],
        "summary": base["summary"],
        "acknowledged": toggles,
    }