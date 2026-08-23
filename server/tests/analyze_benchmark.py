"""One-off analysis of benchmark_results.json — benchmark artifact only."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
data = json.loads((ROOT / "benchmark_results.json").read_text(encoding="utf-8"))
env = data["environment"]
pricing = env["pricing"]


def turn_cost(t):
    inp = t.get("input_tokens") or 0
    cached = t.get("cached_tokens") or 0
    uncached = t.get("uncached_tokens") or max(0, inp - cached)
    out = t.get("output_tokens") or 0
    cw = t.get("cache_write_tokens") or 0
    ni = uncached * pricing["input_per_m"] / 1e6
    ci = cached * pricing["cached_input_per_m"] / 1e6
    co = out * pricing["output_per_m"] / 1e6
    cw_cost = cw * pricing["cache_write_per_m"] / 1e6
    return {
        "uncached_input": ni,
        "cached_input": ci,
        "output": co,
        "cache_write": cw_cost,
        "total": ni + ci + co + cw_cost,
    }


def stats(turns, key):
    vals = [t[key] for t in turns if t.get(key) is not None and t.get("error") is None]
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)

    def pct(p):
        i = min(n - 1, int(p / 100 * n))
        return s[i]

    return {
        "avg": sum(vals) / n,
        "median": statistics.median(vals),
        "p50": pct(50),
        "p95": pct(95),
        "min": min(vals),
        "max": max(vals),
        "n": n,
    }


def cache_stats(turns):
    ratios = [t["cache_ratio"] * 100 for t in turns if t.get("input_tokens", 0) > 0]
    t2plus = [t["cache_ratio"] * 100 for t in turns if t["turn"] > 1]
    cached = [t["cached_tokens"] for t in turns]
    static = env["brain_prompt_estimated_tokens"]
    return {
        "avg_all": sum(ratios) / len(ratios),
        "avg_t2plus": sum(t2plus) / len(t2plus) if t2plus else 0,
        "median": statistics.median(ratios),
        "p50": sorted(ratios)[len(ratios) // 2],
        "p95": sorted(ratios)[int(0.95 * len(ratios))],
        "min": min(ratios),
        "max": max(ratios),
        "avg_cached_tokens": sum(cached) / len(cached),
        "cached_vs_static_pct": sum(cached) / len(cached) / static * 100,
    }


out = {}
for name in ["test_a_20", "test_b_50", "test_c_100"]:
    turns = data["runs"][name]["turns"]
    cs = cache_stats(turns)
    costs = [turn_cost(t) for t in turns]
    out[name] = {
        "cache": cs,
        "ttft": stats(turns, "ttft_ms"),
        "latency": stats(turns, "total_latency_ms"),
        "avg_input": sum(t["input_tokens"] for t in turns) / len(turns),
        "avg_cached": cs["avg_cached_tokens"],
        "avg_output": sum(t["output_tokens"] for t in turns) / len(turns),
        "total_cost": sum(c["total"] for c in costs),
        "per_turn_cost": sum(c["total"] for c in costs) / len(turns),
    }

all_bench = []
for name in ["test_a_20", "test_b_50", "test_c_100"]:
    all_bench.extend(data["runs"][name]["turns"])

out["combined_170"] = {
    "cache_t2plus": cache_stats(all_bench)["avg_t2plus"],
    "ttft": stats(all_bench, "ttft_ms"),
    "latency": stats(all_bench, "total_latency_ms"),
    "avg_input": sum(t["input_tokens"] for t in all_bench) / len(all_bench),
    "avg_cached": sum(t["cached_tokens"] for t in all_bench) / len(all_bench),
    "avg_output": sum(t["output_tokens"] for t in all_bench) / len(all_bench),
}

# Cost scenarios from test_a averages
ta = data["runs"]["test_a_20"]["turns"]
avg_in = sum(t["input_tokens"] for t in ta) / 20
avg_cached = sum(t["cached_tokens"] for t in ta) / 20
avg_out = sum(t["output_tokens"] for t in ta) / 20
avg_uncached = sum(t["uncached_tokens"] for t in ta) / 20
opt = turn_cost(
    {
        "input_tokens": avg_in,
        "cached_tokens": avg_cached,
        "uncached_tokens": avg_uncached,
        "output_tokens": avg_out,
        "cache_write_tokens": 0,
    }
)
no_cache_total = (
    avg_in * pricing["input_per_m"] / 1e6 + avg_out * pricing["output_per_m"] / 1e6
)

# Old arch: use TOKEN_OPTIMIZATION estimate ~3000 tokens input at steady state
old_in = 3000
old_total = old_in * pricing["input_per_m"] / 1e6 + avg_out * pricing["output_per_m"] / 1e6

out["cost_scenarios"] = {
    "optimized_per_turn": opt,
    "no_cache_per_turn": no_cache_total,
    "old_arch_per_turn_est": old_total,
    "caching_savings_pct": (no_cache_total - opt["total"]) / no_cache_total * 100,
    "history_savings_pct": (old_total - no_cache_total) / old_total * 100,
    "total_savings_pct": (old_total - opt["total"]) / old_total * 100,
}

# Test A rows
out["test_a_rows"] = []
for t in ta:
    c = turn_cost(t)
    out["test_a_rows"].append(
        {
            "turn": t["turn"],
            "input": t["input_tokens"],
            "cached": t["cached_tokens"],
            "uncached": t["uncached_tokens"],
            "output": t["output_tokens"],
            "cache_pct": round(t["cache_ratio"] * 100, 1),
            "ttft": round(t["ttft_ms"]),
            "latency": round(t["total_latency_ms"]),
            "cost": c["total"],
        }
    )

# Test B key turns
tb = data["runs"]["test_b_50"]["turns"]
out["test_b_key"] = {}
for k in [1, 10, 20, 30, 40, 50]:
    t = tb[k - 1]
    out["test_b_key"][k] = {
        "input": t["input_tokens"],
        "cached": t["cached_tokens"],
        "uncached": t["uncached_tokens"],
        "output": t["output_tokens"],
        "cache_pct": round(t["cache_ratio"] * 100, 1),
        "ttft": round(t["ttft_ms"]),
        "latency": round(t["total_latency_ms"]),
    }

# Test C stability
tc = data["runs"]["test_c_100"]["turns"]
out["test_c_key"] = {k: tc[k - 1]["input_tokens"] for k in [1, 25, 50, 75, 100]}
out["test_c_cache_key"] = {
    k: round(tc[k - 1]["cache_ratio"] * 100, 1) for k in [1, 25, 50, 75, 100]
}

print(json.dumps(out, indent=2))
