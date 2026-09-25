from pathlib import Path
import os,subprocess,json,time,statistics
b=Path('/tmp/collections-perf/discovery-next/cli-floor');b.mkdir(exist_ok=True)
q=b/'query.graphql';q.write_text('{ __typename }\n')
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
cmd=['/tmp/collections-perf/committed/dagger','--engine','container://dagger-engine.collections-artifact-schema-fork','-m','core','api','query','--doc',str(q)]
rows=[]
for i in range(-1,5):
 start=time.monotonic();p=subprocess.run(cmd,cwd='/tmp/collections-perf/normal-baseline/greetings-split',env=env,capture_output=True)
 elapsed=time.monotonic()-start
 (b/f'{i}.out').write_bytes(p.stdout);(b/f'{i}.err').write_bytes(p.stderr)
 assert p.returncode==0,(p.returncode,p.stderr.decode());assert json.loads(p.stdout)=={'__typename':'Query'}
 row={'iteration':i,'seconds':elapsed,'status':p.returncode};rows.append(row);print(row,flush=True)
(b/'summary.json').write_text(json.dumps({'command':cmd,'diagnostic_only':True,'rows':rows,'median_seconds':statistics.median(r['seconds'] for r in rows if r['iteration']>=0)},indent=2)+'\n')
