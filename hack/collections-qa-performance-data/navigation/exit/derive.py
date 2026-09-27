"""Numeric-only summary of normal Cloud timing and the separate observer runs."""
from pathlib import Path
import collections
import json
import statistics

import experiment as x

LAB = Path(__file__).resolve().parent
SRC = LAB / 'exit-tail-diagnostic-v1'
OUT = LAB / 'exit-tail-evidence-v1'


def union(intervals):
    total, cursor = 0, None
    for start, end in sorted(intervals):
        assert end >= start
        total += max(0, end - max(start, cursor if cursor is not None else start))
        cursor = max(end, cursor if cursor is not None else end)
    return total


def analyze(row, directory):
    events = [json.loads(line) for line in (directory / 'timeline.jsonl').read_text().splitlines()]
    anchors = [event for event in events if event['kind'] == 'anchor']
    assert len(anchors) == 1
    epoch = anchors[0]['unix_ns']
    phases = collections.defaultdict(list)
    for event in events:
        phases[event['kind']].append(event)
    durations = {kind: sum(e['end_ns'] - e['start_ns'] for e in values) / 1e6 for kind, values in phases.items() if kind != 'anchor'}
    requests = []
    for event in events:
        if event['kind'] not in ('cloud.traces', 'cloud.logs', 'cloud.metrics'):
            continue
        values = event.get('values', {})
        requests.append({
            'kind': event['kind'], 'start_ms': event['start_ns'] / 1e6,
            'end_ms': event['end_ns'] / 1e6,
            'duration_ms': (event['end_ns'] - event['start_ns']) / 1e6,
            'numeric_http_values': values,
            'write_to_first_byte_ms': (values['first_byte_ns'] - values['wrote_request_ns']) / 1e6 if 'first_byte_ns' in values and 'wrote_request_ns' in values else None,
        })
    result = {key: row[key] for key in ('variant', 'flow', 'phase', 'index', 'profile', 'seconds', 'correct')}
    result.update(phase_ms=durations, requests=requests,
                  timeline_sha256=x.sha(directory / 'timeline.jsonl'),
                  cli_after_command_ms=(row['exited_unix_ns'] - epoch - max(e['end_ns'] for e in phases['cli.command'])) / 1e6)
    if row['profile']:
        path = directory / 'run.wcprof'
        with path.open() as stream:
            header = json.loads(next(stream))
            operations = [event for line in stream if (event := json.loads(line))['e'] == 'op']
        queries = [op for op in operations if header['strings'][op.get('c', 0)] == 'session.query']
        end = header['epoch_unix_nano'] + max(op['d'] for op in operations)
        result['wcprof'] = {
            'sha256': x.sha(path), 'operations': len(operations),
            'open': len(header.get('open_ops', [])), 'dropped': header['dropped_events'],
            'query_count': len(queries), 'query_union_ms': union((op['s'], op['d']) for op in queries) / 1e6,
            'cli_after_last_engine_operation_ms': (row['exited_unix_ns'] - end) / 1e6,
            'last_operation_relative_to_cli_command_end_ms': (end - epoch - max(e['end_ns'] for e in phases['cli.command'])) / 1e6,
        }
    return result


def main():
    rows = json.loads((SRC / 'results.json').read_text())
    assert len(rows) == 20 and all(row['correct'] for row in rows)
    ordinary = {}
    for variant in ('base', 'candidate'):
        samples = [row['seconds'] for row in rows if row['phase'] == 'ordinary' and row['variant'] == variant]
        assert len(samples) == 4
        ordinary[variant] = {'n': len(samples), 'samples_seconds': samples, 'median_seconds': statistics.median(samples)}
    diagnostic = []
    for row in rows:
        if row['diagnostic']:
            directory = SRC / f"{row['phase']}-{row['index']}-{row['flow']}-{row['variant']}"
            diagnostic.append(analyze(row, directory))
    OUT.mkdir(exist_ok=True)
    x.write(OUT / 'analysis.json', {
        'ordinary': ordinary, 'diagnostic': diagnostic,
        'limits': ['Instrumented/profile runs excluded from ordinary medians.',
                   'CLI HTTP hooks observe only CLI-owned exports, not engine Cloud HTTP calls.',
                   'First-byte delay includes network and receiver work; it is not server-only time.',
                   'Retained engines have unequal prior histories; no new cold-cache comparison.'],
    })
    print(json.dumps({'ordinary': ordinary, 'diagnostic': [{key: row[key] for key in ('variant', 'flow', 'index', 'profile', 'seconds', 'phase_ms')} for row in diagnostic]}, indent=2))


if __name__ == '__main__':
    main()
