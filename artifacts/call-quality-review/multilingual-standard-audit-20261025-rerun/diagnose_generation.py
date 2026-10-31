"""Replay archived generator stages through actual compiler validation offline."""
import asyncio,json
import run_fresh as f

async def main():
 f.a.setup()
 import server.brain.employee_script_pipeline as p
 import server.brain.agent_script_compiler as compiler
 stages=[json.loads(x.read_text(encoding='utf-8')) for x in sorted((f.OUT/'generation-stages').glob('*.json'))]
 kn=[s for s in stages if s.get('language')=='kn-IN']
 extracted=[s['output'] for s in kn if s['stage']=='employee_brief_extract' and s['output'].get('agent_name')=='Nila'][-1]
 write=next(s['output'] for s in kn if s['stage']=='employee_script_write')
 review=next(s['output'] for s in kn if s['stage']=='employee_script_review')
 outputs={'employee_brief_extract':extracted,'employee_script_write':write,'employee_script_review':review}
 async def completion(name,rules,data,model,**kwargs):return model.model_validate(outputs[name])
 p._completion=completion
 original=compiler.validate_agent_script;captured={}
 def observed(script,**kwargs):
  result=original(script,**kwargs);captured.update(script=script,source=kwargs.get('brief'),validation=result)
  return result
 compiler.validate_agent_script=observed
 try:
  await p.compile_employee_script(brief=f.BRIEFS[0]['brief'],language='kn-IN',generation_config={'agentRole':'sales','callDirection':'outbound'})
  captured['status']='ready'
 except Exception as ex:captured['status']=type(ex).__name__;captured['error']=str(ex)
 if captured.get('script'):
  captured['unsupported_numbers']=sorted(p._numbers(captured['script'])-(p._numbers(captured['source'])|p._numbers('kn-IN')))
  captured['word_count']=len(captured['script'].split());captured['opening_compatible']=compiler._opening_line_is_language_compatible(review['fixed_script']['opening'],'kn-IN')
 f.a.dump(f.OUT/'generation-diagnosis.json',captured)
 print(json.dumps({k:v for k,v in captured.items() if k not in {'script','source'}},ensure_ascii=False))
asyncio.run(main())
