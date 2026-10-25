"""Finish the main and integration-failure matrices sequentially, one client."""
import json,subprocess,sys
from pathlib import Path
p=Path(__file__).resolve().parent
base=[sys.executable,str(p/'run_fresh.py'),'--languages','en-IN,te-IN,hi-IN,ta-IN,kn-IN']
for name,extra in [('matrix-complete',[]),('integration-failures',['--failure-cases'])]:
 print(json.dumps({'phase':name,'status':'started'}),flush=True)
 with (p/(name+'.log')).open('w',encoding='utf-8') as log:
  result=subprocess.run(base+extra,stdout=log,stderr=subprocess.STDOUT,cwd=p.parents[2])
 print(json.dumps({'phase':name,'exit_code':result.returncode}),flush=True)
 if result.returncode:sys.exit(result.returncode)
