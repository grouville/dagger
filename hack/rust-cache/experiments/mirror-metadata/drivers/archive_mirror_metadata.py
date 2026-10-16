from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
experiment=base/'mirror-metadata'
root=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/mirror-metadata')
root.mkdir(exist_ok=False)
assert json.loads((experiment/'restored-selected-state.json').read_text())['engine_sha256']=='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721'
def copy(path,relative):
    target=root/relative
    if path.suffix in ['.go','.log','.ndjson','.txt','.trace','.patch'] or path.name.endswith('.cache.json'):
        target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as stream:
            with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped:zipped.write(path.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    return str(target.relative_to(root))
def tree(source,label):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix in ['.test','.db'] or path.name=='dagger-engine' or '__pycache__' in path.parts:continue
        copy(path,str(Path(label)/path.relative_to(source)))
for name in ['prepare_mirror_metadata_experiment.py','measure_source_import_phases.py','analyze_source_import_phases.py','archive_mirror_metadata.py','check_native_discovery_current_reuse.py','restart_owned_engine_clean.py','local_cli_collector.py']:
    copy(base/name,'drivers/'+name)
tree(experiment,'runs')
tree(base/'source-import-phases-current','initial-phases')
tree(base/'source-import-phases-profile','initial-profiles')
tree(base/'native-discovery-retained-mirror-metadata','retained-cache')
mirrors={}
for logical,item in json.loads((experiment/'manifest.json').read_text()).items():
    path=Path(item['replacement']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],logical
    prefix='/tmp/dagger-filesync-snapshot-seeds/'
    if logical.startswith(prefix):relative='dagger/'+logical.removeprefix(prefix)
    else:
        prefix='/tmp/containerd-gc-source/';assert logical.startswith(prefix),logical
        relative='containerd/'+logical.removeprefix(prefix)
    mirrors[logical]=dict(archived=copy(path,'engine/source-mirror/'+relative),sha256=item['sha256'])
(root/'engine/source-mirror.json').write_text(json.dumps(mirrors,indent=2)+'\n')
(root/'README.md').write_text('''# Mirror metadata experiment: not selected

See [the report](../../NATIVE_MIRROR_METADATA.md). Removing engine-owned mirror xattr reads speeds its isolated walk but leaves almost all elapsed pre-copy import time in place. Complete edited commands are mixed. The original selected engine is restored; the upstream batch stays at eight, with no new PR opened.

`initial-phases` contains ten fresh edits with completed normal telemetry spans. `initial-profiles` adds three CLI/engine CPU, Go runtime trace and wcprof captures. Only bounded new telemetry windows were read; completed deduplicated spans are retained in compressed files. The old append-only receiver file is excluded. Its byte offsets and window hashes are provenance, not a claim that the entire original file is archived. Seed depth was not emitted; slow-copy attribution is inferred.

`runs` records the candidate, full affected package suites, race run, six fresh-process walk pairs, eight complete-command pairs for each of four workloads with Cargo controls, four balanced source-import phase pairs, six original-layout/default-option controls, preserved-volume restarts and the final runtime state. Every timed Dagger command edits a used Rust value. All admitted observations are kept, including GC and host-I/O outliers. Component processes have no pressure capture; complete commands do. Initial test-harness compilation mistakes are retained separately from the corrected green runs.

`engine/source-mirror.json` maps every overlay source to an archived gzip file and its uncompressed hash. Build dependencies and configuration are in `runs/engine.go.mod`, `runs/engine.go.sum`, `runs/overlay.json` and `runs/identity.json`; the source base is 19eda924854e7f22582f3a7430272aa729cbeb5f. Absolute paths need adapting when rerunning. The production-only candidate patch omits the diagnostic switch; it is a review aid, not a standalone upstream proposal. The module stays da1ae47b6c96a3117de303b7584d028e35166530 with Rust 1.77.2. No hash formatter or host import policy changes.

`retained-cache` prepares any last input changed by the Cargo controls, then requires full reuse in all six native histories with the candidate enabled. These unchanged commands are correctness checks only. Fixture topology and configurations are in the previous native-discovery and dimension-key archives. Binaries, target directories, volumes and Git metadata are excluded. The broader Rust-cache goal remains incomplete.
''')
files=sorted(path for path in root.rglob('*') if path.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(root))+'\n' for path in files))
print(json.dumps(dict(files=len(files),bytes=sum(path.stat().st_size for path in files),max_file_bytes=max(path.stat().st_size for path in files))))
