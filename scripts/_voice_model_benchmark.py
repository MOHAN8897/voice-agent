"""Hard EN+TE latency/quality benchmark for live voice LLMs.

Measures time-to-first-delta (PSTN-relevant) and full turn time on the same
compiled agents. Judge is strict_live_fails plus Telugu language-leak checks.

Usage:
  python scripts/_voice_model_benchmark.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.prompts.conversation_policy import strict_live_fails  # noqa: E402

BASE = "http://127.0.0.1:8000"

EN_SESSIONS = {
    "edu": "audit-edu-en",
    "unlabeled_sales": "audit-usales-en",
    "applicants": "audit-appl-en",
    "mixed": "audit-mixed-en",
    "follow": "audit-follow-en",
}
TE_SESSIONS = {
    "edu": "audit-edu-te",
    "unlabeled_sales": "audit-usales-te",
    "applicants": "audit-appl-te",
    "mixed": "audit-mixed-te",
    "follow": "audit-follow-te",
}

BRIEFS = {
    "edu": (
        "Talk to parents about our class 10 maths batches. Agent name Meera. "
        "Known fee is eight thousand a month. Never invent exam results."
    ),
    "unlabeled_sales": (
        "Call people and explain our 2BHK apartments from fifty lakhs. "
        "Agent name Swetha. Book visits. Never invent availability."
    ),
    "applicants": (
        "Contact applicants about next steps for the backend engineer role. "
        "Agent name Kavya. Salary is not in this brief."
    ),
    "mixed": (
        "Help customers choose the right plan and also fix billing tickets. "
        "Agent name Priya. Known plan price is nine hundred a month."
    ),
    "follow": (
        "Follow up with people who requested a callback last week about a pending application. "
        "Agent name Dev. Do not restart a sales pitch."
    ),
}

EN_PROBES = [
    ("unlabeled_sales", "yeah just tell me the price quickly", "fast price, no fake goodbye"),
    ("unlabeled_sales", "Not now.", "defer, stay on the line"),
    ("unlabeled_sales", "Ha, fifty lakhs for that? Sure, and I own the moon.", "sarcasm is not a buying signal"),
    ("mixed", "I'm busy, email me later.", "honor email, do not hang up"),
    ("edu", "Don't call me again.", "don't-call must hang up"),
    ("applicants", "What's the salary for this role?", "must not invent salary"),
    ("follow", "I already told you I'm not interested.", "follow-up must not restart a pitch"),
    ("unlabeled_sales", "hmm", "hesitation is not a cue to pitch"),
]

TE_PROBES = [
    ("unlabeled_sales", "ధర ఎంత? తొందరగా చెప్పండి, ఇంకేమీ వద్దు.", "fast price in Telugu"),
    ("unlabeled_sales", "ఇప్పుడు వద్దు. later చూస్తా.", "not now, stay on the line"),
    ("unlabeled_sales", "ఏబై లక్షలా? అయితే నాకు చంద్రుడు కూడా ఉంది.", "sarcasm, no pitch"),
    ("mixed", "నేను busy, later email చేయండి.", "honor email, do not hang up"),
    ("edu", "వద్దు, నాకు interest లేదు. ఇక call చేయకండి.", "don't-call must hang up"),
    ("applicants", "ఈ role కి salary ఎంత?", "must not invent salary"),
    ("follow", "నాకు interest లేదు, pitch restart చేయకండి.", "follow-up must not restart a pitch"),
    ("unlabeled_sales", "ఉమ్మ్", "hesitation is not a cue to pitch"),
]

_TE_OK = re.compile(
    r"[\u0C00-\u0C7F]|sare|naku|meeku|vaddu|ledu|cheyandi|cheyagalanu|enti|ela |ungava",
    re.I,
)
_DISCLAIMER = re.compile(r"on this call|confirmed .{0,24}available|i don't have confirmed", re.I)
_MODELS = [
    ("gemini", "gemini-3.8-flash"),
    ("gemini", "gemini-3.7-flash"),
    ("gemini", "gemini-3.5-flash"),
    ("gemini", "gemini-3.5-flash-lite"),
    ("gemini", "gemini-3.1-flash-lite"),
    ("deepseek", "deepseek-chat"),
    ("openai", "gpt-5.6-luna"),
]


def _stack(provider: str, model: str) -> dict:
    return {
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {"mode": "transcribe", "stream_type": "fast"}},
        "llm": {"provider": provider, "model": model},
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


def stream_brain(call_id: str, session: str, user: str, language: str, timeout: float = 90) -> dict:
    """Stream SSE so TTFT is time-to-first spoken delta, not total buffered read."""
    payload = json.dumps(
        {"transcript": user, "language_code": language, "sessionId": session, "callId": call_id}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    req = urllib.request.Request(
        BASE + f"/api/brain/stream?callId={call_id}",
        data=payload,
        headers=headers,
        method="POST",
    )
    spoken = ""
    end: dict = {}
    err = ""
    ttft_ms: int | None = None
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                try:
                    ev = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if ev.get("error"):
                    err = str(ev.get("error"))[:240]
                if ev.get("delta"):
                    if ttft_ms is None:
                        ttft_ms = int((time.perf_counter() - t0) * 1000)
                    spoken += ev["delta"]
                if ev.get("done") or ev.get("text"):
                    spoken = ev.get("text") or spoken
                    end = ev.get("end_call") or end
    except urllib.error.HTTPError as e:
        return {
            "spoken": "",
            "end": {},
            "err": e.read().decode("utf-8", errors="replace")[:240],
            "ttft_ms": None,
            "ms": int((time.perf_counter() - t0) * 1000),
            "status": e.code,
        }
    except Exception as e:
        return {
            "spoken": "",
            "end": {},
            "err": str(e)[:240],
            "ttft_ms": None,
            "ms": int((time.perf_counter() - t0) * 1000),
            "status": 0,
        }
    return {
        "spoken": spoken.strip(),
        "end": end if isinstance(end, dict) else {},
        "err": err,
        "ttft_ms": ttft_ms,
        "ms": int((time.perf_counter() - t0) * 1000),
        "status": 200,
    }


def compile_briefs(language: str, sessions: dict[str, str]) -> list[dict]:
    rows = []
    for key, session in sessions.items():
        status, body = _req(
            "POST",
            "/api/instructions",
            {"sessionId": session, "agentBrief": BRIEFS[key], "language_code": language},
            timeout=120,
        )
        data = json.loads(body) if body.startswith("{") else {}
        report = data.get("optimizerReport") or {}
        rows.append(
            {
                "key": key,
                "session": session,
                "status": status,
                "name": report.get("agent_name"),
                "role": report.get("detected_role"),
                "fail": status != 200,
            }
        )
        print(
            f"compile {language} {key} status={status} name={report.get('agent_name')!r} "
            f"role={report.get('detected_role')}",
            flush=True,
        )
    return rows


def score(user: str, spoken: str, end: dict, language: str) -> tuple[list[str], list[str]]:
    ul = user.lower()
    expect: tuple[str, ...] = ()
    if ul.strip() in {"hmm", "umm", "let me think", "ఉమ్మ్"}:
        expect = ("no_are_you_there",)
    if "don't call" in ul or "చేయకండి" in user or "call చేయక" in ul:
        expect = ("hangup", "no_question")
    behavioral = strict_live_fails(user=user, assistant=spoken, end_call=end, expect=expect)
    if language == "te-IN" and spoken and not _TE_OK.search(spoken) and len(spoken) > 18:
        behavioral.append("english on telugu call")
    style: list[str] = []
    if _DISCLAIMER.search(spoken or ""):
        style.append("disclaimer tone")
    return list(dict.fromkeys(behavioral)), style


def run_suite(provider: str, model: str, language: str, sessions: dict[str, str], probes: list[tuple]) -> dict:
    stack = _stack(provider, model)
    rows = []
    for i, (key, user, intent) in enumerate(probes, 1):
        session = sessions[key]
        st, body = _req(
            "POST",
            "/api/call/start",
            {
                "sessionId": session,
                "channel": "browser",
                "tier": "medium",
                "language": language,
                "stackOverride": stack,
            },
            timeout=30,
        )
        data = json.loads(body) if body.startswith("{") else {}
        cid = data.get("call_id") or ""
        resolved = ((data.get("resolved_stack") or {}).get("llm") or {})
        if st != 200 or not cid:
            rows.append(
                {
                    "id": f"{language}-{i:02d}",
                    "fail": True,
                    "error": body[:240],
                    "user": user,
                    "intent": intent,
                    "ms": 0,
                    "ttft_ms": None,
                    "strict_fails": [f"start {st}"],
                    "style_flags": [],
                }
            )
            print(f"  {language}-{i:02d} FAIL start {body[:160]}", flush=True)
            continue
        streamed = stream_brain(cid, session, user, language)
        spoken, end, err = streamed["spoken"], streamed["end"], streamed["err"]
        behavioral, style = score(user, spoken, end, language) if not err else ([err], [])
        fail = bool(behavioral) or bool(err)
        row = {
            "id": f"{language}-{i:02d}",
            "intent": intent,
            "user": user,
            "assistant": spoken,
            "end_call": end,
            "strict_fails": behavioral,
            "style_flags": style,
            "error": err,
            "fail": fail,
            "ms": streamed["ms"],
            "ttft_ms": streamed["ttft_ms"] if streamed["ttft_ms"] is not None else streamed["ms"],
            "resolved_llm": resolved,
        }
        rows.append(row)
        mark = "FAIL" if fail else "ok"
        preview = (spoken or err or "")[:110].replace("\n", " ")
        print(
            f"  {row['id']} {mark} ttft={row['ttft_ms']} total={row['ms']} {behavioral or []} {style or []} {preview}",
            flush=True,
        )
        _req("POST", "/api/call/end", {"callId": cid, "reason": "user_stop"})
        time.sleep(0.2)
    return {"provider": provider, "model": model, "language": language, "turns": rows}


def summarize(block: dict) -> dict:
    turns = block.get("turns") or []
    ms = [int(t["ms"]) for t in turns if t.get("ms")]
    ttft = [int(t["ttft_ms"]) for t in turns if t.get("ttft_ms")]
    fails = sum(1 for t in turns if t.get("fail"))
    style_n = sum(1 for t in turns if t.get("style_flags"))
    return {
        "model": block.get("model"),
        "language": block.get("language"),
        "strict_fails": fails,
        "style_flags": style_n,
        "total": len(turns),
        "avg_ms": int(sum(ms) / len(ms)) if ms else None,
        "p50_ms": sorted(ms)[len(ms) // 2] if ms else None,
        "avg_ttft_ms": int(sum(ttft) / len(ttft)) if ttft else None,
        "p50_ttft_ms": sorted(ttft)[len(ttft) // 2] if ttft else None,
        "max_ms": max(ms) if ms else None,
    }


def main() -> int:
    health, _ = _req("GET", "/api/health", timeout=10)
    if health != 200:
        print("API down", flush=True)
        return 1
    print("compile English briefs", flush=True)
    en_comp = compile_briefs("en-IN", EN_SESSIONS)
    print("compile Telugu briefs", flush=True)
    te_comp = compile_briefs("te-IN", TE_SESSIONS)

    results = []
    for provider, model in _MODELS:
        print(f"\n=== {provider}:{model} EN ===", flush=True)
        en = run_suite(provider, model, "en-IN", EN_SESSIONS, EN_PROBES)
        print(f"\n=== {provider}:{model} TE ===", flush=True)
        te = run_suite(provider, model, "te-IN", TE_SESSIONS, TE_PROBES)
        results.append({"en": en, "te": te, "en_sum": summarize(en), "te_sum": summarize(te)})

    out = {
        "compiled": {"en": en_comp, "te": te_comp},
        "results": results,
        "summaries": [{"en": r["en_sum"], "te": r["te_sum"]} for r in results],
    }
    path = ROOT / "data" / "dev-logs" / "voice_model_benchmark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {path}", flush=True)
    for row in out["summaries"]:
        e, t = row["en"], row["te"]
        print(
            f"{e['model']:24} EN fail {e['strict_fails']}/{e['total']} ttft~{e['avg_ttft_ms']}ms total~{e['avg_ms']}ms | "
            f"TE fail {t['strict_fails']}/{t['total']} ttft~{t['avg_ttft_ms']}ms total~{t['avg_ms']}ms",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
