"""Live check that the call LLM picks the right integration action with valid arguments.

Sends real caller requests (English, Telugu, Hindi) to the configured LLM with the
same model-facing tool schemas a call gets (setup-owned parameters removed,
duplicates hidden), and checks the first tool call: right action, and arguments
the router's own validator accepts once tenant setup is filled in. Nothing is
executed against any provider.

    python scripts/verify_llm_tool_alignment.py [--model sarvam-105b-conversations]
"""
import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.brain.capabilities import apply_available_tools  # noqa: E402
from server.brain.compiled_brain_artifact import assemble_unified_brain  # noqa: E402
from server.call.enquiry import SAVE_ENQUIRY_TOOL  # noqa: E402
from server.call.human_handoff import REQUEST_HUMAN_HANDOFF_TOOL  # noqa: E402
from server.providers.sarvam_llm import SarvamLLMAdapter  # noqa: E402
from server.services.call_integrations import capability_rows  # noqa: E402
from server.services.integration_settings import filled_params, model_facing_schema  # noqa: E402
from server.services.tool_schema_registry import get_tools_for_tenant, tool_definition, validate_tool_arguments  # noqa: E402

APPS = ["GOOGLECALENDAR", "HUBSPOT", "SHOPIFY", "ZENDESK", "SLACK", "TWILIO_SMS", "GMAIL"]
SETTINGS = {"SLACK": {"channel": "C0SALES"}, "GOOGLECALENDAR": {"day_start": "10:00", "day_end": "18:00"}}
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

SCRIPT = ("You are Meera, receptionist at Sunrise Dental and Supplies. Book consultations, look up orders and "
          "support tickets, send details by SMS or email when the caller asks, and log callers in the CRM. "
          f"Today is {date.today().isoformat()}; the caller's time zone is Asia/Kolkata.")

CASES = [
    ("en: free slot", "Do you have a free 30 minute slot tomorrow afternoon for a consultation?", {"GOOGLECALENDAR_FIND_FREE_SLOTS"},
     lambda a: a.get("date") == TOMORROW),
    ("en: order status", "Where is my order number 1042? It has not arrived yet.", {"SHOPIFY_GET_ORDER"},
     lambda a: "1042" in str(a.get("order_id", ""))),
    ("en: ticket status", "I raised a complaint last week from ravi.kumar@example.com, what is the status?",
     {"ZENDESK_SEARCH_TICKETS"}, lambda a: "ravi.kumar@example.com" in str(a.get("query", ""))),
    ("en: sms", "Please text me your clinic address on +919876543210.", {"TWILIO_SMS_SEND_MESSAGE"},
     lambda a: a.get("to", "").replace(" ", "").endswith("9876543210") and len(a.get("body", "")) > 5),
    ("en: cancel own booking", "I need to cancel my appointment tomorrow. I booked it with asha.rao@example.com.",
     {"GOOGLECALENDAR_LIST_EVENTS"}, lambda a: a.get("date") == TOMORROW),
    ("en: crm lookup", "Can you check if you already have me on file? My email is neha@example.com.",
     {"HUBSPOT_LOOKUP_CONTACT"}, lambda a: a.get("email") == "neha@example.com"),
    ("te: free slot", "రేపు ఉదయం డాక్టర్ అపాయింట్మెంట్ కి ఖాళీ స్లాట్ ఉందా?", {"GOOGLECALENDAR_FIND_FREE_SLOTS"},
     lambda a: a.get("date") == TOMORROW),
    ("hi: order status", "मेरा ऑर्डर नंबर 1042 कहाँ है? अभी तक नहीं आया।", {"SHOPIFY_GET_ORDER"},
     lambda a: "1042" in str(a.get("order_id", ""))),
    ("en: team alert", "This is urgent, please tell your team my implant is hurting badly and I need a call back today.",
     {"SLACK_SEND_MESSAGE", "REQUEST_HUMAN_HANDOFF"}, lambda a: True),
]


async def run(model: str) -> int:
    tools = [model_facing_schema(t) for t in get_tools_for_tenant(APPS)] + [SAVE_ENQUIRY_TOOL, REQUEST_HUMAN_HANDOFF_TOOL]
    brain = apply_available_tools(assemble_unified_brain(language="en-IN", script=SCRIPT), tools,
                                  call_integration_rows=capability_rows(None, tools))
    adapter = SarvamLLMAdapter()
    failures = 0
    print(f"model={model}  tools offered={len(tools)}")
    for label, utterance, expected, check in CASES:
        messages = [{"role": "system", "content": brain}, {"role": "user", "content": utterance}]
        final: dict = {}
        try:
            async for chunk in adapter.stream_live_turn(messages, model=model, tools=tools, temperature=0,
                                                        max_output_tokens=800, allow_empty_response=True):
                if chunk.get("done"):
                    final = chunk
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  ERROR {label}: {type(exc).__name__}: {str(exc)[:120]}")
            failures += 1
            continue
        calls = final.get("tool_calls") or []
        if not calls:
            print(f"  FAIL  {label}: no tool call; said: {final.get('text', '')[:100]!r}")
            failures += 1
            continue
        fn = calls[0].get("function") or calls[0]
        name = str(fn.get("name") or "").upper()
        try:
            args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
        except json.JSONDecodeError:
            args = {"_unparsable": fn.get("arguments")}
        definition = tool_definition(name)
        app = definition[0] if definition else ""
        full = {**args, **filled_params(app, name, SETTINGS.get(app))} if app not in {"", "PLATFORM"} else args
        error = validate_tool_arguments(name, full) if app not in {"", "PLATFORM"} else None
        ok = name in expected and not error and check(args)
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: {name} {json.dumps(args, ensure_ascii=False)[:140]}"
              + (f"  <- {error}" if error else ""))
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="sarvam-105b-conversations")
    sys.exit(asyncio.run(run(parser.parse_args().model)))
