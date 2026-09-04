"""TEST 8 — Sequential PSTN call stability (registry + bridge cleanup).

Places N outbound calls back-to-back. Answer each call; script auto-hangups after hold window.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"
TERMINAL_STATUSES = frozenset(
    {"completed", "hangup", "failed", "recording.saved", "streaming.stopped", "call.hangup"}
)


def _safe(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
    if login.status_code != 200:
        raise RuntimeError(f"login failed {login.status_code}")
    csrf = client.cookies.get("dev_csrf") or ""
    return {"X-CSRF-Token": csrf} if csrf else {}


async def _wait_stream(
    client: httpx.AsyncClient, headers: dict, seconds: int
) -> tuple[dict, str]:
    external_id = ""
    for i in range(max(1, seconds // 2)):
        await asyncio.sleep(2)
        flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
        external_id = str(flow.get("external_id") or external_id)
        if flow.get("active"):
            neg = flow.get("negotiated") or {}
            print(
                f"    stream active @ {(i + 1) * 2}s "
                f"codec={neg.get('codec')}/{neg.get('sample_rate')} call_id={flow.get('call_id')}"
            )
            return flow, external_id
    return {}, external_id


async def _wait_inactive(
    client: httpx.AsyncClient, headers: dict, external_id: str, seconds: int
) -> bool:
    for _ in range(max(1, seconds // 2)):
        await asyncio.sleep(2)
        params = {"call_id": external_id} if external_id else None
        flow_r = await client.get("/api/dev/telephony/media-flow", params=params, headers=headers)
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
        if not flow.get("active"):
            return True
    return False


async def _call_row(client: httpx.AsyncClient, headers: dict, control_id: str) -> dict | None:
    calls_r = await client.get("/api/dev/telephony/calls", headers=headers)
    if calls_r.status_code != 200:
        return None
    for row in calls_r.json().get("calls") or []:
        if str(row.get("call_control_id") or row.get("id") or "") == control_id:
            return row
    return None


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 8 — sequential PSTN stability")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--to", default=TO)
    parser.add_argument("--calls", type=int, default=5)
    parser.add_argument("--wait-stream", type=int, default=60)
    parser.add_argument("--hold-seconds", type=int, default=20, help="Seconds on call before auto-hangup")
    parser.add_argument("--cleanup-wait", type=int, default=20, help="Seconds to wait for flow inactive")
    args = parser.parse_args()

    results: list[dict] = []

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        headers = await _login(client)

        print(f"TEST 8 — placing {args.calls} sequential outbound calls to {args.to}")
        print("Answer each call; script hangs up automatically after the hold window.")
        print()

        for n in range(1, args.calls + 1):
            print(f"--- Call {n}/{args.calls} ---")
            dial = await client.post(
                "/api/dev/telephony/outbound",
                json={"toE164": args.to, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
                headers=headers,
            )
            body = dial.json()
            ok = dial.status_code == 200 and body.get("ok") is not False
            control_id = str(body.get("call_control_id") or "")
            print(f"  dial ok={ok} control={control_id[:24]}...")

            flow, external_id = await _wait_stream(client, headers, args.wait_stream) if ok else ({}, "")
            negotiated = flow.get("negotiated") or {}
            l16_ok = negotiated.get("codec") == "L16" and int(negotiated.get("sample_rate") or 0) == 16000

            if flow.get("active") and control_id:
                print(f"  on call {args.hold_seconds}s (answer + listen)...")
                await asyncio.sleep(args.hold_seconds)
                hang = await client.post(
                    "/api/dev/telephony/hangup",
                    params={"call_control_id": control_id},
                    headers=headers,
                )
                hang_body = hang.json()
                print(f"  hangup ok={hang_body.get('ok')} status={hang.status_code}")

            inactive = await _wait_inactive(client, headers, external_id or control_id, args.cleanup_wait)
            row = await _call_row(client, headers, control_id) if control_id else None
            status = str((row or {}).get("status") or "")
            completed = status in TERMINAL_STATUSES or inactive

            entry = {
                "call": n,
                "dial_ok": ok,
                "l16_ok": l16_ok,
                "call_id": str(flow.get("call_id") or (row or {}).get("internal_call_id") or ""),
                "registry_status": status,
                "flow_inactive": inactive,
                "completed": completed,
            }
            results.append(entry)
            print(
                f"  result dial={entry['dial_ok']} l16={entry['l16_ok']} "
                f"registry={_safe(status) or '-'} inactive={inactive} completed={completed}"
            )
            print()
            await asyncio.sleep(3)

    print("TEST 8 gate:")
    gates = {
        "all_dials_ok": all(r["dial_ok"] for r in results),
        "all_l16_negotiated": all(r["l16_ok"] for r in results if r["dial_ok"]),
        "all_calls_completed": all(r["completed"] for r in results),
        "registry_rows_seen": sum(1 for r in results if r["registry_status"]) >= max(1, len(results) // 2),
    }
    for key, passed in gates.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {key}")
    overall = all(gates.values())
    print("overall:", "PASS" if overall else "PARTIAL/FAIL")
    for r in results:
        print(f"  call {r['call']}: {r.get('call_id','')[:36]} status={_safe(r.get('registry_status') or '-')}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
