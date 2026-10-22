"""Telnyx webhook Ed25519 signature verification (industry standard).

Telnyx signs `{timestamp}|{raw_body}` with Ed25519. Public key comes from
Mission Control → Account Settings → Keys & Credentials → Public Key.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE_SEC = 300


class TelnyxSignatureError(Exception):
    """Webhook signature missing, expired, or invalid."""


def verify_telnyx_signature(
    *,
    payload: bytes,
    signature_b64: str | None,
    timestamp: str | None,
    public_key: str | None,
    tolerance_sec: int = DEFAULT_TOLERANCE_SEC,
    now: float | None = None,
    require_key: bool = False,
) -> None:
    """Raise TelnyxSignatureError when verification fails.

    If `public_key` is empty:
      - development: skip with warning
      - production/staging (`require_key=True`): reject (fail closed)
    """
    key = (public_key or "").strip()
    if not key:
        if require_key:
            raise TelnyxSignatureError("TELNYX_PUBLIC_KEY required in this environment")
        logger.warning("[TELNYX] webhook signature skipped — TELNYX_PUBLIC_KEY not set")
        return
    if not signature_b64 or not timestamp:
        raise TelnyxSignatureError("missing telnyx-signature-ed25519 or telnyx-timestamp")
    try:
        ts = int(str(timestamp).strip())
    except ValueError as exc:
        raise TelnyxSignatureError("invalid telnyx-timestamp") from exc
    clock = now if now is not None else time.time()
    if abs(clock - ts) > max(30, int(tolerance_sec)):
        raise TelnyxSignatureError("webhook timestamp outside tolerance (possible replay)")

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover
        raise TelnyxSignatureError("cryptography package required for webhook verification") from exc

    try:
        verify_key = Ed25519PublicKey.from_public_bytes(_decode_public_key(key))
        sig = base64.b64decode(signature_b64)
        signed = f"{ts}|".encode("utf-8") + payload
        verify_key.verify(sig, signed)
    except TelnyxSignatureError:
        raise
    except InvalidSignature as exc:
        raise TelnyxSignatureError("invalid Ed25519 signature") from exc
    except Exception as exc:
        raise TelnyxSignatureError(f"signature verify failed: {exc}") from exc


def _decode_public_key(raw: str) -> bytes:
    text = raw.strip()
    # Portal keys are usually URL-safe or standard base64 of 32 bytes.
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            padded = text + ("=" * (-len(text) % 4))
            out = decoder(padded)
            if len(out) == 32:
                return out
        except Exception:
            continue
    if len(text) == 64:
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass
    raise TelnyxSignatureError("TELNYX_PUBLIC_KEY must be 32-byte Ed25519 public key (base64)")


def parse_verified_webhook_json(
    *,
    payload: bytes,
    headers: Any,
    public_key: str | None,
    require_key: bool = False,
) -> dict[str, Any]:
    """Verify signature then json-decode. Returns empty dict on empty body."""
    import json

    sig = None
    ts = None
    if headers is not None:
        get = getattr(headers, "get", None)
        if callable(get):
            sig = get("telnyx-signature-ed25519") or get("Telnyx-Signature-Ed25519")
            ts = get("telnyx-timestamp") or get("Telnyx-Timestamp")
        elif isinstance(headers, dict):
            lower = {str(k).lower(): v for k, v in headers.items()}
            sig = lower.get("telnyx-signature-ed25519")
            ts = lower.get("telnyx-timestamp")
    verify_telnyx_signature(
        payload=payload,
        signature_b64=str(sig) if sig is not None else None,
        timestamp=str(ts) if ts is not None else None,
        public_key=public_key,
        require_key=require_key,
    )
    if not payload:
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise ValueError("webhook body must be JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("webhook body must be a JSON object")
    return data
