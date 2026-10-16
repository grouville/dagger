from pathlib import Path
import gzip
import hashlib
import json
import shutil

family=Path(__file__).parent
base=family.parent
home=base/'rust-go-test-collections'
destination=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/go-full-listing')
destination.mkdir(exist_ok=False)
records=[]
def copy(source,relative):
    data=source.read_bytes()
    compress=source.suffix in ['.ndjson','.log','.stdout','.stderr','.pprof'] or (source.suffix=='.txt' and len(data)>4096)
    target=destination/relative
    if compress:target=target.with_name(target.name+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(gzip.compress(data,mtime=0) if compress else data)
    records.append(dict(source=str(source),path=str(target.relative_to(destination)),original_bytes=len(data),
        original_sha256=hashlib.sha256(data).hexdigest(),stored_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),gzip=compress))

for label in ['clean-main-complete-final','clean-main-no-prof-control','clean-main-marker-files']:
    directory=home/('real-go-discovery-'+label)
    dumps=sorted(directory.glob('goroutines-*.txt'),key=lambda p:int(p.stem.split('-')[1]))
    chosen={min(dumps,key=lambda p:abs(int(p.stem.split('-')[1])-at)) for at in [30,60,80,100]} if dumps else set()
    if dumps:chosen.add(dumps[-1])
    for source in sorted(directory.rglob('*')):
        # Retain one complete event stream and fixed phase samples, rather
        # than duplicate streams and every five-second goroutine snapshot.
        if source.name=='wcprof.ndjson' and (directory/'wcprof-complete.ndjson').exists():continue
        if source.name.startswith('goroutines-') and source not in chosen:continue
        if source.is_file():copy(source,Path('diagnostics')/label/source.relative_to(directory))
for source in sorted(family.rglob('*')):
    if source.is_file() and '__pycache__' not in source.parts:copy(source,Path('experiment')/source.relative_to(family))
for name in ['profile_real_go_active.py','profile_real_go_complete.py','profile_real_go_allocations.py','measure_real_go_complete.py','measure.py']:
    copy(home/name,Path('drivers')/name)
copy(base/'local_cli_collector.py',Path('drivers/local_cli_collector.py'))
for label,path in [('before',Path('/tmp/dagger-go-ordered-discovery-inputs')),('marker-experiment',Path('/tmp/dagger-go-package-module-ownership'))]:
    for name in ['go.dang','gomod/main.dang','.dagger/modules/go-dev/main.dang','AGENTS.md']:
        copy(path/name,Path('module-source')/label/name)
(destination/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
for record in records:
    path=destination/record['path'];stored=path.read_bytes()
    assert hashlib.sha256(stored).hexdigest()==record['stored_sha256']
    data=gzip.decompress(stored) if record['gzip'] else stored
    assert hashlib.sha256(data).hexdigest()==record['original_sha256']
print(json.dumps(dict(files=len(records),stored_bytes=sum((destination/r['path']).stat().st_size for r in records),verified=True)),flush=True)
