from pathlib import Path
import json,subprocess,time,os,urllib.request,threading
b=Path('/tmp/collections-perf/half-second');ws=Path('/tmp/collections-perf/normal-baseline/greetings-split')
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
cmd=['/tmp/collections-perf/committed/dagger','--engine','container://dagger-engine.collections-schema-decode','check','-l','--all']
want=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
for name in ['warmup','cli-profile']:
 e=env.copy()
 if name=='cli-profile':e['CPUPROFILE']=str(b/'cli.cpu')
 t0=time.time_ns();start=time.monotonic_ns()
 p=subprocess.run(cmd,cwd=ws,env=e,capture_output=True)
 elapsed=(time.monotonic_ns()-start)/1e9
 (b/(name+'.out')).write_bytes(p.stdout);(b/(name+'.err')).write_bytes(p.stderr)
 result={'status':p.returncode,'seconds':elapsed,'start_unix_ns':t0,'stdout_correct':p.stdout==want}
 (b/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(name,result,flush=True)
 assert p.returncode==0 and p.stdout==want
