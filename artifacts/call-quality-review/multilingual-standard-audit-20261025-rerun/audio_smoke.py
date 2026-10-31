"""Synthetic real TTS -> realtime STT -> real server/model -> real TTS.

No PSTN carrier or external CRM. Audio is generated test speech, not a person.
"""
import asyncio,base64,json,time,uuid,wave
from datetime import datetime,timezone
from unittest.mock import AsyncMock
import run_fresh as f

PHRASES={'en-IN':'What is the total course fee and the class timing?','te-IN':'కోర్సు మొత్తం ఫీజు ఎంత? క్లాస్ టైమింగ్ ఏంటి?','hi-IN':'कोर्स की कुल फीस कितनी है और क्लास का समय क्या है?','ta-IN':'கோர்ஸ் மொத்த கட்டணம் எவ்வளவு? கிளாஸ் நேரம் என்ன?','kn-IN':'ಕೋರ್ಸ್ ಒಟ್ಟು ಶುಲ್ಕ ಎಷ್ಟು? ಕ್ಲಾಸ್ ಸಮಯ ಏನು?'}
def wav(path,pcm):
 with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)

async def main():
 a=f.a;a.setup()
 from server.services.pstn_voice_core import PstnVoiceLoop,PHASE_LISTENING
 from server.services.pstn_turn_tts import PstnTurnTtsSession
 from server.providers import get_provider_registry
 from server.providers.base import STTConfig,StageSelection,ResolvedStack
 from server.call.call_context import CallContext,put
 from server.call.call_ledger import call_ledger
 from server.call.paths import call_dir
 from server.call.live_turn_orchestrator import LiveTurnOrchestrator,live_turn_orchestrator
 async def no_tools(self,ctx):return []
 LiveTurnOrchestrator._load_composed_tenant_tools=no_tools
 rows=[];(f.OUT/'audio').mkdir(exist_ok=True)
 for lang,phrase in PHRASES.items():
  row={'language':lang,'synthetic_caller':phrase,'stt_model':a.BASE['resolved_stacks'][lang]['stt']['model'],'tts_model':a.BASE['resolved_stacks'][lang]['tts']['model']};t=time.monotonic();tts=None;voice=None
  try:
   stack=a.BASE['resolved_stacks'][lang];cid=str(uuid.uuid4());sid='audio-'+cid
   b=json.loads((f.OUT/'agents'/('language-'+lang)/'build.json').read_text(encoding='utf-8'))
   resolved=ResolvedStack(combination_id='audit-standard-r91',tier='medium',mode='locked',language=lang,stt=StageSelection(**stack['stt']),llm=StageSelection(**stack['llm']),tts=StageSelection(**stack['tts']))
   ctx=CallContext(call_id=cid,session_id=sid,tenant_id=a.TENANT,agent_id=b['agent_id'],channel='pstn',direction='outbound',environment=a.BASE['environment'],tier='medium',pipeline='composed_voice',resolved_stack=resolved,compiled_brain_text=b['compiled'],compiled_brain_version=b['compiled_version'],started_at=datetime.now(timezone.utc),storage_path=str(call_dir(cid)))
   put(ctx);await call_ledger.init(cid,{'call_id':cid,'tenant_id':a.TENANT,'agent_id':b['agent_id'],'session_id':sid,'language':lang,'audit':True})
   voice=PstnVoiceLoop(session_id=sid,call_id=cid,on_agent_wire=AsyncMock(),sample_rate=16000,tts_output_codec='linear16',stack_override=stack);voice._phase=PHASE_LISTENING;voice._intro_phase=False
   voice.current_generation_id=uuid.uuid4().hex;voice.current_turn_id=uuid.uuid4().hex[:12]
   tts=PstnTurnTtsSession(voice)
   async with asyncio.timeout(25):
    await tts.open(language_code=lang,resolved_stack=resolved,pipeline='composed_voice')
    pcm=b''.join(await tts.synthesize_to_frames(phrase))
   if not pcm:raise RuntimeError('Pinned TTS returned no synthetic caller audio')
   row['caller_pcm_bytes']=len(pcm);wav(f.OUT/'audio'/(lang+'-caller.wav'),pcm)
   stt=get_provider_registry().get_stt(stack['stt']['provider']);transcripts=[]
   async with stt.connect_realtime(STTConfig(provider=stack['stt']['provider'],model=stack['stt']['model'],language=lang,sample_rate=16000)) as ws:
    async def receive():
     while True:
      raw=await ws.recv();obj=json.loads(raw);data=obj.get('data') or {};kind=obj.get('event') or obj.get('type');text=obj.get('text') or obj.get('transcript') or ((data.get('text') or data.get('transcript')) if isinstance(data,dict) else '')
      row.setdefault('stt_events',[]).append({'event':kind,'text':text})
      if text and kind=='transcript.final':transcripts.append(str(text))
      if obj.get('error') or obj.get('type')=='error':row.setdefault('stt_errors',[]).append(str(obj)[:220])
    reader=asyncio.create_task(receive())
    audio=b'\0'*6400+pcm+b'\0'*32000
    for start in range(0,len(audio),640):
     await ws.send(json.dumps({'event':'audio_input','audio':base64.b64encode(audio[start:start+640]).decode()}));await asyncio.sleep(.02)
    await ws.send(json.dumps({'event':'flush'}));await asyncio.sleep(2)
    reader.cancel();await asyncio.gather(reader,return_exceptions=True)
   row['transcripts']=transcripts
   if not transcripts:raise RuntimeError('Pinned realtime STT returned no transcript')
   transcript=' '.join(transcripts)
   async with asyncio.timeout(18):
    events=[e async for e in live_turn_orchestrator.handle_user_turn_stream(transcript=transcript,language_code=lang,session_id=sid,call_id=cid)]
   done=next(e for e in events if e.get('done'));row['server_reply']=done.get('text');row['end_call']=done.get('end_call')
   async with asyncio.timeout(25):reply_pcm=b''.join(await tts.synthesize_to_frames(done['text']))
   row['reply_pcm_bytes']=len(reply_pcm)
   if not reply_pcm:raise RuntimeError('Pinned TTS returned no agent reply audio')
   wav(f.OUT/'audio'/(lang+'-reply.wav'),reply_pcm)
   row['status']='passed' if not done.get('end_call',{}).get('should_end') else 'unexpected_close'
  except Exception as ex:row['status']='failed';row['error_type']=type(ex).__name__;row['error']=str(ex)[:250]
  finally:
   if tts:await tts.close()
   if voice:await voice.close()
  row['elapsed_s']=round(time.monotonic()-t,3);rows.append(row);a.dump(f.OUT/'audio-smoke.json',rows);print(json.dumps(row,ensure_ascii=False),flush=True)
asyncio.run(main())
