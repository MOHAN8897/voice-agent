"""Three isolated Premium LLM/server simulations. No TTS, PSTN or external writes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


async def main():
    import pytest
    from server import providers
    from server.agent.conversation_manager import conversation_manager
    from server.call import call_context
    from server.call.call_context import CallContext
    from server.call.call_ledger import call_ledger
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator
    from server.call.memory_manager import memory_manager
    from server.config.env import Settings, get_settings
    from server.providers.base import StageSelection
    from server.providers.sarvam_llm import SarvamLLMAdapter
    from server.services import pstn_voice_core as core
    from server.services.tool_schema_registry import get_tools_for_tenant
    from server.services.user_turn_hints import note_caller_interruption
    from server.prompts.agent_voice_rules import slow_down_fallback_for

    source = json.loads((ROOT / 'data/calls/92064910-e19a-46e5-ba19-420cd8041154/meta.json').read_text(encoding='utf-8'))
    adapter = SarvamLLMAdapter(api_key=SarvamLLMAdapter()._api_key())
    assert adapter._api_key(), 'The pinned model must be configured'
    Settings.model_config['env_file'] = None
    os.environ.pop('DATABASE_URL', None)
    os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='voice-silence-llm-')
    os.environ['SAAS_AUTH_ENABLED'] = 'false'
    os.environ['FX_RATE_LIVE'] = 'false'
    os.environ['ENABLE_CALL_ARCHIVE'] = 'true'
    get_settings.cache_clear()
    llm = StageSelection(**source['resolved_stack']['llm'])
    tools = get_tools_for_tenant(['GOOGLECALENDAR'])
    from server.call.enquiry import SAVE_ENQUIRY_TOOL
    from server.call.order_confirmation import CONFIRM_ORDER_TOOL
    tools += [SAVE_ENQUIRY_TOOL, CONFIRM_ORDER_TOOL]
    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
                               get_llm=lambda *_: adapter)
    contexts, archive_tasks, results, attempts = {}, [], [], []
    orchestrator = LiveTurnOrchestrator()
    original_after = orchestrator._after_assistant

    async def archive(*args, **kwargs):
        archive_tasks.append(asyncio.current_task())
        return await original_after(*args, **kwargs)

    async def prohibit_external_writes(**kwargs):
        attempts.append(kwargs['tool_name'])
        return {'status': 'error', 'message': 'Simulation does not permit external writes.'}

    async def session(name):
        cid = str(uuid.uuid4())
        ctx = CallContext(call_id=cid, session_id=cid, tenant_id=source['tenant_id'], agent_id=source['agent_id'],
            channel='pstn', direction='outbound', environment='simulation', tier=source['resolved_stack']['tier'],
            started_at=datetime.now(timezone.utc), storage_path=os.environ['DATA_DIR'],
            pipeline='composed_voice', compiled_brain_text=source['compiled_brain_text'],
            compiled_brain_version=source['compiled_brain_version'],
            resolved_stack=SimpleNamespace(llm=llm, tts=StageSelection(**source['resolved_stack']['tts']),
                                           language='te-IN', tier=source['resolved_stack']['tier']))
        contexts[cid] = ctx
        await call_ledger.init(cid, {'call_id': cid, 'language': 'te-IN', 'is_test': True, 'pipeline': 'composed_voice'})
        memory_manager.init(cid)
        conversation_manager.add_turn(cid, '', 'మీ digital visiting cards గురించి మాట్లాడటానికి ఈ సమయం సరిపోతుందా అండి? [Opening already delivered.]')
        return ctx, {'scenario': name, 'turns': []}

    async def turn(ctx, report, text):
        started = time.monotonic()
        events = [e async for e in orchestrator.handle_user_turn_stream(
            transcript=text, language_code='te-IN', session_id=ctx.session_id, call_id=ctx.call_id)]
        done = next(e for e in reversed(events) if e.get('done'))
        await asyncio.sleep(0)
        pending = [task for task in archive_tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending)
        row = {'caller': text, 'response': done.get('text'), 'close': bool(done.get('end_call', {}).get('should_end')),
               'wait_for_caller': bool(done.get('wait_for_caller')), 'elapsed_s': round(time.monotonic()-started, 3),
               'finish_reason': done.get('finish_reason'), 'retry_count': done.get('retry_count', 0)}
        report['turns'].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return row

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(providers, 'get_provider_registry', lambda: registry)
        patch.setattr(call_context, 'get', contexts.get)
        patch.setattr(orchestrator, '_load_composed_tenant_tools', AsyncMock(return_value=tools))
        patch.setattr(orchestrator, '_after_assistant', archive)
        patch.setattr('server.services.tool_router.tool_router.route_and_execute', prohibit_external_writes)

        ctx, report = await session('filtered echo interruption then real price question')
        voice = core.PstnVoiceLoop(session_id=ctx.session_id, call_id=ctx.call_id, on_agent_wire=AsyncMock())
        class SttEvents:
            async def __aiter__(self):
                yield json.dumps({'event': 'transcript.final', 'text': 'We only sell visiting cards and identity cards.'})
                yield json.dumps({'event': 'transcript.final', 'text': 'ఒక్కో visiting card ధర ఎంత అండి?'})
        voice._last_tts_text = 'We only sell visiting cards and identity cards.'
        voice._set_phase(core.PHASE_INTERRUPTING)
        voice._awaiting_barge_final = True
        voice._barge_epoch = time.monotonic()
        voice._stt = SttEvents()
        voice._launch_turn = Mock()
        await voice._stt_reader()
        if voice._coalesce_task:
            await voice._coalesce_task
        assert voice._phase == core.PHASE_LISTENING
        voice._launch_turn.assert_called_once()
        recovered = voice._launch_turn.call_args.args[0]
        response = await turn(ctx, report, recovered)
        report['passed'] = bool(response['response']) and not response['close'] and 'twenty five' in response['response'].lower()
        await voice.close()
        results.append(report)

        ctx, report = await session('three interruptions, unknown minimum budget, then payment question')
        for _ in range(3):
            note_caller_interruption(ctx)
        response = await turn(ctx, report, 'మినిమం ఎంత బడ్జెట్ ఉంటుంది? వివరాలు చెప్పండి, ఇప్పుడే order చేయట్లేదు.')
        polite = slow_down_fallback_for('te-IN')
        first_polite = response['response'].count(polite) == 1 and response['response'].count('నెమ్మదిగా') == 1
        followup = await turn(ctx, report, 'Payment ఎలా చేయొచ్చు అండి?')
        report['passed'] = first_polite and polite not in followup['response'] and all(
            row['response'] and not row['close'] for row in report['turns'])
        report['manual_review'] = 'Unknown minimum must be admitted, not invented; no order/contact collection during enquiry.'
        results.append(report)

        ctx, report = await session('cancelled live request then availability check and thanks-plus-question')
        pending = asyncio.create_task(turn(ctx, report, 'ఒక్కో visiting card ధర ఎంత అండి?'))
        await asyncio.sleep(0.2)
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        assert ctx.interrupted_caller_request
        resumed = await turn(ctx, report, 'హలో మీరు ఉన్నారా అండి? చెప్పండి.')
        question = await turn(ctx, report, 'థాంక్స్, కానీ ఇంకో ప్రశ్న ఉంది. Delivery ఎలా చేస్తారు?')
        ending = await turn(ctx, report, 'అంతే అంతే థ్యాంక్ యూ')
        report['passed'] = bool(resumed['response']) and not resumed['close'] and bool(question['response']) and not question['close'] and ending['close']
        results.append(report)

    output = {'source_call': source['call_id'], 'source_brain_version': source['compiled_brain_version'],
              'source_brain_sha256': hashlib.sha256(source['compiled_brain_text'].encode()).hexdigest(),
              'llm': {'provider': llm.provider, 'model': llm.model}, 'tts_invocations': 0, 'pstn_calls': 0,
              'attempted_actions': attempts, 'simulations': results}
    output['passed'] = all(item['passed'] for item in results) and not attempts
    Path(__file__).with_name('llm-simulation-results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SIMULATIONS:', sum(r['passed'] for r in results), '/', len(results), 'No TTS.', flush=True)
    if not output['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
