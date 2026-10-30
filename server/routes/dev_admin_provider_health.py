"""Platform admin "Provider health": every stack vendor, what is failing and why.

One card per stack component (LLM, speech-to-text, text-to-speech, telephony,
integrations, payments) built from incidents recorded at the real failure
points (``server.services.provider_health``) plus the Sarvam key pool. No key
material is ever returned — only slot names.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services import provider_health as ph
from server.services.saas.admin_audit import record_admin_action

router = APIRouter(tags=["dev-admin-provider-health"])

READ_PERMISSION = "dev.admin.tenants"

COMPONENT_LABEL = {
    "llm": "Language model (LLM)",
    "stt": "Speech-to-text",
    "tts": "Text-to-speech",
    "telephony": "Telephony",
    "integrations": "Integrations gateway",
    "payments": "Payments",
}

# (component, provider, settings fields proving it is configured, billing / console link)
CATALOG: list[tuple[str, str, tuple[str, ...], str | None]] = [
    ("llm", "sarvam", ("sarvam_api_key",), "https://dashboard.sarvam.ai/"),
    ("llm", "openai", ("openai_api_key",), "https://platform.openai.com/settings/organization/billing/overview"),
    ("llm", "gemini", ("gemini_api_key",), "https://aistudio.google.com/apikey"),
    ("llm", "deepseek", ("deepseek_api_key",), "https://platform.deepseek.com/usage"),
    ("stt", "sarvam", ("sarvam_api_key",), "https://dashboard.sarvam.ai/"),
    ("stt", "cartesia", ("cartesia_api_key",), "https://play.cartesia.ai/subscription"),
    ("stt", "openai", ("openai_api_key",), "https://platform.openai.com/settings/organization/billing/overview"),
    ("tts", "sarvam", ("sarvam_api_key",), "https://dashboard.sarvam.ai/"),
    ("tts", "cartesia", ("cartesia_api_key",), "https://play.cartesia.ai/subscription"),
    ("tts", "gnani", ("gnani_api_key",), None),
    ("tts", "gemini", ("gemini_api_key",), "https://aistudio.google.com/apikey"),
    ("telephony", "vobiz", ("vobiz_auth_id", "vobiz_auth_token"), "https://console.vobiz.ai/"),
    ("telephony", "telnyx", ("telnyx_api_key",), "https://portal.telnyx.com/#/app/account/billing"),
    ("integrations", "nango", ("nango_secret_key", "nango_api_key"), "https://app.nango.dev/"),
    ("payments", "razorpay", ("razorpay_api_key",), "https://dashboard.razorpay.com/app/keys"),
]

RECOVERED_NOTE_WINDOW_S = 24 * 3600


def _configured(fields: tuple[str, ...]) -> bool:
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    for field in fields:
        value = None
        try:
            value = dev_secrets_store.effective_secret(field)
        except Exception:
            value = None
        if not value:
            value = getattr(settings, field, None)
        if value and str(value).strip():
            return True
    return False


def _severity(incident: dict[str, Any]) -> str:
    """failing = calls using this vendor cannot work; degraded = working around it."""
    category = incident.get("category")
    if incident.get("summary"):
        return "degraded"
    if category in ph.KEY_FAILOVER_CATEGORIES and (incident.get("failedOverTo") or incident.get("servedByBackup")) \
            and not incident.get("allKeysFailed"):
        return "degraded"
    if category in ph.HARD_CATEGORIES:
        return "failing"
    if int(incident.get("callsRejected") or 0) > 0:
        return "failing"
    return "degraded"


def _iso_ago(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    return ph._now_iso(time.time() - seconds)


def _sarvam_keys() -> dict[str, Any]:
    from server.services.sarvam_keys import sarvam_key_pool

    snap = sarvam_key_pool.snapshot()
    for slot in snap["slots"]:
        slot["lastFailureAt"] = _iso_ago(slot.pop("lastFailureAgoSeconds", None))
        slot["lastSuccessAt"] = _iso_ago(slot.pop("lastSuccessAgoSeconds", None))
    return snap


def build_health() -> dict[str, Any]:
    incidents = ph.provider_health.incidents(limit=200)
    now = time.time()
    sarvam_keys = _sarvam_keys()
    components: list[dict[str, Any]] = []
    banner_items: list[dict[str, Any]] = []
    worst = "healthy"
    rank = {"healthy": 0, "not_configured": 0, "degraded": 1, "failing": 2}

    for component in ph.COMPONENTS:
        cards = []
        for comp, provider, fields, link in CATALOG:
            if comp != component:
                continue
            mine = [row for row in incidents if row.get("provider") == provider and row.get("component") == component]
            # Credits/key problems belong to the account, so show them on every Sarvam card.
            if provider == "sarvam":
                mine = [row for row in incidents if row.get("provider") == "sarvam"
                        and (row.get("component") == component or row.get("category") in ph.KEY_FAILOVER_CATEGORIES)]
            active = [row for row in mine if row.get("active")]
            configured = _configured(fields)
            status = "healthy" if configured else "not_configured"
            headline = "No errors recorded." if configured else "Not configured."
            lead = None
            if active:
                severities = [_severity(row) for row in active]
                status = "failing" if "failing" in severities else "degraded"
                lead = sorted(active, key=lambda r: (rank[_severity(r)], r.get("lastSeenTs", 0)), reverse=True)[0]
                headline = str(lead.get("message") or "")
            card: dict[str, Any] = {
                "component": component,
                "provider": provider,
                "label": ph.PROVIDER_LABEL.get(provider, provider.title()),
                "configured": configured,
                "status": status,
                "headline": headline,
                "category": lead.get("category") if lead else None,
                "categoryLabel": ph.CATEGORY_LABEL.get(lead.get("category")) if lead else None,
                "detail": lead.get("detail") if lead else None,
                "since": min((row.get("firstSeen") for row in active), default=None),
                "lastSeen": max((row.get("lastSeen") for row in active), default=None),
                "count": sum(int(row.get("count") or 0) for row in active),
                "callsAffected": sum(int(row.get("callsAffected") or 0) for row in active),
                "callsRejected": sum(int(row.get("callsRejected") or 0) for row in active),
                "tenantsAffected": len({t for row in active for t in (row.get("tenantIds") or [])}),
                "incidentIds": [row["id"] for row in active],
                "billingUrl": link,
                "recentlyRecovered": next(
                    (row.get("message") for row in mine
                     if row.get("resolvedAt") and not row.get("acknowledgedAt")
                     and now - float(row.get("lastSeenTs") or 0) < RECOVERED_NOTE_WINDOW_S),
                    None,
                ),
            }
            if provider == "sarvam":
                card["keys"] = sarvam_keys
                card["activeSlot"] = sarvam_keys.get("activeSlot")
                if sarvam_keys.get("allKeysCoolingDown"):
                    card["status"] = "failing"
                    if not active:
                        card["headline"] = "Sarvam: all API keys are cooling down after rejections — calls using Sarvam are failing."
            if card["status"] in ("failing", "degraded"):
                banner_items.append({k: card[k] for k in ("component", "provider", "label", "status", "headline",
                                                         "since", "callsRejected", "billingUrl")})
            if rank[card["status"]] > rank[worst]:
                worst = card["status"]
            cards.append(card)
        components.append({"component": component, "label": COMPONENT_LABEL[component], "providers": cards})

    # One banner line per failing vendor, even when it serves several stages.
    seen: set[tuple[str, str]] = set()
    banner = []
    for item in sorted(banner_items, key=lambda i: rank[i["status"]], reverse=True):
        key = (item["provider"], item["headline"])
        if key in seen:
            continue
        seen.add(key)
        banner.append(item)
    return {
        "checkedAt": ph._now_iso(),
        "overall": worst,
        "banner": banner,
        "components": components,
        "incidents": incidents[:100],
        "categories": ph.CATEGORY_LABEL,
    }


@router.get("/api/dev/admin/provider-health")
async def provider_health_overview(session: SessionData = Depends(require_dev_session)):
    require_permission(session, READ_PERMISSION)
    return build_health()


@router.post("/api/dev/admin/provider-health/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, request: Request, session: SessionData = Depends(require_dev_session)):
    require_permission(session, READ_PERMISSION)
    if not ph.provider_health.acknowledge(incident_id):
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Incident not found."}})
    await record_admin_action(actor=session.subject, action="provider_health.incident_resolved",
                              resource_type="provider_incident", resource_id=incident_id, request=request)
    return {"ok": True, **build_health()}


@router.post("/api/dev/admin/provider-health/sarvam/recheck")
async def recheck_sarvam(request: Request, session: SessionData = Depends(require_dev_session)):
    """After topping up: test every Sarvam key now (a few tokens each)."""
    require_permission(session, READ_PERMISSION)
    from server.services.sarvam_keys import probe_all

    results = await probe_all()
    await record_admin_action(actor=session.subject, action="provider_health.sarvam_recheck",
                              resource_type="provider", resource_id="sarvam", request=request,
                              payload={"results": results})
    return {"ok": True, "recheck": results, **build_health()}
