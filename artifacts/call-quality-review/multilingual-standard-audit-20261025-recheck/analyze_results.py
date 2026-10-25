"""Grade observed audit behavior, not harness completion labels."""
import collections
import hashlib
import json
from pathlib import Path
import statistics

P = Path(__file__).resolve().parent
ROOT = P.parents[2]
SS = sorted((json.loads(f.read_text(encoding='utf-8')) for f in (P/'sessions').glob('*.json')), key=lambda x:x['key'])
GENERIC = {'en-IN':'Of course — please go ahead.', 'te-IN':'తప్పకుండా, చెప్పండి.', 'hi-IN':'ज़रूर, बताइए।', 'ta-IN':'கண்டிப்பாக, சொல்லுங்கள்.', 'kn-IN':'ಖಂಡಿತ, ಹೇಳಿ.'}
TECH = {'en-IN':'Sorry, we are facing a technical problem.', 'te-IN':'క్షమించండి, మాకు ఒక సాంకేతిక సమస్య', 'hi-IN':'क्षमा करें, हमें एक तकनीकी समस्या', 'ta-IN':'மன்னிக்கவும், எங்களுக்கு ஒரு தொழில்நுட்பச் சிக்கல்', 'kn-IN':'ಕ್ಷಮಿಸಿ, ನಮಗೆ ಒಂದು ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆ'}
SC = {'1_interested':5,'2_future_interest':3,'3_complete_rejection':1,'4_abuse':2,'5_diversion_danger':5,'6_hangup':4,'1b_direct_tool_request':2,'3b_stop_contact':1,'5b_direct_danger':3}
END = {'done','reject','optout','abuse_threat'}
def stats(ss):
    turns=[t for s in ss for t in s['turns']]
    req=[r for s in ss for r in s['requests']]
    results=[r['result'] for r in req if r.get('result',{}).get('done')]
    gates=[g for s in ss for g in s.get('close_gates',[])]
    generic=[(s,t) for s in ss for t in s['turns'] if t['spoken']==GENERIC[s['language']]]
    tech=[(s,t) for s in ss for t in s['turns'] if t['spoken'].startswith(TECH[s['language']])]
    missed=[(s,t) for s in ss for t in s['turns'] if t['caller_key'] in END and not t['server_closed']]
    closure=[(s,t) for s in ss for t in s['turns'] if t['server_closed'] and t['caller_key'] not in END]
    ordinary=[(s,t) for s in ss for t in s['turns'] if t['caller_key'] in {'interested','details','alternate','future','future_more','abuse_mild','divert','return','ack','request'}]
    whitespace=[r for r in req if r.get('sse_content_chars',0)>1000 and len(r.get('sse_content_tail','').strip())==0]
    return {
      'sessions':len(ss),'harness_completed':sum(s['status']=='completed' for s in ss),'planned_caller_turns':sum(SC[s['scenario']] for s in ss),
      'reached_caller_turns':len(turns),'live_llm_requests':len(req),'raw_completed_model_outputs':len(results),
      'model_close_proposals':sum(bool(r.get('end_call',{}).get('should_end')) for r in results),
      'model_do_not_call_proposals':sum(r.get('end_call',{}).get('contact_preference')=='do_not_call' for r in results),
      'generic_continuation_turns':len(generic),'technical_farewell_turns':len(tech),
      'ended_sessions':sum(bool(s['carrier']) for s in ss),'sessions_left_open':sum(not s['carrier'] for s in ss),
      'closed_on_nonterminal_test_turn':len(closure),'ordinary_enquiry_turns':len(ordinary),
      'ordinary_enquiry_generic_turns':sum(t['spoken']==GENERIC[s['language']] for s,t in ordinary),
      'ordinary_enquiry_technical_turns':sum(t['spoken'].startswith(TECH[s['language']]) for s,t in ordinary),
      'explicit_end_turns_reached':sum(t['caller_key'] in END for t in turns),'explicit_end_not_closed':len(missed),
      'model_native_tool_call_chunks':sum(bool(r.get('result',{}).get('tool_calls')) for r in req),
      'mock_integration_executions':sum(len(s['tool_calls']) for s in ss),
      'provider_hangup_attempts':sum(len(s['carrier']) for s in ss),
      'hangup_while_mock_playback_active':sum(bool(c['playback_active']) for s in ss for c in s['carrier']),
      'duplicate_hangup_sessions':sum(len(s['carrier'])>1 for s in ss),
      'finish_reasons':dict(collections.Counter(r.get('sse_finish',r.get('result',{}).get('finish_reason',r.get('finish_reason'))) for r in req)),
      'length_errors':sum(r.get('error_type')=='IncompleteTurnError' for r in req),
      'stream_cancelled_requests':sum(r.get('error_type')=='CancelledError' for r in req),
      'observed_long_whitespace_tail_requests':len(whitespace),
      'close_gate_results_instrumented_subset':dict(collections.Counter(g['server_result'].get('reject_code') or ('accepted' if g['server_result'].get('should_end') else 'continue') for g in gates)),
      'caller_turn_latency_median_s':round(statistics.median(t['elapsed_s'] for t in turns),3),
      'caller_turn_latency_p95_s':round(sorted(t['elapsed_s'] for t in turns)[int((len(turns)-1)*.95)],3),
      'technical_case_keys':[s['key'] for s,t in tech],
      'missed_end_case_turns':[(s['key'],t['index'],t['caller_key']) for s,t in missed],
      'nonterminal_close_case_turns':[(s['key'],t['index'],t['caller_key']) for s,t in closure],
    }

metrics={'overall':stats(SS),'by_language':{},'by_scenario':{},'by_business':{},'by_integration':{}}
for field,key in [('language','by_language'),('scenario','by_scenario'),('business','by_business'),('integration','by_integration')]:
    for value in sorted({s[field] for s in SS},key=str):metrics[key][str(value)]=stats([s for s in SS if s[field]==value])
metrics['request_budgets']=dict(collections.Counter(str(r['max_output_tokens']) for s in SS for r in s['requests']))
metrics['serialized_requests']=sum('serialized' in r for s in SS for r in s['requests'])
metrics['serialized_reasoning_values']=dict(collections.Counter(str(r['serialized'].get('reasoning_effort')) for s in SS for r in s['requests'] if 'serialized' in r))
metrics['model_error_note']='GeneratorExit after a done chunk is consumer closure, not a model failure. Cancelled requests can be the watchdog recovery; count final technical farewells separately.'
builds=[json.loads(f.read_text(encoding='utf-8')) for f in (P/'agents').glob('*/build.json')]
metrics['builds']={'count':len(builds),'statuses':dict(collections.Counter(b['status'] for b in builds)),'prompt_chars':{s['business']+'-'+s['language']:s['prompt_chars'] for s in SS},'generation_failed_attempts':[]}
for f in (P/'agents').glob('*/previous-attempt*.json'):
    b=json.loads(f.read_text(encoding='utf-8'))
    metrics['builds']['generation_failed_attempts'].append({'file':str(f.relative_to(P)),'status':b.get('http_status'),'business':b.get('business'),'language':b.get('language'),'response':b.get('response')})
base=json.loads((P/'baseline.json').read_text(encoding='utf-8'))
metrics['source_drift']={}
for f in P.glob('run-source-*.json'):
    data=json.loads(f.read_text(encoding='utf-8'))
    delta={k:{'baseline':v,'run':data.get(k)} for k,v in base['source_hashes'].items() if data.get(k)!=v}
    if delta:metrics['source_drift'][f.name]=delta
metrics['source_drift_current']={k:{'baseline':v,'current':hashlib.sha256((ROOT/k).read_bytes()).hexdigest() if (ROOT/k).exists() else None} for k,v in base['source_hashes'].items() if not (ROOT/k).exists() or hashlib.sha256((ROOT/k).read_bytes()).hexdigest()!=v}
(P/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
for lang in sorted(metrics['by_language']):
    lines=[f'# {lang}: observed session transcripts','', 'These are real model outputs through the actual server pipeline with mocked speech/carrier boundaries. “Completed” describes harness execution, not quality. Full raw requests, rejected model speech, decisions, checksums and gates are in the linked JSON files.','']
    for s in [s for s in SS if s['language']==lang]:
        lines += [f"## {s['key']}",'',f"Integration offered: {s['integration']}. Compiled version checksum: `{s['compiled_checksum']}`.",f"[Raw evidence]({(P/'sessions'/(s['key']+'.json')).as_posix()})",'']
        offset=0
        for t in s['turns']:
            lines += [f"### Turn {t['index']}: {t['caller_key']}",'',f"Caller: {t['user']}",'',f"Agent sent to mocked TTS: {t['spoken'] or '[no speech]'}",'',f"Server closed: {t['server_closed']}; phase: {t['phase']}; model requests: {t['requests']}; latency: {t['elapsed_s']} seconds.",'']
            requests=s['requests'][offset:offset+t['requests']];offset+=t['requests']
            for r in requests:
                if r.get('result',{}).get('done'):
                    lines += [f"Model speech before server gate: {r['result'].get('text','')}",'',f"Model end proposal: `{json.dumps(r['result'].get('end_call',{}),ensure_ascii=False)}`",'']
            for g in s.get('close_gates',[]):
                if g['turn']==t['index']:lines += [f"Server gate: `{json.dumps(g['server_result'],ensure_ascii=False)}`",'']
    (P/f'transcripts-{lang}.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({k:v for k,v in metrics['overall'].items() if not isinstance(v,list)},ensure_ascii=False,indent=2))
print('source_drift',len(metrics['source_drift']),len(metrics['source_drift_current']))
