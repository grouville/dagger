from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
experiments=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments')
prior=experiments/'artifact-metadata-fields'
prior_mirror=json.loads((prior/'engine/source-mirror.json').read_text())
def archive(name,report,drivers):
    source=base/name;root=experiments/name;root.mkdir(exist_ok=False)
    def copy(path,relative):
        target=root/relative
        if path.suffix in ['.go','.log','.ndjson','.txt','.trace']:
            target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('wb') as stream:
                with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as output:output.write(path.read_bytes())
        else:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        return str(target.relative_to(root))
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix in ['.test','.db'] or path.name in ['dagger-engine','probe','bench']:continue
        copy(path,'runs/'+str(path.relative_to(source)))
    for driver in drivers+['archive_index_and_digest_experiments.py','restart_owned_engine_clean.py','check_native_discovery_current_reuse.py']:
        copy(base/driver,'drivers/'+driver)
    mirror={}
    for logical,item in json.loads((source/'manifest.json').read_text()).items():
        path=Path(item['replacement']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],logical
        old=prior_mirror.get(logical)
        if old and old['sha256']==item['sha256']:
            relative='../artifact-metadata-fields/'+old['archived']
            existing=root/relative
            assert hashlib.sha256(gzip.decompress(existing.read_bytes())).hexdigest()==item['sha256'],logical
        else:
            for prefix,namespace in [('/tmp/dagger-filesync-snapshot-seeds/','dagger'),('/tmp/containerd-gc-source/','containerd')]:
                if logical.startswith(prefix):relative=namespace+'/'+logical.removeprefix(prefix);break
            else:raise AssertionError(logical)
            relative=copy(path,'engine/source-mirror/'+relative)
        mirror[logical]=dict(archived=relative,sha256=item['sha256'])
    (root/'engine').mkdir(exist_ok=True)
    (root/'engine/source-mirror.json').write_text(json.dumps(mirror,indent=2)+'\n')
    retained=base/('native-discovery-retained-'+name)
    if retained.exists():
        for path in sorted(retained.rglob('*')):
            if path.is_file() and path.suffix not in ['.test','.db']:copy(path,'retained-cache/'+str(path.relative_to(retained)))
    for filename in ['manifest.json','identity.json','engine-overlay.json','engine.go.mod','engine.go.sum']:copy(source/filename,'engine/'+filename)
    (root/'README.md').write_text(f'''# {name}

See [the experiment report](../../{report}) for results, disposition and limitations. `runs` retains test logs, component and full-command data, fresh edits, pressure, profiles, source files and runtime settings. Binaries, volumes, target directories and Git metadata are excluded.

The engine source base is `19eda924854e7f22582f3a7430272aa729cbeb5f`. `engine/source-mirror.json` records uncompressed SHA-256 hashes and archived paths relative to this experiment. Unchanged overlays reference the already committed `artifact-metadata-fields` archive; changed files are mirrored locally. Check both archives when reconstructing the engine. Raw overlay and dependency files retain local absolute paths and need adjustment when rerunning.

Complete command benchmarks use warm compiler/engine caches, a fresh used source edit and CLI process, telemetry enabled, ordinary GC and no forced collection. Instrumented captures remain separate from timing cohorts. The selected baseline and whether an upstream branch is prepared are recorded in the report. The native Rust-cache goal remains incomplete.
''')
    files=sorted(p for p in root.rglob('*') if p.is_file())
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
    print(json.dumps(dict(experiment=str(root),files=len(files),bytes=sum(p.stat().st_size for p in files))),flush=True)

archive('digest-paths-mount','NATIVE_DIGEST_PATHS_MOUNT.md',['prepare_digest_paths_mount.py'])
archive('span-lookup-fanout','NATIVE_SPAN_LOOKUP_FANOUT.md',['prepare_span_lookup_fanout.py','span_lookup_fanout_test.template'])
