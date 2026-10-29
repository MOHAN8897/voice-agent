"""Real console DOM/API consumption against isolated fixtures; no customer writes."""
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
        return value.get(key) or next((item for part in value.values() if (item := find(part, key))), None)
    if isinstance(value, list):
        return next((item for part in value if (item := find(part, key))), None)


def element(query, state="visible", **more):
    return {"kind": "element", "query": query, "state": state, **more}


def net(path, method="GET"):
    return {"kind": "net", "urlContains": path, "method": method, "status": 200}


def all_of(*predicates):
    return {"kind": "allOf", "predicates": list(predicates)}


async def main():
    rows = []
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for viewport, width in (("desktop", 1440), ("mobile", 390)):
                lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                    "action": "acquire", "url": "http://127.0.0.1:5173/#dashboard/employees?step=calls&agent=layout-agent",
                    "projectId": "voxly-ai-4807c8a7", "root": str(ROOT / ".reticle"), "hud": "hidden",
                    "initScript": (OUT / "fixture.js").read_text(encoding="utf-8"), "emulate": {"width": width, "height": 1000}}}))
                sid = find(lease, "sessionId")
                if not sid:
                    raise RuntimeError("Reticle did not acquire a session")

                async def act(target, action, args=None):
                    return await session.call_tool("reticle_act", {"sessionId": sid, "target": target, "action": action, "args": args or {}})

                async def press(name, target, predicate, key="Enter"):
                    await act(target, "focus")
                    result = payload(await session.call_tool("reticle_act_and_wait", {
                        "sessionId": sid, "target": target, "action": "press", "args": {"text": key, "confirmDangerous": True},
                        "until": predicate, "timeout_ms": 15000, "detail": "compact"}))
                    rows.append({"viewport": viewport, "step": name, **result})
                    print(viewport, name, result.get("verified"), flush=True)
                    if result.get("verified") != "yes":
                        raise RuntimeError(json.dumps(result))

                try:
                    await press("lead_area", {"testid": "agent-calls-panel-tab-leads"}, element({"role": "navigation", "name": "Lead management"}))
                    await press("queue", {"role": "button", "name": "Callbacks & missed calls"}, all_of(element({"testid": "followup-queue"}), net("/api/follow-ups")))
                    await press("campaign_audience", {"role": "button", "name": "Create follow-up campaign"}, all_of(element({"testid": "campaign-followup-audience"}), net("/api/campaigns/audience/follow-ups")))
                    await press("select_saved_job", {"label": "Select follow-up +12025550123"}, element({"text": "1 selected · showing 1 of 1 available"}), "Space")
                    await act({"label": "Campaign name"}, "fill", {"value": "Reviewed callback campaign"})
                    await press("contact_check", {"role": "button", "name": "Validate contacts"}, all_of(net("/api/contacts/normalize-preview", "POST"), element({"text": "1 ready · 0 invalid · 0 duplicates"})))
                    consent = "I confirm I have authorization and required consent to call these contacts, approve wallet charges, and accept responsibility for the campaign’s purpose, content and legality."
                    await press("campaign_permission", {"role": "checkbox", "name": consent}, element({"role": "button", "name": "Save as draft"}, "enabled"), "Space")
                    await press("saved_campaign", {"role": "button", "name": "Save as draft"}, all_of(net("/api/campaigns", "POST"), element({"role": "dialog"}, absent=True)))
                    await press("review_import", {"role": "button", "name": "Import earlier calls for review"}, element({"label": "Earlier call type"}))
                    await press("import_stays_review", {"role": "button", "name": "Import for review"}, all_of(net("/follow-ups/import-review", "POST"), element({"role": "dialog"}, absent=True)))
                    await press("dnd_area", {"role": "button", "name": "Do not call"}, all_of(net("/api/dnc"), element({"testid": "add-dnc-button"})))
                    await press("removal_dialog", {"role": "button", "name": "Remove from DND"}, element({"testid": "dnc-deactivate-confirm-btn"}, "disabled"))
                    await act({"testid": "dnc-deactivate-reason-input"}, "fill", {"value": "Caller explicitly renewed permission in writing"})
                    await press("renewed_permission", {"testid": "dnc-reconsent-checkbox"}, element({"testid": "dnc-deactivate-confirm-btn"}, "enabled"), "Space")
                    await press("registry_updated", {"testid": "dnc-deactivate-confirm-btn"}, all_of(net("/deactivate", "POST"), element({"text": "No active Do Not Call numbers"}), element({"role": "dialog"}, absent=True)))
                    console = payload(await session.call_tool("reticle_observe", {"action": "console", "level": "error", "sessionId": sid, "since": 0, "limit": 30}))
                    (OUT / f"console-{viewport}.json").write_text(json.dumps(console, indent=2), encoding="utf-8")
                finally:
                    await session.call_tool("reticle_session", {"action": "yield", "sessionId": sid, "mode": "waiting"})
                    await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
                    (OUT / "reticle-results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"verdicts": len(rows), "passed": sum(row.get("verified") == "yes" for row in rows)}))


asyncio.run(main())
