"""Live-model negative controls for independent call/contact decisions."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from environment import setup, write, REQUESTS, NETWORK, ACTOR

CASES = [
    ("ordinary_refusal_observed", "నమస్తే, నాకు ఇప్పుడు విజిటింగ్ కార్డ్స్ అవసరం లేదు. అందుకే ఈ సర్వీస్ వద్దు అని చెప్తున్నాను, దయచేసి కాల్ ముగించండి.", "close", "end_this_call"),
    ("scoped_product", "Visiting cards నే కావాలి. Wedding cards ధరలు ఎలా ఉంటాయో కేవలం తెలుసుకోవడానికి అడుగుతున్నాను. Wedding cards ఆర్డర్ చేయడం లేదు.", "continue", "none"),
    ("future_permission", "నేను కిరణ్. Python course నాకు ఆసక్తి ఉంది. రేపు నేనే మీకు call చేస్తాను. ఇది callback అడగడం కాదు. భవిష్యత్తులో మీ కొత్త offers గురించి నాకు calls చేయవచ్చు, నా number block చేయకండి. ప్రస్తుతం ఇంతే, ధన్యవాదాలు.", "close", "self_callback"),
    ("ordinary_goodbye", "అంతే, కావాల్సిన వివరాలు తెలిసాయి. ధన్యవాదాలు, కాల్ ముగించండి.", "close", "end_this_call"),
    ("optout_question", "ఈ నంబర్‌కు ఇకపై ఎప్పటికీ కాల్ చేయకండి. కానీ ఇప్పుడు వంద విజిటింగ్ కార్డుల ధర ఎంత?", "continue", "do_not_call"),
    ("email_confirmation", "రేపు ఉదయం 10 గంటలకి slot fix చేయండి సురేష్. ఈ servicing లో ఏమేమి parts replace అవ్వొచ్చో మీకు ముందే ఏమైనా idea ఉంటుందా? అలాగే నా email sravani.audit@example.invalid కి confirmation message పంపించగలరా?", "continue", "none"),
    ("pure_callback", "నేను ఇప్పుడు మాట్లాడలేను. ఆరు గంటల తర్వాత ఇదే నంబర్‌కు నాకు కాల్ చేయండి.", "close", "callback"),
    ("decline_callback", "లేదు, callback వద్దు. మీరు నా calendar లో appointment create చేసి confirm అయిందో చెప్పండి.", "continue", "decline_callback"),
    ("name_not_supplied", "నమస్తే కవిత గారు. వంద మ్యాట్ విజిటింగ్ కార్డులకు ధర ఎంత? నా పేరు ఇంకా చెప్పలేదు.", "continue", "none"),
    ("positive_name", "నా పేరు రమణ. నాకు 200 matte visiting cards కావాలి. ధర, delivery వివరాలు చెప్పండి.", "continue", "none"),
]


async def main():
    os.environ["AUDIT_RESUME"] = "1"
    _, stack, _ = await setup()
    ACTOR.set("agent")
    from server.call.close_classifier import classify_close_turn
    results = []
    for name, text, decision, contact in CASES:
        result = await classify_close_turn(transcript=text, agent_previous="మీకు ఏ వివరాలు కావాలో చెప్పండి.",
            language="te-IN", llm=stack.llm, extract_memory=True)
        row = {"name": name, "caller": text, "result": result,
               "passed": bool(result and result.get("decision") == decision and result.get("contact_intent", "none") == contact)}
        if name == "name_not_supplied":
            row["passed"] &= not any(x.get("key") == "caller_name" for x in (result or {}).get("memory_operations", []))
        results.append(row)
        write("controls/results.json", results)
        print(json.dumps({"name": name, "passed": row["passed"], "result": result}, ensure_ascii=False), flush=True)
    write("controls/requests.json", REQUESTS)
    write("controls/network.json", NETWORK)
    from server.db.connection import close_db
    await close_db()
    if not all(r["passed"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
