"""Grade the after-fix rerun against the 2026-10-25 audit findings."""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys

P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[2]
sys.path.insert(0, str(ROOT))

from server.call.action_proof import (  # noqa: E402
    action_unconfirmed_line_for,
    claims_recorded_request,
)

SS = sorted(
    (json.loads(f.read_text(encoding="utf-8")) for f in (P / "sessions").glob("*.json")),
    key=lambda s: s["key"],
)
BASELINE = json.loads((P / "baseline.json").read_text(encoding="utf-8"))
ORIGINAL = json.loads(
    (P.parent / "multilingual-standard-audit-20261025" / "metrics.json").read_text(
        encoding="utf-8"
    )
)["overall"]

GENERIC = {
    "en-IN": "Of course — please go ahead.",
    "te-IN": "తప్పకుండా, చెప్పండి.",
    "hi-IN": "ज़रूर, बताइए।",
    "ta-IN": "கண்டிப்பாக, சொல்லுங்கள்.",
    "kn-IN": "ಖಂಡಿತ, ಹೇಳಿ.",
}
TECH = {
    "en-IN": "Sorry, we are facing a technical problem.",
    "te-IN": "క్షమించండి, మాకు ఒక సాంకేతిక సమస్య",
    "hi-IN": "क्षमा करें, हमें एक तकनीकी समस्या",
    "ta-IN": "மன்னிக்கவும், எங்களுக்கு ஒரு தொழில்நுட்பச் சிக்கல்",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ನಮಗೆ ಒಂದು ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆ",
}
UNCONFIRMED = {lang: action_unconfirmed_line_for(lang) for lang in GENERIC}
SCENARIO_TURNS = {
    "1_interested": 5,
    "2_future_interest": 3,
    "3_complete_rejection": 1,
    "4_abuse": 2,
    "5_diversion_danger": 5,
    "6_hangup": 4,
    "1b_direct_tool_request": 2,
    "3b_stop_contact": 1,
    "5b_direct_danger": 3,
}
END_KEYS = {"done", "reject", "optout", "abuse_threat"}
QUESTION_KEYS = {"interested", "details", "alternate", "future", "future_more", "return"}


def canned(spoken: str, language: str) -> str | None:
    text = (spoken or "").strip()
    if not text:
        return "empty"
    if text == GENERIC.get(language):
        return "generic_continuation"
    if text.startswith(TECH.get(language, "\0")):
        return "technical_farewell"
    if text == UNCONFIRMED.get(language):
        return "unconfirmed_action"
    return None


def grade(ss: list[dict]) -> dict:
    turns = [(s, t) for s in ss for t in s["turns"]]
    requests = [r for s in ss for r in s["requests"]]
    results = [r["result"] for r in requests if r.get("result", {}).get("done")]
    gates = [g for s in ss for g in s.get("close_gates", [])]
    end_turns = [(s, t) for s, t in turns if t["caller_key"] in END_KEYS]
    question_turns = [(s, t) for s, t in turns if t["caller_key"] in QUESTION_KEYS]
    substantive = [
        (s, t)
        for s, t in question_turns
        if not canned(t["spoken"], s["language"]) and len((t["spoken"] or "").strip()) >= 40
    ]
    return {
        "sessions": len(ss),
        "harness_completed": sum(s.get("status") == "completed" for s in ss),
        "reached_turns": len(turns),
        "planned_turns": sum(SCENARIO_TURNS[s["scenario"]] for s in ss),
        "question_turns": len(question_turns),
        "question_turns_substantive": len(substantive),
        "question_turns_canned": len(question_turns) - len(substantive),
        "canned_breakdown": dict(
            collections.Counter(
                canned(t["spoken"], s["language"])
                for s, t in turns
                if canned(t["spoken"], s["language"])
            )
        ),
        "question_canned_cases": [
            (s["key"], t["index"], t["caller_key"], canned(t["spoken"], s["language"]))
            for s, t in question_turns
            if canned(t["spoken"], s["language"])
        ],
        "generic_continuation_turns": sum(
            t["spoken"] == GENERIC.get(s["language"]) for s, t in turns
        ),
        "technical_farewell_turns": sum(
            (t["spoken"] or "").startswith(TECH.get(s["language"], "\0"))
            for s, t in turns
        ),
        "unconfirmed_replacement_turns": sum(
            (t["spoken"] or "").strip() == UNCONFIRMED.get(s["language"]) for s, t in turns
        ),
        "sessions_ended": sum(bool(s["carrier"]) for s in ss),
        "duplicate_hangup_sessions": sum(len(s["carrier"]) > 1 for s in ss),
        "explicit_end_turns": len(end_turns),
        "explicit_end_not_closed": [
            (s["key"], t["index"], t["caller_key"])
            for s, t in end_turns
            if not t["server_closed"]
        ],
        "nonterminal_close_turns": [
            (s["key"], t["index"], t["caller_key"])
            for s, t in turns
            if t["server_closed"] and t["caller_key"] not in END_KEYS
        ],
        "tool_executions": sum(len(s.get("tool_calls") or []) for s in ss),
        "connected_sessions_with_tool": sum(
            bool(s.get("tool_calls")) for s in ss if s["integration"]
        ),
        "tool_calls_outside_request_scenario": [
            (s["key"], call)
            for s in ss
            for call in (s.get("tool_calls") or [])
            if s["scenario"] != "1b_direct_tool_request"
        ],
        "request_turns_without_tool_when_connected": [
            s["key"]
            for s in ss
            if s["integration"]
            and s["scenario"] == "1b_direct_tool_request"
            and not s.get("tool_calls")
        ],
        "request_claims_without_integration": [
            s["key"]
            for s in ss
            if not s["integration"]
            and s["scenario"] == "1b_direct_tool_request"
            and any(claims_recorded_request(t["spoken"]) for t in s["turns"])
        ],
        "finish_reasons": dict(
            collections.Counter(
                str(
                    r.get("sse_finish")
                    or r.get("result", {}).get("finish_reason")
                    or r.get("finish_reason")
                )
                for r in requests
            )
        ),
        "incomplete_turn_errors": sum(
            r.get("error_type") == "IncompleteTurnError" for r in requests
        ),
        "whitespace_tail_requests": sum(
            r.get("sse_content_chars", 0) > 500
            and not (r.get("sse_content_tail") or "").strip()
            for r in requests
        ),
        "long_or_cut_replies": sum(
            1
            for r in results
            if str(r.get("finish_reason")) == "length"
            and (r.get("text") or "").strip()
            and not (r.get("text") or "").rstrip().endswith((".", "!", "?", "।"))
        ),
        "close_gate_rejections": dict(
            collections.Counter(
                g["server_result"].get("reject_code")
                or ("accepted" if g["server_result"].get("should_end") else "continue")
                for g in gates
            )
        ),
        "caller_turn_latency_median_s": round(
            statistics.median([t["elapsed_s"] for _, t in turns]), 3
        )
        if turns
        else None,
        "caller_turn_latency_p95_s": round(
            sorted(t["elapsed_s"] for _, t in turns)[int((len(turns) - 1) * 0.95)], 3
        )
        if turns
        else None,
    }


def main() -> None:
    if not SS:
        raise SystemExit("no sessions yet")
    metrics = {
        "overall": grade(SS),
        "by_language": {
            lang: grade([s for s in SS if s["language"] == lang])
            for lang in sorted({s["language"] for s in SS})
        },
        "by_scenario": {
            scenario: grade([s for s in SS if s["scenario"] == scenario])
            for scenario in sorted({s["scenario"] for s in SS})
        },
        "by_integration": {
            str(value): grade([s for s in SS if s["integration"] == value])
            for value in (False, True)
        },
        "original_overall": {
            key: ORIGINAL.get(key)
            for key in (
                "sessions",
                "harness_completed",
                "reached_caller_turns",
                "generic_continuation_turns",
                "technical_farewell_turns",
                "ended_sessions",
                "closed_on_nonterminal_test_turn",
                "explicit_end_not_closed",
                "mock_integration_executions",
                "finish_reasons",
                "length_errors",
                "observed_long_whitespace_tail_requests",
                "close_gate_results_instrumented_subset",
            )
        },
    }

    builds = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in (P / "agents").glob("*/build.json")
    ]
    metrics["builds"] = {
        "total": len(builds),
        "ready": sorted(b["business"] + "-" + b["language"] for b in builds if b.get("status") == "ready"),
        "failed": [
            {
                "key": b["business"] + "-" + b["language"],
                "http": b.get("http_status"),
                "code": (
                    ((b.get("response") or {}).get("detail") or {}).get("error") or {}
                ).get("code"),
                "message": (
                    ((b.get("response") or {}).get("detail") or {}).get("error") or {}
                ).get("message"),
            }
            for b in builds
            if b.get("status") != "ready"
        ],
    }

    capabilities = {}
    order_tools_offered = []
    for s in SS:
        for r in s["requests"]:
            tools = r.get("tools") or []
            if "CONFIRM_ORDER" in tools:
                order_tools_offered.append(s["key"])
    for f in (P / "agents").glob("*/compiled-brain.txt"):
        text = f.read_text(encoding="utf-8")
        key = f.parent.name
        capabilities[key] = (
            "order_confirmation: not_allowed" in text
            if "CALL CAPABILITIES" in text
            else "missing"
        )
    metrics["f10"] = {
        "compiled_capability_values": capabilities,
        "sessions_offered_confirm_order": order_tools_offered,
    }

    course_texts = {
        f.parent.name: f.read_text(encoding="utf-8")
        for f in (P / "agents").glob("course-*/compiled-brain.txt")
    }
    metrics["f07"] = {
        "course_compiled_with_3999": [k for k, v in course_texts.items() if "3999" in v],
        "course_compiled_with_4999": [k for k, v in course_texts.items() if "4999" in v],
    }

    (P / "verify.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(metrics["overall"], ensure_ascii=False, indent=1, default=str))
    print("canned question cases:", metrics["overall"]["question_canned_cases"][:20])
    print("builds:", metrics["builds"]["total"], "ready", len(metrics["builds"]["ready"]))
    print("failed builds:", json.dumps(metrics["builds"]["failed"], ensure_ascii=False)[:1200])
    print("order tools offered:", len(order_tools_offered))


if __name__ == "__main__":
    main()
