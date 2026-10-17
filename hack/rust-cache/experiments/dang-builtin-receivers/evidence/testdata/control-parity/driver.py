from pathlib import Path
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, '/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
from bench_engine import BenchEngine

family = Path(__file__).parent
root = family / 'control-parity'
root.mkdir(exist_ok=False)
engine = BenchEngine(root)
rows = []
orders = [
    ['baseline', 'control', 'candidate'],
    ['candidate', 'control', 'baseline'],
    ['control', 'baseline', 'candidate'],
    ['candidate', 'baseline', 'control'],
]
(root / 'driver.py').write_bytes(Path(__file__).read_bytes())
(root / 'binaries.json').write_text(json.dumps({
    name: hashlib.sha256((family / name).read_bytes()).hexdigest()
    for name in ['before.test', 'controlled.test']
}, indent=2) + '\n')
for pair, order in enumerate(orders):
    for arm in order:
        label = f'{pair}-{arm}'
        binary = family / ('before.test' if arm == 'baseline' else 'controlled.test')
        env = dict(os.environ, GOMAXPROCS='8',
                   DAGGER_BUILTIN_RECEIVERS_TEST_MODE='on' if arm == 'candidate' else 'off')
        command = [str(binary), '-test.run=^$',
                   '-test.bench=^BenchmarkBuiltinReceiverExpression$',
                   '-test.benchtime=100000x', '-test.count=1']
        engine.idle(label)
        before = engine.pressure()
        started = time.monotonic()
        with (root / (label + '.log')).open('w') as out:
            result = subprocess.run(command, env=env, stdout=out, stderr=subprocess.STDOUT)
        elapsed = time.monotonic() - started
        after = engine.pressure()
        output = (root / (label + '.log')).read_text()
        assert result.returncode == 0, (label, output[-2000:])
        metrics = {}
        for line in output.splitlines():
            if not line.startswith('BenchmarkBuiltinReceiverExpression/'):
                continue
            words = line.split()
            name = words[0].split('/', 1)[1].rsplit('-', 1)[0]
            metrics[name] = {key: float(words[i-1]) for i, key in enumerate(words)
                             if key in ['ns/op', 'B/op', 'allocs/op']}
        assert set(metrics) == {'string', 'list-block'}, (label, output[-1000:])
        row = dict(pair=pair, arm=arm, command=command, exit_code=result.returncode,
                   process_seconds=elapsed, metrics=metrics,
                   pressure={key: (after[key]-before[key])/(elapsed*1e6) for key in before})
        rows.append(row)
        (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(label, json.dumps(metrics), flush=True)
summary = {scenario: {
    arm: {key: statistics.median(row['metrics'][scenario][key] for row in rows if row['arm'] == arm)
          for key in ['ns/op', 'B/op', 'allocs/op']}
    for arm in ['baseline', 'control', 'candidate']
} for scenario in ['string', 'list-block']}
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2), flush=True)
