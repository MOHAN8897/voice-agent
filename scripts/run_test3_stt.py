"""TEST 3 — Inbound audio → STT (stt_final on PSTN path)."""
from __future__ import annotations

import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"

PROMPT_EN = "After agent greeting, say: Hello, this is a speech test."


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code, login.text[:200])
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
        print(">>> ANSWER THE CALL <<<")
        print("1) Listen to agent opening (Namaste / sahayam cheyagalanu)")
        print("2)", PROMPT_EN)
        print()

        best: dict | None = None
        stt_detail = ""
        for i in range(50):
            await asyncio.sleep(2)
            flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
            flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
            stages = flow.get("stages") or {}
            health = flow.get("health") or {}
            stt_audio = stages.get("stt_audio") or {}
            stt_final = stages.get("stt_final") or {}
            in_frames = int((flow.get("metrics") or {}).get("inbound_frames") or 0)
            active = flow.get("active")
            detail = (stt_final.get("detail") or "")[:120]
            detail_safe = detail.encode("ascii", "replace").decode("ascii")
            print(
                f"  [{(i + 1) * 2}s] active={active} inbound={in_frames} "
                f"stt_audio={stt_audio.get('status')} stt_final={stt_final.get('status')} "
                f"detail={detail_safe!r}"
            )
            if stt_final.get("status") == "healthy" and stt_final.get("detail"):
                best = flow
                stt_detail = stt_final.get("detail") or ""
                break
            if stt_audio.get("status") == "healthy":
                best = flow

        print()
        if not best:
            print("FAIL: no media flow captured within 100s")
            return 1

        stages = best.get("stages") or {}
        health = best.get("health") or {}
        checks = health.get("checks") or {}
        fail_list = health.get("failures") or []
        stt_final = stages.get("stt_final") or {}
        lat = best.get("latencies") or {}

        gate = {
            "stt_audio_present": "stt_audio" in stages,
            "stt_final_present": "stt_final" in stages,
            "stt_final_healthy": stt_final.get("status") == "healthy",
            "transcript_non_empty": bool((stt_final.get("detail") or "").strip()),
            "health_stt_check": bool(checks.get("stt")),
            "no_stt_input_failure": "STT_INPUT_FAILURE" not in fail_list,
        }
        print("TEST 3 gate:")
        for key, passed in gate.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        overall = all(gate.values())
        print("overall:", "PASS" if overall else "PARTIAL/FAIL")
        print("transcript:", (stt_detail or stt_final.get("detail") or "(none)").encode("ascii", "replace").decode("ascii"))
        print("stt_final_ms:", lat.get("stt_final_ms"))
        print("call_id:", best.get("call_id"))
        print("health_score:", health.get("score"))
        return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
