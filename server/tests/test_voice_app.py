"""Unit tests for dedicated voice_app gateway."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server.voice_app import app

client = TestClient(app)


def test_voice_app_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["service"] == "voice_gateway"
    assert "/ws/telnyx-stream" in data["websocket_routes"]
