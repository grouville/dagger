from pathlib import Path
import json,os,subprocess,time,urllib.request
r=Path(__file__).parent; base=r.parent; module=Path('/tmp/dagger-go-native-string-sort'); main=module/'gomod/main.dang';candidate=main.read_bytes();before=(r/'before-main.dang').read_bytes()
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'filesync-literal-pathwalk/dagger-after'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15')
def get(route,data=None):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as out:return json.load(out)
routes=['reusable-declarations','telemetry-flush-coalescing','callback-caller-reuse','interface-candidate-pruning','interface-field-snapshots'];saved={x:get(x)['enabled'] for x in routes};rows=[]
try:
 for x in routes:get(x+'?enabled='+str(x=='reusable-declarations').lower(),b'')
 for label,source,checks in [('before',before,['gomod-checks:own-files-check']),('after',candidate,['gomod-checks:own-files-check','gomod-checks:skips-non-modules-check','gomod-checks:discovery-check','go-dev:tests-collection-check','go-dev:generation-globs-check'])]:
  main.write_bytes(source)
  for check in checks:
   tick=time.monotonic()
   with (r/(label+'-'+check.replace(':','-')+'.log')).open('w') as out:result=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
   row=dict(arm=label,check=check,seconds=time.monotonic()-tick,exit_code=result.returncode);rows.append(row);(r/'correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True);assert result.returncode==0,check
finally:
 main.write_bytes(candidate)
 for x,v in saved.items():get(x+'?enabled='+str(v).lower(),b'')
