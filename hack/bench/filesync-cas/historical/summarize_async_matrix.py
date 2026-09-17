#!/usr/bin/env python3
"""Revalidate every arm/flow, preserve failures, report only complete matched rounds."""
import argparse
import json
from pathlib import Path

import async_samples
import build
import matrix_async as matrix


def summarize(output):
    plan = matrix.read_json(output / 'receipt.json')
    assert plan['helpers'] == matrix.helper_hashes(), 'frozen helpers changed'
    run = matrix.read_json(output / 'run.json')
    assert run['plan_sha256'] == build.sha(output / 'receipt.json')
    assert run['baseline_sha256'] == build.sha(output / 'baseline.json')
    baseline = matrix.read_json(output / 'baseline.json')
    original = (output / 'baseline-probe.bin').read_bytes()
    rows, issues, exports, journals, logs = [], [], [], [], []
    completed = []
    last_stop = 0
    for round_spec in plan['rounds']:
        number = round_spec['round']
        assert round_spec['order'] == matrix.round_order(number)
        reference = {}
        before_issues = len(issues)
        for arm in round_spec['order']:
            spec = round_spec['arms'][arm]
            runtime = matrix.runtime_path(spec['attempt'])
            expected = matrix.round_fixture(plan, round_spec, baseline, original)[-1]
            try:
                for kind, labels in [('mixed', ('ab2-edit', 'ab2-exact')), ('reorg', ('ab4-edit', 'ab4-exact'))]:
                    pointer = matrix.read_json(runtime / f'{kind}-fixture.json')
                    backup = Path(pointer['backup'])
                    assert backup.is_relative_to(matrix.ROOT)
                    journal = matrix.read_json(backup / 'plan.json')
                    assert journal['status'] == 'restored', f'{kind} fixture not restored'
                    assert {key: journal['baseline'][key] for key in ('manifest', 'mtime_ns')} == expected['leaf1']
                    planned = {key: journal['expected'][key] for key in ('manifest', 'mtime_ns')}
                    for label in labels:
                        expected[label] = planned
                    journals.append({'round': number, 'arm': arm, 'kind': kind, 'backup': str(backup),
                                     'journal_sha256': build.sha(backup / 'plan.json'),
                                     'counts': journal.get('counts', journal.get('summary', {}).get('counts')),
                                     'impact': journal.get('summary')})
                previous = last_stop
                owner = None
                for label in matrix.LABELS:
                    directory = runtime / label
                    sample, source = async_samples.load(directory, spec, plan['helpers'])
                    state = matrix.read_json(directory / 'matrix-state.json')
                    assert source == expected[label]['manifest'] and state['mtime_ns'] == expected[label]['mtime_ns']
                    assert state['run_sha256'] == plan['helpers']['matrix_async.py']
                    assert sample['started_ns'] > previous
                    previous = sample['process_ended_ns']
                    assert owner is None or sample['owner'] == owner
                    owner = sample['owner']
                    if label in reference:
                        assert reference[label] == (sample['content_digest'], source, state['mtime_ns'])
                    reference[label] = sample['content_digest'], source, state['mtime_ns']
                    relation = matrix.RELATIONS[label]
                    if relation:
                        other = matrix.read_json(runtime / relation[1] / 'receipt.json')['content_digest']
                        assert (sample['content_digest'] == other) == (relation[0] == '--same-as')
                    rows.append({'round': number, 'arm': arm, 'attempt': spec['attempt'], 'flow': label, **sample})
                stop = matrix.read_json(runtime / 'stopped.json')
                assert stop['owner'] == owner and not stop['stopped']['State.Running']
                assert previous < stop['stopped_ns']
                last_stop = stop['stopped_ns']
                logs.append({'round': number, 'arm': arm, **async_samples.pruning_log(runtime)})
                if number == 1:
                    for capture, label in [('edited', 'leaf1-exact'), ('moved', 'ab1-exact'),
                                           ('mixed', 'ab2-exact'), ('reorg', 'ab4-exact')]:
                        path = runtime / f'export-{capture}.json'
                        value = matrix.read_json(path)
                        assert value['status'] == 'complete-tree-readback-passed' and not value['measured']
                        assert value['controller_sha256'] == plan['helpers']['verify_fixture_export.py']
                        assert value['source_manifest'] == expected[label]['manifest']
                        content = lambda items: {name: {key: item for key, item in values.items() if key != 'mode'} for name, values in items.items()}
                        assert content(value['export_manifest']) == content(value['source_manifest'])
                        if ('export', capture) in reference:
                            assert reference['export', capture] == value['export_manifest']
                        reference['export', capture] = value['export_manifest']
                        exports.append({'round': number, 'arm': arm, 'capture': capture, 'sha256': build.sha(path)})
            except (AssertionError, OSError, KeyError, ValueError) as error:
                issues.append({'round': number, 'arm': arm, 'error': repr(error)})
        if len(issues) == before_issues:
            completed.append(number)
    aggregates = []
    for label in matrix.LABELS:
        samples = {(r['round'], r['arm']): r for r in rows if r['round'] in completed and r['flow'] == label}
        for metric in ('engine_ms', 'cli_ms'):
            aggregates.append({'flow': label, 'metric': metric,
                               **{arm: async_samples.describe([samples[n, arm][metric] for n in completed]) for arm in matrix.ARMS},
                               'async_minus_both': async_samples.describe([samples[n, 'async'][metric] - samples[n, 'both'][metric] for n in completed]),
                               'async_minus_main': async_samples.describe([samples[n, 'async'][metric] - samples[n, 'main'][metric] for n in completed])})
    complete = len(completed) == 6 and not issues and run['status'] == 'complete' and run['source_restored']
    return {'status': 'complete-validated-n6' if complete else 'incomplete-diagnostic-only',
            'scope': plan['scope'], 'cold': plan['cold'], 'arm_labels': plan['arm_labels'],
            'completed_rounds': completed, 'issues': issues, 'run_status': run['status'],
            'aggregates': aggregates, 'samples': rows, 'readbacks': exports, 'fixtures': journals,
            'engine_logs': logs, 'plan_sha256': build.sha(output / 'receipt.json'),
            'limitations': [plan['order_caveat'], plan['readback_scope'], plan['async_capture'],
                            'Profiled diagnostic only; native Cargo is not part of this filesync matrix.',
                            'Main means pinned 523f3fe3 plus common diagnostics and the same reserve-floor GC fix.',
                            'n=6 p95 equals the maximum; all outliers and pressure measurements retained.',
                            'Background failures remain diagnostic samples; consult admission outcomes, not just latency.',
                            'Profile draining/validation separates imports; immediate-next-request busy/miss behavior and sustained throughput remain untested.']}


def markdown(report):
    lines = ['# Ruff filesync: main / synchronous CAS / asynchronous CAS', '',
             'Status: ' + report['status'], '',
             'Medians in milliseconds. The delta is the median of matched differences, not a subtraction of medians.', '',
             '| Flow | Metric | Main | CAS sync | CAS async | Async − sync | Async − main |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in report['aggregates']:
        values = ' | '.join('—' if row[key] is None else f'{row[key]["median_ms"]:.3f}' for key in (*matrix.ARMS, 'async_minus_both', 'async_minus_main'))
        lines.append(f'| {matrix.FLOW_NAMES[row["flow"]]} | {row["metric"]} | {values} |')
    lines.extend(['', *['- ' + note for note in report['limitations']], '', 'Full profiles, admission tails, phase timing, failures and pressure are retained in RESULTS.json.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=int, default=1)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    output = matrix.cohort_path(args.cohort)
    result = summarize(output)
    assert args.partial or result['status'] == 'complete-validated-n6', result['issues']
    text = markdown(result)
    if args.write:
        matrix.write_new(output / 'RESULTS.json', result)
        with (output / 'RESULTS.md').open('x') as stream:
            stream.write(text)
    print(text)


if __name__ == '__main__':
    main()
