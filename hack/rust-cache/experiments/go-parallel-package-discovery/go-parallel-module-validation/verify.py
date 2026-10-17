from pathlib import Path
import json,os,subprocess,time,urllib.request
p=Path(__file__).parent
base=p.parent
module=Path('/tmp/dagger-go-parallel-validation')
def get(route,data=None):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as r:return json.load(r)
flags={r:get(r)['enabled'] for r in ['reusable-declarations','callback-caller-reuse','telemetry-flush-coalescing']}
files=[module/'.dagger/modules/go-dev/main.dang',module/'gomod/.dagger/modules/e2e/main.dang']
saved={file:file.read_bytes() for file in files}
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
rows=[]
try:
 assert not get('wcprof/enabled')['global_enabled']
 for route in flags:assert get(route+'?enabled='+str(route=='reusable-declarations').lower(),b'')['enabled']==(route=='reusable-declarations')
 for file,data in saved.items():file.write_bytes(data+f'\n# Unique parallel validation checks {time.time_ns()}\n'.encode())
 for check in ['go-dev:collection-check','go-dev:discovery-from-subdir-check','gomod-checks:discovery-check','gomod-checks:skips-non-modules-check','go-dev:tests-collection-check']:
  tick=time.monotonic()
  with (p/(check.replace(':','-')+'.log')).open('w') as log:r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=log,stderr=subprocess.STDOUT)
  row=dict(check=check,exit_code=r.returncode,seconds=time.monotonic()-tick)
  rows.append(row);(p/'correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
  assert r.returncode==0,check
finally:
 for file,data in saved.items():file.write_bytes(data)
 for route,enabled in flags.items():assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
