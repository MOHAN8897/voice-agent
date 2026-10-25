"""Preserve live-run provenance and select cases affected by the final guard fix."""
import hashlib,json,sys
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parents[2]))
from server.call.action_proof import replace_unavailable_action_promises,replace_unproven_claims,unavailable_action_line_for,caller_requests_external_submission
selected=[];unchanged=[];differences=[]
for f in sorted((P/'sessions').glob('*.json')):
 s=json.loads(f.read_text(encoding='utf-8'));changes=[]
 for t in s['turns']:
  if t['server_closed']:continue
  gates=[g for g in s['close_gates'] if g['turn']==t['index']]
  if not gates:changes.append({'turn':t['index'],'reason':'missing raw gate evidence'});continue
  raw=gates[-1]['spoken_text'];new=raw
  unconfirmed=any(c['turn']==t['index'] and c.get('mode') for c in s['tool_calls'])
  if not s['integration'] or unconfirmed:
   new=replace_unavailable_action_promises(new,s['language'],unconfirmed=unconfirmed,requested_unavailable=not s['integration'] and caller_requests_external_submission(t['user']))
  proofs={'enquiry_saved'} if any(c['turn']==t['index'] and not c.get('mode') for c in s['tool_calls']) else set()
  new=replace_unproven_claims(new,proofs,s['language'],warning_line=unavailable_action_line_for(s['language']) if not s['integration'] else None)
  if new!=t['spoken']:changes.append({'turn':t['index'],'raw':raw,'before':t['spoken'],'after':new})
 # All failed gateway cases also verify newly propagated outcome metadata.
 affected=bool(changes) or s['scenario'].startswith(('7_','8_'))
 record={k:s[k] for k in ('key','source_signature','compiled_checksum')}
 record['case_sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
 if affected:selected.append(s['key']);differences.append({'case':s['key'],'changes':changes})
 else:unchanged.append(record)
for name in ('guard-impact-review.json','final-guard-retest-keys.json','unaffected-case-evidence.json'):
 previous=P/name
 if previous.exists():(P/('previous-'+name)).write_bytes(previous.read_bytes())
(P/'final-guard-retest-keys.json').write_text(json.dumps(selected,indent=2),encoding='utf-8')
(P/'guard-impact-review.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2),encoding='utf-8')
(P/'unaffected-case-evidence.json').write_text(json.dumps({'method':'Impact-based retention: every non-close raw reply was passed through the final action guards; exact delivered-text equality required. All failed gateway cases selected regardless. Other generation, transport, speech and close code unchanged by this final patch. Original source signatures and case hashes retained; this is not a fresh final-source live execution.','cases':unchanged},indent=2),encoding='utf-8')
print(json.dumps({'retest_cases':len(selected),'unchanged_cases':len(unchanged),'changed_turns':sum(len(x['changes']) for x in differences)}))
