"""Same model/business/caller; compare current and speech-only contracts."""
import asyncio,json,time
from types import SimpleNamespace as NS
import run_fresh as f

async def main():
 a=f.a;a.setup()
 from server.providers.sarvam_llm import SarvamLLMAdapter
 from server.providers.base import StageSelection
 from server.services.composed_voice_session import composed_system_prompt
 from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA,LIVE_SPEECH_JSON_SCHEMA
 adapter=SarvamLLMAdapter();rows=[]
 for lang in a.BASE['resolved_stacks']:
  b=json.loads((f.PREVIOUS/'agents'/('repair-'+lang)/'build.json').read_text(encoding='utf-8'));st=a.BASE['resolved_stacks'][lang]
  ctx=NS(compiled_brain_text=b['compiled'],compiled_brain_version=b['compiled_version'],resolved_stack=NS(language=lang,llm=StageSelection(**st['llm']),tts=StageSelection(**st['tts'])))
  c=json.loads((f.PREVIOUS/'corpus'/(lang+'.json')).read_text(encoding='utf-8'))['repair']
  for key in ['future','details']:
   for variant,schema in [('current_full',LIVE_TURN_JSON_SCHEMA),('speech_only',LIVE_SPEECH_JSON_SCHEMA)]:
    row={'language':lang,'caller_key':key,'variant':variant};t=time.monotonic()
    try:
     async with asyncio.timeout(14):
      async for event in adapter.stream_structured_turn(input_messages=[{'role':'system','content':composed_system_prompt(ctx)},{'role':'user','content':c[key]}],schema=schema,model=st['llm']['model'],api_mode='chat_completions_v1',max_output_tokens=1280,reasoning_effort=None,temperature=0):
       if event.get('done'):row['result']=event
     row['status']='completed'
    except Exception as ex:row['status']=type(ex).__name__;row['finish_reason']=getattr(ex,'finish_reason',None)
    row['elapsed_s']=round(time.monotonic()-t,3);rows.append(row);a.dump(f.OUT/'contract-probe.json',rows)
    print(json.dumps({k:v for k,v in row.items() if k!='result'}),flush=True)
asyncio.run(main())
