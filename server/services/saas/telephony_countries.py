"""Countries offered when buying Telnyx DIDs in the subscriber console.

English-speaking SaaS buyers are the primary audience, so the default list
prioritises those markets. Telnyx must still have inventory for a country —
an empty search result is honest inventory, not a bug in this list.
"""
from __future__ import annotations

# ISO-3166 alpha-2 → label shown in the buy-number country dropdown.
BUY_COUNTRIES: list[dict[str, str]] = [
    {"code": "US", "name": "United States", "dial": "+1"},
    {"code": "GB", "name": "United Kingdom", "dial": "+44"},
    {"code": "CA", "name": "Canada", "dial": "+1"},
    {"code": "AU", "name": "Australia", "dial": "+61"},
    {"code": "IE", "name": "Ireland", "dial": "+353"},
    {"code": "NZ", "name": "New Zealand", "dial": "+64"},
    {"code": "SG", "name": "Singapore", "dial": "+65"},
    {"code": "ZA", "name": "South Africa", "dial": "+27"},
    {"code": "PH", "name": "Philippines", "dial": "+63"},
    {"code": "IN", "name": "India", "dial": "+91"},
]

_ALLOWED = {c["code"] for c in BUY_COUNTRIES}


def buy_country_options() -> list[dict[str, str]]:
    return list(BUY_COUNTRIES)


def normalize_buy_country(raw: str | None, *, default: str = "US") -> str:
    code = (raw or default).strip().upper()
    if code in _ALLOWED:
        return code
    return default
