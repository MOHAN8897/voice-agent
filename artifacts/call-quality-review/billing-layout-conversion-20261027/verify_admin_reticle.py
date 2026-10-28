"""Verify admin controls against intercepted APIs; never write real financial settings."""
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
    state = json.loads((ROOT / "web/e2e/.auth/user.json").read_text(encoding="utf-8"))
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    evidence = []
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                "action": "acquire", "url": "http://127.0.0.1:3000/dev/stack", "root": str(ROOT / ".reticle"),
                "projectId": "voxly-ai-4807c8a7", "seedStorage": {"cookies": state["cookies"]},
                "initScript": (OUT / "admin-reticle-fixture.js").read_text(encoding="utf-8"),
                "emulate": {"width": 1440, "height": 1000}}}))
            sid = find(lease, "sessionId")
            if not sid:
                raise RuntimeError("Admin browser lease unavailable")
            try:
                ready = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                    "predicate": {"kind": "element", "query": {"label": "Web agent price (₹/min)"}, "state": "visible"},
                    "timeout_ms": 30000, "detail": "compact"}))
                evidence.append({"flow": "admin_stack_loaded", **ready})
                saved = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                    "target": {"label": "Web agent price (₹/min)"}, "action": "fill", "args": {"value": "4"},
                    "until": {"kind": "allOf", "predicates": [
                        {"kind": "net", "method": "PUT", "urlContains": "/voice-profiles/low", "status": 200},
                        {"kind": "text", "contains": "Auto-saved & applied globally", "visible": True}]},
                    "timeout_ms": 15000, "intent": "Changing a stack’s browser rate saves its exact profile override independently of phone pricing.", "detail": "compact"}))
                evidence.append({"flow": "admin_web_rate_save_mocked", **saved})
                await session.call_tool("reticle_act", {"sessionId": sid, "target": {"label": "GST rate (%)"},
                    "action": "fill", "args": {"value": "20"}})
                await session.call_tool("reticle_act", {"sessionId": sid, "target": {"role": "button", "name": "Preview checkout"},
                    "action": "scrollIntoView"})
                preview = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                    "target": {"role": "button", "name": "Preview checkout"}, "action": "press", "args": {"text": "Enter"},
                    "until": {"kind": "text", "contains": "INR 1200.00", "visible": True}, "timeout_ms": 15000,
                    "intent": "Admin previews edited GST rules without saving them or creating a payment.", "detail": "compact"}))
                evidence.append({"flow": "admin_tax_draft_preview_mocked", **preview})
            finally:
                await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
    (OUT / "reticle-admin.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps([{"flow": r["flow"], "verified": r.get("verified"), "error": r.get("error")} for r in evidence]))
    if any(r.get("verified") != "yes" for r in evidence):
        raise SystemExit(1)


asyncio.run(main())
