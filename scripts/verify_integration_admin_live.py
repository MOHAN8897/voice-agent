"""Live end-to-end check of admin integration control against a running API.

Uses a locally minted admin-portal session and the test workspace's e2e session
(data/e2e_session.json). Switches an app off for every workspace, checks the
workspace catalog, connect, call options and the agent's model tools all refuse
it, then a per-workspace override turns it back on, and everything is restored.

    python scripts/verify_integration_admin_live.py --api http://127.0.0.1:8001
"""
import argparse
import asyncio
import json
import secrets
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.auth.rbac import ROLE_SUPER_ADMIN, ROLE_SUPPORT_AGENT  # noqa: E402
from server.auth.session import create_session_token  # noqa: E402

APP = "GOOGLECALENDAR"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def admin_client(api: str, role: str) -> httpx.Client:
    csrf = secrets.token_urlsafe(24)
    token = create_session_token("dev", f"claude-live-test-{role}", None, role)
    return httpx.Client(base_url=api, timeout=30, cookies={"dev_session": token, "dev_csrf": csrf},
                        headers={"X-CSRF-Token": csrf})


async def agent_tools(tenant: str, agent: str) -> set[str]:
    from server.brain.capabilities import agent_available_tools
    from server.db.connection import init_db
    from server.services import integration_policy

    await init_db()
    integration_policy.invalidate()  # this process has its own cache; read the database fresh
    return {t["name"] for t in await agent_available_tools(agent, "", tenant_id=tenant)}


def main(api: str) -> int:
    sess = json.loads((ROOT / "data/e2e_session.json").read_text())
    tenant = sess["tenant"]["tenantId"]
    agent = "6b7c1183-0bee-4b23-81aa-b710027ae4e0"  # Hima, a booking agent in the test workspace
    t = httpx.Client(base_url=api, timeout=30, headers={"Authorization": f"Bearer {sess['token']}"})
    admin = admin_client(api, ROLE_SUPER_ADMIN)
    support = admin_client(api, ROLE_SUPPORT_AGENT)

    def catalog() -> dict:
        return {i["id"]: i for i in t.get("/api/integrations/catalog").json()["items"]}

    def option(state_app: str) -> str:
        items = t.get(f"/api/integrations/call-options?agentId={agent}").json()["items"]
        return next(i["state"] for i in items if i["app"] == state_app)

    def connect_status() -> int:
        return t.post(f"/api/integrations/{APP}/connect", json={"base_redirect_uri": "http://localhost:5174/api/integrations/callback"}).status_code

    try:
        print("Baseline")
        overview = admin.get("/api/dev/admin/integrations")
        check("admin overview loads", overview.status_code == 200, str(overview.status_code))
        row = next(a for a in overview.json()["apps"] if a["app"] == APP)
        check("gateway reports Google Calendar configured (self-hosted)", row["gatewayReady"] is True)
        check("Google Calendar on by default", row["enabled"] is True)
        check("workspace catalog offers it", APP in catalog() and not catalog()[APP].get("admin_disabled"))
        check("workspace can open the Connect form", connect_status() == 200)

        print("Platform switch off")
        r = admin.put(f"/api/dev/admin/integrations/{APP}", json={"enabled": False, "note": "live test: switch off"})
        check("admin turns it off", r.status_code == 200, str(r.status_code))
        c = catalog()
        check("catalog marks it switched off (still connected)", c.get(APP, {}).get("admin_disabled") is True)
        check("connect refused", connect_status() == 403)
        check("call options say disabled_by_admin", option(APP) == "disabled_by_admin")
        tools = asyncio.run(agent_tools(tenant, agent))
        check("agent's model tools have no calendar actions", not any(n.startswith(APP) for n in tools), ",".join(sorted(tools)))
        check("support role cannot change switches", support.put(f"/api/dev/admin/integrations/{APP}", json={"enabled": True}).status_code == 403)

        print("Workspace override on")
        r = admin.put(f"/api/dev/admin/tenants/{tenant}/integrations/{APP}", json={"enabled": True, "note": "live test: pilot"})
        check("admin turns it on for this workspace only", r.status_code == 200, str(r.status_code))
        check("catalog offers it again", not catalog().get(APP, {}).get("admin_disabled"))
        check("connect allowed again", connect_status() == 200)
        detail = admin.get(f"/api/dev/admin/tenants/{tenant}/integrations").json()
        item = next(i for i in detail["items"] if i["app"] == APP)
        check("workspace view shows override and effective on",
              item["override"] is True and item["effective"] is True and item["platformEnabled"] is False)
        check("workspace view shows connection state", item["connection"] in {"connected", "needs_reauth"}, item["connection"])
    finally:
        print("Restore")
        r1 = admin.put(f"/api/dev/admin/tenants/{tenant}/integrations/{APP}", json={"enabled": None})
        r2 = admin.put(f"/api/dev/admin/integrations/{APP}", json={"enabled": True, "note": "live test: restored"})
        check("override removed and platform switch back on", r1.status_code == 200 and r2.status_code == 200)
        restored = next(a for a in admin.get("/api/dev/admin/integrations").json()["apps"] if a["app"] == APP)
        check("Google Calendar on again", restored["enabled"] is True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    sys.exit(main(parser.parse_args().api))
