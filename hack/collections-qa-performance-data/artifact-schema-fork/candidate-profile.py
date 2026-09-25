from pathlib import Path
import os,subprocess,urllib.request,concurrent.futures,time,json
b=Path('/tmp/collections-perf/discovery-next/candidate-cpu');b.mkdir(exist_ok=True)
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
cmd=['/tmp/collections-perf/committed/dagger','--engine','container://dagger-engine.collections-artifact-schema-fork','check','-l','--all']
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
ws='/tmp/collections-perf/normal-baseline/greetings-split'
def run(label):
 start=time.monotonic();p=subprocess.run(cmd,cwd=ws,env=env,capture_output=True)
 d={'seconds':time.monotonic()-start,'status':p.returncode,'stdout_correct':p.stdout==expected}
 (b/(label+'.json')).write_text(json.dumps(d,indent=2)+'\n');(b/(label+'.out')).write_bytes(p.stdout);(b/(label+'.err')).write_bytes(p.stderr)
 print(label,d,flush=True);assert p.returncode==0 and p.stdout==expected
run('warmup')
def profile():
 (b/'engine.cpu').write_bytes(urllib.request.urlopen('http://127.0.0.1:6146/debug/pprof/profile?seconds=15',timeout=25).read())
with concurrent.futures.ThreadPoolExecutor() as ex:
 f=ex.submit(profile);time.sleep(.25)
 for i in range(4):run('profile-'+str(i))
 f.result()
