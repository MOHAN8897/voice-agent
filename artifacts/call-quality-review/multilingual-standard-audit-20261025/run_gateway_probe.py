"""Replay real diagnostic native calls through actual server gateway orchestration.

This isolates the downstream path; it is NOT a normal-flow matrix success.
"""
import asyncio,json,uuid,time
from types import SimpleNamespace as NS
import run_audit as a

async def main():
 a.setup()
 from server.call.live_turn_orchestrator import live_turn_orchestrator as orch
 from server.services.tool_router import tool_router
 from server.providers.sarvam_llm import SarvamLLMAdapter
 from server.providers.base import StageSelection
 from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
 from server.services.composed_voice_session import composed_system_prompt
 probes=json.loads((a.OUT/'tool-probe-results.json').read_text(encoding='utf-8'))
 rows=[];adapter=SarvamLLMAdapter()
 for lang in ['en-IN','te-IN']:
  b=json.loads((a.OUT/'agents'/('print-'+lang)/'build.json').read_text(encoding='utf-8'));st=a.BASE['resolved_stacks'][lang]
  ctx=NS(call_id=str(uuid.uuid4()),tenant_id=a.TENANT,agent_id=b['agent_id'],compiled_brain_text=b['compiled'],compiled_brain_version=b['compiled_version'],resolved_stack=NS(language=lang,llm=StageSelection(**st['llm']),tts=StageSelection(**st['tts'])))
  calls=next(p['result']['tool_calls'] for p in probes if p['language']==lang and p['variant']=='tools_no_schema')
  user='Please submit my consented quote enquiry for 200 wedding invitations in Baner, Pune, for review tomorrow at 3pm. My name is Audit Customer, email audit.customer@example.invalid. No confirmed booking or order.'
  for mode in ['success','timeout','unauthorized']:
   row={'language':lang,'mode':mode,'executions':[]};t0=time.monotonic()
   async def boundary(**kwargs):
    assert kwargs['tenant_id']==a.TENANT and kwargs['agent_id']==b['agent_id']
    row['executions'].append({'tool_name':kwargs['tool_name'],'arguments':kwargs['arguments']})
    if mode=='timeout':raise TimeoutError('Simulated CRM timeout; save outcome unknown')
    return {'status':'ok','saved':True,'reference':'AUDIT-ONLY','appointment_confirmed':False,'order_confirmed':False,'message':'Enquiry saved for team review only. No email sent and no booking or order confirmed.'}
   tool_router.route_and_execute=boundary
   messages=await orch._execute_composed_tools(ctx=ctx,messages=[{'role':'system','content':composed_system_prompt(ctx)},{'role':'user','content':user}],tool_calls=calls,allowed_tools=set() if mode=='unauthorized' else {'CRM_CREATE_ENQUIRY'})
   row['tool_result_messages']=[m for m in messages if m['role']=='tool']
   row['protocol_pass']=len(row['executions'])==(0 if mode=='unauthorized' else 1) and all(m['tool_call_id']==calls[0]['id'] for m in row['tool_result_messages'])
   try:
    async with asyncio.timeout(18):
     async for event in adapter.stream_structured_turn(input_messages=messages,schema=LIVE_TURN_JSON_SCHEMA,tools=[a.MOCK_TOOL],tool_choice='none',max_output_tokens=1280,reasoning_effort=None,temperature=0,model=st['llm']['model'],api_mode='chat_completions_v1'):
      if event.get('done'):row['result']=event
    row['status']='completed'
   except Exception as e:row['status']=type(e).__name__;row['error']=str(e)[:180]
   row['elapsed_s']=round(time.monotonic()-t0,3);rows.append(row);a.dump(a.OUT/'gateway-probe-results.json',rows)
   print(json.dumps({'language':lang,'mode':mode,'protocol_pass':row['protocol_pass'],'status':row['status']},ensure_ascii=False),flush=True)
asyncio.run(main())
