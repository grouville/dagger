from pathlib import Path
import os,subprocess,time,json,statistics,hashlib,sys
b=Path('/tmp/collections-perf/cli-boundaries');dest=b/sys.argv[1];dest.mkdir(exist_ok=True)
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None);env.pop('CPUPROFILE',None);env.pop('DAGGER_PERF_TIMELINE',None)
labels=sys.argv[2:] or ['control','early-analytics','batch']
rows=[]
for typ in ['core','check']:
 for i in range(-1,8):
  order=labels if i%2==0 else labels[::-1]
  for label in order:
   name=f'{typ}-{i}-{label}';cmd=[str(b/f'dagger-{label}'),'--engine','container://dagger-engine.collections-artifact-schema-fork']
   cmd+=['-m','core','api','query','--doc','/tmp/collections-perf/discovery-next/cli-floor/query.graphql'] if typ=='core' else ['check','-l','--all']
   start=time.monotonic();p=subprocess.run(cmd,cwd='/tmp/collections-perf/normal-baseline/greetings-split',env=env,capture_output=True);elapsed=time.monotonic()-start
   (dest/f'{name}.out').write_bytes(p.stdout);(dest/f'{name}.err').write_bytes(p.stderr)
   assert p.returncode==0,(name,p.stderr.decode())
   if typ=='core':assert json.loads(p.stdout)=={'__typename':'Query'}
   else:assert p.stdout==Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
   result={'type':typ,'iteration':i,'variant':label,'seconds':elapsed,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest()};rows.append(result);print(result,flush=True)
   (dest/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
summary={typ:{label:statistics.median(r['seconds'] for r in rows if r['iteration']>=0 and r['type']==typ and r['variant']==label) for label in labels} for typ in ['core','check']}
(dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary)
