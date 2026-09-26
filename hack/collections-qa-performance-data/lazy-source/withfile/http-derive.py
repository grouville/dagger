"""Offline, aggregate-only proof from the four completed strict HTTP checks."""
from pathlib import Path
import hashlib
import json

LAB = Path(__file__).resolve().parent.parent
SRC = LAB / 'withfile-http-v1'
OUT = Path(__file__).resolve().parent
load = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')

rows = load(SRC / 'results.json')
assert len(rows) == 4 and all(r['correct'] and r['exit_code'] == 0 and not r['timed_out'] for r in rows)
assert load(SRC / 'restoration.json')['full_fixture_restored']
proof = {}
for row in rows:
    if not row['profile']:
        continue
    path = SRC / f"pair-{row['pair_index']}-{row['variant']}" / 'run.wcprof'
    with path.open() as stream:
        header = json.loads(next(stream))
        events = [json.loads(line) for line in stream]
    ops = {event['id']: event for event in events if event['e'] == 'op'}
    text = lambda event, key: header['strings'][event.get(key, 0)]
    epoch = header['epoch_unix_nano']
    summary = {
        'cli_seconds': row['seconds'],
        'profile_sha256': sha(path),
        'operations': len(ops),
        'events': len(events),
        'header_event_count': header['event_count'],
        'open': len(header.get('open_ops', [])),
        'dropped': header['dropped_events'],
        'started_before_cli': sum(epoch + op['s'] < row['started_unix_ns'] for op in ops.values()),
        'ended_after_cli': sum(epoch + op['d'] > row['exited_unix_ns'] for op in ops.values()),
        'earliest_operation_after_cli_start_seconds': (epoch + min(op['s'] for op in ops.values()) - row['started_unix_ns']) / 1e9,
        'latest_operation_before_cli_exit_seconds': (row['exited_unix_ns'] - epoch - max(op['d'] for op in ops.values())) / 1e9,
        'operation_span_seconds': (max(op['d'] for op in ops.values()) - min(op['s'] for op in ops.values())) / 1e9,
        'process_groups': {},
    }
    selected = {'go_build': [], 'otelgotest': []}
    for op in ops.values():
        if text(op, 'c') != 'exec.processRun' or not op.get('m'):
            continue
        argv = json.loads(text(op, 'm'))
        assert isinstance(argv, list)
        if argv[:2] == ['go', 'build']:
            selected['go_build'].append(op)
        elif argv and Path(argv[0]).name == 'otelgotest':
            selected['otelgotest'].append(op)
    for label, processes in selected.items():
        chains = []
        for process in processes:
            chain = []
            seen = set()
            op = process
            while op:
                assert op['id'] not in seen
                seen.add(op['id'])
                chain.append({'kind': op['k'], 'class': text(op, 'c'), 'outcome': op.get('o'), 'seconds': (op['d'] - op['s']) / 1e9})
                op = ops.get(op.get('p'))
            chains.append(chain)
        summary['process_groups'][label] = {
            'count': len(processes),
            'seconds': [(op['d'] - op['s']) / 1e9 for op in processes],
            'started_after_cli_start_seconds': [(epoch + op['s'] - row['started_unix_ns']) / 1e9 for op in processes],
            'parent_chains': chains,
        }
    proof[row['variant']] = summary
assert set(proof) == {'base', 'candidate'}
assert all(p['open'] == p['dropped'] == p['started_before_cli'] == p['ended_after_cli'] == 0 for p in proof.values())
assert all(p['process_groups']['go_build']['count'] >= 1 and p['process_groups']['otelgotest']['count'] == 1 for p in proof.values())
write('http-profile-proof.json', proof)
keys = ('variant','pair_index','profile','seconds','started_unix_ns','exited_unix_ns','exit_code','timed_out','correct','source_sha256','stdout_sha256','engine_cpu_seconds','engine_written_bytes','host_psi_delta_us','counter_bracket_seconds')
samples = []
for row in rows:
    item = {key: row[key] for key in keys}
    item['engine_read_bytes'] = sum(value.get('rbytes',0) for value in row['engine_io_delta'].values())
    item['engine_cpu_throttled_us'] = row['after']['engine_cpu']['throttled_usec'] - row['before']['engine_cpu']['throttled_usec']
    item['free_disk_before_bytes'] = row['before']['free_disk_bytes']
    item['free_disk_after_bytes'] = row['after']['free_disk_bytes']
    samples.append(item)
write('http-samples.json', samples)
write('http-summary.json', load(SRC / 'summary.json'))
write('http-restoration.json', load(SRC / 'restoration.json'))
old = [r for r in load(LAB/'withfile-v1/results.json') if r['phase'] == 'correctness-service']
assert len(old) == 2
write('http-verification.json', {
    'commands_attempted': len(load(SRC/'attempts.json')),
    'commands_validated': len(rows),
    'all_strict_revision_header_checks_passed': True,
    'ordinary_pairs': 1,
    'profiled_pairs': 1,
    'profiled_pair_order': ['candidate','base'],
    'all_profile_bounds_inside_cli': True,
    'all_profiles_open_and_dropped_zero': True,
    'full_fixture_restored': True,
    'same_input_each_pair': all(len({tuple(sorted(r['source_sha256'].items())) for r in rows if r['pair_index']==index}) == 1 for index in (0,1)),
    'different_inputs_across_pairs': rows[0]['source_sha256'] != rows[2]['source_sha256'],
    'engine_sha256': {v: load(SRC/'provenance.json')['engines'][v]['sha256'] for v in ('base','candidate')},
    'cli_sha256': load(SRC/'provenance.json')['engines']['cli_sha256'],
    'original_first_strict_http_seconds': {r['variant']:r['seconds'] for r in old},
    'original_outlier_cause': 'unresolved; original strict HTTP rows have no counter brackets or wcprof and unequal prior volume history',
    'scope': 'local-only fresh semantic edits on retained engines, not a cold comparison; do not pool profiled/unprofiled pairs',
    'source_sha256': {str(p.relative_to(LAB)): sha(p) for p in (SRC/'results.json',SRC/'summary.json',SRC/'provenance.json',SRC/'restoration.json',SRC/'driver.py.txt')},
    'private_payloads_archived': False,
})
print(json.dumps({v:{'operations':p['operations'],'open':p['open'],'dropped':p['dropped'],'go_build_seconds':p['process_groups']['go_build']['seconds'],'otelgotest_seconds':p['process_groups']['otelgotest']['seconds']} for v,p in proof.items()}))
for r in samples:
    print(json.dumps({k:r[k] for k in ('variant','pair_index','profile','seconds','engine_cpu_seconds','engine_read_bytes','engine_written_bytes','host_psi_delta_us','counter_bracket_seconds')}))
