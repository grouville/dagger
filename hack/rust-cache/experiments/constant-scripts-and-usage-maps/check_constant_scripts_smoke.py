from pathlib import Path
import os
import re
import secrets
import shutil
import subprocess

base=Path('/tmp/rust-cache-sipsma-review')
source=Path('/tmp/rust-constant-scripts-smoke')
shutil.copytree('/tmp/rust-native-package-metadata-smoke',source,ignore=shutil.ignore_patterns('.git','target','dagger.lock'))
subprocess.run(['git','init','-q'],cwd=source,check=True)
config=source/'dagger.toml'
original=config.read_text().replace('/tmp/dagger-rust-package-metadata-cache','/tmp/dagger-rust-constant-script-getters').replace('package-metadata-check-smoke','constant-scripts-native-smoke')
config.write_text(original)
filename=source/'app/src/lib.rs'
valid=filename.read_text()
valid,count=re.subn(r'pub fn edited_value\(\) -> u64 \{ \d+ \}',f'pub fn edited_value() -> u64 {{ {secrets.randbits(48)} }}',valid)
assert count==1
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
for label,text,expected_failure,native in [('native-edited',valid,False,True),('native-invalid-rust',valid+'\nthis is invalid Rust\n',True,True),('native-repaired',valid,False,True),('legacy-check',valid,False,False)]:
    config.write_text(original if native else original.replace('nativeCache = true','nativeCache = false').replace('constant-scripts-native-smoke','constant-scripts-legacy-smoke'))
    filename.write_text(text)
    log=base/(f'constant-scripts-{label}.log')
    with log.open('w') as out:
        result=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','rust:packages/check'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
    assert bool(result.returncode)==expected_failure,(label,result.returncode)
    output=log.read_text()
    if expected_failure:assert 'expected' in output and 'lib.rs' in output,label
    else:assert 'passed' in output,label
    print('PASS',label,flush=True)
config.write_text(original)
