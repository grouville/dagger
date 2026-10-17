from pathlib import Path
import difflib
import gzip
import hashlib
import json
import shutil

workspace = Path('/home/dagger/dagger_otra')
base = Path('/tmp/rust-cache-sipsma-review')
experiments = workspace/'hack/rust-cache/experiments'

def digest(data): return hashlib.sha256(data).hexdigest()

def append_tree(dst, sources):
    dst.mkdir(parents=True, exist_ok=True)
    manifest_path = dst/'archive-manifest.json'
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    manifest = {entry['path']: entry for entry in existing}
    for source, relative in sources:
        data = source.read_bytes()
        target = dst/relative
        zipped = len(data)>65536 and source.suffix not in {'.gz','.pprof'}
        if zipped: target = target.with_name(target.name+'.gz')
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = gzip.compress(data, mtime=0) if zipped else data
        target.write_bytes(encoded)
        name = str(target.relative_to(dst))
        manifest[name] = dict(path=name,source=str(source),source_bytes=len(data),source_sha256=digest(data),bytes=len(encoded),sha256=digest(encoded),gzip=zipped)
    manifest_path.write_text(json.dumps(list(manifest.values()),indent=2)+'\n')
    for entry in manifest.values():
        data=(dst/entry['path']).read_bytes()
        assert len(data)==entry['bytes'] and digest(data)==entry['sha256'],entry['path']
        source=gzip.decompress(data) if entry['gzip'] else data
        assert len(source)==entry['source_bytes'] and digest(source)==entry['source_sha256'],entry['path']
    print(dst.name,len(manifest),'verified files',flush=True)

def files_tree(src, relative, excluded=()):
    return [(p,relative/p.relative_to(src)) for p in sorted(src.rglob('*')) if p.is_file() and p.name not in excluded]

shared=base/'go-local-discovery-profile'
append_tree(experiments/'go-shared-workspace-paths',files_tree(shared,Path('evidence/testdata/followup')))

batch=base/'go-package-search-confirmation'
batch_sources=files_tree(batch,Path('evidence/testdata'),excluded=('archive.py',))
mod=Path('/tmp/dagger-go-package-search-recheck')
for name in ['go.dang','.dagger/modules/go-dev/main.dang','AGENTS.md']:
    batch_sources.append((mod/name,Path('module-source')/name))
append_tree(experiments/'go-package-search-recheck',batch_sources)

schema=base/'dang-prepared-schema'
changed=['helpers.go','declarations.go']
patch=''.join(''.join(difflib.unified_diff((schema/('before-'+name)).read_text().splitlines(True),(schema/('after-'+name)).read_text().splitlines(True),fromfile='a/core/sdk/dang/v2/'+name,tofile='b/core/sdk/dang/v2/'+name)) for name in changed)
(schema/'sdk.patch').write_text(patch)
sources=files_tree(schema,Path('evidence/testdata'),excluded=('dagger-engine','archive.py','archive-driver.log'))
sources.append((schema/'archive.py',Path('protocol/archive.py')))
# Retain every source selected by the overlay, including inherited experiments.
overlay=json.loads((schema/'engine-overlay.json').read_text())['Replace']
overlay_manifest=[]
for index,(virtual,actual) in enumerate(sorted(overlay.items())):
    source=Path(actual)
    relative=Path('engine-overlay/testdata')/f'{index:03d}'/source.name
    sources.append((source,relative))
    overlay_manifest.append(dict(virtual=virtual,actual=actual,archived=str(relative),sha256=digest(source.read_bytes())))
(schema/'engine-overlay-manifest.json').write_text(json.dumps(overlay_manifest,indent=2)+'\n')
sources.append((schema/'engine-overlay-manifest.json',Path('engine-overlay-manifest.json')))
retained=base/'native-discovery-retained-prepared-schema-after-first'
sources+=files_tree(retained,Path('evidence/testdata/retained-after-first'))
append_tree(experiments/'dang-prepared-schema',sources)
