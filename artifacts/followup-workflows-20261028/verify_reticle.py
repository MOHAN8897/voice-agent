"""Isolated API doubles; real application, DOM, save dock and network consumption."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def payload(result):
    return json.loads(next(item.text for item in result.content if hasattr(item, "text")))


def find(value, key):
    if isinstance(value, dict):
        return value.get(key) or next((v for item in value.values() if (v := find(item, key))), None)
    if isinstance(value, list):
        return next((v for item in value if (v := find(item, key))), None)


def element(query, state="visible"):
    return {"kind": "element", "query": query, "state": state}


async def main():
    results, observations = [], []
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for label, width in (("desktop", 1440), ("mobile", 390)):
                lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                    "action": "acquire", "url": "http://127.0.0.1:5173/#dashboard/employees?step=settings&agent=layout-agent",
                    "root": str(ROOT / ".reticle"), "projectId": "voxly-ai-4807c8a7",
                    "initScript": (OUT / "fixture.js").read_text(encoding="utf-8"), "emulate": {"width": width, "height": 1000}}}))
                sid = find(lease, "sessionId")
                if not sid:
                    raise RuntimeError("No Reticle lease")
                async def check(name, predicate):
                    result = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                        "predicate": predicate, "timeout_ms": 15000, "detail": "compact"}))
                    results.append({"flow": f"{label}_{name}", **result})
                    print(label, name, result.get("verified"), flush=True)
                    if result.get("verified") != "yes":
                        raise RuntimeError(json.dumps(result))
                async def press(name, target, predicate, key="Enter"):
                    await session.call_tool("reticle_act", {"sessionId": sid, "target": target, "action": "focus"})
                    result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                        "target": target, "action": "press", "args": {"text": key}, "until": predicate,
                        "timeout_ms": 15000, "detail": "compact",
                        "intent": "Tenants explicitly approve callback automation and charges, review unclear callback times, and manage caller opt-outs before follow-up calls can run."}))
                    results.append({"flow": f"{label}_{name}", **result})
                    print(label, name, result.get("verified"), flush=True)
                    if result.get("verified") != "yes":
                        raise RuntimeError(json.dumps(result))
                try:
                    await check("settings_loaded", element({"testid": "followup-settings"}))
                    await press("followup_category", {"role": "button", "name": "Follow-ups & scoring"},
                        element({"scope": "button[aria-label='Follow-ups & scoring'][aria-pressed='true']", "self": True}))
                    await press("permission_warning", {"label": "Allow scheduled follow-up calls"},
                        element({"label": "Authorize follow-up calls and charges"}), "Space")
                    await press("permission_confirmed", {"label": "Authorize follow-up calls and charges"},
                        element({"label": "Authorize follow-up calls and charges"}, "checked"), "Space")
                    # This SDK does not capture successful request bodies. The Playwright
                    # regression asserts the exact permission payload; Reticle proves the live
                    # save request and displayed confirmation together.
                    await press("permission_saved", {"testid": "agent-save"}, {"kind": "allOf", "predicates": [
                        {"kind": "net", "method": "PUT", "urlContains": "/follow-up-policy", "status": 200},
                        {"kind": "text", "contains": "All agent configurations saved successfully"}]})
                    await press("overview_metrics", {"testid": "agent-tab-overview"}, element({"testid": "agent-conversion-metrics"}))
                    await press("overview_pipeline_link", {"role": "button", "name": "Pipeline"}, element({"role": "navigation", "name": "Lead management"}))
                    await press("queue_visible", {"role": "button", "name": "Callbacks & missed calls"},
                        {"kind": "allOf", "predicates": [element({"testid": "followup-queue"}),
                            {"kind": "net", "method": "GET", "urlContains": "/api/follow-ups", "status": 200}]})
                    await press("review_dialog", {"role": "button", "name": "Review time"}, element({"label": "Follow-up date and time"}))
                    await check("approval_required", element({"role": "button", "name": "Schedule follow-up"}, "disabled"))
                    await press("close_review", {"role": "button", "name": "Close dialog"},
                        {"kind": "element", "query": {"label": "Follow-up date and time"}, "absent": True})
                    await press("dnd_management", {"role": "button", "name": "Do not call"},
                        {"kind": "allOf", "predicates": [element({"testid": "add-dnc-button"}),
                            {"kind": "net", "method": "GET", "urlContains": "/api/dnc", "status": 200}]})
                    for action in ("network", "console"):
                        args = {"action": action, "sessionId": sid, "since": 0, "limit": 30}
                        if action == "console":
                            args["level"] = "error"
                        observations.append({"viewport": label, "action": action, "result": payload(await session.call_tool("reticle_observe", args))})
                finally:
                    await session.call_tool("reticle_session", {"action": "yield", "sessionId": sid, "mode": "waiting"})
                    await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
                    (OUT / "reticle-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                    (OUT / "reticle-observations.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
    verdicts = [{"flow": row["flow"], "verified": row.get("verified"), "reason": row.get("verifiedReason")} for row in results]
    print(json.dumps(verdicts))
    if any(row["verified"] != "yes" for row in verdicts):
        raise SystemExit(1)


asyncio.run(main())
