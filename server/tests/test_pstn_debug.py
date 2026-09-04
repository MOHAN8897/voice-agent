"""Tests for PSTN lifecycle debug logging helpers."""
from server.services.pstn_debug import clear, elapsed_ms, mark


def test_pstn_debug_timer():
    key = "test-call-1"
    clear(key)
    assert elapsed_ms(key) is None
    mark(key)
    ms = elapsed_ms(key)
    assert ms is not None
    assert ms >= 0
    clear(key)
    assert elapsed_ms(key) is None
