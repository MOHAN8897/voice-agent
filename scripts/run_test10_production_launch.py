"""TEST 10 — Production launch checklist, SLOs, and release gates.

Usage:
  python scripts/run_test10_production_launch.py
  python scripts/run_test10_production_launch.py --base-url https://api-dev.hustlelabs.in
  python scripts/run_test10_production_launch.py --skip-pytest
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

import httpx

DEFAULT_BASE = os.getenv("PUBLIC_TUNNEL_URL") or os.getenv("CANARY_BASE_URL") or "https://api-dev.hustlelabs.in"


def _run_test0_pytest() -> bool:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "server/tests/test_pstn_voice_core.py",
        "server/tests/test_pstn_l16_frames.py",
        "server/tests/test_telnyx_outbound_wire.py",
        "server/tests/test_production_canary.py",
        "server/tests/test_production_launch.py",
        "-q",
        "--tb=short",
    ]
    print("  running:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0 and result.stderr:
        print(result.stderr.rstrip()[:500])
    return result.returncode == 0


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
    if login.status_code != 200:
        raise RuntimeError(f"login failed {login.status_code}")
    csrf = login.cookies.get("dev_csrf") or ""
    return {"X-CSRF-Token": csrf} if csrf else {}


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 10 — production launch")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--window-hours", type=int, default=168)
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--seed-archives", action="store_true", help="Seed canary log before scoring")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"TEST 10 — production launch @ {base}")
    print()

    gates: dict[str, bool] = {}

    if not args.skip_pytest:
        print("--- Release gate: TEST 0 pytest ---")
        gates["test0_pytest"] = _run_test0_pytest()
        print(f"  {'PASS' if gates['test0_pytest'] else 'FAIL'}: test0_pytest")
        print()

    async with httpx.AsyncClient(base_url=base, timeout=60.0, follow_redirects=True) as client:
        health = await client.get("/api/health")
        health_ok = health.status_code == 200 and (health.json().get("ok") if health.status_code == 200 else False)
        gates["api_health"] = bool(health_ok)
        print(f"API health: {'PASS' if health_ok else 'FAIL'}")

        headers = await _login(client)

        if args.seed_archives:
            seed_r = await client.post(
                "/api/dev/telephony/production-canary/seed-archives",
                params={"hours": args.window_hours, "limit": 50},
                headers=headers,
            )
            seeded = (seed_r.json().get("seeded") if seed_r.status_code == 200 else 0) or 0
            print(f"Seeded {seeded} calls into canary log")

        checklist_r = await client.get("/api/dev/telephony/production-launch/checklist", headers=headers)
        launch = (checklist_r.json().get("launch") or {}) if checklist_r.status_code == 200 else {}
        gates["launch_checklist"] = bool(launch.get("ready_for_launch"))

        print()
        print("Launch checklist (TEST 10):")
        for area, items in (launch.get("areas") or {}).items():
            print(f"  [{area}]")
            if isinstance(items, dict):
                for key, val in items.items():
                    if isinstance(val, dict):
                        ok = all(val.values()) if val else False
                        print(f"    {'PASS' if ok else 'INFO'}: {key}")
                    elif isinstance(val, list):
                        print(f"    INFO: {key} = {len(val)} item(s)")
                    elif val is None:
                        print(f"    SKIP: {key}")
                    else:
                        print(f"    {'PASS' if val else 'FAIL'}: {key} = {val}")

        if launch.get("ongoing_gates"):
            print()
            print("Ongoing release gates:")
            for line in launch["ongoing_gates"]:
                print(f"  - {line}")

        slos_r = await client.get(
            "/api/dev/telephony/production-launch/slos",
            params={"hours": args.window_hours},
            headers=headers,
        )
        production = (slos_r.json().get("production") or {}) if slos_r.status_code == 200 else {}
        slo_gates = production.get("gates") or {}
        gates["production_slos"] = bool(production.get("overall"))
        gates["canary_window"] = bool(production.get("canary_window_pass"))

        print()
        print(f"Production SLOs ({args.window_hours}h window):")
        for name, slo in (production.get("slos") or {}).items():
            passed = slo_gates.get(name)
            val = slo.get("value")
            target = slo.get("target")
            print(f"  {'PASS' if passed else 'FAIL'}: {name} value={val} target={target}")
        print(f"  archives_in_window: {production.get('archive_count')}")

    print()
    print("TEST 10 gate:")
    for key, passed in gates.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {key}")
    overall = all(gates.values())
    print("overall:", "PASS" if overall else "PARTIAL/FAIL")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
