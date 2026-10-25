"""Actual server close executor, simulated playback and carrier fault events."""
import asyncio,json,time,uuid
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import run_audit as a

async def main():
 a.setup()
 from server.services.pstn_voice_core import PstnVoiceLoop,PHASE_LISTENING,PHASE_ENDED
 from server.call.call_lifecycle_service import call_lifecycle_service
 from server.call.call_context import put
 from server.call.call_ledger import call_ledger
 async def end(*args,**kwargs):return {'ok':True}
 call_lifecycle_service.end=end
 rows=[]
 for lang in a.BASE['resolved_stacks']:
  corpus=json.loads((a.OUT/'corpus'/(lang+'.json')).read_text(encoding='utf-8'))['print']
  for mode in ['normal_drain','new_question_during_farewell','duplicate_close','provider_timeout_then_retry']:
   cid=str(uuid.uuid4());start=time.monotonic();trace=[]
   ctx=NS(call_id=cid,session_id='handshake-'+cid,agent_hangup_armed=True,callback_close_phase='idle')
   put(ctx)
   await call_ledger.init(cid,{'call_id':cid,'audit':True,'language':lang})
   class Playback:
    until=time.monotonic()+0.12
    def is_active(self):return time.monotonic()<self.until
   voice=PstnVoiceLoop(session_id='handshake-'+cid,call_id=cid,on_agent_wire=AsyncMock(),playback=Playback(),stack_override=a.BASE['resolved_stacks'][lang])
   voice._phase=PHASE_LISTENING;voice._intro_phase=False
   attempts=0
   async def provider():
    nonlocal attempts
    attempts+=1;trace.append({'kind':'provider_attempt','t':round(time.monotonic()-start,3),'playback_active':voice.playback.is_active()})
    if mode=='provider_timeout_then_retry' and attempts==1:raise TimeoutError('simulated carrier acknowledgement timeout')
   voice.set_hangup_handler(provider)
   injected=None
   if mode=='new_question_during_farewell':
    async def caller():
     await asyncio.sleep(0.04);voice._pending_transcript=corpus['wait'];trace.append({'kind':'caller_question','t':round(time.monotonic()-start,3)})
    injected=asyncio.create_task(caller())
   failures=[]
   try:
    try:await voice._finish_agent_hangup(reason='goodbye')
    except TimeoutError:
     trace.append({'kind':'timeout','hangup_started':voice._hangup_started,'phase':voice._phase})
     if mode!='provider_timeout_then_retry':raise
     if voice._phase==PHASE_ENDED:failures.append('marked ended before carrier success')
     await voice._finish_agent_hangup(reason='goodbye')
    if injected:await injected
    if mode=='duplicate_close':await voice._finish_agent_hangup(reason='goodbye')
    if voice._background_hangup_task:await voice._background_hangup_task
    if any(x.get('playback_active') for x in trace):failures.append('provider called while farewell active')
    if mode=='new_question_during_farewell':
     if attempts:failures.append('caller resumption failed to veto disconnect')
     if voice._phase!=PHASE_LISTENING:failures.append('not listening after revocation')
    elif attempts!=(2 if mode=='provider_timeout_then_retry' else 1):failures.append('wrong provider attempt count')
   except Exception as ex:failures.append(type(ex).__name__+': '+str(ex))
   rows.append({'language':lang,'mode':mode,'pass':not failures,'failures':failures,'trace':trace,'provider_attempts':attempts,'phase':voice._phase})
   await voice.close()
 a.dump(a.OUT/'handshake-results.json',rows)
 print(json.dumps({'checks':len(rows),'passed':sum(r['pass'] for r in rows),'failed':[r for r in rows if not r['pass']]},ensure_ascii=False))
asyncio.run(main())
