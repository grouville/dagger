from pathlib import Path
import json,os,subprocess,time
root=Path(__file__).parent
base=root.parent
module=Path('/tmp/dagger-go-ordered-discovery-inputs')
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
rows=[]
for check in ['gomod-checks:own-files-check','gomod-checks:discovery-check','gomod-checks:skips-non-modules-check','go-dev:tests-collection-check']:
    tick=time.monotonic()
    with (root/(check.replace(':','-')+'.log')).open('w') as out:
        r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
    row=dict(check=check,exit_code=r.returncode,seconds=time.monotonic()-tick);rows.append(row)
    (root/'correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(row,flush=True)
    assert r.returncode==0,check
