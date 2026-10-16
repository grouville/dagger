from pathlib import Path
import json
import os
import subprocess

home=Path(__file__).parent;base=home.parent;root=home/'go64-failure-correctness';root.mkdir(exist_ok=False)
source=home/'fixtures/go-64';file=source/'pkg_063/value_test.go';original=file.read_text()
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
rows=[]
try:
    for label,poison in [('last-package-fails',True),('repaired-all-packages-pass',False)]:
        file.write_text(original.replace('func Test000(t *testing.T) {','func Test000(t *testing.T) { t.Fatal("sentinel64");',1) if poison else original)
        with (root/(label+'.log')).open('w') as out:r=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','go:packages/tests/test'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
        rows.append(dict(label=label,exit_code=r.returncode,sentinel_in_log='sentinel64' in (root/(label+'.log')).read_text(errors='replace')))
        (root/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert (r.returncode!=0)==poison,label
        print(label,r.returncode,flush=True)
finally:file.write_text(original)
