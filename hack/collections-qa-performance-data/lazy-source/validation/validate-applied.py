#!/usr/bin/env python3
"""Run only after the parent releases the exclusive build/test slot.

No engine builds, Dagger invocations, network workloads or Cloud calls.
The baseline must fail for the specific new regression, not a compiler/setup error.
Candidate unit/race tests run directly against the shared applied sources.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = Path('/home/dagger/dag')
SCHEMA_TESTS = r'^(TestContainerWithFileDefersSourceFailure|TestBuiltinMetadataConsumersStopOnFailure)$'
INTERFACE_TESTS = r'^(TestReconcileSignatureSnapshot.*|TestInterfaces|TestViewsFilterInterfacesWithHiddenFields|TestInterfaceFieldDeclarationOrder)$'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    expected = json.loads((HERE / 'applied-validation-inputs.json').read_text())
    actual = {path: sha(REPO / path) for path in expected['sourceSHA256']}
    if actual != expected['sourceSHA256']:
        raise SystemExit('Applied sources changed; review and refresh provenance before running.')
    if sha(HERE / 'container.baseline.go') != expected['baselineSourceSHA256']:
        raise SystemExit('Frozen baseline source changed.')
    if sha(HERE / 'container_source_lazy_test.go') != actual['core/schema/container_source_lazy_test.go']:
        raise SystemExit('Baseline regression overlay does not match applied test.')
    env = os.environ.copy()
    env['GOMAXPROCS'] = '4'
    env['CGO_ENABLED'] = '1'
    report = {
        'startedUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceSHA256': actual,
        'baselineSourceSHA256': expected['baselineSourceSHA256'],
        'commands': [],
        'status': 'running',
    }
    summary = args.output / 'results.json'

    def save():
        summary.write_text(json.dumps(report, indent=2) + '\n')

    def run(label, cmd, *, baseline=False):
        log = args.output / (label + '.jsonl')
        row = {'label': label, 'argv': cmd, 'log': str(log), 'startedUTC': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        report['commands'].append(row)
        save()
        started = time.monotonic()
        with log.open('w') as stream:
            proc = subprocess.run(cmd, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        row.update(exitCode=proc.returncode, seconds=time.monotonic() - started)
        raw = log.read_text()
        events = []
        for line in raw.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        failures = sorted({e.get('Test') for e in events if e.get('Action') == 'fail' and e.get('Test')})
        row['failedTests'] = failures
        if baseline:
            expected_failures = ['TestContainerWithFileDefersSourceFailure', 'TestContainerWithFileDefersSourceFailure/new', 'TestContainerWithFileDefersSourceFailure/restored']
            output = ''.join(e.get('Output', '') for e in events)
            test_lines = (REPO / 'core/schema/container_source_lazy_test.go').read_text().splitlines()
            construction_line = next(i for i, line in enumerate(test_lines, 1) if 'require.NoError(t, srv.Select(ctx, parent, &child' in line)
            row['expectedFailureConfirmed'] = proc.returncode == 1 and failures == expected_failures and 'must not contain a directory' in output and f'container_source_lazy_test.go:{construction_line}' in output
            accepted = row['expectedFailureConfirmed']
        else:
            passed = [e for e in events if e.get('Action') == 'pass' and e.get('Test')]
            accepted = proc.returncode == 0 and bool(passed) and not failures
            row['passedTests'] = len(passed)
        row['accepted'] = accepted
        save()
        print(f'{label}: exit={proc.returncode}, {row["seconds"]:.3f}s, accepted={accepted}', flush=True)
        if not accepted:
            raise RuntimeError(f'{label} did not produce the required result; inspect {log}')

    try:
        run('baseline-expected-failure', ['go', 'test', '-json', '-mod=readonly', '-overlay=' + str(HERE / 'baseline-test-overlay.json'), './core/schema', '-run', '^TestContainerWithFileDefersSourceFailure$', '-count=1'], baseline=True)
        for package, regex, label in [('./core/schema', SCHEMA_TESTS, 'schema'), ('./dagql', INTERFACE_TESTS, 'interfaces')]:
            run(label + '-unit', ['go', 'test', '-json', '-mod=readonly', package, '-run', regex, '-count=1'])
            run(label + '-race', ['go', 'test', '-race', '-json', '-mod=readonly', package, '-run', regex, '-count=1'])
        if {path: sha(REPO / path) for path in actual} != actual:
            raise RuntimeError('Applied sources changed during validation.')
        report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        report['finishedUTC'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()


if __name__ == '__main__':
    main()
