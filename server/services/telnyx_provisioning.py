"""Telnyx Mission Control standard setup — applied to Call Control app, OVP, and every new number."""
from __future__ import annotations

import logging
from typing import Any

from server.config.env import get_settings
from server.config.urls import public_api_base
from server.services.telnyx_client import TelnyxApiError, TelnyxClient

logger = logging.getLogger(__name__)

# India + common regions once account is upgraded (Level 2+).
STANDARD_WHITELISTED_DESTINATIONS = [
    "US",
    "CA",
    "IN",
    "GB",
    "AU",
]


def _webhook_url() -> str:
    base = public_api_base().rstrip("/")
    return f"{base}/api/telnyx/webhook"


async def ensure_call_control_application(client: TelnyxClient) -> dict[str, Any]:
    """Ensure Call Control app exists with webhook + outbound voice profile."""
    settings = get_settings()
    app_id = client.cfg.get("connection_id") or settings.telnyx_connection_id or ""
    ovp_id = settings.telnyx_outbound_voice_profile_id or ""

    if app_id:
        try:
            app = await client.get_call_control_application(app_id)
            outbound = app.get("outbound") or {}
            webhook = str(app.get("webhook_event_url") or "")
            if (
                outbound.get("outbound_voice_profile_id")
                and webhook
                and webhook.rstrip("/") == _webhook_url().rstrip("/")
            ):
                return {"ok": True, "application_id": app_id, "existing": True, "app": app}
        except TelnyxApiError:
            pass

    if not app_id:
        created = await client.create_call_control_application(
            application_name="Voice Agent",
            webhook_event_url=_webhook_url(),
        )
        app_id = str(created.get("id") or "")
        logger.info("[TELNYX] created call control app %s", app_id)

    ovp = await ensure_outbound_voice_profile(client, ovp_id or None)
    ovp_id = str(ovp.get("id") or ovp_id)

    patched = await client.update_call_control_application(
        app_id,
        {
            "active": True,
            "webhook_event_url": _webhook_url(),
            "webhook_api_version": "2",
            "call_cost_in_webhooks": True,
            "outbound": {"outbound_voice_profile_id": ovp_id},
        },
    )
    return {"ok": True, "application_id": app_id, "outbound_voice_profile_id": ovp_id, "app": patched}


async def ensure_outbound_voice_profile(client: TelnyxClient, ovp_id: str | None = None) -> dict[str, Any]:
    """Outbound profile: recording on, international whitelist (when account allows)."""
    if ovp_id:
        try:
            return await client.get_outbound_voice_profile(ovp_id)
        except TelnyxApiError:
            pass

    profiles = await client.list_outbound_voice_profiles()
    if profiles:
        ovp_id = str(profiles[0].get("id") or "")
    else:
        created = await client.create_outbound_voice_profile(name="Voice Agent Outbound")
        ovp_id = str(created.get("id") or "")

    patch: dict[str, Any] = {
        "enabled": True,
        "call_recording": {
            "call_recording_type": "all",
            "call_recording_channels": "dual",
            "call_recording_format": "wav",
        },
    }
    try:
        patch["whitelisted_destinations"] = STANDARD_WHITELISTED_DESTINATIONS
        return await client.update_outbound_voice_profile(ovp_id, patch)
    except TelnyxApiError as e:
        if e.status == 403 and "IN" in (e.body or ""):
            logger.warning("[TELNYX] IN not allowed on account tier — using US/CA whitelist")
            patch["whitelisted_destinations"] = ["US", "CA"]
            return await client.update_outbound_voice_profile(ovp_id, patch)
        raise


async def apply_standard_phone_number_settings(client: TelnyxClient, phone_number_id: str) -> dict[str, Any]:
    """Standard settings for every purchased number: connection, HD voice, recording."""
    settings = get_settings()
    connection_id = client.cfg.get("connection_id") or settings.telnyx_connection_id or ""
    return await client.update_phone_number(
        phone_number_id,
        {
            "connection_id": connection_id,
            "hd_voice_enabled": True,
            "call_recording_enabled": True,
        },
    )


async def provision_ordered_number(client: TelnyxClient, phone_number: str) -> dict[str, Any]:
    """Order number + apply standard settings (connection, recording, HD)."""
    await ensure_call_control_application(client)
    order = await client.place_number_order(phone_number)
    phone_id = None
    for row in (order.get("phone_numbers") or []):
        if row.get("phone_number") == phone_number or row.get("id"):
            phone_id = row.get("id")
            break
    if not phone_id:
        # Poll until number appears
        for row in await client.list_phone_numbers():
            if row.get("phone_number") == phone_number:
                phone_id = row.get("id")
                break
    if phone_id:
        applied = await apply_standard_phone_number_settings(client, str(phone_id))
        return {"ok": True, "order": order, "phone_number_id": phone_id, "phone": applied}
    return {"ok": True, "order": order, "phone_number_id": None}


async def telnyx_setup_status(client: TelnyxClient) -> dict[str, Any]:
    """Readiness checklist for dev UI."""
    settings = get_settings()
    app_id = client.cfg.get("connection_id") or settings.telnyx_connection_id or ""
    checklist: dict[str, Any] = {
        "call_control_app": False,
        "webhook_configured": False,
        "outbound_voice_profile": False,
        "outbound_profile_on_app": False,
        "call_recording_on_profile": False,
        "international_india": False,
        "phone_number_active": False,
        "phone_recording_enabled": False,
        "account_balance_ok": False,
        "verified_numbers": [],
        "errors": [],
        "upgrade_required_for_india": False,
    }
    try:
        bal = await client.get_balance()
        avail = float(bal.get("available_credit") or bal.get("balance") or 0)
        checklist["account_balance_ok"] = avail > 0
        checklist["balance_usd"] = avail
    except TelnyxApiError as e:
        checklist["errors"].append(f"balance: {e}")

    if app_id:
        try:
            app = await client.get_call_control_application(app_id)
            checklist["call_control_app"] = bool(app.get("active"))
            checklist["webhook_configured"] = bool(app.get("webhook_event_url"))
            ovp_on_app = (app.get("outbound") or {}).get("outbound_voice_profile_id")
            checklist["outbound_profile_on_app"] = bool(ovp_on_app)
            if ovp_on_app:
                ovp = await client.get_outbound_voice_profile(str(ovp_on_app))
                checklist["outbound_voice_profile"] = bool(ovp.get("enabled"))
                rec = ovp.get("call_recording") or {}
                checklist["call_recording_on_profile"] = rec.get("call_recording_type") == "all"
                dests = list(ovp.get("whitelisted_destinations") or [])
                checklist["whitelisted_destinations"] = dests
                checklist["international_india"] = "IN" in dests
        except TelnyxApiError as e:
            checklist["errors"].append(f"app: {e}")

    phone = client.cfg.get("phone_number") or settings.telnyx_phone_number or ""
    if phone:
        for row in await client.list_phone_numbers():
            if row.get("phone_number") == phone:
                checklist["phone_number_active"] = row.get("status") == "active"
                checklist["phone_recording_enabled"] = bool(row.get("call_recording_enabled"))
                break

    try:
        verified = await client.list_verified_numbers()
        checklist["verified_numbers"] = [v.get("phone_number") for v in verified if v.get("phone_number")]
    except TelnyxApiError as e:
        checklist["errors"].append(f"verified: {e}")

    # Trial accounts need verified destination OR account upgrade for India
    if not checklist["international_india"]:
        checklist["upgrade_required_for_india"] = True

    checklist["ready_for_us_ca"] = (
        checklist["call_control_app"]
        and checklist["webhook_configured"]
        and checklist["outbound_profile_on_app"]
        and checklist["phone_number_active"]
    )
    checklist["ready_for_india"] = checklist["ready_for_us_ca"] and checklist["international_india"]
    return checklist


async def run_standard_setup(client: TelnyxClient | None = None) -> dict[str, Any]:
    c = client or TelnyxClient()
    app = await ensure_call_control_application(c)
    status = await telnyx_setup_status(c)
    return {"ok": True, "application": app, "checklist": status}
