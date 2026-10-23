"""Razorpay webhook security and exactly-once delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.db.models.saas_models import RazorpayWebhookEvent
from server.routes import razorpay_webhook as webhook
from server.services.saas import razorpay_service

SECRET = "whsec_test_secret"


def _sign(raw: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_webhook_signature_requires_a_secret_and_exact_body():
    raw = b'{"event":"payment.captured"}'
    signature = _sign(raw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
        assert razorpay_service.verify_webhook_signature(raw, signature) is True
        assert razorpay_service.verify_webhook_signature(raw + b" ", signature) is False
        assert razorpay_service.verify_webhook_signature(raw, None) is False

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=""))
        assert razorpay_service.verify_webhook_signature(raw, signature) is False


class _Request:
    def __init__(self, raw: bytes, headers: dict[str, str]):
        self._raw = raw
        self.headers = headers

    async def body(self):
        return self._raw


class _SharedStore(dict):
    pass


class _WebhookSession:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, model, ident, **_kwargs):
        if model is RazorpayWebhookEvent:
            return self.store.get(ident)
        return None

    def add(self, obj):
        if isinstance(obj, RazorpayWebhookEvent):
            self.store[obj.event_id] = obj

    async def commit(self):
        pass


def _factory(store):
    return lambda: _WebhookSession(store)


@pytest.mark.asyncio
async def test_webhook_fails_closed_when_the_secret_is_missing(monkeypatch):
    raw = b'{"event":"payment.captured"}'
    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=""))

    with pytest.raises(HTTPException) as caught:
        await webhook.razorpay_webhook(_Request(raw, {}))

    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_webhook_rejects_an_invalid_signature_before_reading_the_store(monkeypatch):
    raw = b'{"event":"payment.captured"}'
    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(webhook, "get_session_factory", lambda: _factory({}))

    with pytest.raises(HTTPException) as caught:
        await webhook.razorpay_webhook(_Request(raw, {"X-Razorpay-Signature": "bad"}))

    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_captured_payment_is_credited_once_even_if_delivered_twice(monkeypatch):
    store = _SharedStore()
    payload = {
        "event": "payment.captured",
        "created_at": 1_700_000_000,
        "payload": {"payment": {"entity": {"id": "pay_1", "order_id": "order_1", "status": "captured"}}},
    }
    raw = json.dumps(payload).encode()
    headers = {
        "X-Razorpay-Signature": _sign(raw),
        "X-Razorpay-Event-Id": "evt_1",
    }

    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(webhook, "get_session_factory", lambda: _factory(store))
    credit = AsyncMockRecorder()
    monkeypatch.setattr(webhook, "credit_provider_payment", credit)

    first = await webhook.razorpay_webhook(_Request(raw, headers))
    second = await webhook.razorpay_webhook(_Request(raw, headers))

    assert first == {"ok": True, "status": "handled"}
    assert second == {"ok": True, "duplicate": True, "status": "handled"}
    assert credit.calls == [
        ({"id": "pay_1", "order_id": "order_1", "status": "captured"},)
    ]
    assert credit.kwargs_calls == [{"source": "webhook"}]
    assert store["evt_1"].status == "handled"
    assert store["evt_1"].processed_at is not None


@pytest.mark.asyncio
async def test_failed_payment_marks_the_order_without_crediting(monkeypatch):
    store = _SharedStore()
    payload = {
        "event": "payment.failed",
        "created_at": 1_700_000_000,
        "payload": {"payment": {"entity": {"id": "pay_2", "order_id": "order_2", "status": "failed"}}},
    }
    raw = json.dumps(payload).encode()
    headers = {"X-Razorpay-Signature": _sign(raw), "X-Razorpay-Event-Id": "evt_2"}

    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(webhook, "get_session_factory", lambda: _factory(store))
    failed = AsyncMockRecorder()
    credited = AsyncMockRecorder()
    monkeypatch.setattr(webhook, "mark_order_failed", failed)
    monkeypatch.setattr(webhook, "credit_provider_payment", credited)

    result = await webhook.razorpay_webhook(_Request(raw, headers))

    assert result == {"ok": True, "status": "handled"}
    assert failed.calls == [
        ({"id": "pay_2", "order_id": "order_2", "status": "failed"},)
    ]
    assert failed.kwargs_calls == [{"source": "webhook"}]
    assert credited.calls == []


@pytest.mark.asyncio
async def test_refund_processed_webhook_reverses_the_original_payment(monkeypatch):
    store = _SharedStore()
    payload = {
        "event": "refund.processed",
        "created_at": 1_700_000_000,
        "payload": {
            "refund": {
                "entity": {
                    "id": "rfnd_1",
                    "payment_id": "pay_1",
                    "amount": 59000,
                    "currency": "INR",
                    "notes": {"reason": "Customer cancelled"},
                }
            }
        },
    }
    raw = json.dumps(payload).encode()
    headers = {"X-Razorpay-Signature": _sign(raw)}

    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(webhook, "get_session_factory", lambda: _factory(store))
    refund = AsyncMockRecorder(return_value={"ok": True})
    monkeypatch.setattr(webhook, "apply_refund", refund)

    result = await webhook.razorpay_webhook(_Request(raw, headers))

    assert result == {"ok": True, "status": "handled"}
    assert refund.kwargs_calls == [
        {
            "refund_id": "rfnd_1",
            "payment_id": "pay_1",
            "amount_minor": 59000,
            "currency": "INR",
            "reason": "Customer cancelled",
            "created_by": None,
            "status": "processed",
        }
    ]


@pytest.mark.asyncio
async def test_unknown_order_event_is_acknowledged_as_ignored(monkeypatch):
    store = _SharedStore()
    payload = {
        "event": "payment.captured",
        "created_at": 1_700_000_000,
        "payload": {"payment": {"entity": {"id": "pay_x", "order_id": "order_unknown"}}},
    }
    raw = json.dumps(payload).encode()
    headers = {"X-Razorpay-Signature": _sign(raw), "X-Razorpay-Event-Id": "evt_unknown"}

    class CreditFail:
        calls = []

        async def __call__(self, *_args, **_kwargs):
            raise ValueError("order_not_found")

    monkeypatch.setattr(webhook, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(razorpay_service, "get_settings", lambda: SimpleNamespace(razorpay_webhook_secret=SECRET))
    monkeypatch.setattr(webhook, "get_session_factory", lambda: _factory(store))
    monkeypatch.setattr(webhook, "credit_provider_payment", CreditFail())

    result = await webhook.razorpay_webhook(_Request(raw, headers))

    assert result == {"ok": True, "status": "ignored"}
    assert store["evt_unknown"].status == "ignored"


class AsyncMockRecorder:
    """Minimal async double that records positional and keyword calls."""

    def __init__(self, return_value=None):
        self.return_value = return_value if return_value is not None else {"ok": True}
        self.calls = []
        self.kwargs_calls = []

    async def __call__(self, *args, **kwargs):
        if args:
            self.calls.append(args)
        if kwargs:
            self.kwargs_calls.append(kwargs)
        return self.return_value
