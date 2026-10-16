from pathlib import Path
import gzip,hashlib,json,shutil,tarfile
base=Path('/tmp/rust-cache-sipsma-review')
source=base/'usage-maps-real-engine'
root=Path('hack/rust-cache/experiments/usage-maps-real-engine')
root.mkdir(exist_ok=False)
def copy(p,relative):
    destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy(p,destination)
def compress(p,relative):
    destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as output:
            output.write(Path(p).read_bytes())
for series in ['paired','confirmation']:
    for name in ['metadata.json','samples.json','summary.json','admission.jsonl']:
        copy(source/series/name,series+'/'+name)
    compress(source/(series+'.log'),series+'/driver.log.gz')
for name in ['overlay.json','manifest.json','derived-statistics.json','engine.go.mod']:
    copy(source/name,name)
compress(source/'engine.go.sum','engine.go.sum.gz')
for name in ['cache.go','cache_usage.go','mode.go','server.go','debug.go']:
    compress(source/name,'diagnostic-source/'+name+'.gz')
for name in ['unit-race.log','reference-lock-label.log','unit-race-compatible.log','build.log','build-compatible.log','install.log','startup-tail.log','reuse-old.log','reuse-chain.log']:
    compress(source/name,'validation/'+name+'.gz')
for p in (source/'install').iterdir():
    if p.suffix=='.json':copy(p,'installation/'+p.name)
    else:compress(p,'installation/'+p.name+'.gz')
for name in ['prepare_usage_maps_diagnostic.py','measure_real_cache_usage.py','check_deep_artifact_reuse.py','verify_usage_maps_chain_reuse.py','restart_owned_engine_clean.py']:
    copy(base/name,name)
for directory,destination in [(base/'deep-artifact-reuse-usage-maps-post-restart','old-history-reuse.tar.gz'),(source/'chain-post-restart-reuse','chain-history-reuse.tar.gz')]:
    with tarfile.open(root/destination,'w:gz') as output:
        for p in sorted(directory.iterdir()):output.add(p,arcname=p.name)
copy(base/'fingerprint-buffer-engine-overlay-manifest.json','baseline-overlay-manifest.json')
(root/'revisions.json').write_text(json.dumps(dict(upstream_proposal='4cd7f219ff5f43d5dcd38a4f0e256c60ee24f33b',upstream_base='717589c9ccacbba7d3cf902647aa5c9ca68085e8',engine_source='19eda924854e7f22582f3a7430272aa729cbeb5f',previous_engine_sha256='a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa',diagnostic_engine_sha256='f61dfab5738e8f074c805da62a9e1224eebaf448f59c16399bf1953a6278eb04',rust_module='f73c5614a89968afa6f6000328e96ea33745fd93',baseline_overlay_sources='../fingerprint-buffer/engine-source-overlay.tar.gz',dang_library_source='../fingerprint-buffer/dang-library-source.tar.gz',notes='Diagnostic-only code; upstream proposal unchanged. Paths need adjustment to reproduce elsewhere. Build CGO_ENABLED=0 GOMAXPROCS=8 go build -buildvcs=false -p8 -overlay=overlay.json -modfile=engine.go.mod -o dagger-engine ./cmd/engine in engine source worktree.'),indent=2)+'\n')
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
