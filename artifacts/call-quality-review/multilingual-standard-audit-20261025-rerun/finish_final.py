"""One live-model process at a time, followed by deterministic close checks."""
import subprocess,sys
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
steps=[
 ('run_fresh.py',['--languages','en-IN,te-IN,hi-IN,ta-IN,kn-IN','--case-keys',str(P/'final-guard-retest-keys.json')],'matrix-final-submission.log'),
 ('audio_smoke.py',[],'audio-smoke.log'),
 ('run_handshake_checks.py',[],'handshake.log'),
]
for file,args,log in steps:
 with (P/log).open('w',encoding='utf-8') as output:
  result=subprocess.run([sys.executable,'-X','utf8',str(P/file),*args],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
 print(file,result.returncode,flush=True)
 if result.returncode:raise SystemExit(result.returncode)
