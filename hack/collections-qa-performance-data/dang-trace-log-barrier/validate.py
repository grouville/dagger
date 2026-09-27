#!/usr/bin/env python3
"""Frozen offline gates. No Docker, engine invocation, or production Cloud call."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, time

LAB = Path(__file__).resolve().parent
ROOT = Path('/home/dagger/dag')
GO = Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
SERVER_TESTS = (
    'TestSessionTraceLogBarrierAllOriginsAndFinalMetrics',
    'TestSessionTraceLogBarrierRetainsOrderAndErrors',
    'TestSessionTraceLogBarrierCancellation',
    'TestSessionTraceLogBarrierDoesNotJoinUnrelatedMetricDrain',
    'TestSessionTraceLogBarrierRequiresExistingClient',
    'TestSessionTraceLogBarrierJoinsRealLogExport',
    'TestClientShutdownMetricsCollectsEachReaderOnce',
    'TestClientShutdownMetricsPreservesFinalUpdateAfterExplicitFlush',
    'TestClientShutdownMetricsWaitsForFinalExportAndHonorsCancellation',
    'TestClientShutdownMetricsReturnsFinalCollectionErrorAndReleasesReader',
    'TestClientShutdownMetricsFailureStillClosesBothReaders',
    'TestClientShutdownMetricsCancellationStillClosesSecondReader',
    'TestClientRuntimeReclamationDrainsMetricsBeforeUnpublish',
    'TestTelemetryRoutesClientsAndAncestorsExactlyOnce',
    'TestCallPayloadReachesCloudOnce',
)
COMPATIBILITY = {
    'github.com/dagger/dagger/core': ('TestParseCallerCalleeRefs',),
    'github.com/dagger/dagger/core/schema': ('TestCurrentTypeDefsReturnAllTypes',),
    'github.com/dagger/dagger/core/sdk/dang/v2': (
        'TestReportDangSourceError', 'TestDangSourceErrorKeepsGraphQLExtraction',
        'TestDangSourceMessage', 'TestDangSourceMessageFromModule',
    ),
}
SERVER_PACKAGE = 'github.com/dagger/dagger/engine/server'
NEGATIVE = SERVER_TESTS[0]
PATTERN = '^(' + '|'.join(SERVER_TESTS) + ')$'
COMPAT_PATTERN = '^(' + '|'.join(n for names in COMPATIBILITY.values() for n in names) + ')$'
STEPS = (
    {'name': 'negative-full-metric-witness', 'overlay': 'negative-overlay.json',
     'pattern': '^' + NEGATIVE + '$', 'packages': ['./engine/server'], 'race': False},
    {'name': 'candidate-normal', 'overlay': 'test-overlay.json',
     'pattern': PATTERN, 'packages': ['./engine/server'], 'race': False},
    {'name': 'candidate-race', 'overlay': 'test-overlay.json',
     'pattern': PATTERN, 'packages': ['./engine/server'], 'race': True},
    {'name': 'interface-and-dang-compatibility', 'overlay': 'test-overlay.json',
     'pattern': COMPAT_PATTERN, 'packages': ['./core', './core/schema', './core/sdk/dang/v2'], 'race': False},
)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def commands():
    return [
        [str(GO), 'test', '-json', '-p=1', '-parallel=4', '-mod=readonly',
         '-overlay=' + str(LAB / step['overlay']), '-count=1', '-timeout=180s',
         *(['-race'] if step['race'] else []), '-run=' + step['pattern'], *step['packages']]
        for step in STEPS
    ]


def verify_inputs():
    frozen = json.loads((LAB / 'validation-inputs.json').read_text())
    for relative, digest in frozen['lab_files'].items():
        assert sha(LAB / relative) == digest, 'changed prototype input: ' + relative
    for relative, digest in frozen['repository_files'].items():
        assert sha(ROOT / relative) == digest, 'changed repository input: ' + relative
    assert sha(GO) == frozen['go_sha256'], 'changed Go toolchain'
    # Historical source HEAD is provenance only; unrelated docs commits need
    # not invalidate frozen exact source/dependency bytes.
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    frozen = verify_inputs()
    if not args.run:
        print(json.dumps({'execute': False, 'steps': list(STEPS), 'commands': commands(),
                          'engine_calls': 0, 'production_cloud_calls': 0,
                          'local_http': 'only the existing httptest Cloud receiver',
                          'input_manifest_sha256': sha(LAB / 'validation-inputs.json')}, indent=2))
        return
    output = LAB / 'validation-v1'
    assert not output.exists(), 'preserve prior attempt; do not overwrite or retry'
    output.mkdir()
    rows = []
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('DAGGER_', '_DAGGER_', 'OTEL_')) or key in ('TRACEPARENT', 'TRACESTATE'):
            del env[key]
    env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
    for step, command in zip(STEPS, commands()):
        start = time.monotonic()
        log_path = output / (step['name'] + '.private.log')
        row = {'step': step['name'], 'command': command, 'started': True}
        rows.append(row)
        save(output, rows, frozen)
        with log_path.open('wb') as stream:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=900)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = None
                row['timed_out'] = True
        events = []
        for line in log_path.read_text(errors='replace').splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        output_text = ''.join(e.get('Output', '') for e in events)
        passed = [(e.get('Package'), e['Test']) for e in events if e.get('Action') == 'pass' and 'Test' in e]
        failed = [(e.get('Package'), e['Test']) for e in events if e.get('Action') == 'fail' and 'Test' in e]
        package_failed = [e.get('Package') for e in events if e.get('Action') == 'fail' and 'Test' not in e]
        skipped = [(e.get('Package'), e['Test']) for e in events if e.get('Action') == 'skip' and 'Test' in e]
        if step['name'] == 'negative-full-metric-witness':
            valid = (code not in (None, 0) and failed == [(SERVER_PACKAGE, NEGATIVE)]
                     and re.search(r'expected:\s*0\s*\n.*actual\s*:\s*2', output_text) is not None
                     and 'client root' in output_text and not skipped)
        else:
            expected = ({SERVER_PACKAGE: SERVER_TESTS} if step['name'].startswith('candidate-') else COMPATIBILITY)
            expected_roots = {(package, name) for package, names in expected.items() for name in names}
            actual_roots = {(package, name) for package, name in passed if '/' not in name}
            valid = code == 0 and actual_roots == expected_roots and not failed and not package_failed and not skipped
        row.update(exit_code=code, wall_seconds=time.monotonic()-start,
                   passed=passed, failed=failed, package_failed=package_failed, skipped=skipped,
                   expected_outcome=bool(valid), private_log_sha256=sha(log_path))
        save(output, rows, frozen)
        print(json.dumps({k: v for k, v in row.items() if k != 'command'}), flush=True)
        assert valid, 'unexpected gate; preserve this attempt and diagnose before any new execution'


def save(output, rows, frozen):
    (output / 'results.json').write_text(json.dumps({
        'steps': rows, 'input_manifest_sha256': sha(LAB / 'validation-inputs.json'),
        'driver_sha256': sha(Path(__file__)), 'source_head_at_freeze': frozen['source_head'],
        'all_steps_finished': len(rows) == len(STEPS) and all(r.get('expected_outcome') for r in rows),
        'engine_calls': 0, 'production_cloud_calls': 0,
    }, indent=2) + '\n')

if __name__ == '__main__':
    main()
