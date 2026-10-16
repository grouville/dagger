from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
experiment = base / 'native-discovery-selected'
root = Path('hack/rust-cache/experiments/native-discovery-selected')
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

def tree(source, label):
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if not path.is_file() or any(part in ['.git', 'target'] for part in relative.parts):
            continue
        if path.suffix in ['.test', '.db']:
            continue
        if path.name == '14685.json':
            metadata = json.loads(path.read_text())
            body = metadata.pop('body')
            metadata['body_sha256'] = hashlib.sha256(body.encode()).hexdigest()
            metadata['summary'] = 'Removes the final filesystem-wide shutdown flush; the PR explicitly accepts a host-crash durability tradeoff. Not applied to this engine.'
            destination = root / label / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(metadata, indent=2) + '\n')
        else:
            copy(path, str(Path(label) / relative))

for name in [
    'measure_native_discovery_selected.py',
    'profile_native_discovery_selected.py',
    'verify_native_discovery_selected.py',
    'verify_native_discovery_selected_compile.py',
    'verify_native_discovery_selected_cross_module.py',
    'check_native_discovery_current_reuse.py',
    'local_cli_collector.py', 'native_batch_runtime_inspect.go',
    'rust_packages_cache_inspect.go', 'archive_native_discovery_selected.py',
]:
    copy(base / name, 'drivers/' + name)

for name in ['paired', 'profiles', 'cross-module', 'upstream-review']:
    tree(experiment / name, name)
for path in experiment.iterdir():
    if path.is_file():
        copy(path, 'runs/' + path.name)
tree(base / 'native-discovery-selected-oracle', 'validation/oracle')
tree(base / 'native-discovery-selected-compile', 'validation/public-checks')
tree(base / 'native-discovery-retained-oct16-selected', 'validation/retained-cache')

for arm, directory in [('before', Path('/tmp/dagger-rust-native-fused-artifact-inputs')), ('after', Path('/tmp/dagger-rust-native-discovery-current'))]:
    for name in ['main.dang', 'dagger-module.toml', 'compiler/go.mod', 'compiler/go.sum']:
        copy(directory / name, 'source/' + arm + '/' + name)
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=directory), str(directory)
diff = subprocess.check_output(['git', 'diff', '3cd40e5928563ade3ea1cd21ab9924cd03d88fc3', 'da1ae47b6c96a3117de303b7584d028e35166530', '--', 'main.dang'], cwd='/tmp/dagger-rust-native-discovery-current')
target = root / 'source/module.patch.gz'
with target.open('wb') as raw:
    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as output:
        output.write(diff)

(root / 'README.md').write_text('''# Selected native package discovery

The [report](../../NATIVE_DISCOVERY_SELECTED.md) selects Rust-module da1ae47b6c96a3117de303b7584d028e35166530, replacing 3cd40e5928563ade3ea1cd21ab9924cd03d88fc3. The compiler tree is identical. The native backend remains experimental and opt-in; this does not complete the broader roadmap.

`paired` contains eight balanced randomized before/after/Cargo pairs for each of four workloads: 96 measured commands plus 12 preparation commands. Metadata records the random seed, workload-specific orders, module and engine revisions, all heap/CPU/pressure counters, and the fresh numeric source value for every run. Profiling stays off during timing. Every admitted observation is kept, including a candidate check overlapping snapshot collection.

`profiles` contains six separate diagnostic captures: engine/CLI CPU, CLI runtime trace, wcprof and bounded goroutine snapshots. Final wcprof captures have zero dropped events and open operations. Diagnostic timings are excluded from the paired comparison.

`validation/oracle` exercises sixteen discovery cases against Cargo on a fresh namespace. `validation/public-checks` verifies normal public collection checks through a source edit, invalid Rust, repair and reversion, with exact native compiled-result reuse. `cross-module` immediately requires 2/2 hits while switching between the original and candidate, with no preparation step. `validation/retained-cache` preserves initial hit counts and then demands complete reuse in all six older native histories.

`runs/selection.json` preserves all six fixture configurations before and after selection. Fixture source topology and the full diagnostic engine source replacements are archived in the preceding [dimension-key experiment](../artifact-dimension-key-fields/); update absolute paths when rebuilding. The selected engine binary hash is 4699d50526e3b2c358d0467c6cacc79aff1061b9295754648713a21104524c65. The source and patch here capture the exact module delta. The compiler directory is unchanged and available at the recorded Git revisions.

`upstream-review` records Sipsma's latest twenty PRs and the exact shutdown PR head. Its body is referenced by URL and SHA-256 rather than reproduced here. That shutdown patch is not applied. The initial output-parent failure is retained under `runs`; it ran zero benchmark commands. Binaries, cache volumes, targets and Git metadata are excluded.

Final state and validation status are in `runs/final-runtime-state.json` and `runs/status.json`. Direct dimension-key reads stay selected; temporary profiling and measurement controls are restored. There are still eight prepared Dagger proposals and no new upstream PR opened by this experiment.
''')

files = sorted(path for path in root.rglob('*') if path.is_file())
(root / 'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(root)) + '\n' for path in files))
print(json.dumps(dict(files=len(files), bytes=sum(path.stat().st_size for path in files), max_file_bytes=max(path.stat().st_size for path in files))))
