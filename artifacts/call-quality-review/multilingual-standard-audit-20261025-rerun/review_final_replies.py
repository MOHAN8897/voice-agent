import json
from pathlib import Path
P=Path(__file__).resolve().parent
rows=[]
for f in sorted((P/'sessions').glob('*.json')):
 s=json.loads(f.read_text(encoding='utf-8'))
 for t in s['turns']:
  if (t['caller_key']=='request' and (s['scenario'].startswith(('7_','8_')) or s['scenario']=='1b_direct_tool_request' and not s['integration'])) or (s['business']=='language' and t['caller_key'] in {'future','abuse_mild','danger'}):
   rows.append({'case':s['key'],'caller':t['caller_key'],'speech':t['spoken'],'closed':t['server_closed']})
(P/'manual-review-replies.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for x in rows:
 if x['caller']=='request':print(json.dumps(x,ensure_ascii=False))
