"""Direct Telnyx voice check — no agent, no WebSocket, no server webhook required.

Dials a plain PSTN call, then retries Telnyx native `speak` until the call is answered.

Usage:
  python scripts/run_voice_check_direct.py
  python scripts/run_voice_check_direct.py --to +918897908470
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.telnyx_client import TelnyxApiError, TelnyxClient

DEFAULT_TO = "+918897908470"
PHRASE = (
    "Telnyx voice check. This is a test message only. "
    "If you can hear this clearly, Telnyx audio to your phone is working. "
    "Signal test one. Signal test two. Signal test three."
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default=DEFAULT_TO)
    parser.add_argument("--wait", type=int, default=90, help="Seconds to retry speak")
    args = parser.parse_args()

    client = TelnyxClient()
    print(f"Dialing {args.to} (no stream, no agent)...")
    try:
        result = await client.create_simple_outbound_call(to_e164=args.to)
    except Exception as exc:
        print(f"DIAL FAILED: {exc}")
        return 1

    call_control_id = str(result.get("call_control_id") or result.get("id") or "")
    print(f"call_control_id: {call_control_id}")
    print()
    print(">>> ANSWER YOUR PHONE NOW <<<")
    print("Waiting for answer, then Telnyx will speak the test phrase.")
    print(f"Phrase: {PHRASE[:80]}...")
    print()

    attempts = max(1, args.wait // 5)
    for i in range(attempts):
        await asyncio.sleep(5)
        try:
            await client.speak(call_control_id, PHRASE, language="en-US", voice="female")
            print(f"[{(i + 1) * 5}s] SPEAK SENT OK")
            print()
            print("Did you hear the test phrase on your phone?")
            print("  YES = Telnyx -> handset works; problem is in our agent audio path")
            print("  NO  = Telnyx/carrier/account issue, not our TTS/WebSocket code")
            return 0
        except TelnyxApiError as exc:
            msg = str(exc)[:120]
            print(f"[{(i + 1) * 5}s] speak not ready yet: {msg}")

    print("Timed out — call may not have been answered, or speak kept failing.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
