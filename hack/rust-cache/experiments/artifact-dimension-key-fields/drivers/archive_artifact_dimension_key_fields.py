from pathlib import Path
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

base = Path('/tmp/rust-cache-sipsma-review')
experiment = base / 'artifact-dimension-key-fields'
root = Path('hack/rust-cache/experiments/artifact-dimension-key-fields')
root.mkdir(exist_ok=False)

def copy(path, relative):
    target = root / relative
    if path.suffix in ['.go', '.log', '.ndjson', '.txt', '.trace', '.patch'] or path.name.endswith('.cache.json'):
        target = Path(str(target) + '.gz')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as output:
                output.write(path.read_bytes())
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return str(target.relative_to(root))

def tree(source, label):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '.git' in path.relative_to(source).parts:
            continue
        if path.suffix in ['.test', '.db'] or path.name == 'dagger-engine':
            continue
        copy(path, str(Path(label) / path.relative_to(source)))

for name in [
    'prepare_artifact_dimension_key_fields_engine.py',
    'measure_artifact_dimension_key_fields.py',
    'measure_artifact_dimension_key_fields_confirmation.py',
    'measure_artifact_dimension_key_fields_identical_control.py',
    'wait_then_measure_artifact_dimension_key_fields.py',
    'profile_artifact_dimension_key_fields.py',
    'profile_engine_publication_waits.py',
    'profile_engine_publication_waits_no_wcprof.py',
    'check_artifact_dimension_key_fields_reuse.py',
    'restart_owned_engine_clean.py', 'local_cli_collector.py',
    'native_batch_runtime_inspect.go', 'archive_artifact_dimension_key_fields.py',
]:
    copy(base / name, 'drivers/' + name)

tree(experiment, 'runs')
tree(base / 'artifact-dimension-key-fields-engine', 'engine')
tree(base / 'dimension-key-fields-retained-oct16', 'retained-cache')
for name in ['engine-publication-waits', 'engine-publication-waits-no-wcprof']:
    tree(base / name, 'lock-discovery/' + name)
    copy(base / (name + '-driver.log'), 'lock-discovery/' + name + '-driver.log')
for suffix in ['test.log', 'test-retry.log', 'screen.log', 'screen-v2.log', 'race.log', 'race-v2.log']:
    copy(base / ('artifact-dimension-key-fields-' + suffix), 'initial-harness/' + suffix)
copy(base / 'artifact-dimension-key-fields_test.go', 'initial-harness/screen_test.go')
copy(base / 'artifact-dimension-key-fields-bench.overlay.json', 'initial-harness/screen.overlay.json')

manifest = json.loads((base / 'artifact-dimension-key-fields-engine/manifest.json').read_text())
mirrors = {}
prefixes = [('/tmp/dagger-filesync-snapshot-seeds/', 'dagger/'), ('/tmp/containerd-gc-source/', 'containerd/')]
for logical, item in manifest.items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest() == item['sha256'], logical
    relative = None
    for prefix, replacement in prefixes:
        if logical.startswith(prefix):
            relative = replacement + logical[len(prefix):]
            break
    assert relative is not None, logical
    archived = copy(Path(item['replacement']), 'engine/source-mirror/' + relative)
    mirrors[logical] = dict(archived=archived, sha256=item['sha256'])
(root / 'engine/source-mirror.json').write_text(json.dumps(mirrors, indent=2) + '\n')

candidate = Path('/tmp/dagger-artifact-dimension-key-fields')
for arm, revision in [('before', '717589c9ccacbba7d3cf902647aa5c9ca68085e8'), ('after', '104f7ab5b211a739b29cce40bd0fe492617b1b86')]:
    for name in ['core/artifacts.go']:
        contents = subprocess.check_output(['git', 'show', revision + ':' + name], cwd=candidate)
        target = root / 'source' / arm / (name + '.gz')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as output:
                output.write(contents)
copy(candidate / 'core/schema/artifact_dimension_key_fields_test.go', 'source/artifact_dimension_key_fields_test.go')

count = 0
with (root / 'fixture-sources.tar.gz').open('wb') as raw:
    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for size in ['130', '1026', 'small']:
                for side in ['before', 'after']:
                    source = Path('/tmp/rust-native-config-entry-' + size + '-' + side)
                    command = ['rg', '--files', '--hidden', '-g', '!target', '-g', '!.git', '-g', '*.rs', '-g', 'Cargo.toml', '-g', 'Cargo.lock', '-g', 'dagger.toml', str(source)]
                    paths = subprocess.check_output(command, text=True).splitlines()
                    for name in sorted(paths):
                        path = Path(name); contents = path.read_bytes()
                        info = tarfile.TarInfo(str(Path(size + '-' + side) / path.relative_to(source)))
                        info.size = len(contents); info.mode = 0o644; info.mtime = 0
                        archive.addfile(info, io.BytesIO(contents)); count += 1
(root / 'fixture-sources.json').write_text(json.dumps(dict(files=count, note='Final fixture sources; benchmark drivers create fresh random edits. Initialize a local Git boundary and adjust module source paths before rerunning.'), indent=2) + '\n')

(root / 'README.md').write_text('''# Direct artifact dimension-key reads

Standalone patch: grouville/dagger 104f7ab5b211a739b29cce40bd0fe492617b1b86, directly on upstream main 717589c9ccacbba7d3cf902647aa5c9ca68085e8. No PR is open.

See [the report](../../NATIVE_DIMENSION_KEY_FIELDS.md) for complete results and limits.

`runs/commands-stable` and `runs/confirmation` contain two eight-pair complete-command cohorts. The confirmation reverses Dagger ordering. Warmup rounds are explicitly marked. `runs/check-only-control` isolates compilation; `runs/identical-policy-control` keeps both labeled arms on the original code. All observations, pressure and Go-GC counts are retained. `runs/main-validation` contains six fresh-process component pairs, exact binary hashes, before/after compatibility logs and the standalone race log.

`runs/profiles` contains separate CPU/runtime/wcprof diagnostics. `lock-discovery` retains earlier engine runtime traces with wcprof enabled and disabled. Instrumented timings are not benchmark observations; concurrent wait and CPU totals are not additive wall time.

`engine` records the exact build, controlled policy callback, original baseline overlays and hashes. Every replacement source is mirrored under `engine/source-mirror`; its map records the uncompressed source hash. The production patch only adds two struct tags. The dynamic callback, atomic flag and HTTP handler are diagnostics. Test binaries and the engine binary are excluded.

`retained-cache` verifies six native Rust histories after the preserved-volume restart. The helper prepares the current source, then demands complete reuse. The fixture archive contains final Cargo sources and configuration, excluding targets and Git data. Drivers generate fresh random source edits. Original measurements require the native Rust module 3cd40e5928563ade3ea1cd21ab9924cd03d88fc3, Rust 1.77.2 and the recorded CLI/engine overlay setup; update absolute paths when rebuilding. Initialize a local Git boundary in each fixture so default-path resolution has the same scope.

Initial harness failures remain under `initial-harness`. They include outdated test API calls, typed-response assertions and a source overlay that initially omitted existing experimental helpers. The final baseline preserves those helpers and changes only the two getter policies.

Direct getter reads are enabled for subsequent work on the owned engine; final idle state is recorded in `runs/final-runtime-state.json`. Profiling and other temporary modes are off, and ordinary snapshot collection remains enabled. This experiment does not complete the native Rust-cache roadmap.
''')

files = sorted(path for path in root.rglob('*') if path.is_file())
(root / 'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(root)) + '\n' for path in files))
print(json.dumps(dict(files=len(files), bytes=sum(path.stat().st_size for path in files), fixture_source_files=count, max_file_bytes=max(path.stat().st_size for path in files))))
