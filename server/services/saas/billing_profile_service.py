"""Tenant billing identity — who the invoice is legally addressed to.

The profile determines place of supply and whether a GSTIN appears on the
invoice, so it is validated here rather than trusted from the console. Invoices
snapshot the profile at issue time; editing it later never rewrites history.
"""
from __future__ import annotations

import uuid

from server.db.connection import get_session_factory
from server.db.models.saas_models import TenantBillingProfile
from server.services.saas.tax_service import (
    INDIAN_STATES,
    state_name_for,
    validate_gstin,
)


def profile_payload(row: TenantBillingProfile | None) -> dict:
    if row is None:
        return {
            "legalName": "",
            "gstin": None,
            "billingEmail": "",
            "addressLine1": "",
            "addressLine2": "",
            "city": "",
            "stateName": "",
            "stateCode": "",
            "postalCode": "",
            "countryCode": "IN",
            "customerType": "individual",
            "complete": False,
        }
    return {
        "legalName": row.legal_name or "",
        "gstin": row.gstin,
        "billingEmail": row.billing_email or "",
        "addressLine1": row.address_line1 or "",
        "addressLine2": row.address_line2 or "",
        "city": row.city or "",
        "stateName": row.state_name or state_name_for(row.state_code),
        "stateCode": row.state_code or "",
        "postalCode": row.postal_code or "",
        "countryCode": row.country_code or "IN",
        "customerType": row.customer_type or "individual",
        "complete": bool(row.legal_name and row.address_line1 and row.city),
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


async def get_profile(tenant_id: uuid.UUID) -> dict:
    factory = get_session_factory()
    if factory is None:
        return profile_payload(None)
    async with factory() as session:
        return profile_payload(await session.get(TenantBillingProfile, tenant_id))


def _clean(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


async def update_profile(tenant_id: uuid.UUID, payload: dict) -> dict:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    gstin = _clean(payload.get("gstin"), 15).upper() or None
    state_code = _clean(payload.get("stateCode"), 4)
    country = (_clean(payload.get("countryCode"), 2) or "IN").upper()
    customer_type = _clean(payload.get("customerType"), 20).lower() or "individual"
    if customer_type not in ("individual", "business"):
        raise ValueError("invalid_customer_type")
    if country == "IN" and state_code and state_code not in INDIAN_STATES:
        raise ValueError("invalid_state_code")
    if gstin:
        error = validate_gstin(gstin)
        if error:
            raise ValueError(error)
        if state_code and state_code != gstin[:2]:
            raise ValueError("gstin_state_mismatch")
        state_code = gstin[:2]
        customer_type = "business"
    legal_name = _clean(payload.get("legalName"), 255)
    if customer_type == "business" and not legal_name:
        raise ValueError("legal_name_required")

    async with factory() as session:
        row = await session.get(TenantBillingProfile, tenant_id, with_for_update=True)
        if row is None:
            row = TenantBillingProfile(tenant_id=tenant_id)
            session.add(row)
        row.legal_name = legal_name or None
        row.gstin = gstin
        row.billing_email = _clean(payload.get("billingEmail"), 320) or None
        row.address_line1 = _clean(payload.get("addressLine1"), 255) or None
        row.address_line2 = _clean(payload.get("addressLine2"), 255) or None
        row.city = _clean(payload.get("city"), 120) or None
        row.state_code = state_code or None
        row.state_name = state_name_for(state_code) or _clean(payload.get("stateName"), 120) or None
        row.postal_code = _clean(payload.get("postalCode"), 12) or None
        row.country_code = country
        row.customer_type = customer_type
        await session.commit()
        return profile_payload(row)
