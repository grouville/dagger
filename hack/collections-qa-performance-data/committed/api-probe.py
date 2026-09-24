from pathlib import Path
import subprocess,os,json,time
base=Path('/tmp/collections-perf/committed');env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
cmd=[str(base/'dagger'),'--engine','container://dagger-engine.collections-committed-candidate-0','api','call','-m','/tmp/dagger-go-discovery','modules','get','--key','.','path']
t=time.monotonic()
with (base/'validation/api-get.out').open('w') as out,(base/'validation/api-get.err').open('w') as err:
 p=subprocess.run(cmd,cwd=base/'greetings/warm-workspace-candidate',env=env,stdout=out,stderr=err,timeout=60)
error=(base/'validation/api-get.err').read_text()
known='typedef "[GoModule]" not found' in error
row={'exit_code':p.returncode,'known_baseline_failure':known,'seconds':time.monotonic()-t,'command':cmd}
(base/'validation/api-get.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row))
assert p.returncode==1 and known
