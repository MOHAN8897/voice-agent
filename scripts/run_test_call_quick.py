"""Quick outbound test call — dial, wait, print transcript."""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"
TO = "+918897908470"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"


def _safe(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


async def main() -> int:
    talk_seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code)
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/outbound",
            json={"toE164": TO, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
            headers=headers,
        )
        body = dial.json()
        print("dial", dial.status_code, "ok=", body.get("ok"))
        if dial.status_code != 200 or body.get("ok") is False:
            print("error:", body.get("error") or body)
            return 1

        print()
        print(">>> ANSWER YOUR PHONE <<<")
        print("Listen to the greeting, then talk in Telugu. Hang up when done.")
        print()

        call_id = ""
        for i in range(max(1, talk_seconds // 5)):
            await asyncio.sleep(5)
            flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
            flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
            call_id = str(flow.get("call_id") or call_id)
            active = flow.get("active")
            if active:
                neg = flow.get("negotiated") or {}
                print(
                    f"  [{(i + 1) * 5}s] active codec={neg.get('codec')}/{neg.get('sample_rate')} "
                    f"call_id={call_id[:12] if call_id else '-'}"
                )
            elif call_id:
                print(f"  [{(i + 1) * 5}s] call ended")
                break
        else:
            await asyncio.sleep(2)

        if not call_id:
            print("no call_id captured — did you answer?")
            return 1

        tr = await client.get(f"/api/call/{call_id}/transcript", headers=headers)
        lines = (tr.json().get("lines") or []) if tr.status_code == 200 else []
        if lines and isinstance(lines[0], str):
            lines = [json.loads(ln) for ln in lines if ln.strip()]

        print()
        print("Transcript:")
        for ln in lines:
            role = ln.get("role", "?")
            text = _safe(str(ln.get("text") or ""))[:120]
            lat = ln.get("brain_latency_ms")
            extra = f" ({lat}ms)" if lat else ""
            print(f"  [{role}] {text}{extra}")
        print("call_id:", call_id)
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
