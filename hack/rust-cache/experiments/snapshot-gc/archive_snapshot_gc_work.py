from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile

base = Path('/tmp/rust-cache-sipsma-review')
source = base / 'snapshot-gc-causal'
root = Path('hack/rust-cache/experiments/snapshot-gc')
root.mkdir(exist_ok=False)


def copy(path, relative):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)


def compress(path, relative):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as out:
            out.write(path.read_bytes())


for name in ['prepare_snapshot_gc_diagnostic.py', 'measure_snapshot_gc_contention.py',
             'measure_snapshot_gc_prune.py', 'summarize_snapshot_gc_work.py', 'archive_snapshot_gc_work.py']:
    copy(base / name, name)

copy(base / 'verify_snapshot_gc_prune.py', 'verify_snapshot_gc_prune.py')
for name in ['analysis.json', 'progress.json', 'engine.go.mod', 'engine.go.sum', 'final-engine-state.json', 'validation.json']:
    copy(source / name, name)

# The diagnostic engine uses a local Dang source copy rather than a published
# revision. Preserve that build input too; exclude developer dot directories.
dang_source = base / 'dang-module-blueprint-content-key'
with tarfile.open(root / 'dang-build-input.tar.gz', 'w:gz') as archive:
    for path in sorted(dang_source.rglob('*')):
        relative = path.relative_to(dang_source)
        if path.is_file() and not any(part.startswith('.') for part in relative.parts):
            archive.add(path, arcname=str(relative), recursive=False)

for cohort in ['pilot', 'paired', 'upstream-prune-pairs', 'upstream-prune-pairs-initial-fixture-failure']:
    for path in sorted((source / cohort).iterdir()):
        if path.suffix in ['.ndjson', '.log']:
            compress(path, cohort + '/' + path.name + '.gz')
        else:
            copy(path, cohort + '/' + path.name)

for path in sorted(source.glob('*.log')):
    compress(path, 'validation/' + path.name + '.gz')
for path in sorted((source / 'install').iterdir()):
    if path.suffix == '.txt':
        compress(path, 'install/' + path.name + '.gz')
    else:
        copy(path, 'install/' + path.name)

logical_root = Path('/tmp/dagger-filesync-snapshot-seeds')
manifest = json.loads((source / 'manifest.json').read_text())
archived = {}
for logical, item in manifest.items():
    replacement = Path(item['replacement'])
    assert hashlib.sha256(replacement.read_bytes()).hexdigest() == item['sha256'], logical
    relative = Path(logical).relative_to(logical_root)
    destination = 'overlay-source/' + str(relative) + '.gz'
    compress(replacement, destination)
    archived[str(relative)] = dict(sha256=item['sha256'], archived_source=destination,
                                  original_replacement=item['replacement'])
(root / 'overlay-manifest.json').write_text(json.dumps(archived, indent=2) + '\n')

work = Path('/tmp/dagger-coalesce-snapshot-gc-upstream')
for name in ['server.go', 'cache_gc_wiring_test.go', 'cache_gc_wiring_bench_test.go']:
    compress(work / 'engine/server' / name, 'upstream-source/' + name + '.gz')
copy(source / 'upstream-before-overlay.json', 'upstream-source/before-overlay.json')
compress(source / 'upstream-main-server.go', 'upstream-source/main-server.go.gz')
patch = subprocess.check_output(['git', '-C', str(work), 'show', '--format=fuller', '--binary', 'HEAD'])
with (root / 'upstream-source/candidate.patch.gz').open('wb') as raw:
    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as out:
        out.write(patch)
revisions = dict(
    upstream='717589c9ccacbba7d3cf902647aa5c9ca68085e8',
    candidate=subprocess.check_output(['git', '-C', str(work), 'rev-parse', 'HEAD'], text=True).strip(),
    candidate_branch=subprocess.check_output(['git', '-C', str(work), 'branch', '--show-current'], text=True).strip(),
    engine_source=subprocess.check_output(['git', '-C', str(logical_root), 'rev-parse', 'HEAD'], text=True).strip(),
    engine_sha256='bd34b08b9c342bfb20b58a81d67cf442c95dbe668aca123503e2e7686b40137e',
    native_module='f73c5614a89968afa6f6000328e96ea33745fd93',
    no_pr_opened=True,
)
(root / 'revisions.json').write_text(json.dumps(revisions, indent=2) + '\n')
(root / 'README.md').write_text('''This archive supports [the collection-contention report](../../NATIVE_GC_CONTENTION.md) and [the standalone prune proposal](../../upstream-prs/skip-empty-snapshot-gc.md).

`paired/` contains eight rotating four-way edited-command comparisons. `pilot/` contains a separate profiled preparation round and one measured observation per arm. `analysis.json` checks scratch reclamation and reports per-operation wcprof timings. Ordinary containerd collection is deferred in every diagnostic arm and drained after every command. The final engine state records deferral and profiling restored to false. This diagnostic experiment does not measure a production scheduling change.

`upstream-prune-pairs/` contains six fresh-process before/after comparisons of the actual explicit metadata-prune path, using real temporary stores with zero or 1,000 retained empty snapshots. Production logging can split a benchmark name from its numeric result; the driver preserves and parses both. `validation.json` records exact test commands, expected exit codes and binary hashes. Both upstream regression subcases fail without the one-line patch. Seventeen final tests pass normally and under the race detector; eight diagnostic tests also pass with the shared fixture-report environment variable unset.

The initial benchmark trial fails because it tries to reuse a released session. It has no completed performance sample and is retained under `upstream-prune-pairs-initial-fixture-failure/`. The corrected benchmark creates one session per iteration. Initial race-runtime and diagnostic fixture-report failures are preserved in `validation/`; neither is discarded as a timing outlier. The minimal engine image needs a static race binary built with `-tags=netgo,osusergo -ldflags="-linkmode=external -extldflags=-static"`. Normal benchmark binaries use `CGO_ENABLED=0` on both arms.

For the standalone fix, check out the upstream revision in `revisions.json` and apply `upstream-source/candidate.patch.gz` with `git apply` after decompression. The description gives direct test and benchmark commands. The benchmark driver restores the production server file through a Go overlay for its baseline, keeping test and benchmark sources identical. Adjust its local paths and engine name before rerunning.

For the diagnostic engine, check out `engine_source` from `revisions.json`. Decompress each `overlay-manifest.json` replacement to a temporary path and construct a Go overlay mapping the checkout's logical filename to that replacement. Verify the uncompressed source hashes. Extract `dang-build-input.tar.gz` and update the local Dang replacement in `engine.go.mod`; keep its paired `engine.go.sum`. Build with that overlay and modfile. The original preparation script depends on earlier local experiment files; the archived replacements are the complete 44-file overlay and do not require those old paths. Diagnostic source and standalone upstream source are separate.

Large binaries are excluded. `SHA256SUMS` covers all other archived files. Engine, exec and Docker-parent CPU scopes overlap and must not be added together.
''')
files = sorted(path for path in root.rglob('*') if path.is_file())
(root / 'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(root)) + '\n' for path in files))
print(json.dumps(dict(files=len(files), bytes=sum(path.stat().st_size for path in files))))
