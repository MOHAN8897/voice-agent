"""Call lifecycle package — Phase 3 (ledger A, archive, start/end)."""

from __future__ import annotations

from typing import Any

__all__ = ["call_lifecycle_service"]


def __getattr__(name: str) -> Any:
    # Lazy export avoids realtime ↔ call_lifecycle circular imports at package import time.
    if name == "call_lifecycle_service":
        from server.call.call_lifecycle_service import call_lifecycle_service

        return call_lifecycle_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
