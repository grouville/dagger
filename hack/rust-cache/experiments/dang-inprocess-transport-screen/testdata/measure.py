from pathlib import Path
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
import urllib.request

root = Path(__file__).parent
binary = root / 'shared.test'
env = dict(os.environ, GOMAXPROCS='8')
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
cgroup = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')


def engine_cpu():
    return int(next(line.split()[1] for line in (cgroup / 'cpu.stat').read_text().splitlines() if line.startswith('usage_usec '))) / 1e6


def pressure():
    return {kind: int((Path('/proc/pressure') / kind).read_text().splitlines()[0].split('total=')[1]) for kind in ['cpu', 'io']}


def idle(label):
    started = time.monotonic()
    while True:
        a, cpu = pressure(), engine_cpu()
        tick = time.monotonic()
        time.sleep(1)
        seconds = time.monotonic() - tick
        rates = {key: (value - a[key]) / (seconds * 1e6) for key, value in pressure().items()}
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle', timeout=10) as response:
            lifecycle = json.load(response)
        quiet = not lifecycle.get('sessions') and lifecycle['active_requests'] == 0 and (engine_cpu() - cpu) / seconds < .15 and rates['cpu'] < .10 and rates['io'] < .05
        with (root / 'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, admitted=quiet, pressure=rates)) + '\n')
        if quiet:
            return
        assert time.monotonic() - started < 180, 'quiet admission timeout'


metadata = dict(pairs=4, requests=[0, 2, 8], orders=[['tcp', 'handler'] if pair % 2 == 0 else ['handler', 'tcp'] for pair in range(4)],
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), gomaxprocs=8, benchtime='500ms',
                sources={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [root / 'transport_bench_test.go', root / 'test-overlay.json']},
                scope='Component screen only. Handler arm is a benchmark-only lower-cost model, not a production transport. Same GraphQL encoding and decoding, no engine work in mock handler.',
                no_engine_change=True, normal_go_gc=True, no_telemetry_change=True)
(root / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
with (root / 'correctness.log').open('w') as output:
    tests = subprocess.run([str(binary), '-test.v', '-test.timeout=30s'], env=env, stdout=output, stderr=subprocess.STDOUT)
assert tests.returncode == 0, 'existing shared SDK tests failed'
(root / 'correctness.json').write_text(json.dumps(dict(exit_code=tests.returncode), indent=2) + '\n')

rows = []
for requests in metadata['requests']:
    for pair, order in enumerate(metadata['orders']):
        for arm in order:
            label = f'{requests}-{pair}-{arm}'
            command = [str(binary), '-test.run=^$', f'-test.bench=^BenchmarkNestedGraphQLTransport/{arm}/{requests}$', '-test.benchtime=500ms', '-test.count=1', '-test.timeout=30s']
            idle(label)
            with (root / (label + '.log')).open('w') as output:
                result = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT)
            row = dict(requests=requests, pair=pair, arm=arm, exit_code=result.returncode, command=command)
            rows.append(row)
            if result.returncode == 0:
                match = re.search(r'^BenchmarkNestedGraphQLTransport/\S+\s+(\d+)\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op', (root / (label + '.log')).read_text(), re.M)
                assert match, label
                row.update(iterations=int(match[1]), ns_per_op=float(match[2]), bytes_per_op=float(match[3]), allocations=float(match[4]))
            (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            assert result.returncode == 0, label

summary = {}
for requests in metadata['requests']:
    group = [row for row in rows if row['requests'] == requests]
    values = {arm: {metric: statistics.median(row[metric] for row in group if row['arm'] == arm) for metric in ['ns_per_op', 'bytes_per_op', 'allocations']} for arm in ['tcp', 'handler']}
    values['faster_pairs'] = sum(next(row['ns_per_op'] for row in group if row['pair'] == pair and row['arm'] == 'handler') < next(row['ns_per_op'] for row in group if row['pair'] == pair and row['arm'] == 'tcp') for pair in range(4))
    summary[str(requests)] = values
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2), flush=True)
