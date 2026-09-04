"""TEST 7 — PSTN barge-in (caller interrupts agent speech).

Places outbound call, monitors media-flow for queue_cleared + interrupted_frames.
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


def _safe(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


def score_barge_in(flow: dict | None, lines: list[dict], barge_in: bool) -> dict[str, bool]:
    metrics = (flow or {}).get("metrics") or {}
    events = (flow or {}).get("events") or []
    stages = (flow or {}).get("stages") or {}
    health = (flow or {}).get("health") or {}
    checks = health.get("checks") or {}

    user_turns = [ln for ln in lines if ln.get("role") == "user" and (ln.get("text") or "").strip()]
    agent_turns = [ln for ln in lines if ln.get("role") == "assistant" and (ln.get("text") or "").strip()]

    return {
        "barge_in_enabled": barge_in,
        "queue_cleared_logged": any(e.get("stage") == "queue_cleared" for e in events),
        "interrupted_frames_gt_0": int(metrics.get("interrupted_frames") or 0) > 0,
        "outbound_audio_flow": bool(
            checks.get("telnyx_outbound")
            or "outbound_sent" in stages
            or int(metrics.get("outbound_sent_frames") or 0) > 0
        ),
        "tts_in_flow": bool(checks.get("tts") or "tts_audio" in stages),
        "user_turns_gte_2": len(user_turns) >= 2,
        "agent_turns_gte_2": len(agent_turns) >= 2,
        "new_dialogue_after_opening": len(user_turns) >= 1 and len(agent_turns) >= 1,
    }


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
    gates = score_barge_in(None, lines, barge_in)
    gates["trace_turns_gte_2"] = len(trace.get("turns") or []) >= 2
    print("Offline validation for", call_id)
    print("Transcript:")
    for ln in lines:
        role = ln.get("role", "?")
        text = _safe(str(ln.get("text") or ""))[:100]
        print(f"  [{role}] {text}")
    print()
    print("TEST 7 gate:")
    for key, passed in gates.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {key}")
    core = (
        gates["barge_in_enabled"]
        and gates["new_dialogue_after_opening"]
        and gates["user_turns_gte_2"]
        and gates["agent_turns_gte_2"]
    )
    print("overall (dialogue only):", "PASS" if core else "FAIL")
    print("note: queue_cleared / interrupted_frames require live media-flow snapshot")
    return 0 if core else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 7 — PSTN barge-in")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--to", default=TO)
    parser.add_argument("--call-id", default="", help="Validate existing call instead of placing new dial")
    parser.add_argument("--offline-call-id", default="", help="Score call archive on disk (no API)")
    parser.add_argument("--talk-seconds", type=int, default=90, help="How long to keep call open")
    args = parser.parse_args()

    from server.services.pstn_voice_core import ENABLE_PSTN_BARGE_IN

    if not ENABLE_PSTN_BARGE_IN:
        print("FAIL: ENABLE_PSTN_BARGE_IN must be True for TEST 7")
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
        external_id = ""
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
            print("Barge-in test (3 trials recommended):")
            print("  1) Listen to opening greeting")
            print("  2) Ask an open question (e.g. 'meeku entha details cheppagalaru?')")
            print("  3) While agent is speaking, talk over them loudly:")
            print("     'Aapu, vinandi' or 'Stop, listen'")
            print("  4) Ask a NEW short question after interrupt")
            print(f"Stay on call up to {args.talk_seconds}s, then hang up.")
            print()

            saw_queue_clear = False
            for i in range(args.talk_seconds // 5):
                await asyncio.sleep(5)
                try:
                    flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
                except httpx.HTTPError as exc:
                    print(f"  [{(i + 1) * 5}s] media-flow poll error: {exc.__class__.__name__}")
                    continue
                flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
                call_id = str(flow.get("call_id") or call_id)
                external_id = str(flow.get("external_id") or external_id)
                metrics = flow.get("metrics") or {}
                events = flow.get("events") or []
                if any(e.get("stage") == "queue_cleared" for e in events):
                    saw_queue_clear = True
                active = flow.get("active")
                print(
                    f"  [{(i + 1) * 5}s] active={active} call_id={call_id[:12] if call_id else '-'} "
                    f"interrupted_frames={metrics.get('interrupted_frames')} "
                    f"queue_cleared={'yes' if saw_queue_clear else 'no'}"
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
        flow_r = await client.get(
            "/api/dev/telephony/media-flow",
            params={"call_id": external_id or call_id},
            headers=headers,
        )
        lines = (tr.json().get("lines") or []) if tr.status_code == 200 else []
        if lines and isinstance(lines[0], str):
            lines = [json.loads(ln) for ln in lines if ln.strip()]
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}

        print()
        print("Transcript:")
        for ln in lines:
            role = ln.get("role", "?")
            text = _safe(str(ln.get("text") or ""))[:100]
            print(f"  [{role}] {text}")

        gates = score_barge_in(flow, lines, ENABLE_PSTN_BARGE_IN)
        print()
        print("TEST 7 gate:")
        for key, passed in gates.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        metrics = (flow or {}).get("metrics") or {}
        print("interrupted_frames:", metrics.get("interrupted_frames"))
        overall = all(gates.values())
        print("overall:", "PASS" if overall else "PARTIAL/FAIL")
        print("call_id:", call_id)
        print()
        print("Manual: did agent audio STOP within ~500ms when you talked over them? (3/3 trials)")
        return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
