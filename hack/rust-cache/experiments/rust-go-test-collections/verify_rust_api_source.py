from pathlib import Path
import json
import os
import subprocess
import time

home=Path(__file__).parent;base=home.parent;root=home/'final-rust-api-source-check';root.mkdir(exist_ok=False)
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
rows=[]
def run(label,command,cwd,expected=0,diagnostic=None):
    tick=time.monotonic()
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,exit_code=r.returncode,expected=expected,seconds=time.monotonic()-tick,command=command));(root/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert (r.returncode==0)==(expected==0),label
    if diagnostic:assert diagnostic in (root/(label+'.log')).read_text(errors='replace'),label
    print(label,r.returncode,flush=True)
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
small=home/'fixtures/rust-1'
run('plain-workspace-api-still-runs-tests',['python3',str(base/'local_cli_collector.py'),'api','call','rust','test','--source','.'],small)
