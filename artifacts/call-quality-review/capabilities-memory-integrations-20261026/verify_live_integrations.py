"""Read-only verification against the connected workspace; never sends messages."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


async def main():
    import httpx
    from server.db.connection import init_db, close_db
    from server.brain.business_brain_store import business_brain_store
    from server.brain.capabilities import agent_available_tools, apply_available_tools
    from server.brain.compiled_brain_artifact import assemble_unified_brain, is_unified_compiled_brain
    from server.services.nango_service import nango_service
    from server.services.tool_router import VoxlyToolRouter
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator
    from server.providers.sarvam_llm import SarvamLLMAdapter
    from server.providers.base import StageSelection
    from types import SimpleNamespace

    meta = json.loads((ROOT / 'data/calls/a60ba6ec-cfd7-45f0-9876-8abd92f7f0e1/meta.json').read_text(encoding='utf-8'))
    tenant, agent = meta['tenant_id'], meta['agent_id']
    assert await init_db()
    try:
        published = await business_brain_store.get_latest_published(agent)
        raw = published['optimized_prompt']
        brain = raw if is_unified_compiled_brain(raw) else assemble_unified_brain(language='te-IN', script=raw)
        tools = await agent_available_tools(agent, brain, tenant_id=tenant)
        compiled = apply_available_tools(brain, tools)
        names = [t['name'] for t in tools]
        assert compiled.count('--- CALL CAPABILITIES ---') == 1
        assert 'GOOGLECALENDAR_FIND_FREE_SLOTS' in names
        accounts = {}
        for app, action, endpoint, email_field in [
            ('Calendar', 'GOOGLECALENDAR_FIND_FREE_SLOTS', '/calendar/v3/calendars/primary', 'id'),
            ('Gmail', 'GMAIL_SEND_EMAIL', '/gmail/v1/users/me/profile', 'emailAddress'),
        ]:
            connection = await nango_service._get_nango_connection_id(tenant, action)
            assert connection
            provider = nango_service.get_provider_key(nango_service._extract_app_name(action))
            headers = {'Authorization': f'Bearer {nango_service.secret_key}', 'Connection-Id': connection,
                       'Provider-Config-Key': provider}
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(nango_service.base_url + '/proxy' + endpoint, headers=headers)
            accounts[app] = {'http_status': response.status_code,
                             'requested_account_matches': response.status_code == 200 and response.json().get(email_field) == 'mohansaiteja.99@gmail.com'}
        result = await VoxlyToolRouter().route_and_execute(tenant, agent, '', 'GOOGLECALENDAR_FIND_FREE_SLOTS',
                                                         {'date': '2026-10-28', 'duration': 30})
        # Exercise native tool selection, real authorized read, and speech after
        # the result. The schema subset makes external writes impossible here.
        read_tools = [t for t in tools if t['name'] == 'GOOGLECALENDAR_FIND_FREE_SLOTS']
        llm = StageSelection('sarvam', meta['resolved_stack']['llm']['model'], {})
        context = SimpleNamespace(call_id='readonly-calendar-audit', tenant_id=tenant, agent_id=agent,
                                  compiled_brain_text=compiled, pending_tool_result=False)
        events = [event async for event in LiveTurnOrchestrator()._composed_tool_turn(
            ctx=context, adapter=SarvamLLMAdapter(), llm_sel=llm,
            stream_kwargs={'model': llm.model, 'max_output_tokens': 1280, 'temperature': 0},
            messages=[{'role': 'system', 'content': apply_available_tools(
                assemble_unified_brain(language='en-IN', script='You are Meera from Example Appointments. Check calendar availability when asked. Do not invent availability.'), read_tools)},
                {'role': 'user', 'content': 'Please check the real calendar for available 30-minute slots on 2026-10-28. Use the availability action, then tell me the first two options.'}],
            tool_schemas=read_tools, call_id=None, record_request_usage=lambda _: None, allow_retry=True)]
        final = next(event for event in reversed(events) if event.get('done'))
        selection_executed = any(event.get('status') == 'tool_wait' for event in events)
        report = {'accounts': accounts, 'compiled_tool_names': names,
                  'calendar_router': {'status': result.get('status'), 'slot_count': len(result.get('available_slots') or []),
                                      'time_zone': result.get('time_zone'), 'message': result.get('message')},
                  'live_llm_calendar': {'selected_action': selection_executed, 'response': final.get('text'),
                                        'finish_reason': final.get('finish_reason'), 'model': llm.model},
                  'no_external_writes': True}
        Path(__file__).with_name('live-integration-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        assert all(v['requested_account_matches'] for v in accounts.values())
        assert result.get('status') in {'available', 'unavailable'}
        assert selection_executed and final.get('text')
    finally:
        await close_db()


if __name__ == '__main__':
    asyncio.run(main())
