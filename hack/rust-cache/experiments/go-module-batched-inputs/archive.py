from pathlib import Path
import gzip
import hashlib
import json
import os

source=Path(__file__).parent
root=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/go-module-batched-inputs')
root.mkdir(exist_ok=False)
records=[]
for directory, directories, files in os.walk(source):
    directories[:]=sorted(d for d in directories if d not in {'codegen','__pycache__','.git'})
    for name in sorted(files):
        path=Path(directory)/name
        if path.suffix not in {'.py','.json','.jsonl','.log','.txt','.ndjson','.gz','.pprof','.go','.dang','.md','.patch'}:
            continue
        relative=path.relative_to(source)
        data=path.read_bytes()
        # Preserve all raw records; compress large logs, assembled traces and CPU profiles.
        compressed=path.suffix in {'.ndjson','.pprof','.log'} or (len(data)>150000 and path.suffix!='.gz')
        destination=root/(str(relative)+('.gz' if compressed else ''))
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
        restored=gzip.decompress(destination.read_bytes()) if compressed else destination.read_bytes()
        assert restored==data,relative
        records.append(dict(source=str(relative),archived=str(destination.relative_to(root)),
            source_bytes=len(data),source_sha256=hashlib.sha256(data).hexdigest(),
            archived_bytes=destination.stat().st_size,
            archived_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),compressed=compressed))
(root/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
print(len(records),'records;',sum(r['archived_bytes'] for r in records),'archived bytes; all hashes verified')
