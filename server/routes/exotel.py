"""Exotel HTTP webhooks — passthru + status callback + stream URL resolver."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from server.config.env import get_settings
from server.services.exotel_call_registry import exotel_call_registry
from server.services.exotel_client import (
    ExotelClient,
    build_stream_ws_url,
    cached_handshake,
    exotel_enabled,
    public_webhook_urls,
    webhook_base_url,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _form_dict(request: Request, body: bytes) -> dict[str, Any]:
    if request.query_params:
        return dict(request.query_params)
    text = body.decode(errors="ignore").strip()
    if not text:
        return {}
    out: dict[str, Any] = {}
    for part in text.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k] = v
    return out


def _parse_custom_field(custom_field: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not custom_field:
        return out
    for part in str(custom_field).split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


async def _handshake_status() -> tuple[bool, str | None, str | None]:
    handshake_ok = False
    handshake_error: str | None = None
    balance: str | None = None
    if not exotel_enabled():
        return False, "ENABLE_EXOTEL is false", None
    try:
        hs = await cached_handshake()
        handshake_ok = bool(hs.get("ok"))
        balance = hs.get("balance")
    except Exception as e:
        handshake_error = str(e)[:300]
    return handshake_ok, handshake_error, balance


@router.get("/api/exotel/status")
async def exotel_status():
    from server.config.urls import public_api_base, public_app_base
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.exotel_client import _resolve_exotel_config

    settings = get_settings()
    enabled = exotel_enabled()
    configured = False
    handshake_ok, handshake_error, balance = await _handshake_status()

    try:
        _resolve_exotel_config()
        configured = True
    except Exception as e:
        if not handshake_error:
            handshake_error = str(e)[:300]

    urls = public_webhook_urls()
    return {
        "enabled": enabled,
        "configured": configured,
        "handshake_ok": handshake_ok,
        "handshake_error": handshake_error,
        "balance": balance,
        "webhook_base": webhook_base_url(),
        "public_api_url": public_api_base(),
        "public_app_url": public_app_base(),
        "account_sid": dev_secrets_store.effective("exotel_account_sid", settings.exotel_account_sid),
        "exophone": dev_secrets_store.effective("exotel_exophone", settings.exotel_exophone),
        "subdomain": dev_secrets_store.effective("exotel_subdomain", settings.exotel_subdomain),
        **urls,
        "ready": enabled and configured and handshake_ok and bool(urls.get("passthru_url")),
    }


@router.api_route("/api/exotel/stream-url", methods=["GET", "POST"])
async def exotel_stream_url(request: Request):
    """
    Dynamic WSS resolver for Exotel Voicebot applet.
    Returns {"url": "wss://..."} per AgentStream docs.
    """
    agent_id = request.query_params.get("agentId") or request.query_params.get("agent_id")
    tier = request.query_params.get("tier")
    if request.method == "POST":
        body = await request.body()
        fields = _form_dict(request, body)
        agent_id = agent_id or fields.get("agentId") or fields.get("agent_id")
        tier = tier or fields.get("tier")
    url = build_stream_ws_url(agent_id=agent_id, tier=tier)
    if not url:
        return JSONResponse({"error": "EXOTEL_WEBHOOK_BASE_URL not set"}, status_code=503)
    return {"url": url}


@router.api_route("/api/exotel/passthru", methods=["GET", "POST"])
async def exotel_passthru(request: Request):
    """
    Passthru applet webhook — return 200 to route call to Choice A in Exotel flow.
    https://developer.exotel.com/docs/voice-v1/applets/passthru
    """
    body = await request.body()
    fields = _form_dict(request, body)
    call_sid = str(fields.get("CallSid") or fields.get("callsid") or "")
    if call_sid:
        exotel_call_registry.upsert(
            call_sid,
            {
                "status": "passthru",
                "direction": fields.get("Direction") or fields.get("CallType"),
                "from": fields.get("From") or fields.get("CallFrom"),
                "to": fields.get("To") or fields.get("CallTo"),
                "exophone": fields.get("DialWhomNumber") or fields.get("CallerId"),
                "last_event": "passthru",
            },
        )
    logger.info("[EXOTEL] passthru call_sid=%s from=%s", call_sid[:16], fields.get("From"))
    return Response(status_code=200)


@router.api_route("/api/exotel/status-callback", methods=["GET", "POST"])
async def exotel_status_callback(request: Request):
    """StatusCallback webhook — terminal + answered events."""
    body = await request.body()
    fields = _form_dict(request, body)
    call_sid = str(fields.get("CallSid") or fields.get("callsid") or "")
    status = fields.get("Status") or fields.get("EventType") or fields.get("status")
    custom_field = fields.get("CustomField") or fields.get("customfield")
    custom = _parse_custom_field(str(custom_field) if custom_field else None)

    if call_sid:
        patch: dict[str, Any] = {
            "status": status,
            "direction": fields.get("Direction"),
            "from": fields.get("From"),
            "to": fields.get("To"),
            "duration": fields.get("ConversationDuration") or fields.get("Duration"),
            "recording_url": fields.get("RecordingUrl"),
            "custom_field": custom_field,
            "last_event": fields.get("EventType") or "status-callback",
        }
        if custom.get("agent"):
            patch["agent_id"] = custom["agent"]
        if custom.get("tier"):
            patch["tier"] = custom["tier"]
        exotel_call_registry.upsert(call_sid, patch)

        st = str(status or "").lower()
        if st in ("completed", "failed", "busy", "no-answer", "canceled"):
            local = exotel_call_registry.get(call_sid) or {}
            internal_id = local.get("internal_call_id")
            if internal_id:
                from server.call.call_lifecycle_service import call_lifecycle_service

                try:
                    await call_lifecycle_service.end(str(internal_id), reason="pstn_hangup")
                except Exception:
                    pass

    logger.info(
        "[EXOTEL] status-callback call_sid=%s status=%s",
        call_sid[:16] if call_sid else "?",
        status,
    )
    return PlainTextResponse("OK")
