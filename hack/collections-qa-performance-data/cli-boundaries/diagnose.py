from pathlib import Path
import os,subprocess,time,json,sys
b=Path('/tmp/collections-perf/cli-boundaries');env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
for variant in sys.argv[1:]:
 for typ in ['core','check']:
  name=f'diag-{variant}-{typ}';env['DAGGER_PERF_TIMELINE']=str(b/f'{name}.jsonl')
  (b/f'{name}.jsonl').unlink(missing_ok=True)
  binary={'control':'dagger-diagnostic','batch':'dagger-batch-diagnostic','http1':'dagger-http1-diagnostic','payload':'dagger-payload-diagnostic'}[variant]
  cmd=[str(b/binary),'--engine','container://dagger-engine.collections-artifact-schema-fork']
  cmd+=['-m','core','api','query','--doc','/tmp/collections-perf/discovery-next/cli-floor/query.graphql'] if typ=='core' else ['check','-l','--all']
  start=time.monotonic();p=subprocess.run(cmd,cwd='/tmp/collections-perf/normal-baseline/greetings-split',env=env,capture_output=True);elapsed=time.monotonic()-start
  (b/f'{name}.out').write_bytes(p.stdout);(b/f'{name}.err').write_bytes(p.stderr)
  assert p.returncode==0,(name,p.stderr.decode())
  if typ=='core':assert json.loads(p.stdout)=={'__typename':'Query'}
  else:assert p.stdout==Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
  result={'name':name,'seconds':elapsed};(b/f'{name}.json').write_text(json.dumps(result));print(result,flush=True)
