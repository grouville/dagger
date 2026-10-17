from pathlib import Path
import hashlib,json,os,subprocess,time,urllib.request
r=Path(__file__).parent; base=r.parent; module=Path('/tmp/dagger-go-module-test-name-index')
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as response:return json.load(response)
routes=['reusable-declarations','telemetry-flush-coalescing','callback-caller-reuse','interface-candidate-pruning','interface-field-snapshots']
flags={route:get(route)['enabled'] for route in routes}
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(r/'dagger-after'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15')
fixture=next((module/'testdata/go-module-with-testdata').glob('*_test.go')); original=fixture.read_bytes(); rows=[]
try:
    fixture.write_bytes(original+('\n// Fresh input for host glob pruning '+str(time.time_ns())+'\n').encode())
    for route in routes:get(route+'?enabled='+str(route=='reusable-declarations').lower(),b'')
    for check in ['go-dev:tests-collection-check','go-dev:discovery-from-subdir-check','go-dev:generation-globs-check']:
        tick=time.monotonic()
        with (r/(check.replace(':','-')+'.log')).open('w') as out:
            result=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
        row=dict(check=check,exit_code=result.returncode,seconds=time.monotonic()-tick); rows.append(row)
        (r/'module-correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
        assert result.returncode==0,check
finally:
    fixture.write_bytes(original)
    for route,value in flags.items():get(route+'?enabled='+str(value).lower(),b'')
