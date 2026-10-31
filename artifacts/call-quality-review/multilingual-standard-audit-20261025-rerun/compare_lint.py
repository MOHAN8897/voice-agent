"""Compare lint to the preserved initial dirty tree without changing that tree."""
import json,re,subprocess
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
patch=(P/'initial-working-tree.patch').read_text(encoding='utf-8')
sections={}
for piece in re.split(r'(?=^diff --git )',patch,flags=re.M):
 match=re.match(r'diff --git a/(.+) b/(.+)\n',piece)
 if match:sections[match[2]]=piece
files=['server/call/live_turn_orchestrator.py','server/providers/sarvam_llm.py','server/brain/employee_script_pipeline.py','server/tests/test_composed_action_protocol.py','server/tests/test_sarvam_composed_transport.py','server/tests/test_close_speech_gate.py','server/tests/test_employee_script_pipeline.py']
records=[]
for file in files:
 baseline=subprocess.run(['git','show','HEAD:'+file],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if baseline.returncode:
  final=subprocess.run(['python','-m','ruff','check',file,'--output-format','json'],cwd=ROOT,stdout=subprocess.PIPE)
  clean=json.loads(final.stdout)
  assert not clean,(file,'untracked initial contents unavailable; final lint has findings')
  records.append({'file':file,'before':0,'after':0,'introduced':[],'resolved':[],'baseline_note':'Pre-existing untracked file; initial content not snapshotted, final lint clean'})
  continue
 old=baseline.stdout.decode('utf-8').splitlines(keepends=True)
 lines=sections.get(file,'').splitlines(keepends=True);out=[];cursor=0;i=0
 while i<len(lines):
  h=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',lines[i])
  if not h:i+=1;continue
  start=int(h[1])-1;out.extend(old[cursor:start]);cursor=start;i+=1
  while i<len(lines) and not lines[i].startswith(('@@ ','diff --git ')):
   row=lines[i];prefix=row[:1];body=row[1:]
   if prefix in {' ','-'}:
    assert old[cursor].rstrip('\r\n')==body.rstrip('\r\n'),(file,cursor)
    cursor+=1
   if prefix in {' ','+'}:out.append(body)
   i+=1
 out.extend(old[cursor:]);before=''.join(out)
 def lint(text):
  r=subprocess.run(['python','-m','ruff','check','--stdin-filename',file,'-','--output-format','json'],input=text.encode('utf-8'),stdout=subprocess.PIPE,cwd=ROOT)
  return json.loads(r.stdout)
 pre=lint(before);current=(ROOT/file).read_text(encoding='utf-8');post=lint(current)
 def keys(items,text):
  source=text.splitlines();return {(x['code'],x['message'],source[x['location']['row']-1].strip()) for x in items}
 records.append({'file':file,'before':len(pre),'after':len(post),'introduced':sorted(keys(post,current)-keys(pre,before)),'resolved':sorted(keys(pre,before)-keys(post,current))})
(P/'lint-comparison.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps({'before':sum(r['before'] for r in records),'after':sum(r['after'] for r in records),'introduced':sum(len(r['introduced']) for r in records),'resolved':sum(len(r['resolved']) for r in records)}))
