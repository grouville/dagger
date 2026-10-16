from pathlib import Path
import json
import os
import subprocess
import time

home=Path(__file__).parent;base=home.parent;root=home/'subset-correctness';root.mkdir(exist_ok=False)
source=home/'fixtures/rust-1';file=source/'pkg_000/src/lib.rs';original=file.read_text()
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
results=[]
def run(label,selection,expected,diagnostic=None):
    command=['python3',str(base/'local_cli_collector.py'),'check',selection]
    tick=time.monotonic()
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
    results.append(dict(label=label,exit_code=r.returncode,expected=expected,seconds=time.monotonic()-tick,command=command))
    (root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    assert (r.returncode==0)==(expected==0),label
    if diagnostic:assert diagnostic in (root/(label+'.log')).read_text(errors='replace'),label
    print(label,r.returncode,flush=True)
try:
    assert 'fn test_001() { assert!(edited_value() > 0); }' in original
    file.write_text(original.replace('fn test_001() { assert!(edited_value() > 0); }','fn test_001() { panic!("selected-poison"); }'))
    prefix='dag://?check=rust/packages/tests/test&rust-package=pkg_000'
    run('two-selected-others-excluded',prefix+'&rust-test=src/lib.rs::test_000&rust-test=src/lib.rs::test_002',0)
    run('selected-poison-fails',prefix+'&rust-test=src/lib.rs::test_001',1,'selected-poison')
    run('whole-package-poison-fails','rust:packages/tests/test',1,'selected-poison')
    file.write_text(original)
    run('repaired-whole-package','rust:packages/tests/test',0)
finally:file.write_text(original)
