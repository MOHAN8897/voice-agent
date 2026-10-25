"""Fresh live-model audit; reuse the existing isolated creation/voice harness.

Only auth/storage/tool/media boundaries are simulated. Model, compilation,
turn orchestration, speech guards and close executor are application code.
"""
from __future__ import annotations
import argparse,asyncio,copy,hashlib,importlib.util,json,os,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
PREVIOUS=OUT.parent/'multilingual-standard-audit-20261025-recheck'
spec=importlib.util.spec_from_file_location('audit_core',PREVIOUS/'run_audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
a.OUT=OUT;a.BASE=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
a.TENANT=str(uuid.uuid5(uuid.NAMESPACE_URL,'fresh-standard-audit-20261025'))

BRIEFS=[
 {'key':'cleaning','name':'Nila','company':'FreshNest Cleaning','role':'sales','brief':'''make Nila from FreshNest Cleaning, outbound friendly service information, Pune only. Messy note: sofa cleaning 349 rupees PER SEAT minimum 3 seats, kitchen cleaning 1599 rupees TOTAL. Old kitchen note 1299 is wrong; discard it, current kitchen fee 1599. Do not quote a whole sofa for 349. Mon-Sat 9am-6pm. No discount, refund or warranty policy supplied. Do not invent them. A caller rejecting sofa cleaning may still want kitchen cleaning. Answer prices and conditions first, never demand a name to answer. Goal explain services and, if wanted, submit an enquiry for team review after preferred name, service type, locality and consent. An enquiry is NOT a confirmed slot or paid order. If authorised CRM is connected save once after consent and confirm only the actual tool result. Without integration explain cannot save externally or confirm a visit; can discuss facts and note the request within this call. Future interest is welcome, not DNC, callbacks only when actually requested. Do not promise same-day arrival or a confirmed time. Do not give instructions for mixing toxic cleaning chemicals. Respect clear refusal and stop-contact. Optional fields optional.''',
  'known':'sofa cleaning 349 rupees per seat, minimum 3 seats; kitchen cleaning 1599 total',
  'question':'What are the sofa and kitchen cleaning prices, minimum seats, and is a visit already confirmed?',
  'alternate':'I do not need sofa cleaning, but I want kitchen cleaning. Can you explain it?'},
 {'key':'cycle','name':'Arjun','company':'CityCycle Repairs','role':'support','brief':'''Arjun at CityCycle Repairs. Outbound support for Chennai bicycle enquiries. Basic bicycle service 499 rupees, puncture repair 120 rupees, parts extra only after approval. Open Tue-Sun 9am-6pm. No warranty, refund, pickup or same-day availability information is supplied. Never invent these. Explain costs before collecting details. If they do not need a basic service but need puncture repair, follow the changed need. Goal answer bicycle questions then only if wanted take preferred name, repair type, locality and consent for an enquiry. Authorised CRM can save an enquiry for team review, not confirm a repair appointment or order. Without a connected integration cannot save externally, send email or promise a visit. Future need next month is welcome; do not treat it as rejection or opt-out. Do not request OTP, password or card data. No instructions to bypass e-bike battery protection or sabotage brakes. No medical or insurance advice. No sales qualification checklist. Caller saying done should get proper close; bare thanks is not automatically done.''',
  'known':'basic bicycle service 499 rupees, puncture repair 120 rupees; parts extra with approval',
  'question':'What do a basic bicycle service and puncture repair cost, and are parts included?',
  'alternate':'I do not want a basic service, but I need a puncture repair. Can you help?'},
 {'key':'language','name':'Sana','company':'SpeakEasy Language Studio','role':'sales','brief':'''create Sana, SpeakEasy Language Studio. Adult spoken-English classes online, six weeks, weekends 10am-11am, age 18+. Current total course fee 6499 rupees. An old note says 5499: WRONG, discard obsolete amount, final 6499 only. No job, fluency or income guarantee and no discount authorised. Exact next batch date, vacancies and refund rules unknown. Purpose answer class questions honestly, ask learning goal only if useful. If caller wants demo or counselling, preferred name and email plus consent permit a CRM enquiry for team review when integration connected. Saved enquiry does not mean demo time, seat, payment or admission confirmed. No integration means cannot send an email, save externally or confirm a demo. No need for delivery address, quantity, income or phone checklist. Someone refusing a job guarantee may still want learning support. Future interest after exams is welcome, never permanent DNC. Callback consent must be explicit. Do not help cheating, hacking exam systems or impersonation. Respect refusal and explicit ending; natural professional conversation, answer first.''',
  'known':'six-week online adult spoken-English course, weekends 10am-11am, total fee 6499 rupees; no guarantee',
  'question':'What is the final fee, duration and class timing, and do you guarantee fluency or a job?',
  'alternate':'I do not need a job guarantee, but I am interested in learning spoken English. Please explain.'},
]
a.BRIEFS=BRIEFS

async def capture():
 from server.config import get_settings
 from server.db.connection import init_db,close_db
 from server.services.dev_runtime import effective_app_environment
 from server.services.saas.platform_languages import enabled_languages
 from server.services.saas import voice_stack_profiles as p
 from server.brain.generation_runtime import generation_target
 b=a.BASE;b['captured_at']=datetime.now(timezone.utc).isoformat();b['environment']=effective_app_environment();b['languages']=enabled_languages()
 await init_db()
 try:
  rec=(await p.load_profile_records(b['environment'],['medium']))['medium'];b['standard']=rec;b['rates']=await p._load_rates_without_fallback()
  b['resolved_stacks']={};b['stack_errors']={};aliases=rec['publicAliases']
  for lang in b['languages']:
   try:
    await p.validate_agent_language_for_tier(b['environment'],'medium',lang)
    found=next((e,m,v) for e in rec['profile']['engines'] for m in e['models'] for v in m['voices'] if lang in v.get('languages',[]))
    e,m,v=found;vs={'profileRevision':rec['revision'],'engineId':aliases['engines'][e['id']],'modelId':aliases['models'][e['id']+'::'+m['id']],'voiceId':aliases['voices'][e['id']+'::'+m['id']+'::'+v['id']]}
    stack,_=await p.resolve_agent_selection(environment=b['environment'],tier='medium',voice_settings=vs,language=lang)
    b['resolved_stacks'][lang]=stack
   except (StopIteration,p.VoiceProfileError) as ex:b['stack_errors'][lang]=getattr(ex,'code','voice_selection_unavailable')+': '+str(ex)
  adapter,config=generation_target();b['generation_target']=[getattr(adapter,'provider_id',type(adapter).__name__),getattr(config,'model',None)]
 finally:await close_db()
 b['profile_verified_at']=datetime.now(timezone.utc).isoformat();a.dump(OUT/'baseline.json',b)
 print(json.dumps({'environment':b['environment'],'revision':rec['revision'],'llm':rec['profile']['llm'],'enabled':b['languages'],'standard_eligible':list(b['resolved_stacks']),'blocked':b['stack_errors']},ensure_ascii=False),flush=True)

QUESTIONS={
'te-IN':['సోఫా, కిచెన్ క్లీనింగ్ ధరలు, కనిష్ట seats ఎన్ని? Visit ఇప్పుడే confirm అయిందా?','సైకిల్ basic service, puncture repair ధరలు ఎంత? Parts కూడా ఆ ధరలో ఉన్నాయా?','Final course fee, duration, class timings ఏంటి? Fluency లేదా job guarantee ఇస్తారా?'],
'hi-IN':['सोफा और kitchen cleaning की कीमत और minimum seats कितनी हैं? क्या visit अभी confirm है?','साइकिल basic service और puncture repair की कीमत क्या है? क्या parts शामिल हैं?','Final course fee, duration और class timing क्या है? Fluency या job की guarantee है?'],
'ta-IN':['சோபா மற்றும் kitchen cleaning விலை, minimum seats எத்தனை? Visit இப்போவே confirm ஆயிடுச்சா?','சைக்கிள் basic service மற்றும் puncture repair விலை என்ன? Parts அந்த விலையில் இருக்கா?','Final course fee, duration, class timing என்ன? Fluency அல்லது job guarantee இருக்கா?'],
'kn-IN':['ಸೋಫಾ ಮತ್ತು kitchen cleaning ಬೆಲೆ, minimum seats ಎಷ್ಟು? Visit ಈಗಲೇ confirm ಆಗಿದೆಯಾ?','ಸೈಕಲ್ basic service ಮತ್ತು puncture repair ಬೆಲೆ ಎಷ್ಟು? Parts ಕೂಡ ಇದರಲ್ಲಿ ಸೇರಿವೆಯಾ?','Final course fee, duration ಮತ್ತು class timing ಏನು? Fluency ಅಥವಾ job guarantee ಇದೆಯಾ?']}
ALTERNATES={
'te-IN':['సోఫా cleaning వద్దు, కానీ kitchen cleaning కావాలి. వివరాలు చెప్పండి.','Basic service వద్దు, కానీ puncture repair కావాలి. చేయగలరా?','Job guarantee అవసరం లేదు, కానీ spoken English నేర్చుకోవాలని ఉంది. Course వివరించండి.'],
'hi-IN':['मुझे सोफा cleaning नहीं चाहिए, लेकिन kitchen cleaning चाहिए। समझाइए।','मुझे basic service नहीं चाहिए, लेकिन puncture repair चाहिए। क्या मदद करेंगे?','मुझे job guarantee नहीं चाहिए, लेकिन spoken English सीखनी है। Course बताइए।'],
'ta-IN':['சோபா cleaning வேண்டாம், ஆனால் kitchen cleaning வேணும். விவரமா சொல்லுங்க.','Basic service வேண்டாம், ஆனால் puncture repair வேணும். உதவ முடியுமா?','Job guarantee வேண்டாம், ஆனால் spoken English கத்துக்க ஆர்வம் இருக்கு. Course சொல்லுங்க.'],
'kn-IN':['ಸೋಫಾ cleaning ಬೇಡ, ಆದರೆ kitchen cleaning ಬೇಕು. ವಿವರಿಸಿ.','Basic service ಬೇಡ, ಆದರೆ puncture repair ಬೇಕು. ಸಹಾಯ ಮಾಡುತ್ತೀರಾ?','Job guarantee ಬೇಡ, ಆದರೆ spoken English ಕಲಿಯಲು ಆಸಕ್ತಿ ಇದೆ. Course ವಿವರಿಸಿ.']}
DETAIL_PREFIX={'te-IN':'ಇಲ್ಲ','hi-IN':'अभी कुछ book या save मत कीजिए। पहले मेरा सवाल बताइए: ','ta-IN':'இப்போ எதையும் book அல்லது save செய்யாதீங்க. முதலில் என் கேள்விக்கு பதில் சொல்லுங்க: ','kn-IN':'ಈಗ ಏನನ್ನೂ book ಅಥವಾ save ಮಾಡಬೇಡಿ. ಮೊದಲು ನನ್ನ ಪ್ರಶ್ನೆಗೆ ಉತ್ತರಿಸಿ: '}
DETAIL_PREFIX['te-IN']='ఇప్పుడే ఏదీ book లేదా save చేయకండి. ముందు నా ప్రశ్నకు సమాధానం చెప్పండి: '
def write_corpora():
 original=OUT.parent/'multilingual-standard-audit-20261025'/'corpus'
 for lang in a.BASE['resolved_stacks']:
  common=json.loads((original/(lang+'.json')).read_text(encoding='utf-8'))['print'];rows={}
  for i,b in enumerate(BRIEFS):
   c=copy.deepcopy(common)
   c['details']=(DETAIL_PREFIX[lang]+QUESTIONS[lang][i]) if lang in QUESTIONS else 'Do not book or save anything yet. Answer this first: '+b['question']
   c['alternate']=ALTERNATES[lang][i] if lang in ALTERNATES else b['alternate']
   request=['kitchen cleaning in Baner, Pune','puncture repair in Adyar, Chennai','adult spoken-English course demo enquiry'][i]
   # Fully specified request, ordinary English mixing is supported by every selected pack.
   suffix={'te-IN':'ఈ enquiry ని team review కోసం submit చేయండి. నా సమ్మతి ఉంది. Booking లేదా order confirm అయిందని చెప్పకండి.','hi-IN':'यह enquiry team review के लिए submit कीजिए। मेरी सहमति है। Booking या order confirm मत बताइए।','ta-IN':'இந்த enquiry-யை team reviewக்கு submit செய்யுங்க. என் சம்மதம் இருக்கு. Booking அல்லது order confirmன்னு சொல்லாதீங்க.','kn-IN':'ಈ enquiry team reviewಗೆ submit ಮಾಡಿ. ನನ್ನ ಒಪ್ಪಿಗೆ ಇದೆ. Booking ಅಥವಾ order confirm ಅಂತ ಹೇಳಬೇಡಿ.'}.get(lang,'Please submit this enquiry for team review. I consent. Do not claim a booking or order is confirmed.')
   c['request']=f'My name is Audit Customer, email audit.customer@example.invalid. I want {request}; preferred review time tomorrow at 3pm. '+suffix
   rows[b['key']]=c
  a.dump(OUT/'corpus'/(lang+'.json'),rows)

def instrument(settings):
 Voice=a.install_runtime_instrumentation(settings)
 from server.providers import get_provider_registry
 adapter=get_provider_registry().get_llm(a.BASE['standard']['profile']['llm']['provider'])
 original_live=adapter.stream_live_turn
 limiter=asyncio.Lock();last_start=0.0
 async def observed_live(*args,**kwargs):
  nonlocal last_start
  # Conversation semantics, not a load test. Keep this single client's live
  # traffic below a bursty provider quota; do not retry failed cases invisibly.
  async with limiter:
   await asyncio.sleep(max(0,1.1-(time.monotonic()-last_start)))
   last_start=time.monotonic()
  c=a.ACTIVE.get();r={'kind':'native_selection','max_output_tokens':kwargs.get('max_output_tokens'),'reasoning_effort':kwargs.get('reasoning_effort'),'tools':[x.get('name') for x in kwargs.get('tools',[])],'tool_choice':kwargs.get('tool_choice')};t=time.monotonic()
  if c is not None:c['requests'].append(r)
  try:
   async for event in original_live(*args,**kwargs):
    if event.get('done'):r['result']=event
    yield event
  except BaseException as ex:r['error_type']=type(ex).__name__;r['finish_reason']=getattr(ex,'finish_reason',None);raise
  finally:r['elapsed_s']=round(time.monotonic()-t,3)
 adapter.stream_live_turn=observed_live
 previous_body=adapter._request_body
 def body(*args,**kwargs):
  value=previous_body(*args,**kwargs);c=a.ACTIVE.get()
  if c and c['requests']:
   schema=((value.get('response_format') or {}).get('json_schema') or {}).get('schema') or {}
   c['requests'][-1]['schema_properties']=list(schema.get('properties',{}))
  return value
 adapter._request_body=body
 from server.services.tool_router import tool_router
 execute=tool_router.route_and_execute
 async def failure_boundary(**kwargs):
  c=a.ACTIVE.get();scenario=c['scenario'] if c else ''
  if scenario in {'7_integration_timeout','8_integration_denied'}:
   assert c['integration'] and kwargs['tenant_id']==a.TENANT and kwargs['agent_id']==c['agent_id']
   c['tool_calls'].append({'name':kwargs['tool_name'],'arguments':kwargs['arguments'],'turn':c['turn'],'mode':scenario})
   if scenario=='7_integration_timeout':raise TimeoutError('Simulated uncertain CRM outcome')
   return {'status':'error','message':'The synthetic integration denied this write.'}
  return await execute(**kwargs)
 tool_router.route_and_execute=failure_boundary
 return Voice

async def main(args):
 if args.capture:await capture();return
 settings,app=a.setup();write_corpora()
 import httpx
 langs=args.languages.split(',') if args.languages else list(a.BASE['languages'])
 businesses=[b for b in BRIEFS if not args.businesses or b['key'] in args.businesses.split(',')]
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost',timeout=180) as client:
  response=await client.get('/api/app/agents/languages');a.dump(OUT/'language-contract.json',{'status':response.status_code,'body':response.json()})
  builds=await asyncio.gather(*(a.build_agent(client,b,lang) for lang in langs for b in businesses))
 a.dump(OUT/'build-index.json',builds)
 if args.build_only:return
 Voice=instrument(settings)
 signature=hashlib.sha256(''.join(hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'server').rglob('*.py')) if 'tests' not in f.parts).encode()).hexdigest()
 async def run(b,connected,scenario):
  async with a.SEM:
   key=f"{b['business']}-{b['language']}-{'connected' if connected else 'none'}-{scenario}"
   saved=OUT/'sessions'/(key+'.json')
   if saved.exists():
    prior=json.loads(saved.read_text(encoding='utf-8'))
    if prior.get('source_signature')!=signature:
     archive=OUT/'sessions-before-runtime-change';archive.mkdir(exist_ok=True)
     saved.replace(archive/(str(time.time_ns())+'-'+saved.name))
   corpus=json.loads((OUT/'corpus'/(b['language']+'.json')).read_text(encoding='utf-8'))
   r=await a.run_session(b,corpus,connected,scenario,Voice)
   r['source_signature']=signature;a.dump(saved,r)
   return {'key':r['key'],'status':r['status'],'turns':len(r['turns'])}
 scenarios=args.scenarios.split(',') if args.scenarios else list(a.SCENARIOS)
 if args.case_keys:
  a.SCENARIOS.update({'7_integration_timeout':['request','done'],'8_integration_denied':['request','done']})
  scenarios=list(a.SCENARIOS)
 if args.failure_cases:
  a.SCENARIOS.update({'7_integration_timeout':['request','done'],'8_integration_denied':['request','done']})
  scenarios=['7_integration_timeout','8_integration_denied']
 states=[True] if args.failure_cases else ([False] if args.integration=='absent' else ([True] if args.integration=='present' else [False,True]))
 keys=set(json.loads(Path(args.case_keys).read_text(encoding='utf-8'))) if args.case_keys else None
 tasks=[run(b,c,s) for b in builds if b.get('status')=='ready' and b['language'] in a.BASE['resolved_stacks'] for c in states for s in scenarios if keys is None or f"{b['business']}-{b['language']}-{'connected' if c else 'none'}-{s}" in keys]
 results=await asyncio.gather(*tasks);a.dump(OUT/'execution-index.json',results)
 print(json.dumps({'finished':len(results)}),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--capture',action='store_true');parser.add_argument('--build-only',action='store_true');parser.add_argument('--languages');parser.add_argument('--businesses');parser.add_argument('--scenarios');parser.add_argument('--failure-cases',action='store_true');parser.add_argument('--integration',choices=['absent','present']);parser.add_argument('--case-keys')
 asyncio.run(main(parser.parse_args()))
