from pathlib import Path
import json,os,subprocess,time
root=Path('/tmp/rust-cache-sipsma-review/go-full-listing-oct16')
base=root.parent
module=Path('/tmp/dagger-go-package-module-ownership')
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
rows=[]
for check in ['go-dev:tests-collection-check','go-dev:binary-check','go-dev:generation-globs-check','go-dev:selection-check']:
    tick=time.monotonic()
    with (root/(check.replace(':','-')+'.log')).open('w') as out:
        r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check',check],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
    row=dict(check=check,exit_code=r.returncode,seconds=time.monotonic()-tick);rows.append(row)
    (root/'correctness.json').write_text(json.dumps(rows,indent=2)+'\n');print(row,flush=True)
    assert r.returncode==0,check
