from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
root=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/protobuf-field-sorting');root.mkdir(exist_ok=False)
def copy(source,relative):
    target=root/relative
    if source.suffix in ['.go','.log','.ndjson','.txt','.trace']:
        target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as stream:
            with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped:zipped.write(source.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    return str(target.relative_to(root))
def tree(folder,label):
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.suffix in ['.test','.db'] or path.name=='dagger-engine' or '__pycache__' in path.parts:continue
        copy(path,str(Path(label)/path.relative_to(folder)))
for name in ['prepare_small_proto_fields.py','prepare_typed_proto_fields.py','validate_typed_proto_fields.py','analyze_proto_experiments.py','prepare_bulk_proto_json.py','bulk_proto_json_compat_test.template','archive_proto_experiments.py','proto-experiments-final-state.json','restart_owned_engine_clean.py','check_native_discovery_current_reuse.py','local_cli_collector.py']:
    copy(base/name,'drivers/'+name)
for name,label in [('small-proto-fields','small'),('typed-proto-fields','typed'),('bulk-proto-json','bulk-list')]:tree(base/name,label)
for name,label in [('small-proto-fields','small'),('typed-proto-fields','typed')]:
    tree(base/('native-discovery-retained-'+name),label+'/retained-cache')
    manifest=json.loads((base/name/'manifest.json').read_text());mirrors={}
    for logical,item in manifest.items():
        path=Path(item['replacement']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],logical
        for prefix,namespace in [('/tmp/dagger-filesync-snapshot-seeds/','dagger'),('/tmp/containerd-gc-source/','containerd'),('/tmp/protobuf-field-order-experiment/','protobuf')]:
            if logical.startswith(prefix):relative=namespace+'/'+logical.removeprefix(prefix);break
        else:raise AssertionError(logical)
        mirrors[logical]=dict(archived=copy(path,label+'/engine/source-mirror/'+relative),sha256=item['sha256'])
    target=root/label/'engine/source-mirror.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(mirrors,indent=2)+'\n')
copy(Path('/tmp/protobuf-field-order-experiment/internal/order/range_test.go'),'dependency-test-support/range_test.go')
(root/'README.md').write_text('''# Protobuf field sorting: component gains, no selected engine change

See [the report](../../NATIVE_PROTOBUF_FIELD_SORTING.md). `small` records zero/one/two-field fast paths; `typed` also replaces reflective sorting with sort.Interface for larger messages. Each has two independent-order eight-pair/four-workload edited-command cohorts, normal-GC CPU/wcprof diagnostics, full affected dependency and client-database race suites, preserved-volume restarts and six native-history checks. No complete-command speedup is established; both variants remain disabled and the selected f73ec4d9 engine is restored.

`small/standalone` compares the plain production patch with the original dependency, without the diagnostic branch. `small/field-sorter-screen` screens original, small and typed variants in balanced fresh processes; it includes reference tests, component bytes/allocations, pressure and all raw logs. `bulk-list` contains the separate one-encoder attribute-list experiment. It passes compatibility and race tests but is rejected at the component stage: it adds allocations and does not speed the fixture. It was never installed in the engine.

`typed/earlier-range-allocation-lines.txt.gz` corrects the interpretation of the earlier cumulative allocation profile: the visitor's encoding work is included under RangeFields; about 94 MB is attributed to its actual sort.Slice call. The original profile remains in the [allocation archive](../listing-allocations/).

Each engine source mirror maps logical overlay files to archived gzip files and uncompressed hashes. The source base is 19eda924854e7f22582f3a7430272aa729cbeb5f. Protobuf production sources match v1.36.11 before replacement; `small/protobuf-production-baseline.json` records their hashes. Fetch that module to reconstruct the unchanged files. Add `dependency-test-support/range_test.go.gz` to its internal/order directory: it supplies the earlier range-test helper used by the diagnostic reference tests. The benchmark overlay uses a Go-1.23-compatible B.N loop; test/build toolchain is Go 1.26.6. Local absolute paths and dependency replacements need adapting.

The Rust module remains da1ae47b6c96a3117de303b7584d028e35166530. All timed Dagger commands have fresh used source edits, warm engine/compiler state and telemetry enabled through the local receiver. Cargo controls use Rust 1.77.2. All admitted observations, pressure and ordinary-GC outliers are retained. Cumulative CPU/allocation frames overlap and are not elapsed-time savings.

Native-history preparation may compile the final Cargo or listing edit before strict full-reuse checks. These unchanged commands are correctness checks only. Existing fixture topology is in the preceding native-discovery and dimension-key archives. Binaries, volumes and target directories are excluded. The GitHub metadata API failure and initial generator/template mistakes remain recorded; direct public raw-source verification succeeded. Eight Dagger proposals remain prepared, with no new PR or dependency fork created. The broader Rust-cache goal stays incomplete.
''')
files=sorted(p for p in root.rglob('*') if p.is_file());(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files),max_file_bytes=max(p.stat().st_size for p in files))))
