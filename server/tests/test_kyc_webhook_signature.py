"""Webhook signature + dispatch tests for Didit KYC.

These prove the security-critical part: that an unsigned or forged webhook cannot
mark a user verified.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import pytest

from server.config.env import get_settings
from server.services.saas import kyc_service


def _canonical(payload: dict) -> str:
    return json.dumps(
        kyc_service.sort_keys(kyc_service.shorten_floats(payload)),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _sign(payload: dict, secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), _canonical(payload).encode(), hashlib.sha256).hexdigest()
    return digest, ts


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "didit_webhook_secret", "test-secret", raising=False)
    yield


def test_shorten_floats_makes_whole_floats_ints():
    # Didit canonicalises 1.0 to 1 before signing.
    assert kyc_service.shorten_floats({"score": 1.0}) == {"score": 1}
    assert kyc_service.shorten_floats({"score": 0.55}) == {"score": 0.55}


def test_sort_keys_is_recursive_and_preserves_arrays():
    out = kyc_service.sort_keys({"b": 1, "a": {"d": 2, "c": [{"z": 1, "y": 2}]}})
    assert list(out) == ["a", "b"]
    assert list(out["a"]) == ["c", "d"]
    # Array order is meaningful and must survive.
    assert out["a"]["c"] == [{"y": 2, "z": 1}]


def test_valid_signature_is_accepted():
    payload = {"event_id": str(uuid.uuid4()), "status": "Approved"}
    sig, ts = _sign(payload, "test-secret")
    kyc_service.verify_signature(json.dumps(payload), sig, ts)


def test_missing_signature_is_rejected():
    with pytest.raises(kyc_service.KycSignatureError):
        kyc_service.verify_signature("{}", "", str(int(time.time())))


def test_wrong_secret_is_rejected():
    payload = {"event_id": "e1", "status": "Approved"}
    sig, ts = _sign(payload, "attacker-secret")
    with pytest.raises(kyc_service.KycSignatureError):
        kyc_service.verify_signature(json.dumps(payload), sig, ts)


def test_tampered_body_is_rejected():
    """The classic attack: sign a benign payload, deliver a different one."""
    benign = {"event_id": "e1", "status": "In Progress"}
    sig, ts = _sign(benign, "test-secret")
    tampered = {"event_id": "e1", "status": "Approved"}
    with pytest.raises(kyc_service.KycSignatureError):
        kyc_service.verify_signature(json.dumps(tampered), sig, ts)


def test_stale_timestamp_is_rejected():
    """Replay protection: a captured webhook cannot be replayed an hour later."""
    payload = {"event_id": "e1", "status": "Approved"}
    sig, _ = _sign(payload, "test-secret")
    old = str(int(time.time()) - 400)
    with pytest.raises(kyc_service.KycSignatureError):
        kyc_service.verify_signature(json.dumps(payload), sig, old)


def test_unicode_is_not_escaped_in_canonical_form():
    """unescaped Unicode is part of the contract; escaping it breaks the HMAC."""
    payload = {"event_id": "e1", "status": "Approved", "name": "Zoë"}
    assert "Zoë" in _canonical(payload)
    assert "\\u00eb" not in _canonical(payload)


#: Every literal Didit can send. Comparing case-sensitively against this set is
#: what stops a typo'd constant from becoming an unreachable branch.
DIDIT_STATUSES = {
    "Not Started",
    "In Progress",
    "Awaiting User",
    "In Review",
    "Approved",
    "Declined",
    "Resubmitted",
    "Abandoned",
    "Expired",
    "Kyc Expired",
}


def test_service_constants_cover_every_didit_status():
    declared = {
        value
        for name, value in vars(kyc_service).items()
        if name.startswith("STATUS_") and isinstance(value, str)
    }
    assert declared == DIDIT_STATUSES, f"drifted literals: {declared ^ DIDIT_STATUSES}"


def test_event_id_dedupes_a_redelivery():
    kyc_service._applied_events.clear()
    event_id = str(uuid.uuid4())
    assert kyc_service.already_applied(event_id) is False
    kyc_service.mark_applied(event_id)
    assert kyc_service.already_applied(event_id) is True