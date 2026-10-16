from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess
import os

source=Path(__file__).parent
target=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/rust-go-test-collections')
target.mkdir(parents=True,exist_ok=True)
excluded={'fixtures','native-go-cache','native-rust-1-target','native-rust-16-target','native-rust-64-target','rust-codegen-out','rust-codegen-prepared-executions','rust-codegen-prepared-final','__pycache__','.git'}
manifest={}
paths=[]
for directory,dirs,files in os.walk(source):
    dirs[:]=[name for name in dirs if name not in excluded and not name.endswith('-target')]
    paths.extend(Path(directory)/name for name in files)
for path in sorted(paths):
    rel=path.relative_to(source)
    if any(part in excluded or part.endswith('-target') for part in rel.parts):continue
    if path.suffix not in ['.py','.go','.dang','.json','.jsonl','.log','.pprof','.ndjson','.gz','.md','.patch','.mod','.sum','.toml','.txt']:continue
    data=path.read_bytes()
    compress=path.suffix in ['.ndjson','.log','.jsonl','.dang','.go','.txt'] and len(data)>10000
    name=str(rel)+('.gz' if compress else '')
    output=target/name;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(gzip.compress(data,mtime=0) if compress else data)
    manifest[str(rel)]=dict(archived=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for rel,item in manifest.items():
    data=(target/item['archived']).read_bytes()
    if item['archived'].endswith('.gz') and not rel.endswith('.gz'):data=gzip.decompress(data)
    assert hashlib.sha256(data).hexdigest()==item['sha256'],rel
print('Archived and verified',len(manifest),'files; bytes',sum(p.stat().st_size for p in target.rglob('*') if p.is_file()))
