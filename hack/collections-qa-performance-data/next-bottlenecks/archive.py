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
source_copies = {}


def copy(source, target):
    source = LAB / source
    target = DEST / target
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('large artifact requires a separate digest: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == '.go':
        # These are frozen evidence copies, not packages in Dagger's Go module.
        go_target = target
        target = target.with_suffix(target.suffix + '.txt')
        source_copies[str(target.relative_to(DEST))] = str(go_target.relative_to(DEST))
        if go_target.exists():
            assert go_target.read_bytes() == source.read_bytes()
            go_target.unlink()
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
files('telemetry-relay/ts-static-load-v2', ['report.md', 'verification.json', 'process-stop-check.json',
    'provenance.json', 'results.json', 'paired-summary.json', 'burst-summary.json'], 'telemetry-relay/load-v2')
files('telemetry-relay', ['load-independent-review.md'], 'telemetry-relay')
files('sdk-edit-audit/cloud-coalescing', ['correctness-review.md'], 'cloud-coalescing')
files('relay-fairness', ['README.md', 'fairness.patch', 'source-manifest.json', 'fairness_test.go',
    'control-test.log', 'candidate-test.log', 'race-test.log', 'main.go', 'main_test.go',
    'control.go.txt', 'control-overlay.json'], 'relay-fairness')

# New UX evidence: manifests are explicit source/statistic allowlists, never spools.
def from_allowlist(relative, target):
    manifest = json.loads((LAB / relative).read_text())
    root = Path(manifest.get('root', manifest.get('base', str((LAB / relative).parent))))
    assert root.is_relative_to(LAB)
    for entry in manifest['files']:
        name = entry['path'] if isinstance(entry, dict) else entry
        if Path(name).is_absolute():
            name = str(Path(name).relative_to(root))
        path = root / name
        assert path.is_relative_to(root) and '..' not in Path(name).parts
        digest = entry.get('sha256') if isinstance(entry, dict) else manifest.get('sha256', {}).get(name)
        if digest:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, str(path)
        copy(str(path.relative_to(LAB)), target + '/' + name)
    copy(relative, target + '/source-allowlist.json')

from_allowlist('sdk-edit-audit/cloud-coalescing/live/archive-allowlist.json', 'cloud-coalescing/live')
copy('sdk-edit-audit/cloud-coalescing/live/upstream-pr-refresh.json', 'upstream-pr-refresh.json')
from_allowlist('warm-audit/constructor-cache-audit/archive-manifest.json', 'constructor-cache-audit')
from_allowlist('warm-audit/go-sdk-pr36-adapter/archive-manifest.json', 'go-sdk-pr36-adapter')
from_allowlist('sparse-export/archive-allowlist.json', 'sparse-export')
files('sparse-export', ['replay.py', 'no-git-replay/result.json', 'no-git-replay/stdout.txt', 'no-git-replay/stderr.txt'], 'sparse-export')
files('cli-key-scaling', ['report.md', 'build.py', 'measure.py', 'build-provenance.json', 'results.json', 'summary.json', 'independent-review.md', 'vertical.py', 'ux.py', 'analyze_phases.py', 'local-only-source-audit.md'], 'cli-key-scaling')
files('cli-key-scaling/vertical-fixture', ['main.dang', 'dagger.json'], 'cli-key-scaling/vertical-fixture')
for trial in ['vertical-local-disk-v2', 'vertical-local-disk-v3']:
    names = ['driver.py.txt', 'results.json', 'summary.json', 'provenance.json', 'phase-summary.json']
    if trial.endswith('v2'): names += ['measurement-caveats.json']
    files('cli-key-scaling/' + trial, names, 'cli-key-scaling/' + trial)
    for variant in ['baseline', 'candidate']:
        for outcome in ['fail', 'restore']:
            files('cli-key-scaling/' + trial + '/correctness/' + outcome + '-' + variant, ['stdout.txt', 'stderr.txt'], 'cli-key-scaling/' + trial + '/correctness/' + outcome + '-' + variant)

files('sparse-export', ['final-review.md'], 'sparse-export')
files('cli-key-scaling', ['baseline-tests.log', 'candidate-tests.log', 'baseline-overlay.json', 'artifact_list_baseline.go', 'vertical-methodology-review.md', 'service-lock.py', 'service-lock-source-audit.md', 'service-lock-source-provenance.json', 'service-lock-write.py', 'service-lock-web-finite.py', 'filtered-followup.py', 'filtered-followup-original-v1.py', 'filtered-followup-plan.md'], 'cli-key-scaling')
for pair in range(6):
    for variant in ['baseline', 'candidate']:
        files('cli-key-scaling', [f'{pair:02d}-{variant}.log'], 'cli-key-scaling')
files('cli-key-scaling/ux-local-production-v2', ['driver.py.txt', 'results.json', 'summary.json', 'provenance.json', 'restoration.json', 'phase-summary.json', 'profile/expanded-checks/analysis.txt'], 'cli-key-scaling/ux-local-production-v2')
for case in ['comment', 'rename', 'add', 'restore']:
    for variant in ['baseline', 'candidate']:
        files('cli-key-scaling/ux-local-production-v2/edits/edit-' + case + '-' + variant, ['stdout.txt'], 'cli-key-scaling/ux-local-production-v2/edits/edit-' + case + '-' + variant)
for trial in ['service-lock-v3', 'service-lock-write-v1', 'service-lock-web-finite-v1']:
    files('cli-key-scaling/' + trial, ['driver.py.txt', 'provenance.json', 'results.json'], 'cli-key-scaling/' + trial)
files('cli-key-scaling/service-lock-v3', ['preserved-inputs.json', 'phase-summary.json'], 'cli-key-scaling/service-lock-v3')
for trial in ['service-lock-write-v1', 'service-lock-web-finite-v1']:
    files('cli-key-scaling/' + trial, ['source-preserved.json'], 'cli-key-scaling/' + trial)
for trial in ['filtered-followup-v1', 'filtered-identical-memstats-v1']:
    files('cli-key-scaling/' + trial, ['driver.py.txt', 'provenance.json', 'results.json', 'summary.json', 'source-verification.json'], 'cli-key-scaling/' + trial)
files('cli-key-scaling/filtered-followup-v1', ['analysis.md'], 'cli-key-scaling/filtered-followup-v1')
files('deferred-defaults', ['prototype.patch', 'source-manifest.json', 'STATUS.md', 'prepare_fixtures.py', 'test_fixtures.py', 'unit.log', 'unit-scoped.log', 'unit-final.log', 'unit-final-before-fixture-fix.log'], 'deferred-defaults')
files('sdk-edit-audit/git-advertisement-audit', ['review.md', 'saved-profile-git-summary.json', 'vanity-profiling.patch', 'vanity-manifest.json', 'vanity-overlay.json'], 'git-advertisement-audit')
files('snapshot-sparse-flush', ['report.md', 'team-notes.md'], 'snapshot-sparse-flush')

from_allowlist('attachables-lifetime/archive-manifest.json', 'attachables-lifetime')
files('cli-key-scaling', ['service-lifetime-ab.py', 'filtered-engine-allocation.py'], 'cli-key-scaling')
files('cli-key-scaling/service-lifetime-ab-v1', ['driver.py.txt', 'provenance.json', 'results.json', 'summary.json', 'source-preserved.json', 'phase-summary.json'], 'cli-key-scaling/service-lifetime-ab-v1')
files('cli-key-scaling/filtered-identical-memstats-v1', ['analysis.md'], 'cli-key-scaling/filtered-identical-memstats-v1')
from_allowlist('cli-key-scaling/filtered-engine-allocation-v1/archive-allowlist.json', 'cli-key-scaling/filtered-engine-allocation-v1')
git_audit = LAB / 'sdk-edit-audit/git-advertisement-audit'
for name in (git_audit / 'archive-allowlist.txt').read_text().splitlines():
    assert Path(name).name == name
    copy('sdk-edit-audit/git-advertisement-audit/' + name, 'git-advertisement-audit/' + name)

copy('archive-next-bottlenecks.py', 'archive.py')
(DEST / 'archive-manifest.json').write_text(json.dumps({
    'files': {name: hashlib.sha256((DEST / name).read_bytes()).hexdigest() for name in sorted(copied)},
    'compressed_sources': compressed,
    'go_source_copies': source_copies,
    'excludes': ['private telemetry spool', 'credentials', 'large binaries', 'raw binary profiles'],
}, indent=2) + '\n')
print(json.dumps({'archived_files': len(copied)}))
