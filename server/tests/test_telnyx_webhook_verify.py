"""Telnyx webhook signature verification tests."""
from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from server.services.telnyx_webhook_verify import (
    TelnyxSignatureError,
    parse_verified_webhook_json,
    verify_telnyx_signature,
)


def _sign(payload: bytes, ts: int, private_key: Ed25519PrivateKey) -> tuple[str, str, str]:
    signed = f"{ts}|".encode("utf-8") + payload
    sig = private_key.sign(signed)
    pub = base64.b64encode(private_key.public_key().public_bytes_raw()).decode("ascii")
    return base64.b64encode(sig).decode("ascii"), str(ts), pub


def test_verify_valid_signature():
    key = Ed25519PrivateKey.generate()
    body = json.dumps({"data": {"event_type": "call.answered"}}).encode()
    ts = int(time.time())
    sig, ts_s, pub = _sign(body, ts, key)
    verify_telnyx_signature(payload=body, signature_b64=sig, timestamp=ts_s, public_key=pub)


def test_reject_bad_signature():
    key = Ed25519PrivateKey.generate()
    body = b'{"data":{"event_type":"call.answered"}}'
    ts = int(time.time())
    _, ts_s, pub = _sign(body, ts, key)
    with pytest.raises(TelnyxSignatureError):
        verify_telnyx_signature(
            payload=body,
            signature_b64=base64.b64encode(b"x" * 64).decode(),
            timestamp=ts_s,
            public_key=pub,
        )


def test_reject_stale_timestamp():
    key = Ed25519PrivateKey.generate()
    body = b"{}"
    ts = int(time.time()) - 10_000
    sig, ts_s, pub = _sign(body, ts, key)
    with pytest.raises(TelnyxSignatureError):
        verify_telnyx_signature(payload=body, signature_b64=sig, timestamp=ts_s, public_key=pub)


def test_parse_verified_roundtrip():
    key = Ed25519PrivateKey.generate()
    body = json.dumps({"data": {"event_type": "call.initiated", "payload": {"call_control_id": "c1"}}}).encode()
    ts = int(time.time())
    sig, ts_s, pub = _sign(body, ts, key)
    parsed = parse_verified_webhook_json(
        payload=body,
        headers={"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts_s},
        public_key=pub,
    )
    assert parsed["data"]["event_type"] == "call.initiated"


def test_skip_when_public_key_missing():
    verify_telnyx_signature(payload=b"{}", signature_b64=None, timestamp=None, public_key=None)


def test_require_key_fail_closed():
    with pytest.raises(TelnyxSignatureError):
        verify_telnyx_signature(
            payload=b"{}",
            signature_b64=None,
            timestamp=None,
            public_key=None,
            require_key=True,
        )
