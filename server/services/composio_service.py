"""Composio Tooling & Multi-Tenant Integration Gateway (Superseded & Powered by Nango)."""
from __future__ import annotations

from typing import Any

from server.services.nango_service import NangoService, nango_service


class ComposioService(NangoService):
    """Composio compatibility facade directing all integration actions to Nango."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key=api_key)
        self._toolset: Any = None

    @property
    def toolset(self) -> Any:
        return self._toolset


composio_service = nango_service
