"""Razorpay wallet order + signature verification (mocked)."""
from __future__ import annotations

import hashlib
import hmac
import asyncio
import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

from server.services.saas.razorpay_service import (
    _run_provider_call,
    _validate_payment_details,
    verify_payment_signature,
)


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


def test_provider_payment_must_match_order_amount_currency_and_capture_state():
    _validate_payment_details(
        {
            "order_id": "order_1",
            "status": "captured",
            "amount": 12500,
            "currency": "INR",
        },
        order_id="order_1",
        currency="INR",
        amount_minor=12500,
    )

    for details, error in (
        ({"order_id": "order_other"}, "payment_order_mismatch"),
        ({"status": "authorized"}, "payment_not_captured"),
        ({"amount": 12499}, "payment_amount_mismatch"),
        ({"currency": "USD"}, "payment_currency_mismatch"),
    ):
        with pytest.raises(ValueError, match=error):
            _validate_payment_details(
                details,
                order_id="order_1",
                currency="INR",
                amount_minor=12500,
            )


@pytest.mark.asyncio
async def test_blocking_provider_call_runs_off_the_event_loop_thread():
    event_loop_thread = threading.get_ident()

    result = await _run_provider_call(threading.get_ident)

    assert result != event_loop_thread
