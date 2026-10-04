"""Unit tests for post-call recovery and durable finalization tracking."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from server.call.post_call_pipeline import recover_pending_post_calls


@pytest.mark.asyncio
async def test_recover_pending_post_calls_reenqueues():
    mock_calls = [
        {"call_id": "call-1", "finalization_status": "pending"},
        {"call_id": "call-2", "finalization_status": "processing"},
    ]
    with patch("server.call.call_store.call_store.list_pending_finalization", AsyncMock(return_value=mock_calls)):
        with patch("server.call.post_call_pipeline.enqueue", AsyncMock()) as mock_enqueue:
            count = await recover_pending_post_calls()
            assert count == 2
            assert mock_enqueue.call_count == 2
            mock_enqueue.assert_any_call("call-1", force=True)
            mock_enqueue.assert_any_call("call-2", force=True)


@pytest.mark.asyncio
async def test_recover_pending_post_calls_empty():
    with patch("server.call.call_store.call_store.list_pending_finalization", AsyncMock(return_value=[])):
        with patch("server.call.post_call_pipeline.enqueue", AsyncMock()) as mock_enqueue:
            count = await recover_pending_post_calls()
            assert count == 0
            mock_enqueue.assert_not_called()
