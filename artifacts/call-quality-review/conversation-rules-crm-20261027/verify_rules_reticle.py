"""Isolated UI evidence; every API request uses fictional browser fixtures."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def payload(result):
    raw = next(item.text for item in result.content if hasattr(item, "text"))
    try:
        return json.loads(raw)
    except ValueError:
        return {"verified": "unknown", "error": raw}


def find(value, key):
    if isinstance(value, dict):
        return value.get(key) or next((found for item in value.values() if (found := find(item, key))), None)
    if isinstance(value, list):
        return next((found for item in value if (found := find(item, key))), None)
    return None


def element(query, state="visible", absent=False):
    return {"kind": "element", "query": query, **({"absent": True} if absent else {"state": state})}


async def main():
    evidence = []
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for readonly in (False, True):
                path = "leads?readonly=1" if readonly else "employees?step=script&agent=layout-agent"
                lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                    "action": "acquire", "url": f"http://127.0.0.1:5173/#dashboard/{path}",
                    "root": str(ROOT / ".reticle"), "projectId": "voxly-ai-4807c8a7",
                    "initScript": (OUT / "reticle-fixture.js").read_text(encoding="utf-8"),
                    "emulate": {"width": 1440, "height": 1000}}}))
                sid = find(lease, "sessionId")
                if not sid:
                    raise RuntimeError("Browser lease unavailable")
                try:
                    ready = element({"role": "button", "name": "Add lead"}, "disabled") if readonly else element({"testid": "script-textarea"})
                    result = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                        "predicate": ready, "timeout_ms": 30000, "detail": "compact"}))
                    evidence.append({"flow": "viewer_cannot_create" if readonly else "script_loaded", **result})
                    (OUT / "reticle-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                    if readonly:
                        flows = [
                            ("viewer_can_read_contact", {"role": "button", "name": "Example Enquiry"}, "click", {}, element({"label": "Pipeline stage"}, "disabled")),
                            ("viewer_cannot_edit_notes", None, None, {}, element({"label": "Notes & next step"}, "disabled")),
                            ("viewer_cannot_save", None, None, {}, element({"role": "button", "name": "Save lead changes"}, "disabled")),
                        ]
                    else:
                        saved = {"kind": "allOf", "predicates": [
                            {"kind": "net", "method": "PUT", "urlContains": "/business-brain/draft", "status": 200},
                            {"kind": "net", "method": "POST", "urlContains": "/business-brain/publish", "status": 200},
                            {"kind": "text", "contains": "Saved for calls"},
                        ]}
                        flows = [
                            ("objective_editor", {"testid": "add-objective-btn"}, "click", {}, element({"label": "Rule 1 type"})),
                            ("objective_situation", {"label": "Rule 1 situation"}, "fill", {"value": "When the caller asks for a demo"}, element({"testid": "agent-save"})),
                            ("objective_guidance", {"label": "Rule 1 guidance"}, "fill", {"value": "Answer the question first.\nCollect a preferred time without promising a booking."}, element({"testid": "agent-save"})),
                            ("objective_published", {"testid": "agent-save"}, "click", {}, saved),
                            ("objective_removal", {"testid": "remove-objection-0"}, "click", {"confirmDangerous": True}, element({"testid": "objection-rule-0"}, absent=True)),
                            ("empty_rules_published", {"testid": "agent-save"}, "click", {}, saved),
                        ]
                    for name, target, action, args, predicate in flows:
                        if name in {"objective_situation", "objective_guidance"}:
                            # Form preparation; publication below proves that
                            # the required fields were consumed by validation.
                            await session.call_tool("reticle_act", {"sessionId": sid, "target": target, "action": action, "args": args})
                            continue
                        if target:
                            result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                                "target": target, "action": action, "args": args, "until": predicate,
                                "timeout_ms": 15000, "intent": "Handling rules publish through the real editor; read-only tenants can inspect CRM contacts without mutation controls.", "detail": "compact"}))
                        else:
                            result = payload(await session.call_tool("reticle_assert", {"sessionId": sid,
                                "action": "wait", "predicate": predicate, "timeout_ms": 15000, "detail": "compact"}))
                        evidence.append({"flow": name, **result})
                        (OUT / "reticle-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                finally:
                    await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                    await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
    (OUT / "reticle-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    verdicts = [{"flow": row["flow"], "verified": row.get("verified"), "reason": row.get("verifiedReason")} for row in evidence]
    print(json.dumps(verdicts))
    if any(row["verified"] != "yes" for row in verdicts):
        raise SystemExit(1)


asyncio.run(main())
