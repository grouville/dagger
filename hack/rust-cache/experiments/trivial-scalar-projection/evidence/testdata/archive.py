from pathlib import Path
import gzip
import hashlib
import json

workspace=Path('/home/dagger/dagger_otra')
root=Path(__file__).parent
dest=workspace/'hack/rust-cache/experiments/trivial-scalar-projection'
known={}
for family in ['config-host-stat-read','config-content-declarations','dang-builtin-receivers','cache-usage-provider-rows']:
    for row in json.loads((dest.parent/family/'archive-manifest.json').read_text()):
        known.setdefault(row['source_sha256'],(family,row))
sources=[];references=[];omitted=[]
def sha(data):return hashlib.sha256(data).hexdigest()
def add(path,target,reuse=False):
    data=path.read_bytes();digest=sha(data)
    if reuse and digest in known:
        family,row=known[digest]
        references.append(dict(source=str(path),source_bytes=len(data),source_sha256=digest,archived='../'+family+'/'+row['path'],gzip=row['gzip'],archive_bytes=row['bytes'],archive_sha256=row['sha256']))
    else:sources.append((path,target))
def tree(source,target):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:continue
        if path.suffix=='.test' or path.name.startswith('dagger-engine'):
            if path.name.endswith('.json') or path.name.endswith('.log'):add(path,target/path.relative_to(source));continue
            hasher=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1<<20),b''):hasher.update(block)
            omitted.append(dict(source=str(path),bytes=path.stat().st_size,sha256=hasher.hexdigest(),reason='Executable omitted; source and exact build commands retained.'))
        else:add(path,target/path.relative_to(source))
tree(root,Path('evidence/testdata'))
tree(root.parent/'cache-compaction-ownership',Path('compaction/testdata'))
for virtual,actual in sorted(json.loads((root/'engine-overlay.json').read_text())['Replace'].items()):
    add(Path(actual),Path('overlay-inputs/testdata')/sha(virtual.encode())[:16]/Path(actual).name,reuse=True)
for name in ['engine.go.mod','engine.go.sum']:
    add(root.parent/'otel-evicted-queue'/name,Path('protocol/testdata')/name,reuse=True)
for name in ['rust-go-test-collections/measure.py','local_cli_collector.py','restart_owned_engine_clean.py','glob-literal-prefix/full-command-paired/0-before.stdout']:
    add(root.parent/name,Path('protocol/testdata')/name,reuse=True)
for suffix in ['scalar-projection-before-first','scalar-projection-after-first','scalar-projection-post-cohort','scalar-projection-post-capture','scalar-projection-restored-first','scalar-projection-route-before-first']:
    path=root.parent/('native-discovery-retained-'+suffix)
    if path.exists():tree(path,Path('native-retained/testdata')/suffix)
for name in ['dagql/objects.go','dagql/trivial_scalar_projection_test.go','dagql/trivial_scalar_projection_bench_test.go']:
    add(Path('/tmp/dagger-trivial-scalar-fields-only')/name,Path('standalone-source/testdata')/name)
dest.mkdir(parents=True,exist_ok=True)
manifest=[]
for path,target in sources:
    data=path.read_bytes();compress=len(data)>65536 and path.suffix not in {'.gz','.pprof'}
    if compress:target=target.with_name(target.name+'.gz')
    encoded=gzip.compress(data,mtime=0) if compress else data
    output=dest/target;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(encoded)
    manifest.append(dict(path=str(target),source=str(path),source_bytes=len(data),source_sha256=sha(data),bytes=len(encoded),sha256=sha(encoded),gzip=compress))
(dest/'archive-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(dest/'inherited-source-manifest.json').write_text(json.dumps(references,indent=2)+'\n')
(dest/'omitted-executables.json').write_text(json.dumps(omitted,indent=2)+'\n')
(dest/'.gitattributes').write_text('# Preserve captured sources, patches and logs.\n**/testdata/** -whitespace\n')
for row in manifest:
    data=(dest/row['path']).read_bytes();assert len(data)==row['bytes'] and sha(data)==row['sha256']
    raw=gzip.decompress(data) if row['gzip'] else data
    assert len(raw)==row['source_bytes'] and sha(raw)==row['source_sha256']
for row in references:
    data=(dest/row['archived']).read_bytes();assert len(data)==row['archive_bytes'] and sha(data)==row['archive_sha256']
    raw=gzip.decompress(data) if row['gzip'] else data
    assert len(raw)==row['source_bytes'] and sha(raw)==row['source_sha256']
print(len(manifest),'captured,',len(references),'inherited,',len(omitted),'executables omitted; every archive hash verified.',flush=True)
