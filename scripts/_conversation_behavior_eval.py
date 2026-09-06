"""
Live English adversarial eval — golden behavior, not golden wording.

Compiles one agent per role from EVAL_BRIEFS, then runs SCENARIOS in order
per role against /api/brain/stream.

Usage (API must be up):
    python scripts/_conversation_behavior_eval.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.prompts.conversation_policy import judge_turn  # noqa: E402
from server.eval.behavior_scenarios import EVAL_BRIEFS, SCENARIOS  # noqa: E402

BASE = "http://127.0.0.1:8000"
STACK = {
    "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
    "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    "tts": {"provider": "sarvam", "model": "bulbul:v3"},
}


def _req(method: str, path: str, payload: dict | None = None, timeout: float = 90) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return 0, str(e)


def parse_sse(raw: str) -> tuple[str, dict, str]:
    spoken = ""
    end: dict = {}
    err = ""
    for line in raw.splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        try:
            ev = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if ev.get("error"):
            err = str(ev.get("error"))[:240]
        if ev.get("delta"):
            spoken += ev["delta"]
        if ev.get("done") or ev.get("text"):
            spoken = ev.get("text") or spoken
            end = ev.get("end_call") or end
    return spoken.strip(), end if isinstance(end, dict) else {}, err


def compile_agent(role: str) -> tuple[bool, str]:
    spec = EVAL_BRIEFS[role]
    status, body = _req(
        "POST",
        "/api/instructions",
        {
            "sessionId": spec["session"],
            "agentBrief": spec["brief"],
            "language_code": spec["language"],
        },
        timeout=120,
    )
    if status != 200:
        return False, body[:400]
    data = json.loads(body)
    script = data.get("agentScript") or ""
    if "ROLE & OBJECTIVE" not in script:
        return False, "compiled script missing role section"
    return True, script[:200]


def start_call(session: str) -> tuple[str, dict]:
    status, body = _req(
        "POST",
        "/api/call/start",
        {
            "sessionId": session,
            "channel": "browser",
            "tier": "medium",
            "language": "en-IN",
            "stackOverride": STACK,
        },
    )
    if status != 200:
        raise RuntimeError(f"call/start {status} {body[:300]}")
    call = json.loads(body)
    return call["call_id"], (call.get("resolved_stack") or {}).get("llm") or {}


def main() -> int:
    health, _ = _req("GET", "/api/health")
    if health != 200:
        print("API is not running at http://127.0.0.1:8000")
        return 2

    for role in EVAL_BRIEFS:
        ok, msg = compile_agent(role)
        print(f"compile {role}: {'ok' if ok else 'FAIL'} {msg[:120]}")
        if not ok:
            return 1

    by_role: dict[str, list[dict]] = defaultdict(list)
    for sc in SCENARIOS:
        by_role[sc["role"]].append(sc)

    rows = []
    failed = 0
    for role, turns in by_role.items():
        session = EVAL_BRIEFS[role]["session"]
        call_id, llm = start_call(session)
        print(f"\nrole={role} call={call_id} llm={llm.get('provider')}/{llm.get('model')}")
        for sc in turns:
            t0 = time.perf_counter()
            status, raw = _req(
                "POST",
                f"/api/brain/stream?callId={call_id}",
                {
                    "transcript": sc["user"],
                    "language_code": "en-IN",
                    "sessionId": session,
                    "callId": call_id,
                },
                timeout=120,
            )
            ms = int((time.perf_counter() - t0) * 1000)
            spoken, end, err = parse_sse(raw) if status == 200 else ("", {}, raw[:240])
            fails = judge_turn(
                user=sc["user"],
                assistant=spoken,
                end_call=end,
                expect=sc["expect"],
            )
            if err:
                fails.append(f"error:{err[:120]}")
            row = {
                "id": sc["id"],
                "role": role,
                "intent": sc["intent"],
                "user": sc["user"],
                "assistant": spoken,
                "expect": list(sc["expect"]),
                "end_call": end,
                "ms": ms,
                "fails": fails,
            }
            rows.append(row)
            mark = "PASS" if not fails else "FAIL"
            if fails:
                failed += 1
            safe = (spoken or "(empty)").encode("ascii", "replace").decode("ascii")
            print(f"  [{mark}] {sc['id']} q={spoken.count('?')} {safe[:140]}")
            if fails:
                print(f"       {fails}")
            if end.get("should_end"):
                break
        _req("POST", "/api/call/end", {"callId": call_id, "reason": "user_stop"})

    out = ROOT / "data" / "dev-logs" / "conversation_behavior_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"failed": failed, "total": len(rows), "turns": rows}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{failed}/{len(rows)} failed  wrote {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    import os

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
