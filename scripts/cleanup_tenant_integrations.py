"""Remove a tenant's orphaned integration records.

Finds, for one tenant:
  * gateway (Nango) connections no tenant_integrations row points at,
  * tenant_integrations rows that were never gateway-verified (seed/test rows),
  * agent integration rules belonging to agents that are not active.

Dry run by default; nothing is deleted without --apply.

    python scripts/cleanup_tenant_integrations.py <tenant_id>
    python scripts/cleanup_tenant_integrations.py <tenant_id> --apply
"""
import argparse
import asyncio
import uuid

from sqlalchemy import delete, select

from server.db.connection import get_session_factory, init_db
from server.db.models import Agent, AgentIntegration
from server.db.models.integration_models import TenantIntegration
from server.services.nango_service import nango_service


async def main(tenant_id: str, apply: bool) -> None:
    await init_db()
    factory = get_session_factory()
    tid = uuid.UUID(tenant_id)
    async with factory() as session:
        rows = (await session.execute(select(TenantIntegration).where(TenantIntegration.tenant_id == tid))).scalars().all()
        active_agents = {a.agent_id for a in (await session.execute(select(Agent).where(
            Agent.tenant_id == tid, Agent.status == "active"))).scalars().all()}
        rules = (await session.execute(select(AgentIntegration).where(AgentIntegration.tenant_id == tid))).scalars().all()
    referenced = {r.connection_id for r in rows if r.status in ("ACTIVE", "ERROR")}
    orphans = [c for c in await nango_service.get_tenant_connections(tenant_id, include_auth_errors=True)
               if c.get("connection_id") and c["connection_id"] not in referenced]
    unverified = [r for r in rows if r.status == "ACTIVE" and not (r.metadata_ or {}).get("gateway_verified")]
    stale_rules = [r for r in rules if r.agent_id not in active_agents]

    print(f"{'Deleting' if apply else 'Would delete'}:")
    for c in orphans:
        print(f"  gateway connection  {c['provider_config_key']:18} {c['connection_id']}")
    for r in unverified:
        print(f"  unverified row      {r.app_name:18} {r.connection_id}")
    for r in stale_rules:
        print(f"  rule of inactive agent {str(r.agent_id)[:8]}  {r.app_name}")
    if not apply:
        print("Dry run. Re-run with --apply to delete.")
        return
    for c in orphans:
        app = nango_service.get_app_name_from_provider(c["provider_config_key"])
        ok = await nango_service.delete_connection(c["connection_id"], app)
        print(f"  {'deleted' if ok else 'FAILED '} {c['provider_config_key']} {c['connection_id']}")
    async with factory() as session:
        if unverified:
            await session.execute(delete(TenantIntegration).where(
                TenantIntegration.tenant_id == tid, TenantIntegration.id.in_([r.id for r in unverified])))
        if stale_rules:
            await session.execute(delete(AgentIntegration).where(
                AgentIntegration.tenant_id == tid, AgentIntegration.id.in_([r.id for r in stale_rules])))
        await session.commit()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tenant_id")
    parser.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.tenant_id, args.apply))
