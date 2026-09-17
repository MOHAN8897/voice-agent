"""Outbound dial deduplication tests."""
import time
from unittest.mock import AsyncMock

import pytest

from server.services.outbound_dial_guard import (
    STALE_RING_SEC,
    acquire_outbound_slot,
    dest_digits,
    hangup_active_telnyx_to,
    peek_reusable_telnyx_call,
    release_outbound_slot,
)


@pytest.mark.asyncio
async def test_acquire_blocks_duplicate_destination_until_released():
    dest = "+918897908470"
    ok1 = await acquire_outbound_slot("telnyx", dest)
    ok2 = await acquire_outbound_slot("telnyx", dest)
    assert ok1 is True
    assert ok2 is False
    release_outbound_slot("telnyx", dest)
    ok3 = await acquire_outbound_slot("telnyx", dest)
    assert ok3 is True
    release_outbound_slot("telnyx", dest)


@pytest.mark.asyncio
async def test_acquire_treats_e164_aliases_as_same_destination():
    ok1 = await acquire_outbound_slot("telnyx", "+918897908470")
    ok2 = await acquire_outbound_slot("telnyx", "918897908470")
    assert ok1 is True
    assert ok2 is False
    release_outbound_slot("telnyx", "8897908470")


@pytest.mark.asyncio
async def test_acquire_allows_different_destinations():
    a = await acquire_outbound_slot("telnyx", "+911111111111")
    b = await acquire_outbound_slot("telnyx", "+922222222222")
    assert a and b
    release_outbound_slot("telnyx", "+911111111111")
    release_outbound_slot("telnyx", "+922222222222")


@pytest.mark.asyncio
async def test_acquire_is_provider_scoped():
    dest = "+933333333333"
    a = await acquire_outbound_slot("telnyx", dest)
    b = await acquire_outbound_slot("exotel", dest)
    assert a and b
    release_outbound_slot("telnyx", dest)
    release_outbound_slot("exotel", dest)


def test_dest_digits_uses_last_ten():
    assert dest_digits("+918897908470") == dest_digits("918897908470")
    assert dest_digits("+91 88979 08470") == "8897908470"


@pytest.mark.asyncio
async def test_recent_ringing_call_is_reused_not_hung_up():
    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert(
            "ctl-live",
            {"to": "918897908470", "status": "initiated", "call_control_id": "ctl-live"},
        )
        reused = peek_reusable_telnyx_call("+918897908470")
        assert reused is not None
        assert reused["call_control_id"] == "ctl-live"
        client = AsyncMock()
        await hangup_active_telnyx_to(client, "+918897908470")
        client.hangup.assert_not_awaited()
    finally:
        telnyx_call_registry._calls = previous


@pytest.mark.asyncio
async def test_ringing_call_older_than_eight_seconds_is_still_reused():
    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert(
            "ctl-ring",
            {
                "to": "+918897908470",
                "status": "initiated",
                "call_control_id": "ctl-ring",
                "first_seen_at": time.time() - 30,
            },
        )
        reused = peek_reusable_telnyx_call("+918897908470")
        assert reused is not None
        assert reused["call_control_id"] == "ctl-ring"
        client = AsyncMock()
        await hangup_active_telnyx_to(client, "+918897908470")
        client.hangup.assert_not_awaited()
    finally:
        telnyx_call_registry._calls = previous


@pytest.mark.asyncio
async def test_answered_call_is_never_replaced():
    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert(
            "ctl-live",
            {
                "to": "+918897908470",
                "status": "streaming",
                "call_control_id": "ctl-live",
                "first_seen_at": time.time() - 600,
            },
        )
        reused = peek_reusable_telnyx_call("+918897908470")
        assert reused is not None
        client = AsyncMock()
        await hangup_active_telnyx_to(client, "+918897908470")
        client.hangup.assert_not_awaited()
    finally:
        telnyx_call_registry._calls = previous


@pytest.mark.asyncio
async def test_stale_ringing_call_is_replaced():
    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert(
            "ctl-old",
            {
                "to": "+918897908470",
                "status": "initiated",
                "call_control_id": "ctl-old",
                "first_seen_at": time.time() - (STALE_RING_SEC + 20),
            },
        )
        assert peek_reusable_telnyx_call("+918897908470") is None
        client = AsyncMock()
        await hangup_active_telnyx_to(client, "+918897908470")
        client.hangup.assert_awaited_once_with("ctl-old")
    finally:
        telnyx_call_registry._calls = previous


@pytest.mark.asyncio
async def test_voice_check_is_replaced_even_when_recent():
    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert(
            "ctl-check",
            {
                "to": "+918897908470",
                "status": "initiated",
                "call_control_id": "ctl-check",
                "voice_check": True,
            },
        )
        assert peek_reusable_telnyx_call("+918897908470") is None
        client = AsyncMock()
        await hangup_active_telnyx_to(client, "+918897908470")
        client.hangup.assert_awaited_once_with("ctl-check")
    finally:
        telnyx_call_registry._calls = previous
