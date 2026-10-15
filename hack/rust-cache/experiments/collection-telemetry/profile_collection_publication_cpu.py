from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import secrets
import subprocess
import urllib.request

base=Path('/tmp/rust-cache-sipsma-review');root=base/'rust-collection-publication-cpu';root.mkdir(exist_ok=False)
source=Path('/tmp/rust-native-config-entry-1026-after');config=source/'dagger.toml';original=config.read_text()

def capture_engine():
 with urllib.request.urlopen('http://127.0.0.1:16104/debug/pprof/profile?seconds=15',timeout=40) as response:
  (root/'engine.pprof').write_bytes(response.read())
try:
 text,count=re.subn(r'source = "[^"]+"','source = "/tmp/dagger-rust-metadata-toolchain"',original,count=1);assert count==1;config.write_text(text)
 with ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(capture_engine)
  for i in range(2):
   path=source/'leaf_1023/src/lib.rs'
   text,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',path.read_text());assert count==1;path.write_text(text)
   env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',CPUPROFILE=str(root/f'cli-{i}.pprof'))
   with (root/f'command-{i}.log').open('w') as output:
    result=subprocess.run(['python3',str(base/'local_cli.py'),'check','--list','--all','rust:packages/check'],cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
   assert result.returncode==0,i
   print('PASS fresh expanded collection capture',i,flush=True)
  future.result()
finally:config.write_text(original)
print('PASS CPU captures; fixture module restored',flush=True)
