from pathlib import Path
import hashlib
import json
import os
import re
import statistics
import subprocess
import time

root = Path(__file__).parent
env = dict(os.environ, GOMAXPROCS='8')

def pressure():
    return {kind: int((Path('/proc/pressure') / kind).read_text().splitlines()[0].split('total=')[1]) for kind in ['cpu', 'io', 'memory']}

def quiet():
    start = time.monotonic()
    while True:
        before = pressure(); tick = time.monotonic(); time.sleep(1)
        elapsed = time.monotonic() - tick; after = pressure()
        stalls = {kind: (after[kind] - before[kind]) / (elapsed * 1e6) for kind in before}
        if stalls['cpu'] < .10 and stalls['io'] < .05:
            return
        assert time.monotonic() - start < 120, stalls

rows = []
for pair in range(6):
    for arm in (['before', 'after'] if pair % 2 == 0 else ['after', 'before']):
        quiet()
        command = [str(root / (arm + '.test')), '-test.run=^$', '-test.bench=^BenchmarkTreeFingerprintWorkspace$', '-test.benchtime=150ms', '-test.count=1']
        before = pressure(); tick = time.monotonic()
        result = subprocess.run(command, cwd='/tmp/dagger-filesync-snapshot-seeds', env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        elapsed = time.monotonic() - tick; after = pressure()
        (root / f'pair-{pair}-{arm}.log').write_text(result.stdout)
        assert result.returncode == 0, result.returncode
        values = {}
        for line in result.stdout.splitlines():
            match = re.match(r'BenchmarkTreeFingerprintWorkspace/crates=(\d+)-\d+\s+\d+\s+([0-9.]+) ns/op\s+([0-9.]+) B/op\s+([0-9.]+) allocs/op', line)
            if match:
                size, ns, allocated, allocations = match.groups()
                values[size] = dict(ns=float(ns), bytes=float(allocated), allocations=float(allocations))
        assert set(values) == {'128', '1026'}, result.stdout[-1000:]
        rows.append(dict(pair=pair, arm=arm, seconds=elapsed, command=command, values=values, stall_fraction={k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}))
        (root / 'component-runs.json').write_text(json.dumps(rows, indent=2) + '\n')
        print('PASS', pair, arm, values, flush=True)

summary = {}
for size in ['128', '1026']:
    summary[size] = {arm: {field: statistics.median(r['values'][size][field] for r in rows if r['arm'] == arm) for field in ['ns', 'bytes', 'allocations']} for arm in ['before', 'after']}
    summary[size]['faster_pairs'] = sum(next(r['values'][size]['ns'] for r in rows if r['pair'] == pair and r['arm'] == 'after') < next(r['values'][size]['ns'] for r in rows if r['pair'] == pair and r['arm'] == 'before') for pair in range(6))
(root / 'component-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2), flush=True)
