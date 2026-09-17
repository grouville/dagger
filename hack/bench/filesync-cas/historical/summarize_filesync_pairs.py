#!/usr/bin/env python3
"""Analyze the owned filesync cohort; never run engines or mutate raw evidence.

Default: print a complete report, without writing files. --partial permits an
explicitly incomplete report. --write creates RESULTS.json and RESULTS.md only
inside filesync-pairs-r1, and refuses to overwrite either existing result.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys


ROOT = Path(__file__).resolve().parent
COHORT = ROOT / 'filesync-pairs-r1'
LABELS = ('initial', 'exact', 'leaf1', 'leaf1-exact')
PROBE = 'crates/ruff/src/lib.rs'
ACCEPTED = 'source-and-profile-validated-diagnostic-only'
GATES = (
    'analyzer_exit_zero', 'header_event_count_exact', 'native_no_drops',
    'native_no_open_ops', 'analyzer_counts_match',
    'maintained_replay_within_2_percent', 'intervals_inside_process_window',
    'probe_unchanged_during_capture', 'full_source_unchanged_during_capture',
)
FLOW_NAMES = {
    'initial': 'Fresh engine/cache import', 'exact': 'Unchanged after initial',
    'leaf1': 'One-file edit', 'leaf1-exact': 'Unchanged after edit',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def union_ns(intervals):
    total, end = 0, None
    for start, stop in sorted(intervals):
        require(stop >= start, 'negative native profile interval')
        if end is None or start > end:
            total += stop - start
        else:
            total += max(0, stop - end)
        end = stop if end is None else max(end, stop)
    return total


def describe(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {
        'n': len(ordered), 'median_ms': statistics.median(ordered),
        'min_ms': ordered[0], 'max_ms': ordered[-1],
        'p95_nearest_rank_ms': ordered[math.ceil(.95 * len(ordered)) - 1],
    }


def changed_paths(before, after):
    return sorted(name for name in before.keys() | after.keys()
                  if before.get(name) != after.get(name))


def native_profile(directory, receipt):
    """Extract native intervals; maintained analyzer acceptance remains primary."""
    profile = directory / 'profile.wcprof'
    require(sha(profile) == receipt['profile_sha256'], 'profile hash changed')
    with profile.open() as stream:
        header = json.loads(next(stream))
        events = [json.loads(line) for line in stream if line.strip()]
    require(header['schema_version'] == 1, 'unsupported native profile schema')
    require(header['event_count'] == len(events), 'native event count mismatch')
    require(header['dropped_events'] == 0 and not header.get('open_ops'),
            'native profile has drops/open operations')
    epoch = header['epoch_unix_nano']
    require(all(receipt['started_ns'] <= epoch + event['s']
                <= epoch + event['d'] <= receipt['process_ended_ns']
                for event in events), 'native events outside process window')
    ops = [event for event in events if event['e'] == 'op']
    analysis = (directory / 'analysis.txt').read_text()
    counts = re.search(r'ops:\s*(\d+)\s+roots:\s*(\d+)\s+open at dump:\s*(\d+)\s+dropped events:\s*(\d+)', analysis)
    drift = re.search(r'simulated baseline makespan:.*?\(drift vs actual:\s*([+-]?[\d.]+)%\)', analysis)
    require(counts is not None and int(counts[1]) == len(ops)
            and counts[3] == counts[4] == '0', 'maintained analyzer counts mismatch')
    require(drift is not None and abs(float(drift[1])) <= 2,
            'maintained analyzer replay outside 2 percent')
    strings = header['strings']
    query = [event for event in ops if strings[event['c']] == 'session.serveQuery']
    require(query and all(event.get('o') == 'ok' for event in query),
            'missing/failed session.serveQuery')
    query_union = union_ns([(event['s'], event['d']) for event in query])
    recorded = [row for row in receipt['classes'] if row['class'] == 'session.serveQuery']
    require(len(recorded) == 1 and recorded[0]['union_elapsed_ns'] == query_union,
            'recorded query union differs from native profile')
    return {
        'engine_complete_ms': query_union / 1e6,
        'native_event_count': len(events), 'native_op_count': len(ops),
        'replay_drift_percent': float(drift[1]),
        'class_counts': dict(Counter(strings[event['c']] for event in ops)),
    }


def load_sample(pair, arm, spec, label, hashes, query_sha):
    attempt = spec['attempt']
    runtime = ROOT / f'runtime-r{attempt}'
    directory = runtime / label
    receipt = read_json(directory / 'receipt.json')
    require(read_json(runtime / 'cli/config/dagger/engine.json') == {'logLevel': 'debug'},
            'engine config differs from unchanged-default-GC cohort')
    require(receipt['status'] == ACCEPTED and receipt['exit_code'] == 0,
            f"sample status {receipt.get('status')}: {receipt.get('error', '')}")
    require(receipt['label'] == label, 'sample label differs')
    require(receipt['controller_sha256'] == hashes['controller'], 'controller hash differs')
    require(receipt['manifest_helper_sha256'] == hashes['manifest_helper'], 'manifest helper differs')
    require(receipt['source_revision'] == hashes['source_revision'], 'source revision differs')
    require(receipt['image']['id'] == spec['image'] and
            receipt['image']['cli_sha256'] == spec['cli_sha256'], 'arm image/CLI differs')
    require(receipt['analyzer_exit_code'] == 0, 'maintained analyzer failed')
    require(all(receipt['native_analyzer_gates'].get(gate) is True for gate in GATES),
            'a native/source acceptance gate failed or is absent')
    require(sha(directory / 'source-manifest.json') == receipt['source_manifest_sha256'],
            'source manifest hash changed')
    manifest = read_json(directory / 'source-manifest.json')
    require(manifest[PROBE]['sha256'] == receipt['probe_sha256'], 'probe/manifest differs')
    argv = receipt['argv']
    require(argv[1:7] == ['--profile', 'api', 'query', '-M', '--doc', str(ROOT / 'import.graphql')],
            'command differs from profiled raw-import query')
    require(sha(Path(argv[6])) == query_sha, 'query document changed')
    require(json.loads(argv[8]) == {'path': str(ROOT / 'ruff'), 'probe': PROBE},
            'query variables differ')
    stdout = read_json(directory / 'stdout')['host']['directory']
    require(stdout['digest'] == receipt['content_digest'], 'receipt/output digest differs')
    require(hashlib.sha256(stdout['file']['contents'].encode()).hexdigest()
            == receipt['probe_sha256'], 'returned probe bytes differ')
    profile = native_profile(directory, receipt)
    wall = receipt['milliseconds']
    require(math.isfinite(wall) and wall >= profile['engine_complete_ms'],
            'invalid CLI duration or query exceeds CLI wall')
    owner = receipt['owner']['engine']
    require(owner['restart_count'] == 0 and owner['image'] == spec['image'],
            'engine restarted or changed image')
    expected_name = f'dagger-storage-host-efb1uyhh-r{attempt}-engine'
    require(owner['name'] == owner['volume'] == expected_name, 'engine/volume identity differs')
    row = {
        'pair': pair, 'arm': arm, 'attempt': attempt, 'flow': label,
        'receipt': str(directory / 'receipt.json'), 'receipt_sha256': sha(directory / 'receipt.json'),
        'profile_sha256': receipt['profile_sha256'], 'analysis_sha256': sha(directory / 'analysis.txt'),
        'controller_sha256': receipt['controller_sha256'],
        'manifest_helper_sha256': receipt['manifest_helper_sha256'],
        'source_manifest_sha256': receipt['source_manifest_sha256'],
        'probe_sha256': receipt['probe_sha256'], 'content_digest': receipt['content_digest'],
        'started_ns': receipt['started_ns'], 'process_ended_ns': receipt['process_ended_ns'],
        'cli_wall_ms': wall, 'cli_remainder_ms': wall - profile['engine_complete_ms'],
        'owner': owner, 'pressure_before': receipt.get('pressure_before'),
        'pressure_after': receipt.get('pressure_after'), **profile,
    }
    # Do not interpret the supplemental raw parser's validation as an extra gate.
    return row, manifest


def excluded_pilot(override):
    """Keep setup-invalid pilot timings visible without admitting them to pairs."""
    evidence = dict(override)
    evidence['samples'] = []
    runtime = ROOT / f"runtime-r{override['replace_attempt']}"
    for label in LABELS:
        path = runtime / label / 'receipt.json'
        if not path.exists():
            continue
        receipt = read_json(path)
        evidence['samples'].append({
            'flow': label, 'status': receipt.get('status'),
            'cli_wall_ms': receipt.get('milliseconds'),
            'receipt': str(path), 'receipt_sha256': sha(path),
            'included_in_paired_summary': False,
        })
    return evidence


def pruning_log(runtime):
    filename = runtime / 'engine-complete.log'
    if not filename.exists():
        return {'status': 'missing', 'path': str(filename), 'events': []}
    events = []
    for number, line in enumerate(filename.read_text(errors='replace').splitlines(), 1):
        if not re.search(r'prun|garbage.collect|evict', line, re.I):
            continue
        timestamp = re.search(r'\btime=([^ ]+)', line)
        if timestamp is None:
            continue
        when = int(datetime.fromisoformat(timestamp[1].replace('Z', '+00:00')).timestamp() * 1e9)
        kind = 'pruning-diagnostic'
        if 'prune skip' in line:
            kind = 'skipped-no-reclaim'
        elif 'pruned result' in line or re.search(r'\bevicted\b', line, re.I):
            kind = 'eviction'
        elif 'garbage collect' in line:
            kind = 'collection'
        elif 'applied plan' in line:
            kind = 'applied-plan'
        events.append({'line': number, 'time_ns': when, 'kind': kind, 'text': line})
    return {'status': 'read', 'path': str(filename), 'sha256': sha(filename), 'events': events}


def validate_exports(samples, manifests):
    evidence, previous = [], None
    controller = None
    for arm in ('main', 'cas'):
        key = (1, arm, 'leaf1-exact')
        require(key in samples, 'pair 1 edited samples not complete for export gate')
        runtime = ROOT / f"runtime-r{samples[key]['attempt']}"
        path = runtime / 'export.json'
        record = read_json(path)
        require(record['status'] == 'complete-tree-readback-passed' and record['measured'] is False,
                f'{arm} full export/readback did not pass outside measurement')
        require(controller is None or record['controller_sha256'] == controller,
                'export verification controller differs between arms')
        controller = record['controller_sha256']
        source = record['source_manifest']
        require(source == record['export_manifest'] == manifests[key],
                f'{arm} full exported tree differs from measured edited source')
        require(len(source) == 12025, 'unexpected full export entry count')
        require(previous is None or previous == source, 'main/CAS exports differ')
        previous = source
        evidence.append({'arm': arm, 'path': str(path), 'sha256': sha(path), 'entries': len(source),
                         'controller_sha256': controller})
    return {'status': 'passed', 'evidence': evidence, 'scope': 'pair 1 only, byte/type/mode/link-target parity'}


def analyze(allow_partial):
    plan = read_json(COHORT / 'receipt.json')
    override = read_json(COHORT / 'override.json') if (COHORT / 'override.json').exists() else None
    require([pair['pair'] for pair in plan['pairs']] == list(range(1, 7)), 'cohort must contain pairs 1–6')
    require(override is None or (override['pair'] == 1 and override['arm'] == 'main'
            and override['replace_attempt'] == 9 and override['with_attempt'] == 21),
            'unexpected exclusion/replacement; review before analyzing')
    first = override['with_attempt'] if override else plan['pairs'][0]['arms']['main']['attempt']
    captured = read_json(ROOT / f'runtime-r{first}/initial/receipt.json')
    hashes = {'controller': captured['controller_sha256'],
              'manifest_helper': captured['manifest_helper_sha256'],
              'source_revision': plan['source_revision']}
    issues, warnings, rows, manifests, logs, completed = [], [], {}, {}, {}, []
    if plan['profile_sha256'] != hashes['controller']:
        warnings.append('Prepared receipt records an earlier controller hash; all accepted samples are checked against the same captured controller hash. Both hashes are retained.')
    if hashes['controller'] != sha(ROOT / 'profile_import.py'):
        warnings.append('Captured controller differs from the current helper; historical raw gates and cross-sample controller consistency are verified without rewriting receipts.')
    all_attempts = set()
    for pair in plan['pairs']:
        number = pair['pair']
        require(pair['order'] == (['main', 'cas'] if number % 2 else ['cas', 'main']),
                'planned sequence is not alternating')
        for arm in ('main', 'cas'):
            spec = dict(pair['arms'][arm])
            if override is not None and number == 1 and arm == 'main':
                spec['attempt'] = override['with_attempt']
            attempt = spec['attempt']
            require(attempt not in all_attempts, 'engine attempt reused across arms')
            all_attempts.add(attempt)
            runtime = ROOT / f'runtime-r{attempt}'
            logs[str(attempt)] = pruning_log(runtime)
            for label in LABELS:
                key = (number, arm, label)
                try:
                    row, manifest = load_sample(number, arm, spec, label, hashes, plan['query_sha256'])
                    rows[key], manifests[key] = row, manifest
                except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
                    issues.append({'pair': number, 'arm': arm, 'attempt': attempt,
                                   'flow': label, 'error': str(error)})
        keys = [(number, arm, label) for arm in ('main', 'cas') for label in LABELS]
        if not all(key in rows for key in keys):
            continue
        try:
            for arm in ('main', 'cas'):
                samples = [rows[number, arm, label] for label in LABELS]
                require(all(row['owner'] == samples[0]['owner'] for row in samples), 'owner changed during arm')
                require(all(a['process_ended_ns'] < b['started_ns'] for a, b in zip(samples, samples[1:])),
                        'flow commands overlap or are out of order')
                require(manifests[number, arm, 'initial'] == manifests[number, arm, 'exact'], 'initial→exact source changed')
                require(manifests[number, arm, 'leaf1'] == manifests[number, arm, 'leaf1-exact'], 'edit→exact source changed')
                require(changed_paths(manifests[number, arm, 'initial'], manifests[number, arm, 'leaf1']) == [PROBE],
                        'edit must change exactly the probe path')
                require(samples[0]['content_digest'] == samples[1]['content_digest']
                        and samples[2]['content_digest'] == samples[3]['content_digest']
                        and samples[0]['content_digest'] != samples[2]['content_digest'], 'digest transitions do not match edit/unchanged flow')
            for label in LABELS:
                require(manifests[number, 'main', label] == manifests[number, 'cas', label], 'main/CAS full source differs')
                require(rows[number, 'main', label]['content_digest'] == rows[number, 'cas', label]['content_digest'], 'main/CAS public digests differ')
            first, second = pair['order']
            require(rows[number, first, 'leaf1-exact']['process_ended_ns'] < rows[number, second, 'initial']['started_ns'],
                    'actual arm order differs from plan or overlaps')
            require(all(logs[str(rows[number, arm, 'initial']['attempt'])]['status'] == 'read' for arm in ('main', 'cas')),
                    'complete engine log not yet available')
            completed.append(number)
        except (ValueError, KeyError) as error:
            issues.append({'pair': number, 'error': str(error)})
    if plan.get('shutdown_order_gate') == 'required':
        previous_stop = None
        try:
            for pair in plan['pairs']:
                for arm in pair['order']:
                    sample = rows[pair['pair'], arm, 'initial']
                    stop = read_json(ROOT / f"runtime-r{sample['attempt']}/stopped.json")
                    require(stop['owner']['engine'] == sample['owner'], 'shutdown owner differs from measured engine')
                    require(stop['owner'] == read_json(Path(sample['receipt']))['owner'],
                            'shutdown volume/engine receipt differs from measured ownership')
                    require(previous_stop is None or previous_stop < sample['started_ns'],
                            'next benchmark arm overlaps previous export/shutdown')
                    previous_stop = stop['stopped_ns']
                    require(rows[pair['pair'], arm, 'leaf1-exact']['process_ended_ns'] < previous_stop,
                            'shutdown precedes measured arm completion')
        except (OSError, ValueError, KeyError) as error:
            issues.append({'shutdown_order_gate': str(error)})
    try:
        exports = validate_exports(rows, manifests)
    except (OSError, ValueError, KeyError) as error:
        exports = {'status': 'pending-or-failed', 'error': str(error)}
        issues.append({'export_gate': str(error)})
    for key, row in rows.items():
        number, arm, label = key
        position = LABELS.index(label)
        start = row['started_ns'] if position == 0 else rows.get((number, arm, LABELS[position - 1]), row)['process_ended_ns']
        events = [event for event in logs[str(row['attempt'])]['events']
                  if start <= event['time_ns'] <= row['process_ended_ns']]
        row['pruning_since_previous_command'] = events
        row['evictions_since_previous_command'] = sum(event['kind'] == 'eviction' for event in events)
        cold = rows.get((number, arm, 'initial'), {}).get('class_counts', {}).get('filesync.filecache.ingest', 0)
        # A CAS-before/CAS-after cohort has CAS activity in both arms. Do not
        # hide control reingestion behind the historical "main" arm key.
        row['cas_payload_calls'] = row['class_counts'].get('filesync.filecache.ingest', 0) if cold else None
        row['cas_near_full_reingestion'] = bool(position > 0 and cold
                                               and row['cas_payload_calls'] >= math.ceil(.9 * cold))
        row['included_in_paired_summary'] = number in completed
    complete = len(completed) == 6 and not issues and exports['status'] == 'passed'
    if not complete and not allow_partial:
        raise ValueError('Cohort incomplete or validation failed; use --partial for a labeled diagnostic.\n' + json.dumps(issues, indent=2))
    aggregates = []
    for label in LABELS:
        for metric in ('engine_complete_ms', 'cli_wall_ms', 'cli_remainder_ms'):
            main = [rows[pair, 'main', label][metric] for pair in completed]
            cas = [rows[pair, 'cas', label][metric] for pair in completed]
            aggregates.append({'flow': label, 'metric': metric, 'main': describe(main), 'cas': describe(cas),
                               'paired_cas_minus_main': describe([b - a for a, b in zip(main, cas)])})
    return {
        'status': 'complete-validated-n6' if complete else 'partial-not-final',
        'scope': plan['scope'], 'cold': plan['cold'], 'gc': plan['gc'],
        'arm_labels': plan.get('arm_labels', {'main': 'Main', 'cas': 'CAS'}),
        'headline': 'Native wcprof session.serveQuery interval union, including lazy materialization',
        'cli_remainder': 'CLI wall minus engine query union; includes provisioning/connect/shutdown, not isolated overhead attribution',
        'profiled': True, 'p95_caveat': 'Nearest-rank p95 with n=6 equals the maximum; not a stable tail estimate.',
        'reingestion_rule': 'Nominal-warm filesync.filecache.ingest count >=90% of its own initial count; diagnostic indicator, not proof of GC causality.',
        'completed_pairs': completed, 'expected_pairs': 6, 'issues': issues, 'warnings': warnings,
        'provenance': {'plan_sha256': sha(COHORT / 'receipt.json'), 'override_sha256': sha(COHORT / 'override.json') if override else None,
                       'prepared_controller_sha256': plan['profile_sha256'], **hashes,
                       'current_controller_sha256': sha(ROOT / 'profile_import.py'),
                       'summarizer_sha256': sha(Path(__file__))},
        'excluded_pilot': excluded_pilot(override) if override else None, 'full_readback': exports,
        'aggregates': aggregates, 'samples': sorted(rows.values(), key=lambda row: (row['pair'], row['started_ns'])),
        'engine_logs': logs,
    }


def markdown(report):
    control = report['arm_labels']['main']
    candidate = report['arm_labels']['cas']
    lines = ['# Filesync paired comparison', '', f"Status: **{report['status']}**, complete pairs {len(report['completed_pairs'])}/6.", '',
             f"Scope: {report['scope']}. Profiled commands; no Rust/Cargo E2E claim.", '',
             f"Cold: {report['cold']}. GC: {report['gc']}.", '',
             'Headline = `session.serveQuery` native interval union, including lazy materialization. CLI remainder is wall time minus that union; it is not an attribution to one lifecycle phase.', '',
             report['p95_caveat'], '', '## Paired summaries (milliseconds)', '',
             f'Arm keys: `main` = **{control}**; `cas` = **{candidate}**. These labels identify the actual controls; a CAS control is not upstream main.', '',
             f'| Flow | Metric | n | {control} median [min, max] | {candidate} median [min, max] | Control / candidate p95 | Median paired candidate−control |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for aggregate in report['aggregates']:
        main, cas, delta = (aggregate[key] for key in ('main', 'cas', 'paired_cas_minus_main'))
        if main is None:
            continue
        def fmt(stats):
            return f"{stats['median_ms']:.3f} [{stats['min_ms']:.3f}, {stats['max_ms']:.3f}]"
        lines.append(f"| {FLOW_NAMES[aggregate['flow']]} | {aggregate['metric']} | {main['n']} | {fmt(main)} | {fmt(cas)} | {main['p95_nearest_rank_ms']:.3f} / {cas['p95_nearest_rank_ms']:.3f} | {delta['median_ms']:+.3f} |")
    lines += ['', '## Every accepted sample', '', '| Pair | Arm / attempt | Flow | Engine complete ms | CLI wall ms | Remainder ms | CAS payload calls | Evictions since prior command | Near-full reingestion | Paired |',
              '| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |']
    for row in report['samples']:
        payload = '—' if row['cas_payload_calls'] is None else str(row['cas_payload_calls'])
        lines.append(f"| {row['pair']} | {row['arm']} / {row['attempt']} | {row['flow']} | {row['engine_complete_ms']:.3f} | {row['cli_wall_ms']:.3f} | {row['cli_remainder_ms']:.3f} | {payload} | {row['evictions_since_previous_command']} | {row['cas_near_full_reingestion']} | {row['included_in_paired_summary']} |")
    lines += ['', report['reingestion_rule'], '', 'No timing outliers or eviction-affected accepted samples are removed.', '', '## Correctness and provenance', '',
              f"Full export/readback gate: {report['full_readback']['status']} (pair 1, 12,025 entries)."]
    excluded = report['excluded_pilot']
    if excluded:
        lines += ['', f"Excluded setup-overlap pilot: attempt {excluded['replace_attempt']}, replaced by {excluded['with_attempt']}. {excluded['reason']}"]
    for pilot in excluded['samples'] if excluded else []:
        lines += ['', f"Excluded pilot {pilot['flow']}: CLI {pilot['cli_wall_ms']} ms, status `{pilot['status']}`; receipt `{pilot['receipt']}`."]
    for warning in report['warnings']:
        lines += ['', 'Warning: ' + warning]
    if report['issues']:
        lines += ['', '## Missing or rejected evidence', '', '```json', json.dumps(report['issues'], indent=2), '```']
    lines += ['', '## Engine pruning evidence', '']
    for attempt, log in report['engine_logs'].items():
        counts = Counter(event['kind'] for event in log['events'])
        lines.append(f"- Attempt {attempt}: {log['status']}; {dict(counts)}. Log: `{log['path']}`.")
    lines += ['', 'Complete event lines, hashes, per-sample PSI and receipt paths are retained in RESULTS.json when explicitly written.', '']
    return '\n'.join(lines)


def main():
    global COHORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=int, choices=range(1, 10), default=1)
    parser.add_argument('--partial', action='store_true', help='permit a clearly labeled incomplete diagnostic')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true', help='create new RESULTS.json/RESULTS.md inside the cohort directory')
    mode.add_argument('--dry', action='store_true', help='print only (default)')
    parser.add_argument('--json', action='store_true', help='print JSON rather than Markdown')
    args = parser.parse_args()
    COHORT = ROOT / f'filesync-pairs-r{args.cohort}'
    report = analyze(args.partial)
    text = markdown(report)
    if args.write:
        outputs = [COHORT / 'RESULTS.json', COHORT / 'RESULTS.md']
        require(not any(path.exists() for path in outputs), 'refuse to overwrite existing analysis results')
        with outputs[0].open('x') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
        with outputs[1].open('x') as stream:
            stream.write(text)
    print(json.dumps(report, indent=2) if args.json else text)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f'Analysis rejected: {error}', file=sys.stderr)
        sys.exit(1)
