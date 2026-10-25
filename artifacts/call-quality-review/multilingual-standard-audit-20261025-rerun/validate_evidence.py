"""Fail the handover if measured coverage/provenance contradicts the report."""
import hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
def read(name):return json.loads((P/name).read_text(encoding='utf-8'))
m=read('metrics.json');o=m['overall'];done=read('completion.json');frozen=read('frozen-source.json')
assert o['sessions']==300 and o['reached_turns']==o['planned_turns']==840
assert all(x['sessions']==60 for x in m['by_language'].values())
assert len(m['by_language'])==5 and len(m['builds']['ready'])==15
assert sum(m['source_provenance'].values())==300 and m['stale_case_files_excluded']==0
assert m['final_source_live_cases']+m['unaffected_retained_cases']==300
for field in ('technical_farewells','generic_continuations','empty_responses','duplicate_hangups','hangup_during_playback'):
 assert o[field]==0,(field,o[field])
for field,value in o.items():
 if isinstance(value,list):assert not value,(field,value)
for field in ('non_request_warning_replies','saved_reference_not_delivered','failed_write_promise_flags','missing_unavailable_request_boundary'):
 assert not m['request_budget_checks'][field],(field,m['request_budget_checks'][field])
assert m['request_budget_checks']['successful_mock_writes']==m['request_budget_checks']['failed_mock_write_probes']==30
for b in m['brain_checks']:
 assert b['selected_packs']==[b['key'].rsplit('-',2)[1]+'-'+b['key'].rsplit('-',2)[2]]
 assert b['order_capability'] is False and b['checksum_bound_sessions']==20
assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in frozen.items())
assert not done['source_drift'] and done['verdict']=='PASS for the recorded scope'
assert len(read('audio-smoke.json'))==5 and all(x['status']=='passed' for x in read('audio-smoke.json'))
assert len(read('handshake-results.json'))==20 and all(x['pass'] for x in read('handshake-results.json'))
assert '404 passed' in (P/'all-regression-final.log').read_text(encoding='utf-8-sig')
report=(P/'VERIFICATION.md').read_text(encoding='utf-8');missing=[]
for path in re.findall(r'\]\(<([^>]+)>\)',report):
 clean=re.sub(r':\d+$','',path)
 if not Path(clean).exists():missing.append(path)
assert not missing,missing
evidence={'status':'passed','unique_live_cases':300,'caller_turns':840,'final_source_live_cases':m['final_source_live_cases'],'impact_retained_cases':m['unaffected_retained_cases'],'regression_tests':404,'audio_smokes':5,'close_handshakes':20,'report_links_checked':len(re.findall(r'\]\(<([^>]+)>\)',report)),'source_drift':0}
(P/'evidence-validation.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence))
