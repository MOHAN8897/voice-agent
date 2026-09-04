"""TEST 6 — Full PSTN conversation without barge-in.

Places outbound call, monitors live media-flow, validates transcript + trace after hangup.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"


def _validate_offline(call_id: str, barge_in: bool) -> int:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "calls" / call_id
    tr_path = root / "transcript.jsonl"
    trace_path = root / "trace.json"
    if not tr_path.exists():
        print("FAIL: no transcript at", tr_path)
        return 1
    lines = [json.loads(ln) for ln in tr_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}
    gates = score_call(lines, trace, None)
    gates["barge_in_disabled"] = not barge_in
    print("Offline validation for", call_id)
    print("Transcript:")
    for ln in lines:
        role = ln.get("role", "?")
        text = _safe(str(ln.get("text") or ""))[:100]
        lat = ln.get("brain_latency_ms")
        extra = f" ({lat}ms)" if lat else ""
        print(f"  [{role}] {text}{extra}")
    print()
    print("TEST 6 gate:")
    for key, passed in gates.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {key}")
    overall_strict = all(gates.values())
    overall_dev = (
        gates["barge_in_disabled"]
        and gates["min_2_turns_proven"]
        and gates["llm_in_flow"]
        and gates["tts_in_flow"]
        and gates["outbound_in_flow"]
    )
    print("overall (strict 3+ turns):", "PASS" if overall_strict else "PARTIAL/FAIL")
    print("overall (dev 2+ turns):", "PASS" if overall_dev else "FAIL")
    return 0 if overall_strict or overall_dev else 1


def _safe(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


def score_call(lines: list[dict], trace: dict, flow: dict | None) -> dict[str, bool]:
    user_turns = [ln for ln in lines if ln.get("role") == "user" and (ln.get("text") or "").strip()]
    agent_turns = [ln for ln in lines if ln.get("role") == "assistant" and (ln.get("text") or "").strip()]
    trace_turns = trace.get("turns") or []
    stages = (flow or {}).get("stages") or {}
    health = (flow or {}).get("health") or {}
    checks = health.get("checks") or {}
    pipeline_ok = bool(trace_turns) or bool(checks.get("llm"))

    return {
        "barge_in_disabled": True,  # checked separately via import
        "opening_agent_turn": len(agent_turns) >= 1,
        "user_turns_gte_3": len(user_turns) >= 3,
        "agent_turns_gte_3": len(agent_turns) >= 3,
        "trace_turns_gte_3": len(trace_turns) >= 3,
        "llm_in_flow": bool(checks.get("llm") or "llm_started" in stages or pipeline_ok),
        "tts_in_flow": bool(checks.get("tts") or "tts_audio" in stages or pipeline_ok),
        "outbound_in_flow": bool(checks.get("telnyx_outbound") or "outbound_sent" in stages or pipeline_ok),
        "alternating_dialogue": len(lines) >= 6,
        "min_2_turns_proven": len(user_turns) >= 2 and len(agent_turns) >= 2 and len(trace_turns) >= 2,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 6 — multi-turn PSTN conversation")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--to", default=TO)
    parser.add_argument("--call-id", default="", help="Validate existing call instead of placing new dial")
    parser.add_argument("--offline-call-id", default="", help="Score call archive on disk (no API)")
    parser.add_argument("--talk-seconds", type=int, default=120, help="How long to keep call open for turns")
    args = parser.parse_args()

    from server.services.pstn_voice_core import ENABLE_PSTN_BARGE_IN

    if ENABLE_PSTN_BARGE_IN:
        print("FAIL: ENABLE_PSTN_BARGE_IN must be False for TEST 6")
        return 1

    if args.offline_call_id.strip():
        return _validate_offline(args.offline_call_id.strip(), ENABLE_PSTN_BARGE_IN)

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code)
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        call_id = args.call_id.strip()
        if not call_id:
            dial = await client.post(
                "/api/dev/telephony/outbound",
                json={"toE164": args.to, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
                headers=headers,
            )
            body = dial.json()
            print("dial", dial.status_code, "ok=", body.get("ok"))
            if dial.status_code != 200 or body.get("ok") is False:
                print("error:", body.get("error") or body)
                return 1

            print()
            print(">>> ANSWER THE PHONE <<<")
            print("Have a natural 3+ turn conversation in Telugu/Tanglish:")
            print("  Turn 1: Listen to opening, then ask who is calling")
            print("  Turn 2: Ask what the call is about (stay in agent work scope)")
            print("  Turn 3: Ask something slightly off-topic — agent should politely redirect")
            print(f"Talk for up to {args.talk_seconds}s, then hang up.")
            print()

            for i in range(args.talk_seconds // 5):
                await asyncio.sleep(5)
                try:
                    flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
                except httpx.HTTPError as exc:
                    print(f"  [{(i + 1) * 5}s] media-flow poll error: {exc.__class__.__name__}")
                    continue
                flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
                call_id = str(flow.get("call_id") or call_id)
                stages = flow.get("stages") or {}
                llm = stages.get("llm_started", {}).get("status")
                tts = stages.get("tts_audio", {}).get("status")
                out = stages.get("outbound_sent", {}).get("status")
                active = flow.get("active")
                print(
                    f"  [{(i + 1) * 5}s] active={active} call_id={call_id[:12] if call_id else '-'} "
                    f"llm={llm} tts={tts} outbound={out}"
                )
                if not active and call_id:
                    print("call ended")
                    break
            else:
                await asyncio.sleep(3)

        if not call_id:
            print("FAIL: no call_id captured")
            return 1

        tr = await client.get(f"/api/call/{call_id}/transcript", headers=headers)
        trace_r = await client.get(f"/api/call/{call_id}/trace", headers=headers)
        flow_r = await client.get(
            "/api/dev/telephony/media-flow",
            params={"call_id": call_id},
            headers=headers,
        )
        lines = (tr.json().get("lines") or []) if tr.status_code == 200 else []
        if lines and isinstance(lines[0], str):
            lines = [json.loads(ln) for ln in lines if ln.strip()]
        trace = trace_r.json() if trace_r.status_code == 200 else {}
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}

        print()
        print("Transcript:")
        for ln in lines:
            role = ln.get("role", "?")
            text = _safe(str(ln.get("text") or ""))[:100]
            lat = ln.get("brain_latency_ms")
            extra = f" ({lat}ms)" if lat else ""
            print(f"  [{role}] {text}{extra}")

        gates = score_call(lines, trace, flow)
        gates["barge_in_disabled"] = not ENABLE_PSTN_BARGE_IN

        print()
        print("TEST 6 gate:")
        for key, passed in gates.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        overall_strict = all(gates.values())
        overall_dev = (
            gates["barge_in_disabled"]
            and gates["min_2_turns_proven"]
            and gates["llm_in_flow"]
            and gates["tts_in_flow"]
            and gates["outbound_in_flow"]
        )
        print("overall (strict 3+ turns):", "PASS" if overall_strict else "PARTIAL/FAIL")
        print("overall (dev 2+ turns):", "PASS" if overall_dev else "FAIL")
        print("call_id:", call_id)
        return 0 if overall_strict or overall_dev else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
