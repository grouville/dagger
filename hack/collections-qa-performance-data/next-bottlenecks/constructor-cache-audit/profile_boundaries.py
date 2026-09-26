#!/usr/bin/env python3
"""Summarize existing wcprof boundaries; performs no engine requests."""
import argparse
import json
from pathlib import Path

from prepare_measurement import OUT


def analyze(profile, row):
    with profile.open() as f:
        header = json.loads(f.readline())
        strings = header['strings']
        ops = [e for line in f if (e := json.loads(line))['e'] == 'op']
    epoch = header['epoch_unix_nano']
    cli_start = row['started_unix_ns']
    cli_end = row['exited_unix_ns']

    def name(op):
        return strings[op.get('c', 0)]

    def argv(op):
        if not op.get('m'):
            return None
        try:
            return json.loads(strings[op['m']])
        except json.JSONDecodeError:
            return None

    def record(op):
        return {'name': name(op), 'kind': op.get('k'), 'outcome': op.get('o'),
                'start_after_cli_ms': (epoch + op['s'] - cli_start) / 1e6,
                'end_after_cli_ms': (epoch + op['d'] - cli_start) / 1e6,
                'duration_ms': (op['d'] - op['s']) / 1e6}

    calls = sorted((e for e in ops if e.get('k') == 'call'), key=lambda e: e['s'])
    producers = [e for e in calls if name(e).startswith('go:GoTests') and name(e).endswith('.run')]
    checks = [e for e in calls if name(e) == 'Check.sync']
    processes = sorted((e for e in ops if name(e) == 'exec.processRun'), key=lambda e: e['s'])
    tests = [e for e in processes if (a := argv(e)) and a[0] == 'otelgotest']
    interesting = {'backend:Query.backend', 'backend:Backend.goTestBase',
                   'Workspace.artifacts', 'Artifacts.__evaluationItems', 'Artifact.value', 'Check.sync'}
    tail_phases = [e for e in ops if any(part in name(e).lower() for part in ('telemetry', 'shutdown', 'drain'))]
    selected = [record(e) for e in calls if name(e) in interesting or e in producers]
    process_rows = [record(e) | {'argv': argv(e)} for e in processes]
    return {
        'profile': str(profile), 'operation_count': len(ops),
        'dropped_events': header['dropped_events'], 'open_operations': len(header.get('open_ops', [])),
        'cli_wall_ms': row['seconds'] * 1000,
        'cli_to_first_selected_producer_ms': record(producers[0])['start_after_cli_ms'] if producers else None,
        'cli_to_first_check_sync_ms': record(checks[0])['start_after_cli_ms'] if checks else None,
        'cli_to_first_test_process_ms': record(tests[0])['start_after_cli_ms'] if tests else None,
        'last_check_completion_to_cli_exit_ms': (cli_end - epoch - max(e['d'] for e in checks)) / 1e6 if checks else None,
        'last_test_process_completion_to_cli_exit_ms': (cli_end - epoch - max(e['d'] for e in tests)) / 1e6 if tests else None,
        'fresh_test_processes': len(tests),
        'no_fresh_test_note': None if tests else 'No otelgotest process recorded; inspect selected producer/Check.sync cache outcomes. Do not interpret a warm cache hit as a newly executed test.',
        'selected_calls': selected, 'processes': process_rows,
        'recorded_tail_phases': [record(e) for e in sorted(tail_phases, key=lambda e: e['s'])],
        'limits': 'Start offsets use same-host CLI wall time and wcprof epoch; no clock step assumed. Nested intervals are not additive. Residual completion-to-exit includes output/RPC/shutdown work and is not wholly attributed to telemetry.',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('calibrate', 'measure'))
    args = p.parse_args()
    folder = OUT / args.phase
    rows = json.loads((folder / 'results.json').read_text())
    results = {row['label']: analyze(folder / row['label'] / 'run.wcprof', row)
               for row in rows if row['profile']}
    (folder / 'profile-boundaries.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
