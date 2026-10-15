import collections
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'owner-lease-phases-profile'
root.mkdir(exist_ok=False)

def debug(route, data=None):
    request = urllib.request.Request('http://127.0.0.1:16103/debug/wcprof/' + route, data=data)
    return urllib.request.urlopen(request, timeout=30)

with debug('enabled') as response:
    assert not json.load(response)['global_enabled']


record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-checkpoint-snapshot-key-oct14']))[0]
group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
def io_state():
    pressure = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                pressure[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return dict(pressure=pressure, engine_io=(group/'io.stat').read_text(), vmstat='\n'.join(line for line in Path('/proc/vmstat').read_text().splitlines() if line.split()[0] in ['nr_dirty','nr_writeback','pgpgin','pgpgout','pswpin','pswpout']))

for variant in ['before', 'after']:
    source = Path('/tmp/rust-native-bulk-digests-1026-' + variant)
    filename = source/'leaf_1023/src/lib.rs'
    text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
    assert count == 1
    filename.write_text(text)
    with (root/('prepare-' + variant + '.log')).open('w') as output:
        result = subprocess.run(['python3', str(base/'local_cli.py'), 'check', 'rust:check'], cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16275'), stdout=output, stderr=subprocess.STDOUT)
    assert not result.returncode, variant
    print('fresh-edit preparation', variant, 'PASS', flush=True)

summaries = {}
for case, variant in enumerate(['before', 'after', 'before', 'after', 'before', 'after']):
    label = f'{case}-{variant}'
    source = Path('/tmp/rust-native-bulk-digests-1026-' + variant)
    filename = source / 'leaf_1023/src/lib.rs'
    text, count = re.subn(r'pub const EDIT: u64 = \d+;',
                         f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
    assert count == 1
    filename.write_text(text)
    debug('enabled', b'on').close()
    with debug('dump') as response:
        while response.read(1048576):
            pass
    try:
        io_before = io_state()
        started = time.monotonic()
        with (root / (label + '.log')).open('w') as output:
            process = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', 'rust:check'],
                cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16275'),
                stdout=output, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        io_after = io_state()
        assert not process.returncode, variant
    finally:
        debug('enabled', b'off').close()
        with debug('dump') as response, (root / (label + '.ndjson')).open('wb') as output:
            while data := response.read(1048576):
                output.write(data)
    with (root / (label + '.ndjson')).open() as data:
        header = json.loads(next(data))
        assert not header['dropped_events'] and not header.get('open_ops'), header
        names = header['strings']
        ops = [dict(item, cls=names[item.get('c', 0)], ident=names[item.get('i', 0)])
               for item in map(json.loads, data) if item['e'] == 'op']
    calls = collections.Counter(o['cls'] for o in ops if o['k'] == 'call_exec')
    classes = collections.defaultdict(lambda: [0, 0.0])
    for op in ops:
        name = op['k'] + ' ' + op['cls']
        classes[name][0] += 1
        classes[name][1] += (op['d'] - op['s']) / 1e6
    summaries[label] = dict(seconds=seconds, events=header['event_count'],
        dropped_events=header['dropped_events'], open_ops=header.get('open_ops', 0),
        calls={name: calls[name] for name in ['Directory.withoutDirectory', 'Directory.withoutFiles',
                                            'Directory.directory', 'Directory.digest', 'Directory.digests']},
        workloads_ms=[(o['d'] - o['s']) / 1e6 for o in ops if o['cls'] == 'exec.workload'],
        classes={name: dict(count=value[0], total_ms=value[1]) for name, value in classes.items()})
    by = {op['id']: op for op in ops}
    requests = {}
    for op in ops:
        if op['k'] != 'call_exec' or op['cls'] not in ['FunctionCall.parentName', 'FunctionCall.name', 'FunctionCall.parent', 'FunctionCall.inputArgs', 'FunctionCallArgValue.name', 'FunctionCallArgValue.value']:
            continue
        current = op
        while current.get('p') in by and current['cls'] != 'session.query':
            current = by[current['p']]
        if current['cls'] == 'session.query':
            requests[current['id']] = current
    summaries[label]['metadata_requests'] = len(requests)
    summaries[label]['io_before'] = io_before
    summaries[label]['io_after'] = io_after
    summaries[label]['metadata_query_sum_ms'] = sum((op['d'] - op['s']) / 1e6 for op in requests.values())
    summaries[label]['metadata_request_envelope_ms'] = (max(op['d'] for op in requests.values()) - min(op['s'] for op in requests.values())) / 1e6
    summaries[label]['session_queries'] = sum(op['cls'] == 'session.query' for op in ops)
    print(label, 'metadata requests', len(requests), 'metadata envelope ms', summaries[label]['metadata_request_envelope_ms'], 'total queries', summaries[label]['session_queries'], flush=True)
(root / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
print('PASS: fresh edited root-package command profiles', flush=True)
