import os,re,subprocess
from pathlib import Path
base=Path('/tmp/rust-cache-sipsma-review')
source=Path('/tmp/rust-native-literal-display-1026-before')
config=source/'dagger.toml'
original=config.read_text()
try:
 text,n=re.subn(r'source = "[^\"]+"','source = "/tmp/dagger-rust-config-plan-file-transfer"',original,count=1)
 assert n==1
 config.write_text(text)
 with (base/'config-plan-file-legacy-smoke.log').open('w') as output:
  result=subprocess.run(['python3',str(base/'local_cli.py'),'check','rust:check'],cwd=source,env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276'),stdout=output,stderr=subprocess.STDOUT)
 assert not result.returncode,'new module check failed'
 print('PASS: new module accepts the existing plan and native cache',flush=True)
finally:
 config.write_text(original)
