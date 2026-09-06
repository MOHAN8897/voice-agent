"""Hard isolated conversation probe — compare LLM stacks on remaining failure modes.

Usage:
  python scripts/_hard_conversation_probe.py
  python scripts/_hard_conversation_probe.py gemini-3.7-flash
Sessions must already be compiled (wave 1 live_audit compile).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.prompts.conversation_policy import strict_live_fails  # noqa: E402

BASE = "http://127.0.0.1:8000"
SESSIONS = {
    "edu": "audit-edu-en",
    "unlabeled_sales": "audit-usales-en",
    "applicants": "audit-appl-en",
    "mixed": "audit-mixed-en",
    "follow": "audit-follow-en",
}

PROBES = [
    ("unlabeled_sales", "yeah just tell me the price quickly", "fast price, no fake goodbye"),
    ("unlabeled_sales", "Not now.", "defer, stay on the line"),
    ("unlabeled_sales", "Ha, fifty lakhs for that? Sure, and I own the moon.", "sarcasm is not a buying signal"),
    ("mixed", "I'm busy, email me later.", "honor email, do not hang up"),
    ("edu", "Don't call me again.", "don't-call must hang up"),
    ("applicants", "What's the salary for this role?", "must not invent salary"),
    ("follow", "I already told you I'm not interested.", "follow-up must not restart a pitch"),
    ("unlabeled_sales", "hmm", "hesitation is not a cue to pitch"),
]


def _stack(model: str) -> dict:
    if model.startswith("gemini"):
        return {
            "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
            "llm": {"provider": "gemini", "model": model},
            "tts": {"provider": "sarvam", "model": "bulbul:v3"},
        }
    return {
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
        "llm": {"provider": "openai", "model": model},
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
    except Exception as e:
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


def main() -> int:
    model = (sys.argv[1] if len(sys.argv) > 1 else "gpt-5.6-luna").strip()
    stack = _stack(model)
    rows = []
    for i, (key, user, intent) in enumerate(PROBES, 1):
        session = SESSIONS[key]
        st, body = _req(
            "POST",
            "/api/call/start",
            {
                "sessionId": session,
                "channel": "browser",
                "tier": "medium",
                "language": "en-IN",
                "stackOverride": stack,
            },
            timeout=30,
        )
        data = json.loads(body) if body.startswith("{") else {}
        cid = data.get("call_id") or ""
        if st != 200 or not cid:
            rows.append({"id": f"P-{i:02d}", "fail": True, "error": body[:200], "user": user, "intent": intent})
            print(f"P-{i:02d} FAIL start {body[:160]}", flush=True)
            continue
        t0 = time.time()
        status, raw = _req(
            "POST",
            f"/api/brain/stream?callId={cid}",
            {"transcript": user, "language_code": "en-IN", "sessionId": session, "callId": cid},
            timeout=90,
        )
        spoken, end, err = parse_sse(raw) if status == 200 else ("", {}, raw[:240])
        expect: tuple[str, ...] = ()
        ul = user.lower()
        if ul.strip() in {"hmm", "umm", "let me think"}:
            expect = ("no_are_you_there",)
        if "don't call" in ul:
            expect = ("hangup", "no_question")
        fails = strict_live_fails(user=user, assistant=spoken, end_call=end, expect=expect)
        fail = bool(fails) or bool(err)
        row = {
            "id": f"P-{i:02d}",
            "intent": intent,
            "user": user,
            "assistant": spoken,
            "end_call": end,
            "strict_fails": fails,
            "error": err,
            "fail": fail,
            "ms": int((time.time() - t0) * 1000),
        }
        rows.append(row)
        mark = "FAIL" if fail else "ok"
        preview = (spoken or err or "")[:120].replace("\n", " ")
        print(f"P-{i:02d} {mark} {fails or []} {preview}", flush=True)
        _req("POST", "/api/call/end", {"callId": cid, "reason": "user_stop"})

    fail_n = sum(1 for r in rows if r.get("fail"))
    out = {"model": model, "stack": stack, "turns": rows, "strict_fails": fail_n, "total": len(rows)}
    path = ROOT / "data" / "dev-logs" / f"hard_probe_{model.replace(':', '_')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path} strict fails {fail_n}/{len(rows)} model={model}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
