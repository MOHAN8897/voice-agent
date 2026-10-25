"""Real Standard-model diagnostics; counterfactuals, not website pass results."""
import asyncio,json,time,copy
from pathlib import Path
import run_audit as audit

async def main():
 settings,_=audit.setup()
 from server.providers.sarvam_llm import SarvamLLMAdapter
 from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
 from server.services.composed_voice_session import composed_system_prompt
 from server.providers.base import StageSelection
 from types import SimpleNamespace as NS
 import httpx
 current={}
 Client=httpx.AsyncClient
 class Observe(Client):
  async def send(self,request,**kwargs):
   response=await super().send(request,**kwargs)
   if request.url.host=='api.sarvam.ai':
    lines0=response.aiter_lines
    async def lines():
     async for line in lines0():
      if line.startswith('data:'):
       try:
        data=json.loads(line[5:].strip())
        if data.get('usage'):current['usage']=data['usage']
        for choice in data.get('choices',[]):
         d=choice.get('delta') or {};s=d.get('content')
         if isinstance(s,str):
          current['raw_content']=current.get('raw_content','')+s
         if d.get('reasoning_content'):current['reasoning_chars']=current.get('reasoning_chars',0)+len(d['reasoning_content'])
         if choice.get('finish_reason'):current['sse_finish']=choice['finish_reason']
       except (ValueError,TypeError):pass
      yield line
    response.aiter_lines=lines
   return response
 httpx.AsyncClient=Observe
 adapter=SarvamLLMAdapter()
 output=audit.OUT/'ablation-results.json'
 results=json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
 for lang in ['en-IN','te-IN','hi-IN']:
  b=json.loads((audit.OUT/'agents'/('print-'+lang)/'build.json').read_text(encoding='utf-8'))
  stack=audit.BASE['resolved_stacks'][lang]
  ctx=NS(compiled_brain_text=b['compiled'],compiled_brain_version=b['compiled_version'],resolved_stack=NS(language=lang,llm=StageSelection(**stack['llm']),tts=StageSelection(**stack['tts'])))
  actual=composed_system_prompt(ctx)
  corpus=json.loads((audit.OUT/'corpus'/(lang+'.json')).read_text(encoding='utf-8'))['print']
  for variant in ['full_schema','speech_only_schema','plain_text','minimal_prompt_full_schema','full_schema_no_length']:
   if any(r['language']==lang and r['variant']==variant for r in results):continue
   current={'language':lang,'variant':variant};t0=time.monotonic()
   prompt=actual
   schema=LIVE_TURN_JSON_SCHEMA
   if variant=='speech_only_schema':schema={'type':'object','properties':{'spoken_response':{'type':'string'}},'required':['spoken_response'],'additionalProperties':False}
   if variant=='full_schema_no_length':
    schema=copy.deepcopy(LIVE_TURN_JSON_SCHEMA)
    def strip(x):
     if isinstance(x,dict):
      x.pop('maxLength',None);x.pop('minLength',None)
      for value in x.values():strip(value)
     elif isinstance(x,list):
      for value in x:strip(value)
    strip(schema)
   if variant=='plain_text':
    schema=None;prompt+='\nDiagnostic: return only the spoken answer, without JSON. Keep the call open for this price question.'
   if variant=='minimal_prompt_full_schema':prompt=f'You are Meera of ClearPrint Studio. Reply in {lang}. Visiting cards cost 25 rupees each, minimum 100. Wedding invitations use a design-based quote. Delivery five working days after approval. Answer questions directly. Caller interest is continue, none, no opt-out. Copy current words for evidence. Never invent prices or tool results. Produce only the supplied JSON structure. Do not claim an order.'
   messages=[{'role':'system','content':prompt},{'role':'user','content':corpus['interested']}]
   try:
    stream=adapter.stream_structured_turn if schema else adapter.stream_live_turn
    async with asyncio.timeout(18):
     async for event in stream(input_messages=messages,schema=schema,model=stack['llm']['model'],api_mode='chat_completions_v1',reasoning_effort=None,max_output_tokens=1280,temperature=0):
      if event.get('done'):current['result']=event
    current['status']='completed'
   except Exception as ex:current['status']=type(ex).__name__;current['error']=str(ex)[:150]
   current['elapsed_s']=round(time.monotonic()-t0,3)
   raw=current.pop('raw_content','');current['content_chars']=len(raw);current['whitespace_ratio']=round(sum(c.isspace() for c in raw)/max(1,len(raw)),3);current['content_preview']=raw[:1700];current['content_tail']=raw[-500:]
   results.append(current);audit.dump(audit.OUT/'ablation-results.json',results)
   print(json.dumps({k:current.get(k) for k in ['language','variant','status','sse_finish','content_chars','whitespace_ratio','elapsed_s']},ensure_ascii=False),flush=True)
asyncio.run(main())
