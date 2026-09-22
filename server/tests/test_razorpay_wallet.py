"""Razorpay wallet order + signature verification (mocked)."""
from __future__ import annotations

import hashlib
import hmac
import uuid
from unittest.mock import MagicMock, patch

import pytest

from server.services.saas.razorpay_service import verify_payment_signature


def test_verify_payment_signature_valid():
    order_id = "order_test123"
    payment_id = "pay_test456"
    secret = "test_secret"
    body = f"{order_id}|{payment_id}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    with patch("server.services.saas.razorpay_service.get_settings") as gs:
        gs.return_value = MagicMock(razorpay_api_secret=secret)
        assert verify_payment_signature(order_id, payment_id, sig) is True


def test_verify_payment_signature_rejects_tamper():
    with patch("server.services.saas.razorpay_service.get_settings") as gs:
        gs.return_value = MagicMock(razorpay_api_secret="secret")
        assert verify_payment_signature("o", "p", "bad") is False
