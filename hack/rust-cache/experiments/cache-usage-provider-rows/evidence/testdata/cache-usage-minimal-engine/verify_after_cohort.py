from pathlib import Path
import json,subprocess
from bench_engine import BenchEngine
root=Path(__file__).parent
engine=BenchEngine(root)
routes=['usage-sampling','reusable-declarations','prepared-schema','restored-posting-removal','batch-metadata','attribute-array-decode']
previous={route:engine.get(route)['enabled'] for route in routes}
(root/'post-cohort-modes-before.json').write_text(json.dumps(previous,indent=2)+'\n')
try:
 engine.idle('strict-post-cohort-cache-reuse')
 for route in ['usage-sampling','reusable-declarations','restored-posting-removal']:engine.mode(route,True)
 engine.mode('prepared-schema',False)
 command=['python3',str(root/'verify_retained_first.py'),'usage-minimal-post-cohort']
 with (root/'retained-post-cohort.log').open('w') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
 (root/'retained-post-cohort.json').write_text(json.dumps(dict(command=command,exit_code=r.returncode),indent=2)+'\n')
 print('strict retained histories',r.returncode,flush=True)
 assert r.returncode==0
finally:
 for route,enabled in previous.items():engine.mode(route,enabled)
 (root/'post-cohort-modes-after.json').write_text(json.dumps({route:engine.get(route) for route in routes},indent=2)+'\n')
