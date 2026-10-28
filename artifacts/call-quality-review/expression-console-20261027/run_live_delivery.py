"""Isolated real LLM and speech-provider checks; no call or business writes."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent


async def main():
    from server.config.env import Settings, get_settings
    from server.providers.sarvam_llm import SarvamLLMAdapter
    from server.providers.gnani_tts import GnaniTTSAdapter
    from server.providers.base import StageSelection, TTSConfig
    from server.services.saas.voice_stack_profiles import load_profile_records
    from server.services.dev_runtime import effective_app_environment
    from server.db.connection import init_db, close_db

    adapter = SarvamLLMAdapter(api_key=SarvamLLMAdapter()._api_key())
    speech_key = GnaniTTSAdapter()._api_key()
    assert adapter._api_key(), 'Pinned LLM is not configured'
    # Read current persisted profiles, but never update platform configuration.
    await init_db()
    profiles = await load_profile_records(effective_app_environment(), None)
    report = {'tiers': [], 'llm': [], 'tts': []}
    for tier, record in profiles.items():
        profile = record.get('profile') or {}
        report['tiers'].append({'tier': tier, 'revision': record.get('revision'),
            'enabled': profile.get('enabled'), 'llm': profile.get('llm'),
            'ttsModels': [{'provider': m.get('provider'), 'model': m.get('model')}
                for e in profile.get('engines', []) for m in e.get('models', [])]})
    await close_db()
    # All subsequent conversation state belongs to a disposable local directory.
    Settings.model_config['env_file'] = None
    os.environ.pop('DATABASE_URL', None)
    os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='voice-expression-')
    os.environ['FX_RATE_LIVE'] = 'false'
    get_settings.cache_clear()
    from server.brain.compiled_brain_artifact import assemble_unified_brain
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator, finalize_live_spoken_text
    from server.services.composed_voice_session import composed_system_prompt

    ctx = SimpleNamespace(pipeline='composed_voice', tier='simulation',
        compiled_brain_version='delivery-simulation',
        compiled_brain_text=assemble_unified_brain(language='te-IN', script=(
            'You are Meera from Example Cards. Visiting cards cost 25 rupees each. '
            'Delivery takes two days. Answer enquiries and objections using approved facts. '
            'No integrations are connected. Never invent a completed order.\n'
            'When: Too expensive\nReply: Explain the approved price and ask what concerns them.\n'
            'Action: continue_script')),
        resolved_stack=SimpleNamespace(language='te-IN', llm=StageSelection('sarvam', 'sarvam-105b-conversations', {}),
                                       tts=StageSelection('gnani', 'timbre-v3.0', {})))
    scenarios = [
        ('positive', 'మీ service నచ్చింది! మా office opening కోసం cards తీసుకోవాలని చాలా excited గా ఉన్నాను!'),
        ('slow', 'కొంచెం నెమ్మదిగా చెప్పండి, ఒక్క card ధర ఎంత?'),
        ('neutral', 'Delivery కి ఎన్ని రోజులు పడుతుంది?'),
        ('objection', 'ఒక్క card కి ఇరవై ఐదు రూపాయలా? చాలా ఎక్కువగా ఉంది.'),
    ]
    with patch('server.call.call_context.get', return_value=ctx):
        for name, caller in scenarios:
            start = time.monotonic()
            events = [e async for e in LiveTurnOrchestrator()._stream_composed_speech(
                adapter=adapter, messages=[{'role': 'developer', 'content': composed_system_prompt(ctx)},
                    {'role': 'user', 'content': caller}], schema=None,
                stream_kwargs={'model': 'sarvam-105b-conversations', 'max_output_tokens': 1280, 'temperature': 0.2},
                call_id='isolated-expression', provider='sarvam', model='sarvam-105b-conversations')]
            raw = next(e.get('text', '') for e in reversed(events) if e.get('done'))
            text = finalize_live_spoken_text(caller, raw, ctx=ctx)
            row = {'scenario': name, 'caller': caller, 'speech': text,
                   'elapsed_s': round(time.monotonic()-start, 3), 'nonempty': bool(text),
                   'standalone_honorific_count': len(re.findall(r'(?<!\w)అండి(?!\w)', text))}
            if name in {'positive', 'slow'}:
                row['expected_tag_present'] = ('<excited>' if name == 'positive' else '<slow>') in text
            report['llm'].append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
    if speech_key:
        from server.services import gnani_tts_ws
        from server.services.saas.voice_preview import pcm16_to_wav
        for row in report['llm'][:2]:
            start = time.monotonic()
            chunks = []
            with patch.object(gnani_tts_ws, '_gnani_api_key', return_value=speech_key):
                async with gnani_tts_ws.connect_gnani_tts_ws(model='timbre-v3.0') as socket:
                    await socket.send(json.dumps({'type': 'config', 'data': {'speaker': 'Shivani', 'language_code': 'te-IN', 'speech_sample_rate': 16000}}))
                    await socket.send(json.dumps({'type': 'text', 'data': {'text': row['speech']}}))
                    await socket.send(json.dumps({'type': 'flush'}))
                    while True:
                        event = json.loads(await asyncio.wait_for(socket.__anext__(), timeout=20))
                        if event.get('type') == 'error':
                            raise RuntimeError('Speech provider returned an error')
                        if event.get('type') == 'end_of_stream':
                            break
                        if event.get('type') == 'audio':
                            chunks.append(base64.b64decode(event['data']['audio']))
            pcm = b''.join(chunks)
            assert pcm, 'Provider returned no audio'
            filename = f"{row['scenario']}.wav"
            (OUT / filename).write_bytes(pcm16_to_wav(pcm, 16000))
            report['tts'].append({'scenario': row['scenario'], 'pcm_bytes': len(pcm),
                'sample_rate': 16000, 'seconds': round(len(pcm)/32000, 3),
                'elapsed_s': round(time.monotonic()-start, 3), 'file': filename})
    report['pass'] = all(row['nonempty'] and row.get('expected_tag_present', True)
                         and not row['standalone_honorific_count'] for row in report['llm'])
    (OUT / 'live-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['pass'], 'Inspect live response evidence'


asyncio.run(main())
