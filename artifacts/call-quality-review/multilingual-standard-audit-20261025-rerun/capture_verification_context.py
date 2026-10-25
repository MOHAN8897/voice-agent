import hashlib,json
from pathlib import Path
import run_fresh as r
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
settings,_=r.a.setup()
context={k:getattr(settings,k) for k in ('working_memory_enabled','enable_call_archive','memory_extraction_fallback','rolling_summary_interval_turns')}
context.update(database_boundary='isolated: database_url=None',redis_boundary='isolated: redis_url=None')
(P/'verification-context.json').write_text(json.dumps(context,indent=2),encoding='utf-8')
(P/'frozen-source.json').write_text(json.dumps({f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'server').rglob('*.py'))},indent=2),encoding='utf-8')
print(json.dumps(context))
