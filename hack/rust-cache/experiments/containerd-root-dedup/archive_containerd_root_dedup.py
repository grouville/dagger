from pathlib import Path
import gzip
import hashlib
import json
import shutil

base = Path('/tmp/rust-cache-sipsma-review')
graph = base/'containerd-mark-graph'
engine = base/'containerd-root-dedup-engine'
profiles = base/'snapshot-gc-import-waits'
root = Path('hack/rust-cache/experiments/containerd-root-dedup')
root.mkdir(exist_ok=False)


def copy(path, relative):
    if path.suffix == '.go' and relative.endswith('.go'):
        compress(path, relative+'.gz')
        return
    destination=root/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,destination)


def compress(path, relative):
    destination=root/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:
            output.write(path.read_bytes())


for name in ['profile_snapshot_gc_import_waits.py','measure_containerd_root_dedup.py',
             'measure_containerd_root_dedup_command.py','measure_containerd_root_dedup_command_confirmation.py',
             'verify_containerd_root_dedup_native.py','summarize_containerd_root_dedup_commands.py',
             'archive_containerd_root_dedup.py']:
    copy(base/name,name)
copy(base/'containerd-root-dedup-evidence-README.md','README.md')

for name in ['capture.json','graph-statistics.json','progress.json','retained-graph.json.gz',
             'probe.go.mod','probe.go.sum','upstream-gc-content.json','upstream-gc.go']:
    copy(graph/name,'graph/'+name)
for name in ['gc-before.go','production-gc.go','production-duplicate_roots_test.go','export_graph_test.go']:
    copy(graph/name,'source/'+name)
copy(Path('/tmp/containerd-gc-source/core/metadata/retained_mark_bench_test.go'),'source/retained_mark_bench_test.go')
for path in sorted(graph.glob('*.log')):
    compress(path,'validation/'+path.name+'.gz')
for path in sorted((graph/'paired').iterdir()):
    if path.suffix=='.log':compress(path,'component/'+path.name+'.gz')
    else:copy(path,'component/'+path.name)

for label,directory in [('commands',base/'containerd-root-dedup-commands'),
                        ('one-file',base/'containerd-root-dedup-commands-one-file')]:
    for path in sorted(directory.iterdir()):
        if path.suffix=='.log':compress(path,label+'/'+path.name+'.gz')
        else:copy(path,label+'/'+path.name)

for path in sorted(profiles.iterdir()):
    if path.suffix in ['.log','.ndjson']:compress(path,'wait-profiles/'+path.name+'.gz')
    else:copy(path,'wait-profiles/'+path.name)

for name in ['engine.go.mod','engine.go.sum','identity.json','external-source.json','final-engine-state.json','source-audit.json']:
    copy(engine/name,'engine/'+name)
copy(engine/'debug.go','engine/debug.go')
copy(Path('/tmp/containerd-gc-source/pkg/gc/gc.go'),'engine/diagnostic-gc.go')
for path in sorted(engine.glob('*.log')):compress(path,'validation/'+path.name+'.gz')
for path in sorted((engine/'install').iterdir()):
    if path.suffix=='.txt':compress(path,'install/'+path.name+'.gz')
    else:copy(path,'install/'+path.name)

manifest=json.loads((engine/'manifest.json').read_text())
archived={}
logical_root=Path('/tmp/dagger-filesync-snapshot-seeds')
for logical,entry in manifest.items():
    replacement=Path(entry['replacement'])
    assert hashlib.sha256(replacement.read_bytes()).hexdigest()==entry['sha256'],logical
    relative=str(Path(logical).relative_to(logical_root))
    previous=Path('hack/rust-cache/experiments/snapshot-gc/overlay-source')/(relative+'.gz')
    if previous.is_file() and hashlib.sha256(gzip.decompress(previous.read_bytes())).hexdigest()==entry['sha256']:
        archived[relative]=dict(sha256=entry['sha256'],source='../snapshot-gc/overlay-source/'+relative+'.gz')
    else:
        compress(replacement,'overlay-source/'+relative+'.gz')
        archived[relative]=dict(sha256=entry['sha256'],source='overlay-source/'+relative+'.gz')
(root/'engine/overlay-manifest.json').write_text(json.dumps(archived,indent=2)+'\n')

native=base/'containerd-root-dedup-validation'
for path in sorted(native.iterdir()):
    if path.name.endswith('-error.txt'):compress(path,'native/'+path.name+'.gz')
    else:copy(path,'native/'+path.name)
for optional in ['upstream-source.patch','upstream-revision.json','upstream-race.log','retained-reuse.log']:
    if (graph/optional).is_file():copy(graph/optional,optional)

files=sorted(path for path in root.rglob('*') if path.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(root))+'\n' for path in files))
print(json.dumps(dict(files=len(files),bytes=sum(path.stat().st_size for path in files))))
