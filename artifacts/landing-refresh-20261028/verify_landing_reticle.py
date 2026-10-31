"""Verify public marketing journeys in isolated, anonymous desktop/mobile tabs."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

FIXTURE = """
const originalFetch=window.fetch.bind(window);
window.fetch=async(input,init)=>{
 const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
 if(!path.startsWith('/api/')) return originalFetch(input,init);
 const body=path==='/api/auth/session'?{authenticated:false,saas_auth_enabled:true}:{ok:true,socialLinks:{},items:[]};
 return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
};
document.addEventListener('DOMContentLoaded',()=>{const style=document.createElement('style');style.textContent='[data-reticle-overlay]{display:none!important}';document.head.append(style);});
"""


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


def element(testid):
    return {"kind": "element", "query": {"testid": testid}, "state": "visible"}


async def main():
    evidence = []
    observations = []
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for label, width, height in [("desktop", 1440, 1000), ("mobile", 390, 844)]:
                lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                    "action": "acquire", "url": "http://127.0.0.1:5173/", "root": str(ROOT / ".reticle"),
                    "projectId": "voxly-ai-4807c8a7", "initScript": FIXTURE, "emulate": {"width": width, "height": height}}}))
                sid = find(lease, "sessionId")
                if not sid:
                    raise RuntimeError("No browser lease")
                try:
                    ready = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                        "predicate": element("landing-refresh"), "timeout_ms": 30000, "detail": "compact"}))
                    evidence.append({"flow": f"{label}_landing_loaded", **ready})
                    flows = [
                        ("workflow_selection", {"role": "button", "name": "Customer support"}, {"kind": "text", "contains": "Make the first conversation count", "visible": True}),
                        ("faq_expansion", {"text": "What happens after the call?"}, {"kind": "text", "contains": "Callback requests do not automatically schedule a redial.", "visible": True}),
                        ("pricing_destination", {"role": "button", "name": "Explore workspace pricing"}, element("auth-modal")),
                    ]
                    for name, target, predicate in flows:
                        await session.call_tool("reticle_act", {"sessionId": sid, "target": target, "action": "focus"})
                        result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid, "target": target,
                            "action": "press", "args": {"text": "Enter"}, "until": predicate, "timeout_ms": 15000,
                            "intent": "Marketing visitors can inspect relevant calling workflows, understand follow-up limits, and enter workspace pricing through sign-in on desktop and mobile.", "detail": "compact"}))
                        evidence.append({"flow": f"{label}_{name}", **result})
                        (OUT / "reticle-verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                    for action in ("network", "console"):
                        result = payload(await session.call_tool("reticle_observe", {"action": action, "sessionId": sid, "since": 0, "limit": 30, **({"level": "error"} if action == "console" else {})}))
                        if result.get("error"):
                            raise RuntimeError(result["error"])
                        observations.append({"viewport": label, "channel": action, "result": result})
                finally:
                    await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                    await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
    (OUT / "reticle-observations.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
    verdicts = [{"flow": row["flow"], "verified": row.get("verified"), "reason": row.get("verifiedReason"), "error": row.get("error")} for row in evidence]
    print(json.dumps(verdicts))
    if any(row["verified"] != "yes" for row in verdicts):
        raise SystemExit(1)


asyncio.run(main())
