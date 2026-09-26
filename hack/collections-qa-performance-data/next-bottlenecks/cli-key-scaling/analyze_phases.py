"""Correlate separate wcprof captures with same-host CLI clock anchors.

Records producer, evaluation and interpreter/process boundaries separately.
Nested intervals are observations, not additive costs or simulated speedups.
"""
from collections import Counter
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
rows = json.loads((root / 'results.json').read_text())
summary = []
for row in rows:
    if not row.get('profile'):
        continue
    file = root / row['label'] / 'run.wcprof'
    with file.open() as f:
        header = json.loads(next(f))
        events = [json.loads(line) for line in f if line.strip()]
    assert not header['dropped_events'] and not header.get('open_ops'), str(file)
    strings = header['strings']
    ops = [e for e in events if e['e'] == 'op']
    assert ops, f'no completed operations: {file}'
    by_id = {e['id']: e for e in ops}
    start = row['started_unix_ns']
    exit_ns = row['exited_unix_ns']
    epoch = header['epoch_unix_nano']

    def name(e):
        return strings[e.get('c', 0)]

    def ancestors(e):
        result = []
        visited = {e['id']}
        parent = e.get('p')
        while parent in by_id and parent not in visited:
            visited.add(parent)
            ancestor = by_id[parent]
            result.append(ancestor)
            parent = ancestor.get('p')
        return result

    def offset(e):
        return (epoch + e['s'] - start) / 1e6

    def entry(e):
        data = {
            'op_id': e['id'], 'class': name(e), 'kind': e['k'],
            'outcome': e.get('o'), 'start_from_cli_ms': offset(e),
            'duration_ms': (e['d'] - e['s']) / 1e6,
            'end_to_cli_exit_ms': (exit_ns - epoch - e['d']) / 1e6,
        }
        # Op metadata is not generally argv. Only exec.processRun owns that
        # representation; other operation metadata must not be mislabelled.
        if name(e) == 'exec.processRun' and e.get('m'):
            try:
                argv = json.loads(strings[e['m']])
                if isinstance(argv, list) and all(isinstance(arg, str) for arg in argv):
                    data['argv'] = argv
                else:
                    data['argv_decode_error'] = 'process metadata was not a string list'
            except json.JSONDecodeError:
                data['argv_decode_error'] = 'process metadata was not JSON'
        if name(e) == 'dang.invoke':
            chain = ancestors(e)
            data['ancestor_operations'] = [
                {'op_id': ancestor['id'], 'class': name(ancestor), 'kind': ancestor['k']}
                for ancestor in chain
                if ancestor['k'] in ('call', 'call_exec') or name(ancestor) == 'dang.invoke'
            ]
            data['inside_check_sync'] = any(name(ancestor) == 'Check.sync' for ancestor in chain)
            data['boundary_note'] = (
                'Interpreter callback invocation; includes dispatch. This is not a timestamp '
                'of the first authored source instruction. A verify call can merely construct Check.'
            )
        return data

    names = {'Workspace.artifacts', 'Artifacts.__evaluationItems', 'Check.sync', 'Host.directory', 'Container.from'}
    session_names = {'session.workspaceLoad', 'session.modulesLoad', 'session.schemaBuild'}
    suffixes = ('verify', 'render', 'web', 'read', 'run', 'goTestBase')

    def selected_call(e):
        return e['k'] in ('call', 'call_exec') and (
            name(e) in names or any(name(e).endswith('.' + suffix) for suffix in suffixes)
        )

    relevant = [e for e in ops if (
        (e['k'] == 'exec_phase' and name(e) in ('exec.processRun', 'exec.setupNetwork'))
        or e['k'] == 'service_start'
        or name(e) in session_names
        or name(e) == 'dang.invoke'
        or selected_call(e)
    )]
    relevant.sort(key=lambda e: e['s'])
    interesting = [entry(e) for e in relevant]
    check_calls = [e for e in relevant if e['k'] == 'call' and name(e) == 'Check.sync']
    check_producers = [e for e in relevant if e['k'] == 'call' and name(e).endswith('.verify')]
    check_invocations = [e for e in relevant if name(e) == 'dang.invoke'
                         and any(name(ancestor) == 'Check.sync' for ancestor in ancestors(e))]
    # Count calls only: call_exec represents the body for a miss/singleflight
    # owner, and counting both would count one lookup twice.
    selected_outcomes = Counter(e.get('o', '') for e in relevant if e['k'] == 'call')
    summary.append({
        'flow': row['flow'], 'profile': str(file),
        'cli_seconds_profiled': row['seconds'],
        'clock_basis': 'same-host UNIX clock; engine profiler has a monotonic epoch anchored to UNIX time; separate diagnostic captures, not unprofiled latency samples',
        'ops': len(ops), 'dropped_events': header['dropped_events'],
        'first_engine_op_from_cli_ms': (epoch + min(e['s'] for e in ops) - start) / 1e6,
        'last_engine_op_to_exit_ms': (exit_ns - epoch - max(e['d'] for e in ops)) / 1e6,
        'operations_starting_before_cli': sum(epoch + e['s'] < start for e in ops),
        'operations_finishing_after_cli': sum(epoch + e['d'] > exit_ns for e in ops),
        'first_verify_producer_from_cli_ms': offset(check_producers[0]) if check_producers else None,
        'first_check_sync_from_cli_ms': offset(check_calls[0]) if check_calls else None,
        'first_dang_invoke_nested_in_check_sync_from_cli_ms': offset(check_invocations[0]) if check_invocations else None,
        'selected_call_outcomes': dict(selected_outcomes),
        'interpretation': 'A missing call_exec or fresh process can be a legitimate result cache hit. A projected Void @check producer creates Check; evaluation and author invocation occur later. Nested intervals are not additive. Time after the last recorded op includes unrecorded work and must not be assigned wholly to telemetry.',
        'boundaries': interesting,
    })
(root / 'phase-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
