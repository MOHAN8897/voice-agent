"""Live source-grounding checks with the actual pinned Sarvam stack."""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
sys.stdout.reconfigure(encoding='utf-8')
from environment import setup, write, REQUESTS, NETWORK, ACTOR


async def main():
    os.environ['AUDIT_RESUME'] = '1'
    _, stack, _ = await setup()
    ACTOR.set('agent')
    from server.call.business_answer_plan import resolve_business_answers
    from server.call.spoken_fact_review import review_spoken_turn
    from server.call.memory_manager import memory_manager
    from server.db.connection import close_db
    cases = [
        ('ac_inspection_unknown', 'B', 'Split AC servicing 599 అని చెప్పారు. AC inspection charge ఎంత? అది servicing లో include అయిందా?',
         'AC inspection charge సున్నా; servicing లోనే included.', 'not_stated'),
        ('course_extras_unknown', 'C', 'Python course fee కాకుండా study material, certificate charges కూడా included ఆ? Hidden charges లేవు కదా?',
         'అన్నీ included, hidden charges లేవు.', 'not_stated'),
        ('cards_total', 'A', 'నాకు 200 matte visiting cards కావాలి. మొత్తం ఎంత?',
         'మొత్తం 350 రూపాయలు.', '700'),
    ]
    results = []
    for name, agent_id, caller, draft, expected in cases:
        agent = json.loads((ROOT / 'agents' / f'{agent_id}-published.json').read_text(encoding='utf-8'))
        ctx = SimpleNamespace(call_id=str(uuid.uuid4()), session_id='business-probe-' + name,
            compiled_brain_text=agent['snapshot']['compiled_text'], resolved_stack=stack,
            action_receipts=[], turn_action_results=[], available_tools=[], turn_control={}, communication_receipts=[])
        memory_manager.init(ctx.call_id)
        ctx.business_answers = await resolve_business_answers(ctx, caller)
        spoken = await review_spoken_turn(ctx, caller=caller, draft=draft, language='te-IN')
        results.append({'name': name, 'caller': caller, 'draft': draft, 'expected': expected,
                        'plan': ctx.business_answers, 'spoken': spoken})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        write('business-probes/results.json', results)
    write('business-probes/requests.json', REQUESTS)
    write('business-probes/network.json', NETWORK)
    await close_db()


if __name__ == '__main__':
    asyncio.run(main())
