from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review');experiment=base/'artifact-metadata-fields'
root=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/artifact-metadata-fields');root.mkdir(exist_ok=False)
def copy(source,relative):
    target=root/relative
    if source.suffix in ['.go','.log','.ndjson','.txt','.trace']:
        target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as stream:
            with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as output:output.write(source.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    return str(target.relative_to(root))
def tree(source,label):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix in ['.test','.db'] or path.name=='dagger-engine' or '__pycache__' in path.parts:continue
        copy(path,str(Path(label)/path.relative_to(source)))
for name in ['prepare_artifact_metadata_fields.py','prepare_artifact_metadata_engine.py','artifact_metadata_fields_test.template','prepare_artifact_key_lists.py','artifact_key_lists_test.template','archive_artifact_metadata_fields.py','restart_owned_engine_clean.py','check_native_discovery_current_reuse.py','local_cli_collector.py']:
    copy(base/name,'drivers/'+name)
tree(experiment,'runs')
tree(base/'artifact-key-lists','rejected-object-list')
tree(base/'native-discovery-retained-artifact-metadata-fields','retained-cache')
mirrors={}
for logical,item in json.loads((experiment/'manifest.json').read_text()).items():
    path=Path(item['replacement']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],logical
    for prefix,namespace in [('/tmp/dagger-filesync-snapshot-seeds/','dagger'),('/tmp/containerd-gc-source/','containerd')]:
        if logical.startswith(prefix):relative=namespace+'/'+logical.removeprefix(prefix);break
    else:raise AssertionError(logical)
    mirrors[logical]=dict(archived=copy(path,'engine/source-mirror/'+relative),sha256=item['sha256'])
(root/'engine/source-mirror.json').write_text(json.dumps(mirrors,indent=2)+'\n')
for name in ['manifest.json','identity.json','engine-overlay.json','engine.go.mod','engine.go.sum']:copy(experiment/name,'engine/'+name)
(root/'README.md').write_text('''# Direct artifact metadata string getters: selected

See [the report](../../NATIVE_ARTIFACT_METADATA_FIELDS.md). Two existing field policies remove separate result-cache entries for Artifact.description and Artifact.uri. Complete edited 1,026-package listings improve in 15/16 pairs, with 328 ms median paired saving and 368 MB less allocation. Build/test controls show no established compilation gain. The native Rust module stays da1ae47; the selected diagnostic engine is ad2af24c562b892d82ca71303c2df12e3c1f4cba7a71227386218a658ffac7c0 with the metadata and existing dimension-key policies enabled.

`runs` contains the component and standalone-main benchmarks, both full-command cohorts, completed CPU/wcprof/CLI runtime diagnostics, source edits, pressure, test logs, the fork description and final runtime state. All timed Dagger commands edit a used Rust value; telemetry and ordinary Go/snapshot collection stay enabled. All admitted observations are retained. An isolated upstream worktree checkout occurred during confirmation; its provenance and host pressure remain disclosed. The maximum timed listing I/O pressure is 5.9% initially and 3.3% in confirmation.

`rejected-object-list` preserves the earlier direct-list prototype and the object-ID test failure. Its uncached key objects become detached. That production change is excluded; cached artifact and key lists preserve attachment and IDs. The final scalar-field compatibility test loads both kinds of IDs across changing parent generations. Initial fixture compilation failure is retained separately from the corrected tests.

`retained-cache` prepares the last Cargo/listing source edit when necessary, then requires complete reuse in six native histories. These unchanged commands are correctness evidence only. The original source base is 19eda924854e7f22582f3a7430272aa729cbeb5f. Every overlay source is mirrored under `engine/source-mirror`, with uncompressed hashes in `engine/source-mirror.json`. The standalone branch is e86fabff3ee6a91f2f20d56b3b159aacf9b8172a, based directly on main 717589c9ccacbba7d3cf902647aa5c9ca68085e8. Upstream-main focused race tests and six component pairs run without engine overlays.

Absolute paths and local dependency replacements need adapting when rerunning. Fixture source topology/configuration is in the preceding native-discovery and dimension-key archives. Binaries, volumes, target directories and Git metadata are excluded. The branch and description are pushed to Guillaume's fork; no PR is open. There are nine prepared Dagger proposals. The broader native Rust-cache goal remains incomplete.
''')
files=sorted(path for path in root.rglob('*') if path.is_file());(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(root))+'\n' for path in files))
print(json.dumps(dict(files=len(files),bytes=sum(path.stat().st_size for path in files))))
