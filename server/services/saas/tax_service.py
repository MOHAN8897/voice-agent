"""Indian GST configuration, place of supply, and invoice tax arithmetic.

Three rules drive everything here:

* A supply is taxed where it is consumed. For a domestic invoice the supplier
  state decides CGST+SGST (same state) versus IGST (different state).
* Export of services is zero-rated when the operator has filed an LUT; the
  invoice still records the supply and the LUT number.
* Tax is computed once, at checkout, and snapshotted onto the order and the
  invoice. A later rate change must never move an amount a customer has
  already paid, so nothing here is re-derived at payment time.

Every amount is an integer in minor units. Recipient location and the configured
export treatment determine GST; currency alone never establishes an export.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from server.config.env import get_settings
from server.db.connection import get_session_factory

#: GST state codes (first two digits of a GSTIN) — CBIC, as of 2026.
INDIAN_STATES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

STATE_CODE_BY_NAME: dict[str, str] = {name.lower(): code for code, name in INDIAN_STATES.items()}

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: India Standard Time — financial years and invoice dates are IST, never UTC.
IST = timezone(timedelta(hours=5, minutes=30))

#: Voice/telecom service accounting code used for the wallet top-up supply.
DEFAULT_SAC_CODE = "998413"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def financial_year(moment: datetime | None = None) -> str:
    """Indian FY label, e.g. 2026-27, from an IST date (April 1 to March 31)."""
    local = (moment or _utcnow()).astimezone(IST)
    start = local.year if local.month >= 4 else local.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def financial_year_compact(fy: str) -> str:
    """`2026-27` -> `2627`, for the statutory <=16-character serial."""
    start, end = fy.split("-")
    return f"{start[-2:]}{end[-2:]}"


def gstin_checksum(gstin: str) -> str:
    """The 15th character of a GSTIN, computed from the first 14."""
    body = gstin[:14]
    total = 0
    for index, char in enumerate(body):
        value = _BASE36.index(char)
        factor = 2 if index % 2 else 1
        product = value * factor
        total += product // 36 + product % 36
    return _BASE36[(36 - total % 36) % 36]


def validate_gstin(raw: str | None) -> str | None:
    """Return an error code, or None when the GSTIN is well formed.

    Validating locally keeps a malformed buyer GSTIN out of an invoice where it
    would make the document non-compliant and the recipient's input credit fail.
    """
    value = str(raw or "").strip().upper()
    if not value:
        return "gstin_required"
    if len(value) != 15 or not _GSTIN_RE.match(value):
        return "gstin_invalid_format"
    if value[:2] not in INDIAN_STATES:
        return "gstin_invalid_state"
    if gstin_checksum(value) != value[-1]:
        return "gstin_invalid_checksum"
    return None


def state_name_for(code: str | None) -> str:
    return INDIAN_STATES.get(str(code or ""), "")


def state_code_for_name(name: str | None) -> str | None:
    return STATE_CODE_BY_NAME.get(str(name or "").strip().lower())


def _env_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": False,
        "legalName": settings.platform_legal_name or "",
        "tradeName": settings.platform_trade_name or settings.platform_legal_name or "",
        "gstin": (settings.platform_gstin or "").upper(),
        "pan": "",
        "addressLine1": settings.platform_address or "",
        "addressLine2": "",
        "city": settings.platform_city or "",
        "stateName": settings.platform_state_name or state_name_for(settings.platform_state_code),
        "stateCode": settings.platform_state_code or "",
        "postalCode": settings.platform_postal_code or "",
        "countryCode": "IN",
        "supportEmail": settings.platform_support_email or "",
        "supportPhone": "",
        "sacCode": DEFAULT_SAC_CODE,
        "defaultRateBps": int(settings.gst_default_rate_bps or 1800),
        "priceIncludesTax": bool(settings.gst_price_includes_tax),
        "exportZeroRated": True,
        "invoicePrefix": "INV",
        "creditNotePrefix": "CN",
        "lutNumber": "",
        "invoiceTerms": "",
        "updatedBy": None,
    }


def _row_to_config(row: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """DB values win; blank identity fields fall back to env defaults."""
    config = dict(fallback)
    mappings = {
        "enabled": "enabled",
        "legal_name": "legalName",
        "trade_name": "tradeName",
        "gstin": "gstin",
        "pan": "pan",
        "address_line1": "addressLine1",
        "address_line2": "addressLine2",
        "city": "city",
        "state_name": "stateName",
        "state_code": "stateCode",
        "postal_code": "postalCode",
        "country_code": "countryCode",
        "support_email": "supportEmail",
        "support_phone": "supportPhone",
        "sac_code": "sacCode",
        "default_rate_bps": "defaultRateBps",
        "price_includes_tax": "priceIncludesTax",
        "export_zero_rated": "exportZeroRated",
        "invoice_prefix": "invoicePrefix",
        "credit_note_prefix": "creditNotePrefix",
        "lut_number": "lutNumber",
        "invoice_terms": "invoiceTerms",
        "updated_by": "updatedBy",
    }
    for column, key in mappings.items():
        value = getattr(row, column, None)
        if isinstance(value, str) and not value.strip() and isinstance(config.get(key), str):
            continue
        if value is not None:
            config[key] = value
    config["stateCode"] = str(config.get("stateCode") or "")
    if not config.get("stateName"):
        config["stateName"] = state_name_for(config["stateCode"])
    config["updatedAt"] = getattr(row, "updated_at", None).isoformat() if getattr(row, "updated_at", None) else None
    return config


async def load_config(*, strict: bool = False) -> dict[str, Any]:
    """Read saved tax settings; strict checkout reads fail when the store is unavailable."""
    fallback = _env_config()
    factory = get_session_factory()
    if factory is None:
        if strict:
            raise ValueError("tax_configuration_unavailable")
        return fallback
    from server.db.models.saas_models import PlatformTaxSettings

    try:
        async with factory() as session:
            row = await session.get(PlatformTaxSettings, 1)
            return _row_to_config(row, fallback) if row else fallback
    except Exception:
        if strict:
            raise ValueError("tax_configuration_unavailable") from None
        # Non-checkout readers may still use the configured environment identity.
        return fallback


def config_configured(config: dict[str, Any]) -> bool:
    """Whether a compliant tax invoice can be issued with these settings."""
    if not config.get("legalName") or not config.get("addressLine1") or not config.get("city"):
        return False
    if config.get("countryCode", "IN") == "IN":
        if not config.get("stateCode") or config.get("stateCode") not in INDIAN_STATES:
            return False
        if validate_gstin(config.get("gstin")) is not None:
            return False
    return True


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Settings plus the derived flags the admin and checkout surfaces need."""
    return {
        **config,
        "configured": config_configured(config),
        "stateOptions": [{"code": code, "name": name} for code, name in INDIAN_STATES.items()],
        "ratePercent": round(int(config.get("defaultRateBps") or 0) / 100.0, 2),
    }


def _clean_prefix(raw: str, fallback: str) -> str:
    value = re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())[:4]
    return value or fallback


async def save_config(payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Validate and persist the singleton settings row."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    from server.db.models.saas_models import PlatformTaxSettings

    enabled = bool(payload.get("enabled", False))
    gstin = str(payload.get("gstin") or "").strip().upper() or None
    state_code = str(payload.get("stateCode") or "").strip()
    if state_code and state_code not in INDIAN_STATES:
        raise ValueError("invalid_state_code")
    if enabled:
        if not str(payload.get("legalName") or "").strip():
            raise ValueError("legal_name_required")
        if not str(payload.get("addressLine1") or "").strip() or not str(payload.get("city") or "").strip():
            raise ValueError("address_required")
        if not state_code:
            raise ValueError("state_required")
        if gstin:
            error = validate_gstin(gstin)
            if error:
                raise ValueError(error)
            if gstin[:2] != state_code:
                raise ValueError("gstin_state_mismatch")
        else:
            raise ValueError("gstin_required")
    rate = int(payload.get("defaultRateBps") or 0)
    if rate < 0 or rate > 5000:
        raise ValueError("invalid_rate")

    async with factory() as session:
        row = await session.get(PlatformTaxSettings, 1, with_for_update=True)
        expected = payload.get("expectedUpdatedAt")
        if expected and row is not None and str(expected) != (row.updated_at.isoformat() if row.updated_at else None):
            raise ValueError("tax_settings_conflict")
        if row is None:
            row = PlatformTaxSettings(id=1)
            session.add(row)
        row.enabled = enabled
        row.legal_name = str(payload.get("legalName") or "").strip()
        row.trade_name = str(payload.get("tradeName") or "").strip()
        row.gstin = gstin
        row.pan = str(payload.get("pan") or "").strip().upper() or None
        row.address_line1 = str(payload.get("addressLine1") or "").strip()
        row.address_line2 = str(payload.get("addressLine2") or "").strip()
        row.city = str(payload.get("city") or "").strip()
        row.state_code = state_code
        row.state_name = str(payload.get("stateName") or "").strip() or state_name_for(state_code)
        row.postal_code = str(payload.get("postalCode") or "").strip()
        row.country_code = str(payload.get("countryCode") or "IN").strip().upper()[:2]
        row.support_email = str(payload.get("supportEmail") or "").strip()
        row.support_phone = str(payload.get("supportPhone") or "").strip()
        row.sac_code = str(payload.get("sacCode") or DEFAULT_SAC_CODE).strip()[:12] or DEFAULT_SAC_CODE
        row.default_rate_bps = rate
        row.price_includes_tax = bool(payload.get("priceIncludesTax", False))
        row.export_zero_rated = bool(payload.get("exportZeroRated", True))
        row.invoice_prefix = _clean_prefix(payload.get("invoicePrefix"), "INV")
        row.credit_note_prefix = _clean_prefix(payload.get("creditNotePrefix"), "CN")
        row.lut_number = str(payload.get("lutNumber") or "").strip() or None
        row.invoice_terms = str(payload.get("invoiceTerms") or "").strip()
        row.updated_by = actor
        row.updated_at = _utcnow()
        await session.commit()
        return public_config(_row_to_config(row, _env_config()))


def supplier_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "legalName": config.get("legalName") or "",
        "tradeName": config.get("tradeName") or config.get("legalName") or "",
        "gstin": config.get("gstin") or None,
        "pan": config.get("pan") or None,
        "addressLine1": config.get("addressLine1") or "",
        "addressLine2": config.get("addressLine2") or "",
        "city": config.get("city") or "",
        "stateName": config.get("stateName") or state_name_for(config.get("stateCode")),
        "stateCode": config.get("stateCode") or "",
        "postalCode": config.get("postalCode") or "",
        "countryCode": config.get("countryCode") or "IN",
        "supportEmail": config.get("supportEmail") or "",
        "supportPhone": config.get("supportPhone") or "",
        "sacCode": config.get("sacCode") or DEFAULT_SAC_CODE,
        "lutNumber": config.get("lutNumber") or None,
        "invoiceTerms": config.get("invoiceTerms") or "",
    }


def buyer_snapshot(
    profile: dict[str, Any] | None,
    *,
    fallback_name: str = "",
    fallback_email: str = "",
    fallback_country: str = "IN",
) -> dict[str, Any]:
    profile = profile or {}
    gstin = str(profile.get("gstin") or "").strip().upper() or None
    state_code = str(profile.get("state_code") or profile.get("stateCode") or "").strip()
    if gstin and len(gstin) >= 2:
        state_code = gstin[:2]
    country = str(profile.get("country_code") or profile.get("countryCode") or fallback_country or "IN").upper()[:2]
    return {
        "legalName": str(profile.get("legal_name") or profile.get("legalName") or fallback_name or "").strip(),
        "gstin": gstin,
        "email": str(profile.get("billing_email") or profile.get("email") or fallback_email or "").strip(),
        "addressLine1": str(profile.get("address_line1") or profile.get("addressLine1") or "").strip(),
        "addressLine2": str(profile.get("address_line2") or profile.get("addressLine2") or "").strip(),
        "city": str(profile.get("city") or "").strip(),
        "stateName": state_name_for(state_code) or str(profile.get("state_name") or profile.get("stateName") or "").strip(),
        "stateCode": state_code,
        "postalCode": str(profile.get("postal_code") or profile.get("postalCode") or "").strip(),
        "countryCode": country,
        "customerType": str(profile.get("customer_type") or profile.get("customerType") or ("business" if gstin else "individual")),
    }


def _split_cgst_sgst(tax_paise: int, rate_bps: int) -> tuple[int, int]:
    """Equal halves; the odd paise goes to SGST so the two always sum exactly."""
    half = tax_paise // 2
    return half, tax_paise - half


def compute_tax(
    amount: float,
    currency: str,
    *,
    fx_rate_inr: float,
    config: dict[str, Any],
    buyer: dict[str, Any] | None = None,
    supplier_state_code: str | None = None,
) -> dict[str, Any]:
    """Quote a top-up with its GST split, in both charge and INR currency.

    `amount` is the listed price. When prices are exclusive it is the taxable
    value and GST is added; when inclusive the amount is the gross and the
    taxable value is derived. The wallet is always credited the taxable value,
    because GST collected is a liability and not spendable balance.
    """
    currency = str(currency or "INR").upper()
    amount = max(0.0, float(amount or 0.0))
    unit = 100  # every currency offered at checkout uses two decimals
    if currency in ("JPY", "KRW"):
        unit = 1
    amount_minor = int((Decimal(str(amount)) * unit).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    fx = float(fx_rate_inr or 95.64) or 95.64

    buyer = buyer or {}
    buyer_country = str(buyer.get("countryCode") or buyer.get("country_code") or "IN").upper()
    supplier_state = str(supplier_state_code or config.get("stateCode") or "")
    buyer_state = str(buyer.get("stateCode") or buyer.get("state_code") or "")
    if buyer.get("gstin"):
        buyer_state = str(buyer["gstin"])[:2]

    configured = config_configured(config)
    enabled = bool(config.get("enabled")) and configured
    # Zero-rating as an export needs foreign exchange, not just a foreign
    # address: `countryCode` is tenant-editable, so an INR payment is always
    # taxed as a domestic supply. A genuine foreign-currency order from a
    # buyer outside India keeps the export treatment.
    domestic = buyer_country == "IN" or currency == "INR"
    export = not domestic
    zero_rated = export and bool(config.get("exportZeroRated", True))
    rate_bps = int(config.get("defaultRateBps") or 0) if enabled and not zero_rated else 0
    price_includes = bool(config.get("priceIncludesTax"))

    tax_minor = 0
    taxable_minor = amount_minor
    gross_minor = amount_minor
    if rate_bps > 0:
        if price_includes:
            taxable_minor = int((Decimal(amount_minor) * 10_000 / (10_000 + rate_bps)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            tax_minor = amount_minor - taxable_minor
            gross_minor = amount_minor
        else:
            taxable_minor = amount_minor
            tax_minor = int((Decimal(amount_minor) * rate_bps / 10_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            gross_minor = taxable_minor + tax_minor

    if currency == "INR":
        taxable_inr = taxable_minor
        tax_inr = tax_minor
        gross_inr = gross_minor
        credit_paise = taxable_minor
    else:
        taxable_inr = int((Decimal(taxable_minor) / unit * Decimal(str(fx)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        tax_inr = int((Decimal(tax_minor) / unit * Decimal(str(fx)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        # International settlement credits what Razorpay converts; the quote is
        # the contract value and is replaced by `base_amount` on confirmation.
        gross_inr = taxable_inr + tax_inr
        credit_paise = taxable_inr

    if rate_bps <= 0:
        tax_kind = "export" if export and config.get("exportZeroRated", True) else "none"
    elif buyer_country == "IN" and buyer_state and supplier_state and buyer_state == supplier_state:
        tax_kind = "cgst_sgst"
    else:
        tax_kind = "igst"

    cgst = sgst = igst = 0
    if tax_kind == "cgst_sgst":
        cgst, sgst = _split_cgst_sgst(tax_inr, rate_bps)
    elif tax_kind == "igst":
        igst = tax_inr

    # A foreign-address buyer paying INR is taxed (not an export), as an
    # inter-state supply with IGST and the buyer's country as place of supply.
    place_state = (buyer_state or supplier_state) if buyer_country == "IN" else buyer_country
    charge_cgst = charge_sgst = 0
    if tax_kind == "cgst_sgst":
        charge_cgst, charge_sgst = _split_cgst_sgst(tax_minor, rate_bps)
    return {
        "currency": currency,
        "amount": amount,
        "amountMinor": amount_minor,
        "subtotal": round(taxable_minor / unit, 2),
        "tax": round(tax_minor / unit, 2),
        "total": round(gross_minor / unit, 2),
        "subtotalMinor": taxable_minor,
        "taxMinor": tax_minor,
        "totalMinor": gross_minor,
        "taxableInrPaise": taxable_inr,
        "taxInrPaise": tax_inr,
        "grossInrPaise": gross_inr,
        "creditInrPaise": credit_paise,
        "creditInr": round(credit_paise / 100.0, 2),
        "rateBps": rate_bps,
        "ratePercent": round(rate_bps / 100.0, 2),
        "taxKind": tax_kind,
        "cgstInrPaise": cgst,
        "sgstInrPaise": sgst,
        "igstInrPaise": igst,
        "cgst": round(charge_cgst / unit, 2),
        "sgst": round(charge_sgst / unit, 2),
        "igst": round(tax_minor / unit, 2) if tax_kind == "igst" else 0,
        "priceIncludesTax": price_includes,
        "sacCode": config.get("sacCode") or DEFAULT_SAC_CODE,
        "placeOfSupply": state_name_for(place_state) or place_state,
        "placeOfSupplyCode": place_state,
        "supplierStateCode": supplier_state,
        "export": export,
        "taxEnabled": enabled,
        "taxConfigured": configured,
        "buyerGstin": buyer.get("gstin") or None,
    }


def tax_summary_from_invoice(invoice: Any) -> dict[str, Any]:
    return {
        "taxableInrPaise": int(getattr(invoice, "taxable_inr_paise", 0) or 0),
        "taxInrPaise": int(getattr(invoice, "tax_inr_paise", 0) or 0),
        "cgstInrPaise": int(getattr(invoice, "cgst_inr_paise", 0) or 0),
        "sgstInrPaise": int(getattr(invoice, "sgst_inr_paise", 0) or 0),
        "igstInrPaise": int(getattr(invoice, "igst_inr_paise", 0) or 0),
        "taxRateBps": int(getattr(invoice, "tax_rate_bps", 0) or 0),
        "taxKind": getattr(invoice, "tax_kind", "none") or "none",
    }
