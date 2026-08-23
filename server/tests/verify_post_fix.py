"""
Post-fix verification — restart test, 20-turn cache, 100-turn stress, cross-call, invalidation.

Run against a LIVE server (must be freshly restarted):
  python server/tests/verify_post_fix.py [--base http://127.0.0.1:8000]

Writes: verify_post_fix_results.json
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

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
    "Intraday అంటే ఏమిటి?", "Delivery trading అంటే?", "Stop loss అంటే?",
    "Target price అంటే?", "Volume అంటే?", "Liquidity అంటే?",
    "Brokerage ఎంత ఉంటుంది?", "Demat account అవసరమా?", "Margin అంటే?",
    "Leverage అంటే?", "Hedging అంటే?", "Portfolio అంటే?",
    "Diversification అంటే?", "Bull market అంటే?", "Bear market అంటే?",
    "Index fund అంటే?", "Mutual fund అంటే?", "SIP అంటే?",
    "Tax on trading?", "Long term vs short term?", "Chart reading basics?",
    "Support level అంటే?", "Resistance అంటే?", "Trend line అంటే?",
    "Candlestick అంటే?", "Green candle అంటే?", "Red candle అంటే?",
    "Breakout అంటే?", "Pullback అంటే?", "Volatility అంటే?",
]


def wait_for_server(client: httpx.Client, timeout_s: float = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = client.get("/api/health", timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Server not ready at {BASE} after {timeout_s}s")


def reset_metrics(client: httpx.Client) -> None:
    client.post("/api/metrics/reset", timeout=10)


def clear_session(client: httpx.Client, session_id: str) -> None:
    client.post("/api/session/clear", json={"sessionId": session_id}, timeout=10)


def last_brain_turn(client: httpx.Client) -> dict | None:
    m = client.get("/api/metrics", timeout=10).json()
    turns = m.get("recent_brain_turns") or []
    return turns[-1] if turns else None


def brain_stream_turn(
    client: httpx.Client,
    transcript: str,
    session_id: str,
    turn: int,
) -> dict:
    t0 = time.perf_counter()
    ttft_ms = None
    usage: dict = {}
    err = None

    try:
        with client.stream(
            "POST",
            "/api/brain/stream",
            json={"transcript": transcript, "language_code": "te-IN", "sessionId": session_id},
            timeout=120,
        ) as r:
            if r.status_code != 200:
                return {"turn": turn, "session_id": session_id, "error": f"HTTP {r.status_code}"}
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if payload.get("error"):
                    err = str(payload["error"])
                    break
                if payload.get("delta") and ttft_ms is None:
                    ttft_ms = round((time.perf_counter() - t0) * 1000)
                if payload.get("done"):
                    usage = payload.get("usage") or {}
                    break
    except Exception as e:
        err = str(e)[:300]

    total_ms = round((time.perf_counter() - t0) * 1000)
    server_turn = last_brain_turn(client) or {}

    inp = usage.get("input_tokens") or server_turn.get("input_tokens")
    cached = usage.get("cached_tokens") or server_turn.get("cached_tokens")
    cache_write = usage.get("cache_write_tokens") or server_turn.get("cache_write_tokens")
    out = usage.get("output_tokens") or server_turn.get("output_tokens")
    brain_est = server_turn.get("brain_tokens_est")
    history_est = server_turn.get("history_tokens_est")
    transcript_est = server_turn.get("transcript_tokens_est")
    cache_event = server_turn.get("cache_event")
    prep_ms = server_turn.get("prep_ms")
    srv_ttft = server_turn.get("ttft_ms")
    request_id = server_turn.get("request_id")

    uncached = max(0, int(inp or 0) - int(cached or 0)) if inp is not None else None
    brain_cache_pct = (
        round(int(cached or 0) / int(brain_est) * 100, 1)
        if brain_est and cached is not None and brain_est > 0
        else None
    )

    return {
        "turn": turn,
        "session_id": session_id,
        "transcript": transcript[:60],
        "ttft_ms": srv_ttft or ttft_ms,
        "client_ttft_ms": ttft_ms,
        "prep_ms": prep_ms,
        "total_ms": server_turn.get("total_ms") or total_ms,
        "input_tokens": inp,
        "cached_tokens": cached,
        "uncached_tokens": uncached,
        "cache_write_tokens": cache_write,
        "output_tokens": out,
        "brain_tokens_est": brain_est,
        "history_tokens_est": history_est,
        "transcript_tokens_est": transcript_est,
        "cache_event": cache_event,
        "brain_cache_pct": brain_cache_pct,
        "request_id": request_id,
        "error": err,
    }


def run_conversation(
    client: httpx.Client,
    session_id: str,
    messages: list[str],
    *,
    label: str,
    pace_s: float = 0.3,
) -> list[dict]:
    clear_session(client, session_id)
    rows = []
    for i, msg in enumerate(messages, 1):
        row = brain_stream_turn(client, msg, session_id, i)
        row["label"] = label
        rows.append(row)
        print(
            f"  [{label}] T{i:3d} in={row.get('input_tokens')} cached={row.get('cached_tokens')} "
            f"write={row.get('cache_write_tokens')} brain%={row.get('brain_cache_pct')} "
            f"ttft={row.get('ttft_ms')}ms prep={row.get('prep_ms')}ms event={row.get('cache_event')}"
        )
        time.sleep(pace_s)
    return rows


def extract_rewrites(rows: list[dict]) -> list[dict]:
    rewrites = []
    prev_time = None
    for r in rows:
        if int(r.get("cache_write_tokens") or 0) > 0:
            rewrites.append({
                "turn": r["turn"],
                "session_id": r.get("session_id"),
                "label": r.get("label"),
                "cache_write_tokens": r.get("cache_write_tokens"),
                "cached_tokens": r.get("cached_tokens"),
                "seconds_since_previous": None,
                "global_index": len(rewrites) + 1,
            })
    return rewrites


def main() -> None:
    print("=" * 70)
    print("POST-FIX VERIFICATION")
    print(f"Target: {BASE}")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    results: dict = {"base_url": BASE, "timestamp_utc": datetime.now(timezone.utc).isoformat()}

    with httpx.Client(base_url=BASE, timeout=120) as client:
        wait_for_server(client)
        health = client.get("/api/health").json()
        results["health"] = health
        meta = client.get("/api/meta").json()
        results["server_version"] = meta.get("version")
        reset_metrics(client)

        # --- Test 1: 10 fresh first-turn calls ---
        print("\n--- TEST 1: 10 fresh calls (one message each) ---")
        fresh_rows = []
        for i in range(1, 11):
            sid = f"verify-fresh-{i:02d}"
            clear_session(client, sid)
            row = brain_stream_turn(client, TURNS_20[0], sid, 1)
            row["call"] = i
            fresh_rows.append(row)
            print(
                f"  Call {i:2d}: ttft={row.get('ttft_ms')}ms prep={row.get('prep_ms')}ms "
                f"in={row.get('input_tokens')} cached={row.get('cached_tokens')} "
                f"write={row.get('cache_write_tokens')} event={row.get('cache_event')}"
            )
            time.sleep(0.5)
        results["test1_fresh_calls"] = fresh_rows
        ttfts = [r["ttft_ms"] for r in fresh_rows if r.get("ttft_ms")]
        results["test1_summary"] = {
            "avg_ttft_ms": round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
            "min_ttft_ms": min(ttfts) if ttfts else None,
            "max_ttft_ms": max(ttfts) if ttfts else None,
            "first_call_ttft_ms": fresh_rows[0].get("ttft_ms") if fresh_rows else None,
        }

        # --- Test 2: 20-turn cache ---
        print("\n--- TEST 2: 20-turn conversation ---")
        rows_20 = run_conversation(client, "verify-20turn", TURNS_20, label="20turn")
        results["test2_20turn"] = rows_20
        t2_brain_pct = [
            r["brain_cache_pct"] for r in rows_20
            if r.get("brain_cache_pct") is not None and r.get("cached_tokens", 0) > 0
        ]
        results["test2_summary"] = {
            "avg_brain_cache_pct": round(sum(t2_brain_pct) / len(t2_brain_pct), 1) if t2_brain_pct else None,
            "turn1": rows_20[0] if rows_20 else None,
            "turn2": rows_20[1] if len(rows_20) > 1 else None,
        }

        # --- Test 3: 100-turn stress ---
        print("\n--- TEST 3: 100-turn stress ---")
        msgs_100 = (TURNS_20 + TURNS_50_EXTRA) * 2
        rows_100 = run_conversation(client, "verify-100turn", msgs_100, label="100turn", pace_s=0.25)
        results["test3_100turn"] = rows_100
        key_turns = [1, 25, 50, 75, 100]
        results["test3_key_turns"] = {k: rows_100[k - 1] for k in key_turns if k <= len(rows_100)}
        rewrites_100 = [r for r in rows_100 if int(r.get("cache_write_tokens") or 0) > 0]
        results["test3_rewrites"] = [
            {
                "rewrite_n": i + 1,
                "turn": r["turn"],
                "cached_before": 0,
                "cache_write": r.get("cache_write_tokens"),
                "ttft_ms": r.get("ttft_ms"),
                "cache_event": r.get("cache_event"),
            }
            for i, r in enumerate(rewrites_100)
        ]
        results["test3_rewrite_count"] = len(rewrites_100)

        # --- Test 5: Cross-call cache ---
        print("\n--- TEST 5: Cross-call cache (A=20 turns, B/C fresh turn 1) ---")
        run_conversation(client, "verify-call-a", TURNS_20, label="call-a")
        time.sleep(1)
        row_b = brain_stream_turn(client, TURNS_20[0], "verify-call-b", 1)
        row_b["label"] = "call-b-turn1"
        print(f"  Call B T1: cached={row_b.get('cached_tokens')} write={row_b.get('cache_write_tokens')} event={row_b.get('cache_event')}")
        time.sleep(0.5)
        row_c = brain_stream_turn(client, TURNS_20[0], "verify-call-c", 1)
        row_c["label"] = "call-c-turn1"
        print(f"  Call C T1: cached={row_c.get('cached_tokens')} write={row_c.get('cache_write_tokens')} event={row_c.get('cache_event')}")
        results["test5_cross_call"] = {"call_b_turn1": row_b, "call_c_turn1": row_c}

        # --- Test 6: Cache invalidation ---
        print("\n--- TEST 6: Cache invalidation ---")
        sid_inv = "verify-invalidate"
        clear_session(client, sid_inv)
        base = brain_stream_turn(client, TURNS_20[0], sid_inv, 1)
        # Modify behaviour slightly
        client.post(
            "/api/instructions",
            json={
                "sessionId": sid_inv,
                "behaviourInstructions": (
                    "VOICE CALL MODE — Telugu-first assistant\n"
                    "- Speak natural conversational Telugu.\n"
                    "- STRICT: 1–2 short sentences only.\n"
                    "- One idea per turn."
                ),
                "businessInstructions": "Trading education assistant for beginners.",
            },
            timeout=10,
        )
        inv_rows = []
        for i, msg in enumerate(TURNS_20[1:4], 2):
            inv_rows.append(brain_stream_turn(client, msg, sid_inv, i))
            time.sleep(0.3)
        client.delete("/api/instructions", params={"sessionId": sid_inv})
        results["test6_invalidation"] = {"baseline": base, "after_change": inv_rows}

        # Final metrics snapshot
        results["final_metrics"] = client.get("/api/metrics").json()

    out = ROOT / "verify_post_fix_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {out}")
    print("\n--- SUMMARY ---")
    s1 = results.get("test1_summary", {})
    print(f"Test 1 first call TTFT: {s1.get('first_call_ttft_ms')}ms (avg fresh: {s1.get('avg_ttft_ms')}ms)")
    s2 = results.get("test2_summary", {})
    print(f"Test 2 avg brain cache %: {s2.get('avg_brain_cache_pct')}%")
    print(f"Test 3 rewrites in 100 turns: {results.get('test3_rewrite_count')}")
    kt = results.get("test3_key_turns", {})
    for k, v in kt.items():
        print(f"  Turn {k}: input={v.get('input_tokens')} cached={v.get('cached_tokens')}")


if __name__ == "__main__":
    main()
