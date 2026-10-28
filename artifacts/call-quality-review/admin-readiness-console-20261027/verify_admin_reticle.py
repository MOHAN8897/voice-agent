"""Use the matching leased Reticle driver; keep local auth state out of output."""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def payload(result):
    return json.loads(next(item.text for item in result.content if hasattr(item, "text")))


async def main():
    state = json.loads((ROOT / "web/e2e/.auth/user.json").read_text(encoding="utf-8"))
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "@reticlehq/server@3.8.2", "mcp"], cwd=str(ROOT))
    evidence = []
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                "action": "acquire", "url": "http://127.0.0.1:3000/dev", "root": str(ROOT / ".reticle"),
                "projectId": "voxly-ai-4807c8a7", "seedStorage": {"cookies": state["cookies"]},
                "emulate": {"width": 1440, "height": 1000}}}))
            # Response nesting differs between daemon minor versions.
            def find(value, key):
                if isinstance(value, dict):
                    if value.get(key):
                        return value[key]
                    return next((found for item in value.values() if (found := find(item, key))), None)
                if isinstance(value, list):
                    return next((found for item in value if (found := find(item, key))), None)
                return None
            sid = find(lease, "sessionId")
            if not sid:
                print(json.dumps({"lease": "failed", "error": lease.get("error", "No session returned")}))
                return
            try:
                ready = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                    "predicate": {"kind": "element", "query": {"role": "heading", "name": "SaaS overview"}},
                    "timeout_ms": 30000, "detail": "compact"}))
                evidence.append({"flow": "overview_loaded", "verified": ready.get("verified"), "reason": ready.get("verifiedReason")})
                result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                    "target": {"role": "button", "name": "7d"}, "action": "click", "timeout_ms": 15000,
                    "until": {"kind": "allOf", "predicates": [
                        {"kind": "net", "method": "GET", "urlContains": "/analytics?days=7", "status": 200},
                        {"kind": "text", "contains": "Calls (7d)", "visible": True}]},
                    "intent": "Overview window selection reloads real server analytics for the chosen date range.", "detail": "compact"}))
                evidence.append({"flow": "overview_window", "verified": result.get("verified"),
                    "pass": (result.get("verdict") or {}).get("pass"), "reason": result.get("verifiedReason"),
                    "error": result.get("error")})
            finally:
                await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
            # Disposable fixtures exercise the workspace without sending a
            # synthetic credential or mutation to the real application API.
            fixture = r"""
            const user = {id:'layout-fixture', userId:'layout-fixture', fullName:'Layout Tester',
              email:'layout@example.invalid', tenantId:'layout-tenant', hasCompletedOnboarding:true};
            const encode = value => btoa(JSON.stringify(value)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
            sessionStorage.setItem('voxly_auth_token', `${encode({alg:'none'})}.${encode({sub:user.id,exp:Math.floor(Date.now()/1000)+3600})}.synthetic`);
            localStorage.setItem('voxly_auth_session', JSON.stringify(user));
            localStorage.setItem('voxly_tour_completed_layout@example.invalid','true');
            const agent = {id:'layout-agent', agent_id:'layout-agent', name:'Layout Agent', status:'active',
              languages:['te-IN'], defaultTier:'low', voiceRevision:1, active_compiled_brain_version:'published',
              voiceSettings:{stackSelectionVersion:1,profileRevision:1,engineId:'eng-fixture',modelId:'mod-fixture',voiceId:'voc-fixture'}};
            const profiles = [{tier:'low', label:'Economical', ready:true, enabled:true, profileRevision:1,
              retailRate:{complete:true,usdMicrosPerMin:10000,inrPaisePerMin:100,fxRateInr:100,version:1},
              engines:[{id:'eng-fixture',label:'Voice engine',models:[{id:'mod-fixture',label:'Speech model',
                voices:[{id:'voc-fixture',label:'Voice one',languages:['te-IN'],gender:'female'}]}]}]}];
            const realFetch = window.fetch.bind(window);
            window.fetch = async (input, init) => {
              const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
              if (!path.startsWith('/api/')) return realFetch(input,init);
              let body = {ok:true,items:[]};
              if (path === '/api/auth/me') body={user,tenant:{tenantId:user.tenantId},role:'owner'};
              else if (path === '/api/auth/session') body={authenticated:true,saas_auth_enabled:true};
              else if (path === '/api/agents') body={agents:[agent]};
              else if (path === '/api/agents/layout-agent') body={agent};
              else if (path === '/api/voice-stacks/catalog') body={profiles};
              else if (path.includes('/voice-options')) body={voices:[],languages:[{code:'te-IN',label:'Telugu'}]};
              else if (path.endsWith('/billing/wallet')) body={balanceUsd:100};
              else if (path.endsWith('/business-brain')) body={draft:{revision:'fixture',sections:[{section_id:'script',type:'facts',title:'Calling script',raw_text:'Hello, how can I help?',enabled:true,order:20}]},published:{version_id:'published'}};
              else if (path.endsWith('/telephony-profile')) body={profile:{}};
              return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
            };
            """
            lease = payload(await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {
                "action": "acquire", "url": "http://127.0.0.1:5173/#dashboard/employees?step=script&agent=layout-agent",
                "root": str(ROOT / ".reticle"), "projectId": "voxly-ai-4807c8a7", "initScript": fixture,
                "emulate": {"width": 1440, "height": 1000}}}))
            sid = find(lease, "sessionId")
            if sid:
                try:
                    ready = payload(await session.call_tool("reticle_assert", {"action": "wait", "sessionId": sid,
                        "predicate": {"kind": "element", "query": {"role": "button", "name": "Expand sidebar"}},
                        "timeout_ms": 30000, "detail": "compact"}))
                    evidence.append({"flow": "workspace_auto_collapse", "verified": ready.get("verified"), "fixtures": True})
                    for name, target, predicate in [
                        ("workspace_expand", {"testid": "sidebar-collapse-toggle"}, {"kind": "element", "query": {"role": "button", "name": "Collapse sidebar"}}),
                        ("workspace_settings", {"testid": "agent-tab-settings"}, {"kind": "element", "query": {"testid": "agent-settings-save-bar"}}),
                    ]:
                        result = payload(await session.call_tool("reticle_act_and_wait", {"sessionId": sid,
                            "target": target, "action": "click", "until": predicate, "timeout_ms": 15000,
                            "intent": "Agent workspace navigation exposes expansion and the settings save action without losing the editor.", "detail": "compact"}))
                        evidence.append({"flow": name, "verified": result.get("verified"), "pass": (result.get("verdict") or {}).get("pass"),
                            "version_skew": result.get("version_skew"), "fixtures": True, "error": result.get("error")})
                finally:
                    await session.call_tool("reticle_session", {"action": "yield", "mode": "waiting", "sessionId": sid})
                    await session.call_tool("reticle_run", {"tool": "reticle_lease", "args": {"action": "release", "sessionId": sid}})
    (OUT / "reticle-admin.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))


asyncio.run(main())
