"""Plivo HTTP webhooks — answer, hangup, stream-status."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from server.config.env import get_settings

router = APIRouter()

# In-memory stream tokens for WSS binding (production: Redis)
_stream_tokens: dict[str, dict[str, Any]] = {}


def _validate_plivo_signature(request: Request, body: bytes) -> bool:
    settings = get_settings()
    if not settings.plivo_auth_token:
        return settings.app_environment == "development"
    sig = request.headers.get("X-Plivo-Signature-V2") or request.headers.get("X-Plivo-Signature")
    if not sig:
        return settings.app_environment == "development"
    url = settings.plivo_webhook_base_url or str(request.url).split("?")[0]
    nonce = request.headers.get("X-Plivo-Signature-V2-Nonce") or ""
    digest = hmac.new(
        settings.plivo_auth_token.encode(),
        (url + nonce).encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, sig)


def _stream_ws_url(call_uuid: str) -> str:
    settings = get_settings()
    base = settings.plivo_public_base_url or settings.plivo_webhook_base_url or "http://localhost:8000"
    token = secrets.token_urlsafe(24)
    _stream_tokens[token] = {"call_uuid": call_uuid, "expires": None}
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/ws/plivo-stream?token={token}&call_uuid={call_uuid}"


@router.api_route("/api/plivo/answer", methods=["GET", "POST"])
async def plivo_answer(request: Request):
    body = await request.body()
    if not _validate_plivo_signature(request, body):
        return PlainTextResponse("invalid signature", status_code=403)
    call_uuid = request.query_params.get("CallUUID") or request.query_params.get("call_uuid") or str(uuid.uuid4())
    ws_url = _stream_ws_url(call_uuid)
    xml = (
        f"<Response><Stream bidirectional=\"true\" keepCallAlive=\"true\" "
        f"contentType=\"audio/x-mulaw;rate=8000\">{ws_url}</Stream></Response>"
    )
    return Response(content=xml, media_type="application/xml")


@router.post("/api/plivo/hangup")
async def plivo_hangup(request: Request):
    body = await request.body()
    if not _validate_plivo_signature(request, body):
        return PlainTextResponse("invalid signature", status_code=403)
    return {"ok": True}


@router.post("/api/plivo/stream-status")
async def plivo_stream_status(request: Request):
    body = await request.body()
    if not _validate_plivo_signature(request, body):
        return PlainTextResponse("invalid signature", status_code=403)
    return {"ok": True}


@router.get("/api/plivo/status")
async def plivo_status():
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    auth_id = dev_secrets_store.effective_secret("plivo_auth_id") or settings.plivo_auth_id
    auth_token = dev_secrets_store.effective_secret("plivo_auth_token") or settings.plivo_auth_token
    configured = bool(auth_id and auth_token)
    enabled = bool(dev_secrets_store.effective("enable_plivo", settings.enable_plivo))
    webhook = dev_secrets_store.effective("plivo_webhook_base_url", settings.plivo_webhook_base_url)
    number = dev_secrets_store.effective("plivo_number", settings.plivo_number)
    return {
        "enabled": enabled,
        "configured": configured,
        "webhook_base": webhook or None,
        "number": number or None,
    }


def validate_stream_token(token: str, call_uuid: str | None) -> bool:
    entry = _stream_tokens.get(token)
    if not entry:
        return False
    if call_uuid and entry.get("call_uuid") != call_uuid:
        return False
    return True
