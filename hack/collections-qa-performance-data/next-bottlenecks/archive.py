"""Archive an explicit allowlist of small, non-secret performance evidence."""
from pathlib import Path
import hashlib
import gzip
import json
import shutil

LAB = Path('/tmp/collections-perf')
DEST = Path('/home/dagger/dag/hack/collections-qa-performance-data/next-bottlenecks')
DEST.mkdir(exist_ok=True)
copied = []
compressed = {}


def copy(source, target):
    source = LAB / source
    target = DEST / target
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('large artifact requires a separate digest: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.name == 'samples.json' and source.stat().st_size > 256 * 1024:
        data = source.read_bytes()
        plain_target = target
        target = target.with_suffix(target.suffix + '.gz')
        target.write_bytes(gzip.compress(data, compresslevel=6, mtime=0))
        # Remove only an earlier copy made by this same archive script.
        if plain_target.exists():
            assert plain_target.read_bytes() == data
            plain_target.unlink()
        compressed[str(target.relative_to(DEST))] = {
            'encoding': 'gzip', 'original_sha256': hashlib.sha256(data).hexdigest(),
            'original_bytes': len(data),
        }
    else:
        shutil.copyfile(source, target)
    copied.append(str(target.relative_to(DEST)))


def files(folder, names, target=None):
    for name in names:
        copy(folder + '/' + name, (target or folder) + '/' + name)


files('warm-audit', ['report.md', 'module-cwd.patch', 'module-manifest.json', 'benchmark.py'], 'go-module')
files('warm-audit/measured', ['results.json', 'summary.json', 'profile-summary.json', 'qa.json', 'qa.stdout', 'qa.stderr'], 'go-module/measured')
for variant in ['batch-index', 'batch-index-lazy']:
    files('warm-audit/' + variant, ['report.md', 'source-provenance.json', 'results.json',
                                   'summary.json', 'benchmark.py'], variant)
    for path in sorted((LAB / 'warm-audit' / variant).glob('*.log')):
        copy(str(path.relative_to(LAB)), variant + '/' + path.name)

files('sdk-edit-audit', ['findings.md', 'retained-commit-review.md',
                        'dang-retain-object-directives.patch', 'engine-remove-directive-pass.patch',
                        'dang-skip-discarded-functions.patch', 'dang-combined-tests.patch',
                        'candidate-test.log', 'control-test.log', 'combined-test.log',
                        'pairs.py', 'pairs.log'], 'dang')
files('sdk-edit-audit/pairs', ['results.json', 'summary.json'], 'dang/pairs')
files('sdk-edit-audit', ['shutdown-loss-test.patch', 'shutdown-control-test.log',
                        'shutdown-candidate-test.log'], 'shutdown-overlap')
files('shutdown-overlap', ['prepare.py', 'pairs.py', 'pairs.log'], 'shutdown-overlap')
files('shutdown-overlap/pairs', ['results.json', 'summary.json'], 'shutdown-overlap/pairs')

cold = 'post-rebase-io/cold-scratch-audit'
files(cold, ['prepare.py', 'benchmark.py', 'prepared.json', 'result.md',
             'retained-commit-review.md'], 'cold-scratch')
files(cold + '/cold-scratch-abba', ['summary.json', 'provenance.json'], 'cold-scratch/runs')
for path in sorted((LAB / cold / 'cold-scratch-abba').glob('dagger-engine.*/**/*')):
    if path.is_file() and path.name in {'result.json', 'summary.json', 'samples.json', 'stdout.txt'}:
        copy(str(path.relative_to(LAB)), 'cold-scratch/runs/' + str(path.relative_to(LAB / cold / 'cold-scratch-abba')))

files('cli-startup-audit', ['findings.md', 'fs-prefix.patch', 'overlay.json',
                           'engine_telemetry_labels.go', 'internal_fsutil_fs.go',
                           'engine_client_client.go'], 'cli-startup')
copy('open-prs-current.json', 'open-prs-current.json')
copy('perf-pr-status-current.json', 'perf-pr-status-current.json')

# Results from the complete experimental SDK stack and real execution loop.
files('sdk-edit-audit', ['combined-integration.log', 'combined-directives-correct-cwd.log'], 'dang')
files('sdk-edit-audit/ts-static', ['design.md', 'results.md', 'prepare.py', 'validate.py',
    'benchmark.py', 'engine-manifest.json', 'pinned-inputs.json', 'helper.go.fragment'], 'ts-static')
files('sdk-edit-audit/ts-static/measurements', ['results.json', 'summary.json', 'profile-summary.json'], 'ts-static/measurements')
files('sdk-edit-audit/ts-static/validation', ['results.json'], 'ts-static/validation')
for path in sorted((LAB / 'sdk-edit-audit/ts-static/validation').iterdir()):
    if path.suffix in {'.out', '.err'}:
        copy(str(path.relative_to(LAB)), 'ts-static/validation/' + path.name)
files('sdk-edit-audit/ts-generic', ['README.md', 'freshness-design.md', 'sdk-emitter-prototype.patch',
    'engine-guard-prototype.patch', 'prepare.py', 'unit.log', 'generator-compile.log', 'runtime-compile.log'], 'ts-generic')
files('warm-audit/list-workspace-reuse', ['report.md', 'pipeline-review.md', 'workspace-reuse.patch',
    'benchmark.py', 'test.log'], 'cli-workspace-reuse')
files('warm-audit/list-workspace-reuse/measured', ['manifest.json', 'results.json', 'summary.json',
    'paired-summary.json', 'profile-summary.json', 'restoration.json'], 'cli-workspace-reuse/measured')
files('warm-audit/backend-go-cache', ['report.md', 'benchmark.py', 'cache-mounts.patch',
    'main.before.go', 'main.after.go', 'provenance.json', 'baseline-exec-phases.json'], 'backend-go-cache')
files('warm-audit/backend-go-cache/measured', ['manifest.json', 'results.json', 'summary.json',
    'paired-edit-summary.json', 'profile-summary.json', 'restoration.json'], 'backend-go-cache/measured')
for path in sorted((LAB / 'warm-audit/backend-go-cache/measured/correctness').glob('*/*')):
    if path.name in {'stdout.txt', 'stderr.txt', 'result.json'}:
        copy(str(path.relative_to(LAB)), 'backend-go-cache/measured/correctness/' + str(path.relative_to(LAB / 'warm-audit/backend-go-cache/measured/correctness')))
files('warm-audit/execution-matrix', ['benchmark.py', 'report.md'], 'execution')
files('execution-first', ['provenance.json', 'restoration.json', 'results.json', 'summary.json',
    'edited-profile-analysis.txt'], 'execution/measured')
for path in sorted((LAB / 'execution-first/correctness').glob('*/*')):
    if path.name in {'stdout.txt', 'stderr.txt', 'result.json'}:
        copy(str(path.relative_to(LAB)), 'execution/measured/correctness/' + str(path.relative_to(LAB / 'execution-first/correctness')))

files('sdk-edit-audit/ts-static/cold-audit', ['cold_abba.py', 'results.md', 'results.json'], 'ts-static/cold')
for run in ['cold-ts-static-abba', 'cold-ts-static-extra-ab']:
    folder = 'sdk-edit-audit/ts-static/cold-audit/' + run
    files(folder, ['prepared.json', 'summary.json'], 'ts-static/cold/' + run)
    for path in sorted((LAB / folder).glob('dagger-engine.*/**/*')):
        if path.is_file() and path.name in {'result.json', 'summary.json', 'samples.json', 'stdout.txt'}:
            copy(str(path.relative_to(LAB)), 'ts-static/cold/' + run + '/' + str(path.relative_to(LAB / folder)))

files('warm-audit/constructor-cache-audit', ['report.md', 'constructor-only-source.patch'], 'constructor-cache-audit')
files('sdk-edit-audit/typedef-bulk', ['results.md', 'bench.log', 'bench-summary.json',
    'engine-consumer-final.patch', 'engine-manifest.json', 'source-manifest.json',
    'consumer-unit.log', 'benchmark.py', 'typedef_bulk_bench_original.go.txt'], 'typedef-bulk')
files('sdk-edit-audit/typedef-bulk/measurements', ['results.json', 'summary.json', 'profile-summary.json'], 'typedef-bulk/measurements')

files('sdk-edit-audit/cloud-coalescing', ['README.md', 'prototype.patch', 'source-manifest.json', 'overlay.json', 'prepare.py', 'unit.log'], 'cloud-coalescing')

# NEVER recurse into telemetry-relay. Its spool and admin-token contain secrets.
# Explicit public source/test/statistic names only. No config, admin files or spool.
files('telemetry-relay', ['README.md', 'engine-handoff-review.md', 'relay-v1-source.go',
    'relay-v1-source_test.go', 'relay-v1-validation.json', 'relay-v2-source.go',
    'relay-v2-source_test.go', 'relay-v2-validation.json', 'benchmark.py', 'run_trial.py', 'run_load.py'], 'telemetry-relay')
files('telemetry-relay', ['cloud-coalescing-review.md', 'load-driver-review.md', 'load-v2-approval-comparison.md', 'load-v2-launch-blocked.json'], 'telemetry-relay')
files('telemetry-relay/ts-static-trial-2', ['before-crash.json', 'crash-disk-counts.json',
    'recovered.json', 'recovery.json', 'recovery-check.out'], 'telemetry-relay/trial-2')
files('telemetry-relay/ts-static-trial-2/measurements', ['provenance.json', 'results.json', 'summary.json',
    'async-shutdown.txt', 'direct-shutdown.txt', 'sync-shutdown.txt',
    'async-wcprof.txt', 'direct-wcprof.txt', 'sync-wcprof.txt'], 'telemetry-relay/trial-2/measurements')
copy('archive-next-bottlenecks.py', 'archive.py')
(DEST / 'archive-manifest.json').write_text(json.dumps({
    'files': {name: hashlib.sha256((DEST / name).read_bytes()).hexdigest() for name in sorted(copied)},
    'compressed_sources': compressed,
    'excludes': ['private telemetry spool', 'credentials', 'large binaries', 'raw binary profiles'],
}, indent=2) + '\n')
print(json.dumps({'archived_files': len(copied)}))
