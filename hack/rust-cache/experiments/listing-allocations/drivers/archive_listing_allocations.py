from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
root=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/listing-allocations')
root.mkdir(exist_ok=False)
def copy(source,relative):
    target=root/relative
    if source.suffix in ['.log','.trace','.ndjson','.txt']:
        target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as stream:
            with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as output:output.write(source.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for name in ['capture_listing_allocations.py','capture_listing_allocation_stacks.py','archive_listing_allocations.py']:copy(base/name,'drivers/'+name)
for name,label in [('listing-allocations','unflushed'),('listing-allocation-stacks','flushed')]:
    for p in sorted((base/name).rglob('*')):
        if p.is_file():copy(p,str(Path(label)/p.relative_to(base/name)))
(root/'README.md').write_text('''# Locate allocation costs in a complete collection listing

See [the report](../../NATIVE_LISTING_ALLOCATIONS.md). This is profiling evidence, not a new optimization or timing cohort. Both captures use the selected native-discovery module and serial-fingerprint engine; there is no production source change.

`unflushed` contains a fresh edited listing with CPU, CLI runtime trace, completed wcprof and a five-second delta allocation profile. The allocation profile largely sees subsequent cache maintenance and is unsuitable for attributing the request's allocations. It is retained to make that limitation explicit.

`flushed` contains cumulative allocation profiles before and after another fresh edited listing, with two explicit Go GCs at each boundary to flush delayed allocation samples. It includes heap snapshots, exact command allocation counters, source value and the final runtime state. These forced collections are diagnostic only. The elapsed command timestamps must not be used as benchmark results. Ordinary cache cleanup remains enabled and may contribute additional background stacks.

The source manifests are unchanged from [the selected engine archive](../parallel-fingerprint/engine/manifest.json) and [source mirrors](../parallel-fingerprint/engine/source-mirror.json). The engine binary is f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721; module revision da1ae47b6c96a3117de303b7584d028e35166530. Binaries, volumes and target directories are excluded. Update absolute paths when rerunning.

Use `go tool pprof -sample_index=alloc_space -base flushed/before.allocs.pprof flushed/after.allocs.pprof` for the allocation comparison. Cumulative caller totals overlap. No PR is opened; the prepared upstream batch remains eight.
''')
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
