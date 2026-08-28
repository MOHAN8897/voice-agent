"""Probe custom stack wiring + measure latency/cost for one turn."""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

import server.app as app_mod
from server.agent.brain_prompt_composer import estimate_tokens
from server.config.env import get_settings

STACK = {
    "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
    "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    "tts": {"provider": "cartesia", "model": "sonic-3.5"},
}

# OpenAI gpt-5.6-luna short context (USD per 1M tokens) — benchmark_voice_cache.py
LLM_PRICING = {
    "input_per_m": 0.20,
    "cached_input_per_m": 0.02,
    "output_per_m": 1.20,
}


def main() -> None:
    get_settings.cache_clear()
    client = TestClient(app_mod.app)

    print("=== STACK CONNECTIVITY ===")
    cat = client.get("/api/providers/catalog")
    if cat.status_code != 200:
        print("FAIL catalog", cat.status_code)
        return
    raw = cat.json()
    providers = raw.get("providers", raw)
    if isinstance(providers, dict):
        providers = providers.get("providers", [])
    ids = [p["id"] for p in providers]
    print("providers:", ", ".join(ids))
    for need in ("sarvam", "openai", "cartesia"):
        ok = need in ids
        p = next((x for x in providers if x["id"] == need), {})
        print(f"  {need}: {'OK' if ok else 'MISSING'} configured={p.get('configured')} enabled={p.get('enabled')}")

    t0 = time.perf_counter()
    start = client.post(
        "/api/call/start",
        json={
            "sessionId": "test-studio",
            "channel": "browser",
            "tier": "medium",
            "language": "te-IN",
            "stackOverride": STACK,
        },
    )
    start_ms = (time.perf_counter() - t0) * 1000
    if start.status_code != 200:
        print("FAIL call/start", start.status_code, start.text[:300])
        return
    call = start.json()
    call_id = call["call_id"]
    rs = call.get("resolved_stack") or {}
    print(f"\ncall/start: {start_ms:.0f}ms  call_id={call_id[:8]}…")
    print("resolved STT:", rs.get("stt"))
    print("resolved LLM:", rs.get("llm"))
    print("resolved TTS:", rs.get("tts"))

    wired = (
        rs.get("stt", {}).get("provider") == "sarvam"
        and rs.get("llm", {}).get("model") == "gpt-5.6-luna"
        and rs.get("tts", {}).get("provider") == "cartesia"
    )
    print("stack_wired:", "YES" if wired else "NO")

    transcript = "Hello, what services do you offer?"

    # Brain without callId (session-only) for baseline latency
    t1b = time.perf_counter()
    brain2 = client.post(
        "/api/brain/stream",
        json={
            "transcript": transcript,
            "language_code": "te-IN",
            "sessionId": "test-studio",
        },
    )
    brain2_wall = (time.perf_counter() - t1b) * 1000
    out2 = ""
    ttft2 = None
    if brain2.status_code == 200:
        for line in brain2.text.split("\n"):
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                ev = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if ttft2 is None and (ev.get("delta") or ev.get("text")):
                ttft2 = (time.perf_counter() - t1b) * 1000
            if ev.get("delta"):
                out2 += ev["delta"]
            if ev.get("text"):
                out2 = ev["text"]

    t1 = time.perf_counter()
    brain = client.post(
        f"/api/brain/stream?callId={call_id}",
        json={
            "transcript": transcript,
            "language_code": "te-IN",
            "sessionId": "test-studio",
            "callId": call_id,
        },
    )
    brain_wall_ms = (time.perf_counter() - t1) * 1000
    out = ""
    ttft_ms = None
    if brain.status_code == 200:
        t_first = None
        for line in brain.text.split("\n"):
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                ev = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if ev.get("error"):
                print("brain error", ev["error"])
            if t_first is None and (ev.get("delta") or ev.get("text")):
                t_first = time.perf_counter()
                ttft_ms = (t_first - t1) * 1000
            if ev.get("delta"):
                out += ev["delta"]
            if ev.get("text"):
                out = ev["text"]
    else:
        print("FAIL brain", brain.status_code, brain.text[:300])

    tts_text = (out or out2 or "Hello, this is a voice test.")[:250]
    t2 = time.perf_counter()
    tts = client.post(
        "/api/tts",
        json={
            "text": tts_text,
            "language_code": "te-IN",
            "sessionId": "test-studio",
            "callId": call_id,
        },
    )
    tts_ms = (time.perf_counter() - t2) * 1000
    tts_provider = tts.headers.get("x-tts-provider", "?")
    audio_bytes = len(tts.content) if tts.status_code == 200 else 0
    audio_sec = audio_bytes / (16000 * 2) if tts_provider == "cartesia" and audio_bytes else 0

    metrics = client.get("/api/metrics")
    usage = {}
    if metrics.status_code == 200:
        mj = metrics.json()
        usage = mj.get("last_turn") or mj.get("brain") or {}

    client.post("/api/call/end", json={"callId": call_id, "reason": "probe"})

    print("\n=== LATENCY (one turn, local server) ===")
    print(f"call/start:          {start_ms:6.0f} ms")
    print(f"brain session-only:  {brain2_wall:6.0f} ms  TTFT {ttft2 or 0:.0f}ms  chars {len(out2)}")
    print(f"brain with call_id:  {brain_wall_ms:6.0f} ms  TTFT {ttft_ms or 0:.0f}ms  chars {len(out)}")
    print(f"TTS ({tts_provider}):      {tts_ms:6.0f} ms  ({audio_bytes} bytes, ~{audio_sec:.1f}s audio)")
    use_out = out or out2
    e2e_est = (ttft_ms or ttft2 or brain_wall_ms) + tts_ms
    print(f"est. voice E2E:      {e2e_est:6.0f} ms  (after STT final; STT ~300-800ms typical)")

    print("\n=== LLM OUTPUT ===")
    print(f"chars: {len(use_out)}  preview: {use_out[:120].replace(chr(10), ' ')}")

    print("\n=== TOKEN / COST ESTIMATE ===")
    brain_est = estimate_tokens(use_out) + estimate_tokens(transcript) + 1800
    out_est = estimate_tokens(use_out)
    uncached_in = brain_est
    cached_in = int(uncached_in * 0.85)
    uncached_in = uncached_in - cached_in
    cost_in = uncached_in / 1e6 * LLM_PRICING["input_per_m"]
    cost_cached = cached_in / 1e6 * LLM_PRICING["cached_input_per_m"]
    cost_out = out_est / 1e6 * LLM_PRICING["output_per_m"]
    cost_total = cost_in + cost_cached + cost_out
    print(f"brain context est: ~{brain_est} input tokens (incl. ~1800 cached brain)")
    print(f"output est:        ~{out_est} tokens")
    print(f"LLM cost/turn:     ~${cost_total:.5f}  (cached brain assumed turn 2+)")
    print(f"  input uncached:  ${cost_in:.5f}")
    print(f"  input cached:    ${cost_cached:.5f}")
    print(f"  output:          ${cost_out:.5f}")
    print("STT/TTS provider pricing (registry metadata):")
    print("  Sarvam STT realtime: ~$0.008/min")
    print("  OpenAI gpt-5.6-luna: $0.20/M input, $0.02/M cached, $1.20/M output")
    print("  Cartesia sonic-3.5:  provider billing (chars/chars-equivalent)")
    print("  Typical 1-min call:  ~$0.01 STT + ~$0.002-0.008 LLM + Cartesia TTS")

    if tts.status_code != 200:
        print("\nTTS FAIL:", tts.status_code, tts.text[:200])
    if not wired:
        sys.exit(1)


if __name__ == "__main__":
    main()
