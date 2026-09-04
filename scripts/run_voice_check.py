"""Telnyx-only voice check — dial with NO agent, play native speak on answer.

Usage:
  python scripts/run_voice_check.py
  python scripts/run_voice_check.py --to +918897908470
  python scripts/run_voice_check.py --base-url https://api-dev.hustlelabs.in
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

DEFAULT_TO = "+918897908470"
DEFAULT_BASE = "http://127.0.0.1:8000"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Telnyx native speak voice-check call")
    parser.add_argument("--to", default=DEFAULT_TO, help="Destination E.164")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="API base URL")
    parser.add_argument("--wait", type=int, default=90, help="Max seconds to wait for call")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print(f"login failed {login.status_code}: {login.text[:300]}")
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/voice-check",
            json={"toE164": args.to},
            headers=headers,
        )
        print("voice-check dial", dial.status_code)
        body = dial.json()
        if not body.get("ok"):
            print("dial error:", body.get("error") or dial.text[:400])
            return 1

        call_control_id = body.get("call_control_id") or ""
        print("call_control_id:", call_control_id)
        print("mode:", body.get("mode"))
        print("phrase:", body.get("phrase", "")[:120], "...")
        print()
        print(">>> ANSWER YOUR PHONE <<<")
        print("You should hear: Telnyx voice check... Signal test one, two, three.")
        print("(No agent. No WebSocket audio. Telnyx speak API only.)")
        print()

        deadline = args.wait
        for i in range(deadline // 2):
            await asyncio.sleep(2)
            calls = await client.get("/api/dev/telephony/calls", headers=headers)
            rows = (calls.json().get("calls") or []) if calls.status_code == 200 else []
            row = next((r for r in rows if r.get("call_control_id") == call_control_id), None)
            if not row and rows:
                row = rows[0]
            status = (row or {}).get("status") or (row or {}).get("last_event") or ""
            speak_sent = (row or {}).get("voice_check_speak_sent")
            speak_err = (row or {}).get("voice_check_error")
            print(f"  [{i * 2 + 2}s] status={status} speak_sent={speak_sent}")

            if speak_sent:
                print()
                print("SUCCESS: Telnyx speak command was sent.")
                print("Did you HEAR the test phrase on your phone? (yes/no)")
                return 0

            if speak_err:
                print("speak error:", speak_err)
                return 1

            if status in ("answered", "call.answered") and not speak_sent and i >= 3:
                # Webhook may not have fired speak — fallback
                fb = await client.post(
                    "/api/dev/telephony/media-flow/test-telnyx-speak",
                    params={"call_id": call_control_id},
                    headers=headers,
                )
                print("  fallback speak", fb.status_code, fb.text[:200])

            if status in ("hangup", "call.hangup", "failed", "call.failed"):
                print("call ended before speak:", status)
                return 1

        print(f"timed out after {deadline}s — check Telnyx webhook reaches {args.base_url}/api/telnyx/webhook")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
