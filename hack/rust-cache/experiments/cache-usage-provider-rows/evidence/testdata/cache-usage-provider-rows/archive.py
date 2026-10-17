from pathlib import Path
import gzip,hashlib,json,subprocess
workspace=Path('/home/dagger/dagger_otra')
base=Path('/tmp/rust-cache-sipsma-review')
dest=workspace/'hack/rust-cache/experiments/cache-usage-provider-rows'
def digest(data):return hashlib.sha256(data).hexdigest()
sources=[];omissions=[]
def tree(source,relative):
    for path in sorted(source.rglob('*')):
        if not path.is_file():continue
        if '__pycache__' in path.parts:continue
        target=relative/path.relative_to(source)
        if path.name=='dagger-engine' or path.suffix=='.test':
            data=path.read_bytes();omissions.append(dict(source=str(path),bytes=len(data),sha256=digest(data),reason='Executable omitted; source, build command and binary identity retained.'));continue
        sources.append((path,target))
for name in ['cache-usage-provider-rows','cache-usage-read-once-engine','cache-usage-minimal-engine','go-publication-waits']:
    tree(base/name,Path('evidence/testdata')/name)
for family in ['cache-usage-provider-rows','cache-usage-read-once-engine','cache-usage-minimal-engine']:
    overlay=json.loads((base/family/'engine-overlay.json').read_text())['Replace'];selected=[]
    for index,(virtual,actual) in enumerate(sorted(overlay.items())):
        path=Path(actual);target=Path('overlay-inputs/testdata')/family/f'{index:03d}'/path.name
        sources.append((path,target));selected.append(dict(virtual=virtual,actual=actual,archived=str(target),sha256=digest(path.read_bytes())))
    manifest=base/family/'archived-overlay-inputs.json';manifest.write_text(json.dumps(selected,indent=2)+'\n');sources.append((manifest,Path('overlay-inputs')/(family+'.json')))
for name in ['engine.go.mod','engine.go.sum']:
    sources.append((base/'otel-evicted-queue'/name,Path('protocol/testdata')/name))
for name in ['rust-go-test-collections/measure.py','local_cli_collector.py','restart_owned_engine_clean.py','glob-literal-prefix/full-command-paired/0-before.stdout']:
    sources.append((base/name,Path('protocol/testdata')/name))
for suffix in ['usage-preflight-before-first','usage-preflight-after-first','usage-preflight-post-cohort','usage-minimal-before-first','usage-minimal-after-first','usage-minimal-post-cohort']:
    tree(base/('native-discovery-retained-'+suffix),Path('evidence/testdata/native-retained')/suffix)
module=Path('/tmp/dagger-go-module-test-name-index')
for name in ['go.dang','gomod/main.dang','dagger.json','dagger.toml','AGENTS.md']:
    path=module/name
    if path.exists():sources.append((path,Path('module-source/testdata')/name))
dest.mkdir(parents=True,exist_ok=True)
manifest_path=dest/'archive-manifest.json'
manifest={row['path']:row for row in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
for source,target in sources:
    data=source.read_bytes();compressed=len(data)>65536 and source.suffix not in {'.gz','.pprof'}
    if compressed:target=target.with_name(target.name+'.gz')
    encoded=gzip.compress(data,mtime=0) if compressed else data
    output=dest/target;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(encoded)
    manifest[str(target)]=dict(path=str(target),source=str(source),source_bytes=len(data),source_sha256=digest(data),bytes=len(encoded),sha256=digest(encoded),gzip=compressed)
manifest_path.write_text(json.dumps(list(manifest.values()),indent=2)+'\n')
(dest/'omitted-executables.json').write_text(json.dumps(omissions,indent=2)+'\n')
(dest/'.gitattributes').write_text('# Preserve captured source, patches and logs exactly.\n**/testdata/** -whitespace\n')
for row in manifest.values():
    data=(dest/row['path']).read_bytes();assert len(data)==row['bytes'] and digest(data)==row['sha256'],row['path']
    raw=gzip.decompress(data) if row['gzip'] else data
    assert len(raw)==row['source_bytes'] and digest(raw)==row['source_sha256'],row['path']
print(len(manifest),'files archived and round-trip verified;',len(omissions),'executables identified but omitted.',flush=True)
