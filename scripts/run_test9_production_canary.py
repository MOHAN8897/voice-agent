"""TEST 9 — Production canary deploy checklist + post-deploy smoke.

Runs against a remote API base (production or named tunnel).

Usage:
  python scripts/run_test9_production_canary.py --base-url https://api-dev.hustlelabs.in
  python scripts/run_test9_production_canary.py --base-url https://api.yourdomain.com --smoke-only
  python scripts/run_test9_production_canary.py --base-url https://api.yourdomain.com --score-only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx

DEFAULT_TO = "+918897908470"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
FRAME_BYTES = 640


def _safe(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
    if login.status_code != 200:
        raise RuntimeError(f"login failed {login.status_code}: {login.text[:200]}")
    csrf = client.cookies.get("dev_csrf") or ""
    return {"X-CSRF-Token": csrf} if csrf else {}


async def _check_health(client: httpx.AsyncClient) -> dict:
    r = await client.get("/api/health")
    return r.json() if r.status_code == 200 else {"ok": False, "status": r.status_code}


async def _deploy_checklist(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.get("/api/dev/telephony/production-canary/checklist", headers=headers)
    body = r.json() if r.status_code == 200 else {}
    return body.get("deploy") or {}


async def _canary_status(client: httpx.AsyncClient, headers: dict, hours: int) -> dict:
    r = await client.get(
        "/api/dev/telephony/production-canary/status",
        params={"hours": hours},
        headers=headers,
    )
    body = r.json() if r.status_code == 200 else {}
    return body.get("canary") or {}


async def _voice_check(client: httpx.AsyncClient, headers: dict, to: str, wait: int) -> bool:
    dial = await client.post(
        "/api/dev/telephony/voice-check",
        json={"toE164": to},
        headers=headers,
    )
    body = dial.json()
    if not body.get("ok"):
        print("  voice-check dial failed:", body.get("error") or dial.text[:200])
        return False
    control_id = str(body.get("call_control_id") or "")
    print(f"  voice-check placed control={control_id[:28]}...")
    print("  >>> ANSWER PHONE — Telnyx native speak only (no agent) <<<")
    for i in range(max(1, wait // 2)):
        await asyncio.sleep(2)
        calls = await client.get("/api/dev/telephony/calls", headers=headers)
        rows = (calls.json().get("calls") or []) if calls.status_code == 200 else []
        row = next((r for r in rows if r.get("call_control_id") == control_id), None)
        if row and row.get("voice_check_speak_sent"):
            print(f"  voice-check speak_sent @ {(i + 1) * 2}s")
            return True
        if row and row.get("voice_check_error"):
            print("  voice-check error:", row.get("voice_check_error"))
            return False
    print(f"  voice-check timed out after {wait}s")
    return False


async def _test5_smoke(client: httpx.AsyncClient, headers: dict, to: str, wait_stream: int) -> dict:
    """Abbreviated TEST 5 — outbound agent TTS path."""
    dial = await client.post(
        "/api/dev/telephony/outbound",
        json={"toE164": to, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
        headers=headers,
    )
    body = dial.json()
    if dial.status_code != 200 or body.get("ok") is False:
        return {"ok": False, "error": body.get("error") or dial.text[:200]}

    external_id = str(body.get("call_control_id") or "")
    print(f"  TEST 5 dial ok control={external_id[:28]}...")
    print("  >>> ANSWER PHONE — greeting + signal test <<<")

    flow: dict = {}
    for i in range(max(1, wait_stream // 2)):
        await asyncio.sleep(2)
        flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
        if flow.get("active"):
            external_id = str(flow.get("external_id") or external_id)
            neg = flow.get("negotiated") or {}
            print(f"  stream @ {(i + 1) * 2}s {neg.get('codec')}/{neg.get('sample_rate')}")
            break

    if not flow.get("active"):
        return {"ok": False, "error": "no active stream"}

    await asyncio.sleep(6)
    test = await client.post(
        "/api/dev/telephony/media-flow/test-audio",
        params={"call_id": external_id} if external_id else None,
        headers=headers,
    )
    print("  test-audio", test.status_code)
    await asyncio.sleep(20)

    flow_r = await client.get(
        "/api/dev/telephony/media-flow",
        params={"call_id": external_id} if external_id else None,
        headers=headers,
    )
    flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
    metrics = flow.get("metrics") or {}
    health = flow.get("health") or {}
    checks = health.get("checks") or {}
    frames = int(metrics.get("outbound_sent_frames") or 0)
    frame_bytes = int((metrics.get("outbound_bytes") or 0) / max(frames, 1))

    if external_id:
        hang = await client.post(
            "/api/dev/telephony/hangup",
            params={"call_control_id": external_id},
            headers=headers,
        )
        print("  hangup", hang.status_code, hang.json().get("ok"))

    return {
        "ok": frames > 0 and checks.get("telnyx_outbound"),
        "l16": (flow.get("negotiated") or {}).get("codec") == "L16",
        "outbound_frames": frames,
        "frame_bytes": frame_bytes,
        "health_score": health.get("score"),
        "call_id": flow.get("call_id"),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 9 — production canary")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PUBLIC_TUNNEL_URL") or os.getenv("CANARY_BASE_URL") or "https://api-dev.hustlelabs.in",
        help="Production or staging API URL (HTTPS)",
    )
    parser.add_argument("--to", default=DEFAULT_TO)
    parser.add_argument("--voice-check-wait", type=int, default=60)
    parser.add_argument("--wait-stream", type=int, default=45)
    parser.add_argument("--window-hours", type=int, default=48)
    parser.add_argument("--smoke-only", action="store_true", help="Skip canary window scoring")
    parser.add_argument("--score-only", action="store_true", help="Only score canary window (no new calls)")
    parser.add_argument("--skip-test5", action="store_true", help="Skip agent TTS smoke (voice-check only)")
    parser.add_argument(
        "--seed-archives",
        action="store_true",
        help="Import recent PSTN call archives into canary log before scoring",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    if not base.startswith("https://"):
        print("WARN: production canary should use HTTPS base URL")

    print(f"TEST 9 — production canary @ {base}")
    print()

    async with httpx.AsyncClient(base_url=base, timeout=90.0, follow_redirects=True) as client:
        health = await _check_health(client)
        print("health ok=", health.get("ok"), "envValid=", health.get("envValid"))
        if not health.get("ok"):
            print("FAIL: API health check failed")
            return 1

        headers = await _login(client)
        deploy = await _deploy_checklist(client, headers)
        items = deploy.get("items") or {}
        print()
        print("Deploy checklist (9.1):")
        for key, val in items.items():
            if key in ("webhook_url",):
                print(f"  {key}: {_safe(str(val))}")
            else:
                print(f"  {'PASS' if val else 'FAIL' if val is False else 'INFO'}: {key} = {val}")
        print(f"  ready_for_smoke: {deploy.get('ready_for_smoke')}")
        rollback = (deploy.get("rollback") or {})
        print()
        print("Rollback plan (9.5):")
        for k, v in rollback.items():
            print(f"  {k}: {v}")

        gates: dict[str, bool] = {
            "deploy_ready_for_smoke": bool(deploy.get("ready_for_smoke")),
        }

        if not args.score_only:
            print()
            print("--- 9.3a Voice-check ---")
            gates["voice_check"] = await _voice_check(client, headers, args.to, args.voice_check_wait)

            if not args.skip_test5:
                print()
                print("--- 9.3b TEST 5 agent TTS smoke ---")
                t5 = await _test5_smoke(client, headers, args.to, args.wait_stream)
                print("  result:", json.dumps({k: t5.get(k) for k in ("ok", "l16", "outbound_frames", "health_score")}))
                gates["test5_outbound"] = bool(t5.get("ok"))
                gates["test5_l16"] = bool(t5.get("l16"))
                frame_ok = int(t5.get("frame_bytes") or 0) in (0, FRAME_BYTES)
                gates["test5_frame_bytes"] = frame_ok or int(t5.get("outbound_frames") or 0) == 0

        if not args.smoke_only:
            if args.seed_archives:
                seed_r = await client.post(
                    "/api/dev/telephony/production-canary/seed-archives",
                    params={"hours": args.window_hours, "limit": 30},
                    headers=headers,
                )
                seeded = (seed_r.json().get("seeded") if seed_r.status_code == 200 else 0) or 0
                print(f"  seeded {seeded} calls from server archives into canary log")
            print()
            print(f"--- Canary window ({args.window_hours}h) ---")
            window = await _canary_status(client, headers, args.window_hours)
            cg = window.get("gates") or {}
            for key, passed in cg.items():
                print(f"  {'PASS' if passed else 'FAIL'}: {key}")
            print(
                f"  bidirectional_ok={window.get('bidirectional_ok_calls')} "
                f"total={window.get('total_calls')} "
                f"outbound_failures={window.get('outbound_transmission_failures')}"
            )
            gates["canary_window"] = bool(window.get("overall"))
            if int(window.get("bidirectional_ok_calls") or 0) < 10:
                print("  note: need >=10 bidirectional_ok calls in window for full 9.2 gate")

        print()
        print("TEST 9 gate:")
        for key, passed in gates.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        smoke_keys = [k for k in gates if k != "canary_window"]
        smoke_pass = all(gates.get(k) for k in smoke_keys)
        overall = smoke_pass and (args.smoke_only or gates.get("canary_window", True))
        print("overall:", "PASS" if overall else "PARTIAL/FAIL")
        return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
