"""Comprehensive test suite for Vobiz telephony integration and dual-infrastructure switching."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app
from server.services.dev_secrets_store import dev_secrets_store
from server.services.telephony import (
    active_telephony_provider,
    provider_configured,
    provider_enabled,
    telephony_guard_error,
)
from server.services.vobiz_client import (
    VobizCallRegistry,
    VobizClient,
    vobiz_call_registry,
    vobiz_stream_tokens,
)


def test_vobiz_provider_overlay_and_guard():
    """Verify Vobiz respects overlay flags, configuration presence, and guard errors."""
    dev_secrets_store.update({
        "enable_vobiz": True,
        "vobiz_auth_id": "MAMCK...TEST",
        "vobiz_auth_token": "secret_token_123",
        "telephony_provider": "vobiz",
    })
    try:
        assert provider_enabled("vobiz") is True
        assert provider_configured("vobiz") is True
        assert active_telephony_provider() == "vobiz"
        assert telephony_guard_error("vobiz") is None

        # When auth token is empty
        dev_secrets_store.update({"vobiz_auth_token": ""})
        assert provider_configured("vobiz") is False
        assert "missing API keys" in (telephony_guard_error("vobiz") or "")

        # When disabled
        dev_secrets_store.update({"enable_vobiz": False})
        assert provider_enabled("vobiz") is False
        assert "disabled" in (telephony_guard_error("vobiz") or "")
    finally:
        for k in ("enable_vobiz", "vobiz_auth_id", "vobiz_auth_token", "telephony_provider"):
            dev_secrets_store.remove_overlay_key(k)


def test_vobiz_stream_tokens_lifecycle():
    """Verify cryptographically signed stream tokens are strictly single-use and tamper-evident."""
    token = vobiz_stream_tokens.create(call_id="call-test-uuid-1", agent_id="agent-007", sample_rate=8000)
    assert token is not None
    assert len(token) > 20

    # Peek should return metadata without consuming the token
    peeked = vobiz_stream_tokens.peek(token)
    assert peeked is not None
    assert peeked.get("call_id") == "call-test-uuid-1"
    assert peeked.get("agent_id") == "agent-007"
    assert peeked.get("sample_rate") == 8000

    # First consume succeeds
    consumed = vobiz_stream_tokens.consume(token)
    assert consumed is not None
    assert consumed.get("call_id") == "call-test-uuid-1"

    # Second consume must fail (replay protection)
    consumed_again = vobiz_stream_tokens.consume(token)
    assert consumed_again is None

    # Invalid / tampered token fails
    assert vobiz_stream_tokens.consume("fake.invalid.token") is None


def test_vobiz_call_registry():
    """Verify in-memory Vobiz call registry lifecycle."""
    registry = VobizCallRegistry()
    registry.upsert(
        call_uuid="call-vobiz-999",
        updates={
            "direction": "inbound",
            "from_number": "+15551234567",
            "to_number": "+15557654321",
            "status": "in-progress",
            "session_id": "sess-999",
        },
    )
    item = registry.get("call-vobiz-999")
    assert item is not None
    assert item["direction"] == "inbound"
    assert item["status"] == "in-progress"

    registry.upsert("call-vobiz-999", {"status": "completed", "duration_s": 42})
    updated = registry.get("call-vobiz-999")
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["duration_s"] == 42


@pytest.mark.asyncio
async def test_vobiz_answer_webhook_returns_valid_xml():
    """Verify POST /api/vobiz/answer generates valid VoiceXML with WebSocket stream instructions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Simulate incoming Vobiz call answer POST
        res = await client.post(
            "/api/vobiz/answer",
            data={
                "CallUUID": "vobiz-call-abc-123",
                "From": "+15559998888",
                "To": "+15551112222",
                "Direction": "inbound",
                "CallStatus": "ringing",
            },
        )
        assert res.status_code == 200
        assert "application/xml" in res.headers["content-type"]
        xml_text = res.text
        assert "<Response>" in xml_text
        assert "</Response>" in xml_text
        assert '<Stream bidirectional="true"' in xml_text
        assert "ws/vobiz-stream?token=" in xml_text


@pytest.mark.asyncio
async def test_vobiz_fallback_webhook():
    """Verify POST /api/vobiz/fallback returns graceful XML message and hangup."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post(
            "/api/vobiz/fallback",
            data={
                "CallUUID": "vobiz-call-abc-123",
                "From": "+15559998888",
                "To": "+15551112222",
                "ErrorMessage": "Primary answer URL timed out",
            },
        )
        assert res.status_code == 200
        assert "application/xml" in res.headers["content-type"]
        assert "<Speak>" in res.text
        assert "<Hangup" in res.text


@pytest.mark.asyncio
async def test_vobiz_hangup_webhook():
    """Verify POST /api/vobiz/hangup cleans up call registry and accepts call end notifications."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post(
            "/api/vobiz/hangup",
            data={
                "CallUUID": "vobiz-call-abc-123",
                "Duration": "45",
                "HangupCause": "NORMAL_CLEARING",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True
        assert data.get("call_uuid") == "vobiz-call-abc-123"


@pytest.mark.asyncio
async def test_vobiz_client_balance():
    """Verify VobizClient get_balance returns structured balance dict."""
    client = VobizClient()
    bal = await client.get_balance()
    assert bal.get("ok") is True
    assert "balance" in bal


@pytest.mark.asyncio
async def test_vobiz_numbers_search_and_provision():
    """Verify VobizClient number search and ordering flows."""
    client = VobizClient()
    numbers = await client.search_available_numbers(country="IN", limit=3)
    assert len(numbers) > 0
    first = numbers[0]
    assert first["country"] == "IN"
    assert first["provider"] == "vobiz"
    assert first["e164"].startswith("+")

    prov = await client.provision_ordered_number(first["e164"])
    assert prov.get("ok") is True
    assert prov.get("provider") == "vobiz"
    assert prov.get("e164") == first["e164"]


def test_vobiz_xml_escaping_prevents_parse_errors():
    """Verify stream URL query parameters are XML escaped (&amp;) preventing FreeSWITCH parse errors."""
    from server.routes.vobiz import _build_vobiz_xml_response

    test_url = "wss://api-dev.hustlelabs.in/ws/vobiz-stream?token=abc123xyz&call_uuid=uuid-456&agent=ag-1"
    resp = _build_vobiz_xml_response(test_url)
    assert resp.status_code == 200
    xml_str = resp.body.decode("utf-8")
    assert "&amp;" in xml_str
    assert "token=abc123xyz&amp;call_uuid=uuid-456&amp;agent=ag-1" in xml_str
    # Raw unescaped ampersand must not exist outside of XML entities
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_str)
    assert root.tag == "Response"
    stream_node = root.find("Stream")
    assert stream_node is not None
    assert stream_node.text == test_url


def test_tenant_dial_error_sanitization():
    """Verify internal carrier error messages and stack traces never leak to tenant callers."""
    from server.services.saas.telephony_orchestrator import _sanitize_tenant_dial_error

    carrier_leak = "Vobiz API 401: {'error': 'Invalid X-Auth-Token or secret key', 'account_id': 12345}"
    sanitized = _sanitize_tenant_dial_error(carrier_leak)
    assert "X-Auth-Token" not in sanitized
    assert "secret" not in sanitized
    assert "12345" not in sanitized
    assert "Unable to connect call" in sanitized

    balance_leak = "Carrier prepaid balance exhausted ($0.00 left on Vobiz account)"
    sanitized_bal = _sanitize_tenant_dial_error(balance_leak)
    assert "Vobiz account" not in sanitized_bal
    assert "support" in sanitized_bal

