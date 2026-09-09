"""Outbound dial deduplication tests."""
import asyncio

import pytest

from server.services.outbound_dial_guard import (
    acquire_outbound_slot,
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
