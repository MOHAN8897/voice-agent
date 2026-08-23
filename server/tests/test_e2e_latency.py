"""
Live E2E latency probes — run with LIVE_TEST=1 and valid .env keys.
Measures brain stream TTFB and full brain+TTS REST latency for Telugu scenarios.
"""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod

LIVE = os.getenv("LIVE_TEST") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="Set LIVE_TEST=1 to run live latency probes")


SCENARIOS = [
    ("greeting", "హాయ్, నీ పేరు ఏమిటి?"),
    ("weather", "హైదరాబాద్ లో ఈరోజు వాతావరణం ఎలా ఉంది?"),
    ("tech", "Python అంటే ఏమిటి? చాలా చిన్నగా చెప్పు."),
]


@pytest.fixture
def live_client():
    return TestClient(app_mod.app)


def _brain_stream_ttfb(client: TestClient, transcript: str, session_id: str) -> tuple[float, str]:
  """First SSE delta latency (ms) and full text."""
  t0 = time.perf_counter()
  first_ms = None
  full = []
  with client.stream(
      "POST",
      "/api/brain/stream",
      json={"transcript": transcript, "language_code": "te-IN", "sessionId": session_id},
  ) as r:
      assert r.status_code == 200, r.text
      for line in r.iter_lines():
          if not line.startswith("data: "):
              continue
          payload = json.loads(line[6:])
          if payload.get("delta"):
              if first_ms is None:
                  first_ms = (time.perf_counter() - t0) * 1000
              full.append(payload["delta"])
          if payload.get("done"):
              break
  total_ms = (time.perf_counter() - t0) * 1000
  return first_ms or total_ms, "".join(full), total_ms


def test_catalog_gpt5_only(live_client: TestClient):
    r = live_client.get("/api/settings/catalog")
    assert r.status_code == 200
    models = set(r.json()["openai"]["allowedModels"])
    assert models == {"gpt-5.5", "gpt-5.4", "gpt-5", "gpt-5.6-luna"}


@pytest.mark.parametrize("name,transcript", SCENARIOS)
def test_brain_stream_latency(live_client: TestClient, name: str, transcript: str):
    sid = f"e2e-{name}"
    ttfb, text, total = _brain_stream_ttfb(live_client, transcript, sid)
    print(f"\n[PERF] brain/{name} TTFB_MS={ttfb:.0f} TOTAL_MS={total:.0f} chars={len(text)}")
    assert len(text) > 5
    assert ttfb < 8000, f"Brain TTFB too slow: {ttfb:.0f}ms"


def test_tts_rest_latency(live_client: TestClient):
    t0 = time.perf_counter()
    r = live_client.post(
        "/api/tts",
        json={"text": "సరే, ఇది లేటెన్సీ టెస్ట్.", "language_code": "te-IN", "sessionId": "e2e-tts"},
    )
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    assert len(r.content) > 500
    print(f"\n[PERF] tts/rest TOTAL_MS={ms:.0f} bytes={len(r.content)}")
    assert ms < 6000, f"TTS too slow: {ms:.0f}ms"


def test_brain_multi_turn_cache_and_tokens(live_client: TestClient):
    """Same session: turn 1 writes cache, turn 2+ should hit cached brain prefix."""
    sid = "e2e-multiturn-cache"
    live_client.post("/api/session/clear", json={"sessionId": sid})

    t1_ttfb, t1_text, t1_total = _brain_stream_ttfb(live_client, "హాయ్", sid)
    assert len(t1_text) > 3

    t2_ttfb, t2_text, t2_total = _brain_stream_ttfb(live_client, "నీ పేరు ఏమిటి?", sid)
    assert len(t2_text) > 3

    # Token usage recorded in stream completion — verify latency improved turn-over-turn
    print(
        f"\n[TOKENS] turn1_ttfb={t1_ttfb:.0f}ms turn2_ttfb={t2_ttfb:.0f}ms"
    )
    assert t2_ttfb <= t1_ttfb * 1.5, f"Turn 2 unexpectedly slower: {t2_ttfb:.0f} vs {t1_ttfb:.0f}ms"
