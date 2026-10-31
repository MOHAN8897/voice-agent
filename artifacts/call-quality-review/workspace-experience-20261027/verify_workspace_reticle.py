"""Disposable browser fixture; never send a mock credential to the real API."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def payload(result):
    return json.loads(next(item.text for item in result.content if hasattr(item, "text")))


def find(value, key):
    if isinstance(value, dict):
        return value.get(key) or next((found for item in value.values() if (found := find(item, key))), None)
    if isinstance(value, list):
        return next((found for item in value if (found := find(item, key))), None)
    return None


async def main():
    evidence = []
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                "action": "acquire", "url": "http://127.0.0.1:5173/#dashboard/employees?step=script&agent=layout-agent",
                "root": str(ROOT / ".reticle"), "projectId": "voxly-ai-4807c8a7",
                "initScript": (OUT / "reticle-fixture.js").read_text(encoding="utf-8"),
                "emulate": {"width": 1440, "height": 1000}}}))
            sid = find(lease, "sessionId")
            if not sid:
                raise RuntimeError("Browser lease unavailable")
            def element(testid, absent=False):
                return {"kind": "element", "query": {"testid": testid}, **({"absent": True} if absent else {"state": "visible"})}
            try:
                ready = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                    "predicate": element("script-textarea"), "timeout_ms": 30000, "detail": "compact"}))
                evidence.append({"flow": "script_loaded", **ready})
                flows = [
                    ("edit_opens_save_dock", "script-textarea", "fill", {"value": "Hello, how can I help?\nApproved script edit. @cont"}, {"kind": "allOf", "predicates": [element("agent-save"), element("script-variable-suggestions")] }),
                    ("discard_hides_save_dock", "agent-studio-discard", "click", {}, element("agent-save", True)),
                    ("settings_navigation", "agent-tab-settings", "click", {}, element("agent-settings-name")),
                    ("settings_edit_opens_same_dock", "agent-settings-name", "fill", {"value": "Revised agent name"}, element("agent-save")),
                    ("settings_discard_hides_dock", "agent-studio-discard", "click", {}, element("agent-save", True)),
                    ("lead_navigation", "agent-tab-calls", "click", {}, element("agent-calls-panel-tab-leads")),
                    ("lead_pipeline", "agent-calls-panel-tab-leads", "click", {}, element("lead-row-fixture-lead")),
                ]
                for name, testid, action, args, predicate in flows:
                    result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                        "target": {"testid": testid}, "action": action, "args": args, "until": predicate,
                        "timeout_ms": 15000, "intent": "A single floating save action appears only for unsaved agent edits, and discard restores the saved configuration.",
                        "detail": "compact"}))
                    evidence.append({"flow": name, **result})
                for name, target, action, args, predicate, intent in [
                    ("lead_filter_empty", {"role": "searchbox", "name": "Search leads"}, "fill", {"value": "missing"},
                     {"kind": "text", "contains": "No leads match these filters", "visible": True},
                     "Lead search filters the server-backed pipeline and exposes a clear empty state."),
                    ("lead_filter_clear", {"role": "button", "name": "Clear filters"}, "click", {}, element("lead-row-fixture-lead"),
                     "Clearing lead filters restores contacts without changing their pipeline metadata."),
                    ("lead_bulk_selection", {"role": "checkbox", "name": "Select Example Enquiry"}, "check", {},
                     {"kind": "element", "query": {"role": "button", "name": "Create campaign (1)"}, "state": "visible"},
                     "Selecting callable leads makes them available for campaign setup."),
                    ("lead_campaign_handoff", {"role": "button", "name": "Create campaign (1)"}, "click", {}, element("campaign-selected-leads"),
                     "Selected leads open the existing campaign review with their contact metadata intact."),
                    ("close_campaign", {"role": "button", "name": "Close dialog"}, "click", {}, element("campaign-selected-leads", True),
                     "Closing campaign setup returns to the lead pipeline."),
                    ("voice_navigation", {"testid": "agent-tab-voice"}, "click", {}, element("voice-stack-selector"),
                     "The voice catalog remains available after lead work."),
                    ("voice_style_filter", {"role": "combobox", "name": "Voice style for Economical"}, "select", {"value": "Conversational"},
                     {"kind": "element", "query": {"role": "button", "name": "Male (0)"}, "state": "visible"},
                     "Voice gender counts reflect the selected voice style, including zero available voices."),
                    ("voice_zero_results", {"role": "button", "name": "Male (0)"}, "click", {},
                     {"kind": "text", "contains": "0 Telugu voices match your filters", "visible": True},
                     "Empty voice filter combinations display zero availability without changing the saved voice."),
                ]:
                    result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                        "target": target, "action": action, "args": args, "until": predicate,
                        "timeout_ms": 15000, "intent": intent, "detail": "compact"}))
                    evidence.append({"flow": name, **result})
            finally:
                await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
    (OUT / "reticle-workspace.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    verdicts = [{"flow": r["flow"], "verified": r.get("verified"), "pass": r.get("verdict", {}).get("pass"), "error": r.get("error"), "version_skew": r.get("version_skew")} for r in evidence]
    print(json.dumps(verdicts))
    if any(r["verified"] != "yes" for r in verdicts):
        raise SystemExit(1)


asyncio.run(main())
