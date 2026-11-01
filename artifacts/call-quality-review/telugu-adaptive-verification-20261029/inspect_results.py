"""Rebuild readable transcripts and objective counts from retained session data."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
cases = []
for path in sorted((ROOT / "sessions").glob("*.json")):
    if path.name.endswith("-prompt.json"):
        continue
    value = json.loads(path.read_text(encoding="utf-8"))
    if "scenario" in value and "wall_elapsed_s" in value:
        cases.append(value)
out = ["# Current-runtime Telugu verification transcripts", "",
       "Fresh subject-model responses; the caller is adaptive except cases explicitly listing fixed_turns.",
       "TTS, STT, carrier and external integration transport are mocked. Caller and subject use live Sarvam inference.", ""]
summaries = []
for case in cases:
    name = case["scenario"]["id"]
    carrier = case.get("carrier", [])
    row = {"id": name, "turns": len(case["turns"]), "errors": case.get("errors", []),
           "agent_closed": case.get("ended_by_agent"), "carrier_attempts": len(carrier),
           "carrier_acks": sum(c.get("acknowledged") is True for c in carrier),
           "external_actions": [a.get("name") for a in case.get("external_actions", [])],
           "contact_preference": (case.get("metadata") or {}).get("contact_preference"),
           "new_callback_records": [v for v in (case.get("db") or {}).get("callbacks", [])
                                    if v.get("original_call_id") == case["call_id"]],
           "new_followup_jobs": [v for v in (case.get("db") or {}).get("jobs", [])
                                 if v.get("source_id") == case["call_id"]],
           "disposition": (case.get("outcome") or {}).get("disposition"),
           "status_tags": (case.get("outcome") or {}).get("status_tags"),
           "final_facts": case["turns"][-1].get("memory_after", {}).get("facts") if case["turns"] else {},
           "elapsed_s": case.get("wall_elapsed_s")}
    summaries.append(row)
    out += [f"## {name}", "", f"Agent closed: {row['agent_closed']}; carrier acknowledgements: {row['carrier_acks']}; disposition: {row['disposition']}",
            f"External actions: {', '.join(row['external_actions']) or 'none'}", ""]
    for turn in case["turns"]:
        out += [f"### Turn {turn['turn']}", "", "Caller: " + turn["caller"]["utterance"], "",
                "Delivered: " + turn.get("spoken", ""), "",
                "Memory after: " + json.dumps(turn.get("memory_after", {}), ensure_ascii=False), ""]
        for done in turn.get("done", []):
            if done.get("text"):
                out += ["Final text: " + done["text"], ""]
    out += ["Final outcome: " + json.dumps(case.get("outcome"), ensure_ascii=False), ""]
(ROOT / "TRANSCRIPTS.md").write_text("\n".join(out), encoding="utf-8")
(ROOT / "case-summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"sessions": len(cases), "turns": sum(len(c['turns']) for c in cases),
                  "carrier_acks": sum(r['carrier_acks'] for r in summaries),
                  "harness_errors": sum(bool(r['errors']) for r in summaries),
                  "dispositions": dict(Counter(r['disposition'] for r in summaries))}))
