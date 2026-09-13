#!/usr/bin/env python3
"""Post-capture warm phase diagnostic; no workload execution or timing replacement.

Uses the already accepted ordinary and wcprof traces. Preserve within-run medians
and three independent AB/BA/AB pairs. Diagnostic recovery/restart samples remain
separate from the ordinary edit workflow, including every observed outlier.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

OWNER = Path(__file__).resolve().parent
COHORT = Path('/tmp/dagger-rust-unix-readiness-ab-dda1zn80')
CARGO = ['sh', '-c', 'rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked']
INPUTS = {
    'cohort': COHORT / 'cohort.json',
    'ordinary': COHORT / 'ordinary-exec-audit/report.json',
    'profiles': COHORT / 'analysis-r2/report.json',
    'headline': OWNER / 'summary.json',
}
HEADLINES = {'exact', 'application', 'workspace-library', 'dependency-upgrade'}
FIELDS = (
    'process_ms', 'root_ms', 'before_root_ms', 'after_root_ms',
    'connect_ms', 'creating_client_ms', 'info_first_ms', 'info_version_ms',
    'info_gap_ms', 'client_outside_info_ms', 'docker_ms', 'docker_list_ms',
    'docker_start_ms', 'docker_version_ms', 'connect_other_ms',
    'cargo_action_ms', 'root_other_ms',
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def duration(span):
    return (span['endNs'] - span['startNs']) / 1e6


def one(items):
    assert len(items) == 1, f'expected one span, received {len(items)}'
    return items[0]


def contained(inner, outer):
    return outer['startNs'] <= inner['startNs'] <= inner['endNs'] <= outer['endNs']


def stats(values):
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values), values=values)


def main():
    output = OWNER / 'warm-phases.json'
    assert not output.exists(), 'preserve an earlier diagnostic, never overwrite it'
    hashes = {str(path): sha(path) for path in INPUTS.values()}
    data = {name: json.loads(path.read_text()) for name, path in INPUTS.items()}
    meta, ordinary, profiles, headline = (data[name] for name in ('cohort', 'ordinary', 'profiles', 'headline'))
    assert meta['status'] == 'passed' and meta['order'] == 'ABBAAB'
    assert [run['side'] for run in meta['runs']] == list('ABBAAB')
    assert set(meta['cli_sha256'].values()) == {'6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad'}
    assert meta['image_ids'] == {
        'A': 'sha256:1fb3565bb5bac059d2a89e52e231203befe215ba4396ea40c93393b19f77aeb0',
        'B': 'sha256:5d660298fd273eec4facabca4b1ecaf56cac7bc2342aaf3eec6a6d26ff1bb8da',
    }
    assert ordinary['all_pass'] and len(ordinary['checks']) == 54
    assert profiles['all_captures_pass'] and len(profiles['profiles']) == 36
    assert len(profiles['caches']) == 18 and len(profiles['warm_rebuilds']) == 36
    samples = []
    for check in ordinary['checks']:
        prefix = f'{check["index"]}-{check["side"]}-{check["scenario"]}-{check["sample"]}-dagger'
        samples.append(dict(index=check['index'], side=check['side'], flow=check['scenario'],
                            iteration=check['sample'], profiled=False, headline=True,
                            trace=str(COHORT / 'ordinary-exec-audit' / (prefix + '.trace.jsonl')),
                            envelope=check['envelope']))
    for check in profiles['profiles']:
        if check['label'] == 'warmup-dagger':
            continue
        flow = 'dependency-upgrade' if check['label'] == 'dependency-upgrade-dagger' else check['label']
        prefix = f'{check["index"]}-{check["side"]}-{check["label"]}'
        samples.append(dict(index=check['index'], side=check['side'], flow=flow,
                            iteration=0, profiled=True, headline=flow in HEADLINES,
                            trace=str(COHORT / 'analysis-r2' / (prefix + '.trace.jsonl')),
                            envelope={key: check[key] for key in ('process_ms', 'root_ms', 'before_root_ms', 'after_root_ms')},
                            replay_drift=check['replay_drift']))
    assert len(samples) == 84
    for sample in samples:
        path = Path(sample['trace'])
        hashes[str(path)] = sha(path)
        spans = {}
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['kind'] == 'span' and row.get('endNs', 0) >= spans.get(row['spanId'], {}).get('endNs', 0):
                    spans[row['spanId']] = row
        root = one([span for span in spans.values() if span.get('scope') == 'dagger.io/cli' and not span.get('parentId')])
        connect = one([span for span in spans.values() if span['name'] == 'connect' and span.get('parentId') == root['spanId']])
        client = one([span for span in spans.values() if span['name'] == 'creating client' and span.get('scope') == 'dagger.io/engine.client'])
        assert contained(connect, root) and contained(client, connect)
        infos = sorted((span for span in spans.values() if span['name'] == 'moby.buildkit.v1.Control/Info' and span.get('parentId') == client['spanId']), key=lambda span: span['startNs'])
        assert len(infos) == 2 and all(contained(span, client) for span in infos)
        assert all(span.get('attrs', {}).get('rpc.grpc.status_code') == 0 for span in infos)
        assert infos[0]['endNs'] <= infos[1]['startNs']
        commands = sorted((span for span in spans.values() if span['name'].startswith('exec docker ')), key=lambda span: span['startNs'])
        assert all(contained(span, connect) for span in commands)
        serial = sorted(commands + [client], key=lambda span: span['startNs'])
        assert all(a['endNs'] <= b['startNs'] for a, b in zip(serial, serial[1:])), 'cannot subtract overlapping connection phases'
        cargo = []
        for span in spans.values():
            attrs = span.get('attrs', {})
            if span['name'] == 'exec.processRun' and attrs.get('wcprof.op.kind') == 'exec_phase':
                assert json.loads(attrs['wcprof.exec.argv']) == CARGO
                assert contained(span, root) and connect['endNs'] <= span['startNs']
                cargo.append(span)
        assert len(cargo) == (0 if sample['flow'] in ('exact', 'profile-exact', 'profile-restart-exact') else 1)
        sample.update({key: sample['envelope'][key] for key in ('process_ms', 'root_ms', 'before_root_ms', 'after_root_ms')})
        assert abs(sample['root_ms'] - duration(root)) < 0.001
        sample.update(connect_ms=duration(connect), creating_client_ms=duration(client),
                      info_first_ms=duration(infos[0]), info_version_ms=duration(infos[1]),
                      info_gap_ms=(infos[1]['startNs'] - infos[0]['endNs']) / 1e6,
                      client_outside_info_ms=duration(client) - sum(duration(span) for span in infos),
                      docker_ms=sum(duration(span) for span in commands),
                      cargo_action_ms=sum(duration(span) for span in cargo),
                      info_calls=[dict(ms=duration(span), status=span.get('status'), status_msg=span.get('statusMsg'),
                                       grpc_status=span.get('attrs', {}).get('rpc.grpc.status_code')) for span in infos])
        for key, prefix in (('docker_list_ms', 'exec docker ps '), ('docker_start_ms', 'exec docker start '), ('docker_version_ms', 'exec docker version')):
            matching = [span for span in commands if span['name'].startswith(prefix)]
            assert len(matching) == 1
            sample[key] = duration(matching[0])
        sample['connect_other_ms'] = sample['connect_ms'] - sample['creating_client_ms'] - sample['docker_ms']
        sample['root_other_ms'] = sample['root_ms'] - sample['connect_ms'] - sample['cargo_action_ms']
        assert sample['connect_other_ms'] >= 0 and sample['root_other_ms'] >= 0
        sample['wall_minus_monotonic_ms'] = sum(sample[key] for key in ('before_root_ms', 'root_ms', 'after_root_ms')) - sample['process_ms']
        del sample['envelope']
    grouped = defaultdict(list)
    for sample in samples:
        grouped[sample['flow'], sample['index'], sample['side']].append(sample)
    per_run = []
    for (flow, index, side), rows in sorted(grouped.items()):
        record = dict(flow=flow, index=index, side=side, n=len(rows), headline=flow in HEADLINES,
                      **{key: statistics.median(row[key] for row in rows) for key in FIELDS})
        if record['headline']:
            original = one([row for row in headline['samples'] if row['index'] == index])['flows'][flow]
            assert abs(record['process_ms'] - original['dagger_ms']) < 0.000001
            record.update(native_ms=original['native_ms'], native_overhead_ms=original['overhead_ms'])
        per_run.append(record)
    flows = {}
    for flow in sorted({row['flow'] for row in per_run}):
        fields = FIELDS + (('native_ms', 'native_overhead_ms') if flow in HEADLINES else ())
        rows = [row for row in per_run if row['flow'] == flow]
        assert len(rows) == 6
        pairs = []
        for pair_index in range(3):
            pair = {row['side']: row for row in rows if row['index'] // 2 == pair_index}
            assert set(pair) == {'A', 'B'}
            pairs.append(dict(pair=pair_index, a_index=pair['A']['index'], b_index=pair['B']['index'],
                              saved_ms={key: pair['A'][key] - pair['B'][key] for key in fields}))
        flows[flow] = dict(headline=flow in HEADLINES, pairs=pairs,
                          metrics={key: dict(A=stats([row[key] for row in rows if row['side'] == 'A']),
                                             B=stats([row[key] for row in rows if row['side'] == 'B']),
                                             paired_saved_ms=stats([pair['saved_ms'][key] for pair in pairs]),
                                             favorable=sum(pair['saved_ms'][key] > 0 for pair in pairs)) for key in fields})
    assert all(sha(Path(path)) == expected for path, expected in hashes.items()), 'input changed during diagnostic'
    result = dict(scope=__doc__, post_capture=True, script_sha256=sha(Path(__file__)), inputs_sha256=hashes,
                  samples=samples, per_run=per_run, flows=flows, all_phase_contracts_pass=True,
                  limits=[
                      'Read-only analysis of existing accepted captures; no new benchmark, no edits to frozen controllers or raw records',
                      'Three independent matched runs; within-run medians precede pair comparisons',
                      'Positive paired saving favors B; all losses and outliers retained',
                      'Info duration includes helper/runtime startup, transport handshake/backoff and server work; no direct retry-count or helper-wait span exists',
                      'Absence of a large connection wait does not prove absence of a small helper regression',
                      'Cargo action includes rsync plus cargo check; wall duration is not pure compiler CPU',
                      'Per-sample disjoint partitions validated; separately summarized medians are not additive',
                      'Recovery and restart profiles follow failure/revisit and are not ordinary timed edits',
                      'No cold timing, network correction or native outlier exclusion is performed here',
                  ])
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    keys = ('process_ms', 'creating_client_ms', 'info_first_ms', 'docker_list_ms', 'connect_other_ms', 'cargo_action_ms', 'root_other_ms')
    print(json.dumps({flow: {key: round(data['metrics'][key]['paired_saved_ms']['median'], 3) for key in keys}
                      for flow, data in flows.items()}, indent=2))


if __name__ == '__main__':
    main()
