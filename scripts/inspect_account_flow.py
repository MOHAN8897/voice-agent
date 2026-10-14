import asyncio
from sqlalchemy import select
from server.db.connection import init_db, get_session_factory
from server.db.models import User, Tenant, Agent, AgentIntegration
from server.db.models.saas_models import TenantMembership
from server.db.models.brain_models import CompiledBrainSnapshot
from server.db.models.integration_models import TenantIntegration, ToolExecution

async def main():
    await init_db()
    sf = get_session_factory()
    async with sf() as session:
        res = await session.execute(select(User).where(User.email == 'mohansaiteja.99@gmail.com'))
        u = res.scalar_one_or_none()
        if not u:
            print("User not found!")
            return
        print(f"User: user_id={u.user_id}, email={u.email}, status={u.status}")
        
        m_res = await session.execute(select(TenantMembership).where(TenantMembership.user_id == u.user_id))
        memberships = m_res.scalars().all()
        for m in memberships:
            t = await session.get(Tenant, str(m.tenant_id))
            tenant_name = t.name if t else "N/A"
            print(f"\n--- Tenant: {m.tenant_id} ('{tenant_name}') Role: {m.role} ---")
            
            # Tenant integrations
            ti_res = await session.execute(select(TenantIntegration).where(TenantIntegration.tenant_id == m.tenant_id))
            for ti in ti_res.scalars().all():
                print(f"  Connected Tenant Integration: {ti.app_name} (conn_id={ti.connection_id}, status={ti.status})")

            # Agents
            ag_res = await session.execute(select(Agent).where(Agent.tenant_id == str(m.tenant_id)))
            agents = ag_res.scalars().all()
            for a in agents:
                print(f"\n  [Agent] ID: {a.agent_id} | Name: '{a.name}' | Languages: {a.languages} | Active CB: {a.active_compiled_brain_version}")
                if a.active_compiled_brain_version:
                    cb = await session.get(CompiledBrainSnapshot, a.active_compiled_brain_version)
                    if cb:
                        print(f"    CB Snapshot: {cb.compiled_version}, tokens={cb.token_estimate}, checksum={cb.checksum}")
                        print(f"    CB Compiled Text ({len(cb.compiled_text or '')} chars): {repr((cb.compiled_text or '')[:160])}...")
                
                ai_res = await session.execute(select(AgentIntegration).where(AgentIntegration.agent_id == a.agent_id))
                for ai in ai_res.scalars().all():
                    print(f"    Tool: {ai.app_name} | enabled={ai.enabled} | whitelist={ai.action_whitelist} | timing={ai.timing_mode}")
            
            # Recent tool executions
            te_res = await session.execute(
                select(ToolExecution).where(ToolExecution.tenant_id == m.tenant_id).order_by(ToolExecution.started_at.desc()).limit(5)
            )
            tool_execs = te_res.scalars().all()
            print(f"\n  Recent Tool Executions in Tenant ({len(tool_execs)}):")
            for te in tool_execs:
                print(f"    - Action: {te.action} | Status: {te.status} | Started: {te.started_at}")

if __name__ == "__main__":
    asyncio.run(main())
