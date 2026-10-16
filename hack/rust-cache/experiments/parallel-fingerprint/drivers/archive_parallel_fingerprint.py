from pathlib import Path
import gzip, hashlib, json, shutil

base = Path('/tmp/rust-cache-sipsma-review')
root = Path('hack/rust-cache/experiments/parallel-fingerprint')
root.mkdir(exist_ok=False)

def copy(path, relative):
    target = root / relative
    if path.suffix in ['.go', '.log', '.ndjson', '.txt', '.trace'] or path.name.endswith('.cache.json'):
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
        if not path.is_file() or any(part in ['.git', 'target'] for part in path.relative_to(source).parts):
            continue
        if path.suffix in ['.test', '.db'] or path.name == 'dagger-engine':
            continue
        copy(path, str(Path(label) / path.relative_to(source)))

for name in ['prepare_parallel_fingerprint.py', 'prepare_parallel_fingerprint_engine.py', 'archive_parallel_fingerprint.py', 'check_native_discovery_current_reuse.py', 'restart_owned_engine_clean.py', 'local_cli_collector.py', 'native_batch_runtime_inspect.go']:
    copy(base / name, 'drivers/' + name)
tree(base / 'parallel-fingerprint', 'runs')
tree(base / 'parallel-fingerprint-engine', 'engine')
tree(base / 'native-discovery-retained-oct16-parallel-serial', 'retained-cache')
manifest = json.loads((base / 'parallel-fingerprint-engine/manifest.json').read_text())
mirrors = {}
for logical, item in manifest.items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest() == item['sha256'], logical
    if logical.startswith('/tmp/dagger-filesync-snapshot-seeds/'):
        relative = 'dagger/' + logical.removeprefix('/tmp/dagger-filesync-snapshot-seeds/')
    else:
        assert logical.startswith('/tmp/containerd-gc-source/'), logical
        relative = 'containerd/' + logical.removeprefix('/tmp/containerd-gc-source/')
    mirrors[logical] = dict(archived=copy(Path(item['replacement']), 'engine/source-mirror/' + relative), sha256=item['sha256'])
(root / 'engine/source-mirror.json').write_text(json.dumps(mirrors, indent=2) + '\n')
(root / 'README.md').write_text('''# Parallel fingerprint scan: not selected

See [the report](../../NATIVE_PARALLEL_FINGERPRINT.md). The component improvement does not establish a consistent full-command gain; serial scanning remains selected. No PR is opened and the upstream proposal count remains eight.

`runs` contains before/after source, exact-byte reference tests, race logs, six fresh-process component pairs, an eight-pair/four-workload full-command series, a listing-only confirmation and six separate profile captures. Every timed command edits a used Rust value. Orders are balanced and randomized per workload; all admitted observations and source values are retained. Instrumented timings are not part of the cohorts. The confirmation reverses the initial favorable listing conclusion.

`engine` records the actual binary hash, build, mode switch and all replacement source hashes. Sources are mirrored under `engine/source-mirror`; the JSON map records each uncompressed source hash. The serial implementation is unchanged apart from its diagnostic name. Parallel mode is off by default and remains off in the final state. Binaries, volumes, targets and Git metadata are excluded.

`retained-cache` verifies six histories after the preserved-volume restart. It prepares any last edit not compiled by Dagger, then requires complete reuse. These unchanged checks are correctness evidence only. Fixture source topology is in the preceding [dimension-key archive](../artifact-dimension-key-fields/); selected configurations are in [native-discovery-selected](../native-discovery-selected/runs/selection.json). Update absolute paths when rerunning. The module is da1ae47b6c96a3117de303b7584d028e35166530 with Rust 1.77.2.

The final runtime state and the rejection decision are in `runs/final-runtime-state.json` and `runs/status.json`. The broader native Rust-cache goal remains active and incomplete.
''')
files = sorted(path for path in root.rglob('*') if path.is_file())
(root / 'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(root)) + '\n' for path in files))
print(json.dumps(dict(files=len(files), bytes=sum(path.stat().st_size for path in files), max_file_bytes=max(path.stat().st_size for path in files))))
