"""One-shot Test Studio brain eval — 25 human-call utterances."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
SESSION = "test-studio"
STACK = {
    "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
    "llm": {"provider": "openai", "model": "gpt-5.6-luna"},
    "tts": {"provider": "sarvam", "model": "bulbul:v3"},
}

TURNS = [
    "నాకు 10,000 square feet apartment కావాలి.",
    "మీ దగ్గర 1,000 square feet కాకుండా bigger apartments ఏమైనా ఉన్నాయా?",
    "Price ఎంత?",
    "నాకు budget ఇంకా decide కాలేదు.",
    "Just price చెప్పండి, ఇంకేమీ వద్దు.",
    "నాకు ఇప్పుడే కొనాలని లేదు, just information కోసం అడుగుతున్నాను.",
    "మీరు చెప్పేది నాకు already తెలుసు.",
    "Location నాకు నచ్చలేదు.",
    "చాలా expensive గా ఉంది.",
    "నాకు ఇంకో property already చూసాను.",
    "నేను నా husband/wife తో మాట్లాడి చెప్తాను.",
    "నాకు WhatsApp లో details పంపించండి.",
    "Call later చేయండి.",
    "నేను busy గా ఉన్నాను.",
    "మీరు చాలా questions అడుగుతున్నారు.",
    "నన్ను ఎందుకు ఇంత అడుగుతున్నారు?",
    "నాకు apartment కావాలో plot కావాలో ఇంకా decide కాలేదు.",
    "Plot కూడా చూడొచ్చు, apartment కూడా చూడొచ్చు.",
    "నాకు 50 lakhs budget ఉంది, కానీ size important.",
    "నాకు 10,000 square feet కావాలి కానీ 50 lakhs కంటే ఎక్కువ budget లేదు.",
    "Exact price మీకు తెలియదా? అయితే ఎందుకు call చేస్తున్నారు?",
    "అది నాకు తెలియదు, మీరు చెప్పండి.",
    "సరే, మీరే suggest చేయండి నాకు ఏది better?",
    "Okay, నాకు interest ఉంది. Next step ఏంటి?",
    "వద్దు, నాకు interest లేదు. ఇక call చేయకండి.",
]


def _req(method: str, path: str, payload: dict | None = None, timeout: float = 90) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def parse_sse(raw: str) -> tuple[str, dict, dict]:
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
    return spoken.strip(), end if isinstance(end, dict) else {}, {"error": err}


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    start_status, start_body = _req(
        "POST",
        "/api/call/start",
        {
            "sessionId": SESSION,
            "channel": "browser",
            "tier": "medium",
            "language": "te-IN",
            "stackOverride": STACK,
        },
    )
    if start_status != 200:
        print("FAIL call/start", start_status, start_body[:400])
        return 1
    call = json.loads(start_body)
    call_id = call["call_id"]
    llm = (call.get("resolved_stack") or {}).get("llm") or {}
    print(f"call={call_id} llm={llm.get('provider')}/{llm.get('model')} label={label}")
    rows = []
    for i, text in enumerate(TURNS, 1):
        t0 = time.perf_counter()
        status, raw = _req(
            "POST",
            f"/api/brain/stream?callId={call_id}",
            {
                "transcript": text,
                "language_code": "te-IN",
                "sessionId": SESSION,
                "callId": call_id,
            },
            timeout=120,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        spoken, end, extra = parse_sse(raw) if status == 200 else ("", {}, {"error": raw[:240]})
        q = spoken.count("?") + spoken.count("？")
        row = {
            "n": i,
            "user": text,
            "assistant": spoken,
            "questions": q,
            "ms": ms,
            "end_call": end,
            "error": extra.get("error") or ("" if status == 200 else f"http {status}"),
        }
        rows.append(row)
        end_bit = ""
        if end.get("should_end"):
            end_bit = f" END:{end.get('reason')}"
        safe = (spoken or "(empty)").encode("ascii", "replace").decode("ascii")
        print(f"[{i:02d}] q={q} chars={len(spoken)} ms={ms}{end_bit}", flush=True)
        print(f"     {safe[:180]}", flush=True)
        if row["error"]:
            print(f"     ERR {row['error'][:200]}", flush=True)
        if end.get("should_end") and i < len(TURNS):
            print("     (call ended early)", flush=True)
    out = ROOT / "data" / "dev-logs" / f"human_call_eval_{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"call_id": call_id, "llm": llm, "turns": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    _req("POST", "/api/call/end", {"callId": call_id, "reason": "user_stop"})
    return 0


if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
