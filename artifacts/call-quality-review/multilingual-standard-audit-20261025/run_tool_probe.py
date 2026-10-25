"""Isolate offered tools versus structured-output constraints on Standard LLM."""
import asyncio,json,time
import run_audit as a

async def main():
 a.setup()
 from server.providers.sarvam_llm import SarvamLLMAdapter
 from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
 from server.providers.base import StageSelection
 from server.services.composed_voice_session import composed_system_prompt
 from types import SimpleNamespace as NS
 adapter=SarvamLLMAdapter();rows=[]
 for lang in ['en-IN','te-IN']:
  b=json.loads((a.OUT/'agents'/('print-'+lang)/'build.json').read_text(encoding='utf-8'));st=a.BASE['resolved_stacks'][lang]
  ctx=NS(compiled_brain_text=b['compiled'],compiled_brain_version=b['compiled_version'],resolved_stack=NS(language=lang,llm=StageSelection(**st['llm']),tts=StageSelection(**st['tts'])))
  prompt=composed_system_prompt(ctx)
  user='I want a quote for 200 wedding invitations delivered to Baner, Pune. My name is Audit Customer, email audit.customer@example.invalid. Preferred review time is tomorrow at 3pm. I consent to saving this enquiry for team review now. Please submit it with your connected enquiry integration. This is not a confirmed order.'
  for variant in ['tools_full_schema','tools_no_schema','tools_no_schema_required']:
   row={'language':lang,'variant':variant};t0=time.monotonic()
   kwargs={'tools':[a.MOCK_TOOL],'tool_choice':'required' if variant.endswith('required') else 'auto','max_output_tokens':1280,'reasoning_effort':None,'temperature':0,'model':st['llm']['model'],'api_mode':'chat_completions_v1'}
   schema=LIVE_TURN_JSON_SCHEMA if variant=='tools_full_schema' else None
   stream=adapter.stream_structured_turn if schema else adapter.stream_live_turn
   try:
    async with asyncio.timeout(18):
     async for event in stream(input_messages=[{'role':'system','content':prompt},{'role':'user','content':user}],schema=schema,**kwargs):
      if event.get('done'):row['result']=event
    row['status']='completed'
   except Exception as e:row['status']=type(e).__name__;row['error']=str(e)[:160]
   row['elapsed_s']=round(time.monotonic()-t0,3);rows.append(row);a.dump(a.OUT/'tool-probe-results.json',rows)
   print(json.dumps({'language':lang,'variant':variant,'status':row['status'],'tool_calls':len(row.get('result',{}).get('tool_calls',[]))},ensure_ascii=False),flush=True)
asyncio.run(main())
