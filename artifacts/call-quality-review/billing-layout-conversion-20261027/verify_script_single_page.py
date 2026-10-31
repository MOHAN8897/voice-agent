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
                    "predicate": {"kind":"allOf","predicates":[element("script-textarea"),element("agent-studio-greeting"),element("agent-studio-farewell"),element("add-objection-btn"),{"kind":"element","query":{"role":"navigation","name":"Script sections"},"absent":True}]}, "timeout_ms": 30000, "detail": "compact"}))
                evidence.append({"flow": "script_loaded", **ready})
            finally:
                await session.call_tool("reticle_session", {"action":"yield","mode":"waiting","sessionId":sid})
                await session.call_tool("reticle_run", {"tool":"reticle_lease","args":{"action":"release","sessionId":sid}})
    (OUT / "reticle-script-single-page.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps([{"flow":r["flow"],"verified":r.get("verified"),"reason":r.get("verifiedReason")} for r in evidence]))
    if any(r.get("verified")!="yes" for r in evidence):
        raise SystemExit(1)

asyncio.run(main())
