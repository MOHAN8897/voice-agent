"""Measure current-source cases; never count harness completion as quality."""
import collections,hashlib,json,re,statistics,sys
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[2];sys.path.insert(0,str(ROOT))
from server.call.action_proof import action_unconfirmed_line_for,unproven_claim,replace_unavailable_action_promises,unavailable_action_line_for,caller_requests_external_submission
from server.brain.capabilities import order_confirmation_allowed
SC={'1_interested':5,'2_future_interest':3,'3_complete_rejection':1,'4_abuse':2,'5_diversion_danger':5,'6_hangup':4,'1b_direct_tool_request':2,'3b_stop_contact':1,'5b_direct_danger':3,'7_integration_timeout':2,'8_integration_denied':2}
GENERIC={'en-IN':'Of course — please go ahead.','te-IN':'తప్పకుండా, చెప్పండి.','hi-IN':'ज़रूर, बताइए।','ta-IN':'கண்டிப்பாக, சொல்லுங்கள்.','kn-IN':'ಖಂಡಿತ, ಹೇಳಿ.'}
TECH={'en-IN':'Sorry, we are facing a technical problem.','te-IN':'క్షమించండి, మాకు ఒక సాంకేతిక సమస్య','hi-IN':'क्षमा करें, हमें एक तकनीकी समस्या','ta-IN':'மன்னிக்கவும், எங்களுக்கு ஒரு தொழில்நுட்பச் சிக்கல்','kn-IN':'ಕ್ಷಮಿಸಿ, ನಮಗೆ ಒಂದು ತಾಂತ್ರಿಕ ಸಮಸ್ಯೆ'}
END={'done','reject','optout','abuse_threat'}
SIGNATURE=hashlib.sha256(''.join(hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'server').rglob('*.py')) if 'tests' not in f.parts).encode()).hexdigest()
all_cases=[json.loads(f.read_text(encoding='utf-8')) for f in sorted((P/'sessions').glob('*.json'))]
unaffected=json.loads((P/'unaffected-case-evidence.json').read_text(encoding='utf-8'))['cases']
approved={(x['key'],x['source_signature'],x['compiled_checksum'],x['case_sha256']) for x in unaffected}
SS=[s for s in all_cases if s.get('source_signature')==SIGNATURE or (s['key'],s.get('source_signature'),s['compiled_checksum'],hashlib.sha256((P/'sessions'/(s['key']+'.json')).read_bytes()).hexdigest()) in approved]
def stats(ss):
 turns=[(s,t) for s in ss for t in s['turns']];requests=[r for s in ss for r in s['requests']]
 explicit=[(s,t) for s,t in turns if t['caller_key'] in END]
 early=[(s,t) for s,t in turns if t['server_closed'] and t['caller_key'] not in END]
 technical=[(s,t) for s,t in turns if t['spoken'].startswith(TECH[s['language']])]
 generic=[(s,t) for s,t in turns if t['spoken']==GENERIC[s['language']]]
 issues=[]
 for s,t in turns:
  proofs={'enquiry_saved'} if s['integration'] and any(c['turn']<=t['index'] and not c.get('mode') for c in s['tool_calls']) else set()
  problem=unproven_claim(t['spoken'],proofs)
  if problem:issues.append({'case':s['key'],'turn':t['index'],'claim':problem,'spoken':t['spoken']})
 return {'sessions':len(ss),'harness_errors':[s['key'] for s in ss if s['status']!='completed'],'planned_turns':sum(SC[s['scenario']] for s in ss),'reached_turns':len(turns),'requests':len(requests),'technical_farewells':len(technical),'generic_continuations':len(generic),'unconfirmed_replacements':sum(t['spoken']==action_unconfirmed_line_for(s['language']) for s,t in turns),'empty_responses':sum(not t['spoken'].strip() for s,t in turns),'explicit_ends':len(explicit),'missed_explicit_ends':[{'case':s['key'],'turn':t['index']} for s,t in explicit if not t['server_closed']],'early_closes':[{'case':s['key'],'turn':t['index'],'caller_key':t['caller_key'],'spoken':t['spoken']} for s,t in early],'ended_sessions':sum(bool(s['carrier']) for s in ss),'duplicate_hangups':sum(len(s['carrier'])>1 for s in ss),'hangup_during_playback':sum(c['playback_active'] for s in ss for c in s['carrier']),'integration_attempts':sum(len(s['tool_calls']) for s in ss),'connected_sessions_with_attempt':sum(bool(s['tool_calls']) and s['integration'] for s in ss),'integration_request_turns_reached':sum(s['integration'] and t['caller_key']=='request' for s,t in turns),'integration_request_turns_without_attempt':[s['key'] for s,t in turns if s['integration'] and t['caller_key']=='request' and not any(c['turn']==t['index'] for c in s['tool_calls'])],'unproven_spoken_claim_flags':issues,'unavailable_promise_flags':[{'case':s['key'],'turn':t['index'],'spoken':t['spoken']} for s,t in turns if not s['integration'] and replace_unavailable_action_promises(t['spoken'],s['language'])!=t['spoken']],'raw_control_speech':[{'case':s['key'],'turn':t['index']} for s,t in turns if re.search(r'"(?:end_call|spoken_response|memory_update)"\s*:',t['spoken'])],'provider_errors':dict(collections.Counter(r.get('error_type') for r in requests if r.get('error_type') not in {None,'GeneratorExit'})),'finish_reasons':dict(collections.Counter(r.get('sse_finish') or r.get('result',{}).get('finish_reason') or r.get('finish_reason') or 'unobserved' for r in requests)),'p95_server_turn_s':round(sorted(t['elapsed_s'] for s,t in turns)[int((len(turns)-1)*.95)],3) if turns else None,'median_server_turn_s':round(statistics.median(t['elapsed_s'] for s,t in turns),3) if turns else None}

builds=[json.loads(f.read_text(encoding='utf-8')) for f in (P/'agents').glob('*/build.json')]
m={'source_signature':SIGNATURE,'source_provenance':dict(collections.Counter(s.get('source_signature') for s in SS)),'final_source_live_cases':sum(s.get('source_signature')==SIGNATURE for s in SS),'unaffected_retained_cases':sum(s.get('source_signature')!=SIGNATURE for s in SS),'stale_case_files_excluded':len(all_cases)-len(SS),'overall':stats(SS),'by_language':{},'by_business':{},'by_scenario':{},'builds':{'ready':[b['business']+'-'+b['language'] for b in builds if b['status']=='ready'],'blocked_or_failed':[{k:b.get(k) for k in ['business','language','http_status','response']} for b in builds if b['status']!='ready']},'brain_checks':[]}
for field,key in [('language','by_language'),('business','by_business'),('scenario','by_scenario')]:
 for val in sorted({s[field] for s in SS}):m[key][val]=stats([s for s in SS if s[field]==val])
for b in builds:
 if b['status']!='ready':continue
 script=b['compiled'];m['brain_checks'].append({'key':b['business']+'-'+b['language'],'checksum':b['checksum'],'selected_packs':re.findall(r'--- SPOKEN LANGUAGE \(([^)]+)\) ---',script),'order_capability':order_confirmation_allowed(script),'obsolete_price_present':bool(re.search(r'(?<!\d)(?:1299|5499)(?!\d)',script)),'checksum_bound_sessions':sum(s['compiled_checksum']==b['checksum'] for s in SS if s['business']==b['business'] and s['language']==b['language'])})
(P/'metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
requests=[r for s in SS for r in s['requests']]
m['request_budget_checks']={
 'observed_prompt_token_peak':max((int((r.get('sse_usage') or {}).get('prompt_tokens') or 0) for r in requests),default=0),
 'observed_output_token_peak':max((int((r.get('sse_usage') or {}).get('completion_tokens') or 0) for r in requests),default=0),
 'requested_output_limits':sorted({r.get('max_output_tokens') for r in requests if r.get('max_output_tokens')}),
 'non_request_warning_replies':[{'case':s['key'],'turn':t['index']} for s in SS for t in s['turns'] if t['caller_key']!='request' and t['spoken']==action_unconfirmed_line_for(s['language'])],
 'successful_mock_writes':sum(not c.get('mode') for s in SS for c in s['tool_calls']),
 'failed_mock_write_probes':sum(bool(c.get('mode')) for s in SS for c in s['tool_calls']),
 'saved_reference_not_delivered':[s['key'] for s in SS for t in s['turns'] if any(c['turn']==t['index'] and not c.get('mode') for c in s['tool_calls']) and 'AUDIT-ENQUIRY-1' not in t['spoken']],
 'failed_write_promise_flags':[{'case':s['key'],'turn':t['index'],'spoken':t['spoken']} for s in SS for t in s['turns'] if any(c['turn']==t['index'] and c.get('mode') for c in s['tool_calls']) and replace_unavailable_action_promises(t['spoken'],s['language'],unconfirmed=True)!=t['spoken']],
 'missing_unavailable_request_boundary':[{'case':s['key'],'turn':t['index']} for s in SS for t in s['turns'] if not s['integration'] and caller_requests_external_submission(t['user']) and unavailable_action_line_for(s['language']) not in t['spoken']],
}
(P/'metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
for lang in m['by_language']:
 lines=[f'# {lang} — verified transcripts','',f'Final application signature: `{SIGNATURE}`. Cases unaffected by the final action-guard patch retain their original executed source signature and content hashes. This uses impact-based retention, not restamping every case as a new live run. Real Standard model; TTS/carrier and CRM boundaries mocked.','']
 for s in [s for s in SS if s['language']==lang]:
  lines += ['## '+s['key'],'',f"Executed source signature: `{s.get('source_signature')}`.",f"[Raw model, tool and close evidence](<{(P/'sessions'/(s['key']+'.json')).as_posix()}>)",'']
  for t in s['turns']:lines += [f"### {t['index']}: {t['caller_key']}",'','Caller: '+t['user'],'','Agent sent to mocked TTS: '+t['spoken'],'',f"Closed: {t['server_closed']}; model requests: {t['requests']}; server elapsed: {t['elapsed_s']}s.",'']
 (P/f'transcripts-{lang}.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({k:v for k,v in m['overall'].items() if not isinstance(v,(list,dict))},ensure_ascii=True))
print('flags',json.dumps({k:v for k,v in m['overall'].items() if isinstance(v,list)},ensure_ascii=True)[:3000])
