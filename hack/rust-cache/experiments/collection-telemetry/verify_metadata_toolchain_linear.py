import json
import os
from pathlib import Path
import subprocess

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'metadata-toolchain-linear-correctness'
root.mkdir(exist_ok=False)
module=Path('/tmp/dagger-rust-metadata-toolchain')
cargo='/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin/cargo'
rustc='/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin/rustc'

def write(source,name,text):
 path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

def fixture(name,with_root=False):
 source=root/name;source.mkdir()
 workspace='[workspace]\nmembers=["app"]\nexclude=["external"]\nresolver="2"\n'
 if with_root:
  workspace+='\n[package]\nname="root-member"\nversion="0.1.0"\nedition="2021"\n'
  write(source,'src/lib.rs','pub fn root() {}\n')
 write(source,'Cargo.toml',workspace)
 write(source,'app/Cargo.toml','[package]\nname="app"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nexternal={path="../external"}\n')
 write(source,'app/src/lib.rs','pub fn value() -> u64 { external::value() }\n')
 write(source,'external/Cargo.toml','[package]\nname="external"\nversion="0.1.0"\nedition="2021"\n')
 write(source,'external/src/lib.rs','pub fn value() -> u64 { 1 }\n')
 subprocess.run([cargo,'generate-lockfile','--offline'],cwd=source,env=dict(os.environ,RUSTC=rustc),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 return source

def inspect(source,label,expected,should_fail=False):
 env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
 command=['python3',str(base/'local_cli.py'),'api','with-session','--',str(base/'rust-packages-inspect'),'-source',str(source)]
 if expected:command+=['-expected',expected]
 log=root/(label+'.log')
 with log.open('w') as output:
  result=subprocess.run(command,cwd=module,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=60)
 if should_fail:
  text=log.read_text()
  assert result.returncode!=0 and ('invalid toolchain' in text.lower() or 'invalid character' in text.lower()),(label,result.returncode)
 else:assert result.returncode==0,(label,result.returncode)
 print(label,'PASS',flush=True)

virtual=fixture('virtual')
root_member=fixture('root-member',True)
inspect(virtual,'virtual-excludes-path-dependency','app')
inspect(root_member,'includes-root-member','app,root-member')
# Cargo's --no-deps contract is also checked independently of the module.
metadata=json.loads(subprocess.check_output([cargo,'metadata','--offline','--locked','--no-deps','--format-version=1'],cwd=virtual,env=dict(os.environ,RUSTC=rustc)))
assert [package['name'] for package in metadata['packages']]==['app']
(root/'cargo-no-deps.json').write_text(json.dumps(metadata,indent=2)+'\n')
for filename in ['rust-toolchain','rust-toolchain.toml']:
 text='invalid toolchain name\n' if filename=='rust-toolchain' else '[toolchain]\nchannel="invalid toolchain name"\n'
 write(virtual,filename,text)
 inspect(virtual,filename+'-invalid','',True)
 (virtual/filename).unlink()
write(virtual,'rust-toolchain.toml','[toolchain]\nchannel="1.77.2"\n')
inspect(virtual,'installed-project-toolchain','app')
print('PASS: real module metadata preserves workspace membership and project toolchain selection',flush=True)
