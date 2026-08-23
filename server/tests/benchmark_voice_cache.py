"""
VOICE AGENT — Multi-turn latency, token & prompt cache benchmark.

BENCHMARK ONLY — does not modify production code.
Run: python server/tests/benchmark_voice_cache.py

Requires valid .env API keys and network access.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

# Project root on path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import server.app as app_mod  # noqa: E402
from server.agent.brain_prompt_composer import compose_brain_prompt, estimate_tokens  # noqa: E402
from server.config.constants import constants  # noqa: E402
from server.config.env import get_settings  # noqa: E402
from server.services.prompt_cache_key import compute_cache_key  # noqa: E402
from server.services.brain_budget import resolve_brain_budget  # noqa: E402

# OpenAI published pricing — gpt-5.6-luna short context (Aug 2026)
# Source: https://developers.openai.com/api/docs/pricing
PRICING = {
    "input_per_m": 0.20,
    "cached_input_per_m": 0.02,
    "cache_write_per_m": 0.25,
    "output_per_m": 1.20,
    "source": "OpenAI API pricing docs (gpt-5.6-luna, short context)",
}

TURNS_20 = [
    "నా పేరు సాయి.",
    "నేను హైదరాబాద్‌లో ఉంటాను.",
    "నాకు trading గురించి తెలుసుకోవాలి.",
    "Options అంటే ఏమిటి?",
    "Nifty options ఎలా పని చేస్తాయి?",
    "Call option అంటే ఏమిటి?",
    "Put option అంటే?",
    "Premium అంటే ఏమిటి?",
    "Strike price అంటే?",
    "Expiry అంటే?",
    "ATM అంటే ఏమిటి?",
    "ITM అంటే?",
    "OTM అంటే?",
    "Risk ఎలా ఉంటుంది?",
    "Beginner అయితే ఏం నేర్చుకోవాలి?",
    "ఒక simple example చెప్పు.",
    "మళ్లీ shortగా explain చేయి.",
    "నా పేరు గుర్తుందా?",
    "నేను ఎక్కడ ఉంటానని చెప్పాను?",
    "ఇప్పటివరకు మనం ఏం మాట్లాడుకున్నాం?",
]

TURNS_50_EXTRA = [
    "Intraday అంటే ఏమిటి?",
    "Delivery trading అంటే?",
    "Stop loss అంటే?",
    "Target price అంటే?",
    "Volume అంటే?",
    "Liquidity అంటే?",
    "Brokerage ఎంత ఉంటుంది?",
    "Demat account అవసరమా?",
    "Margin అంటే?",
    "Leverage అంటే?",
    "Hedging అంటే?",
    "Portfolio అంటే?",
    "Diversification అంటే?",
    "Bull market అంటే?",
    "Bear market అంటే?",
    "Index fund అంటే?",
    "Mutual fund అంటే?",
    "SIP అంటే?",
    "Tax on trading?",
    "Long term vs short term?",
    "Chart reading basics?",
    "Support level అంటే?",
    "Resistance అంటే?",
    "Trend line అంటే?",
    "Candlestick అంటే?",
    "Green candle అంటే?",
    "Red candle అంటే?",
    "Breakout అంటే?",
    "Pullback అంటే?",
    "Volatility అంటే?",
]


@dataclass
class TurnResult:
    turn: int
    session_id: str
    transcript: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    uncached_tokens: int | None = None
    cache_ratio: float | None = None
    ttft_ms: float | None = None
    total_latency_ms: float | None = None
    brain_est: int | None = None
    history_est: int | None = None
    transcript_est: int | None = None
    model: str | None = None
    request_id: str | None = None
    response_chars: int = 0
    error: str | None = None
    cache_state: str = "unknown"  # hit | miss | partial | unknown


@dataclass
class BenchmarkRun:
    label: str
    session_id: str
    turns: list[TurnResult] = field(default_factory=list)


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "NOT AVAILABLE"


def collect_environment(client: TestClient) -> dict:
    settings = get_settings()
    brain = compose_brain_prompt()
    brain_est = estimate_tokens(brain)
    budget = resolve_brain_budget("default")
    cache_key = compute_cache_key(brain, budget)
    eff = client.get("/api/prompt/effective", params={"sessionId": "benchmark-env", "transcript": "test"}).json()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": settings.openai_model,
        "server_version": constants.APP_VERSION,
        "git_commit": _git_commit(),
        "brain_prompt_estimated_tokens": brain_est,
        "brain_prompt_budget": budget,
        "max_output_tokens": settings.max_response_length,
        "reasoning": "none (gpt-5.6-luna voice_optimized)",
        "enable_prompt_caching": settings.enable_prompt_caching,
        "prompt_cache_ttl": settings.prompt_cache_ttl,
        "prompt_cache_min_tokens": settings.prompt_cache_min_tokens,
        "prompt_cache_key_prefix": settings.prompt_cache_key_prefix,
        "sample_cache_key": cache_key,
        "max_context_messages": settings.max_context_messages,
        "brain_context_turns": settings.brain_context_turns,
        "max_history_assistant_chars": settings.max_history_assistant_chars,
        "max_history_user_chars": settings.max_history_user_chars,
        "enable_session_summary": settings.enable_session_summary,
        "pricing": PRICING,
        "effective_prompt_sample": {
            "estimatedTokens": eff.get("estimatedTokens"),
            "cacheEligible": eff.get("cacheEligible"),
            "token_estimates": eff.get("token_estimates"),
        },
    }


def brain_stream_turn(client: TestClient, transcript: str, session_id: str, turn: int) -> TurnResult:
    t0 = time.perf_counter()
    ttft_ms = None
    full_text = ""
    usage: dict = {}
    request_id = None
    err = None

    try:
        with client.stream(
            "POST",
            "/api/brain/stream",
            json={"transcript": transcript, "language_code": "te-IN", "sessionId": session_id},
        ) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {r.text[:300]}"
                return TurnResult(turn=turn, session_id=session_id, transcript=transcript, error=err)

            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if payload.get("error"):
                    err = str(payload["error"])
                    break
                if payload.get("delta"):
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t0) * 1000
                    full_text += payload["delta"]
                if payload.get("done"):
                    full_text = payload.get("text") or full_text
                    usage = payload.get("usage") or {}
                    break
    except Exception as e:
        err = str(e)[:500]

    total_ms = (time.perf_counter() - t0) * 1000
    inp = usage.get("input_tokens")
    cached = usage.get("cached_tokens")
    cache_write = usage.get("cache_write_tokens")
    out = usage.get("output_tokens")
    total = usage.get("total_tokens")

    uncached = None
    ratio = None
    cache_state = "unknown"
    if inp is not None and inp > 0:
        uncached = max(0, int(inp) - int(cached or 0))
        ratio = round(int(cached or 0) / int(inp), 4)
        if int(cached or 0) > 0 and uncached < 50:
            cache_state = "hit"
        elif int(cache_write or 0) > 0:
            cache_state = "miss_write"
        elif int(cached or 0) == 0:
            cache_state = "miss"
        else:
            cache_state = "partial"

    return TurnResult(
        turn=turn,
        session_id=session_id,
        transcript=transcript,
        input_tokens=inp,
        output_tokens=out,
        cached_tokens=cached,
        cache_write_tokens=cache_write,
        total_tokens=total,
        uncached_tokens=uncached,
        cache_ratio=ratio,
        ttft_ms=ttft_ms,
        total_latency_ms=total_ms,
        request_id=request_id,
        response_chars=len(full_text),
        error=err,
        cache_state=cache_state,
    )


def turn_cost(tr: TurnResult) -> float | None:
    if tr.input_tokens is None or tr.output_tokens is None:
        return None
    uncached = tr.uncached_tokens if tr.uncached_tokens is not None else max(0, tr.input_tokens - (tr.cached_tokens or 0))
    cached = tr.cached_tokens or 0
    cw = tr.cache_write_tokens or 0
    out = tr.output_tokens or 0
    cost = (
        uncached * PRICING["input_per_m"] / 1_000_000
        + cached * PRICING["cached_input_per_m"] / 1_000_000
        + cw * PRICING["cache_write_per_m"] / 1_000_000
        + out * PRICING["output_per_m"] / 1_000_000
    )
    return round(cost, 8)


def percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def stats(vals: list[float]) -> dict:
    if not vals:
        return {"count": 0, "avg": None, "p50": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(vals),
        "avg": round(statistics.mean(vals), 2),
        "p50": round(percentile(vals, 50) or 0, 2),
        "p95": round(percentile(vals, 95) or 0, 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
    }


def run_conversation(client: TestClient, session_id: str, messages: list[str], label: str) -> BenchmarkRun:
    client.post("/api/session/clear", json={"sessionId": session_id})
    run = BenchmarkRun(label=label, session_id=session_id)
    for i, msg in enumerate(messages, 1):
        tr = brain_stream_turn(client, msg, session_id, i)
        run.turns.append(tr)
        if tr.error:
            print(f"  [{label}] turn {i} ERROR: {tr.error}")
        else:
            print(
                f"  [{label}] turn {i:3d} in={tr.input_tokens} cached={tr.cached_tokens} "
                f"cache%={tr.cache_ratio} ttft={tr.ttft_ms:.0f}ms total={tr.total_latency_ms:.0f}ms"
            )
        time.sleep(0.3)  # gentle pacing
    return run


def main() -> None:
    print("=" * 60)
    print("VOICE AGENT CACHE & LATENCY BENCHMARK")
    print("=" * 60)

    client = TestClient(app_mod.app)
    env = collect_environment(client)
    print(json.dumps(env, indent=2))

    results: dict = {"environment": env, "runs": {}}

    # Test A — 20 turns
    print("\n--- TEST A: 20-turn conversation ---")
    run_a = run_conversation(client, "bench-20turn", TURNS_20, "test_a_20")
    results["runs"]["test_a_20"] = {"turns": [asdict(t) for t in run_a.turns]}

    # Test B — 50 turns
    print("\n--- TEST B: 50-turn conversation ---")
    msgs_50 = TURNS_20 + TURNS_50_EXTRA
    run_b = run_conversation(client, "bench-50turn", msgs_50, "test_b_50")
    results["runs"]["test_b_50"] = {"turns": [asdict(t) for t in run_b.turns]}

    # Test C — 100 turns (repeat/extend 50-turn set)
    print("\n--- TEST C: 100-turn simulation ---")
    msgs_100 = msgs_50 * 2
    run_c = run_conversation(client, "bench-100turn", msgs_100, "test_c_100")
    results["runs"]["test_c_100"] = {"turns": [asdict(t) for t in run_c.turns]}

    # Test D — cache warm-up cross-session
    print("\n--- TEST D: cross-session cache warm-up ---")
    run_d_a = run_conversation(client, "bench-session-a", TURNS_20[:3], "test_d_session_a")
    run_d_b = run_conversation(client, "bench-session-b", TURNS_20[:3], "test_d_session_b")
    results["runs"]["test_d"] = {
        "session_a": [asdict(t) for t in run_d_a.turns],
        "session_b": [asdict(t) for t in run_d_b.turns],
    }

    # Test E — cache invalidation (change brain prompt)
    print("\n--- TEST E: cache invalidation ---")
    sid_e = "bench-invalidate"
    client.post("/api/session/clear", json={"sessionId": sid_e})
    # baseline 1 turn
    base = brain_stream_turn(client, TURNS_20[0], sid_e, 1)
    # save modified instructions
    client.post(
        "/api/instructions",
        json={
            "sessionId": sid_e,
            "behaviourInstructions": "Keep responses concise. Answer in one short Telugu sentence.",
            "businessInstructions": "Benchmark test — trading education only.",
        },
    )
    inv_turns = []
    for i, msg in enumerate(TURNS_20[1:4], 2):
        inv_turns.append(brain_stream_turn(client, msg, sid_e, i))
    client.delete("/api/instructions", params={"sessionId": sid_e})
    results["runs"]["test_e_invalidation"] = {
        "baseline_before_change": asdict(base),
        "after_prompt_change": [asdict(t) for t in inv_turns],
    }

    # Test F — TTL
    results["runs"]["test_f_ttl"] = {"status": "TTL not fully tested — 30m wait impractical in automated run"}

    # Test G — note STT/TTS scope
    results["runs"]["test_g_streaming"] = {
        "note": "Brain stream TTFT/total measured per turn. STT/TTS/end-to-end voice: NOT AVAILABLE in this brain-only benchmark.",
    }

    out_path = ROOT / "benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRaw results written to {out_path}")

    # Quick summary to stdout
    def summarize(run: BenchmarkRun, from_turn: int = 2) -> None:
        valid = [t for t in run.turns if t.input_tokens and not t.error]
        t2 = [t for t in valid if t.turn >= from_turn]
        ratios = [t.cache_ratio for t in t2 if t.cache_ratio is not None]
        if ratios:
            avg_r = statistics.mean(ratios) * 100
            print(f"  {run.label}: turns {from_turn}+ avg cache% = {avg_r:.2f}% (n={len(ratios)})")

    print("\n--- QUICK SUMMARY ---")
    summarize(run_a)
    summarize(run_b)
    summarize(run_c)


if __name__ == "__main__":
    main()
