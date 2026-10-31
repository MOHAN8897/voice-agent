import json,sys
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parents[2]))
from server.call.action_proof import action_unconfirmed_line_for,unproven_claim
for f in sorted((P/'sessions').glob('*.json')):
 s=json.loads(f.read_text(encoding='utf-8'))
 for t in s['turns']:
  if t['spoken']!=action_unconfirmed_line_for(s['language']):continue
  gates=[g for g in s['close_gates'] if g['turn']==t['index']]
  raw=gates[-1]['spoken_text'] if gates else ''
  proofs={'enquiry_saved'} if any(c['turn']==t['index'] and not c.get('mode') for c in s['tool_calls']) else set()
  print(json.dumps({'case':s['key'],'turn':t['index'],'caller':t['caller_key'],'raw':raw,'proofs':list(proofs),'claim':unproven_claim(raw,proofs)},ensure_ascii=False))
