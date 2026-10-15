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
root = base / 'go-call-batch-profile'
root.mkdir(exist_ok=False)

def debug(route, data=None):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/wcprof/' + route, data=data)
    return urllib.request.urlopen(request, timeout=30)

with debug('enabled') as response:
    assert not json.load(response)['global_enabled']

summaries = {}
for variant in ['before', 'after']:
    source = Path('/tmp/rust-native-go-call-130-' + variant)
    filename = source / 'leaf_0127/src/lib.rs'
    text, count = re.subn(r'pub const EDIT: u64 = \d+;',
                         f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
    assert count == 1
    filename.write_text(text)
    debug('enabled', b'on').close()
    with debug('dump') as response:
        while response.read(1048576):
            pass
    try:
        started = time.monotonic()
        with (root / (variant + '.log')).open('w') as output:
            process = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', 'rust:check'],
                cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276'),
                stdout=output, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        assert not process.returncode, variant
    finally:
        debug('enabled', b'off').close()
        with debug('dump') as response, (root / (variant + '.ndjson')).open('wb') as output:
            while data := response.read(1048576):
                output.write(data)
    with (root / (variant + '.ndjson')).open() as data:
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
    summaries[variant] = dict(seconds=seconds, events=header['event_count'],
        dropped_events=header['dropped_events'], open_ops=header.get('open_ops', 0),
        calls={name: calls[name] for name in ['Directory.withoutDirectory', 'Directory.withoutFiles',
                                            'Directory.directory', 'Directory.digest']},
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
    summaries[variant]['metadata_requests'] = len(requests)
    summaries[variant]['metadata_query_sum_ms'] = sum((op['d'] - op['s']) / 1e6 for op in requests.values())
    summaries[variant]['metadata_request_envelope_ms'] = (max(op['d'] for op in requests.values()) - min(op['s'] for op in requests.values())) / 1e6
    summaries[variant]['session_queries'] = sum(op['cls'] == 'session.query' for op in ops)
    print(variant, 'metadata requests', len(requests), 'metadata envelope ms', summaries[variant]['metadata_request_envelope_ms'], 'total queries', summaries[variant]['session_queries'], flush=True)
(root / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
print('PASS: fresh edited root-package command profiles', flush=True)
