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
root = family/'components'
root.mkdir(exist_ok=False)
engine = BenchEngine(root)
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
builds = []
for arm in ['baseline', 'candidate']:
    command = [go, 'test', '-p', '2', '-overlay', str(family/(arm+'-overlay.json')),
               '-c', '-o', str(root/(arm+'.test')), './core']
    with (root/(arm+'-build.log')).open('w') as out:
        result = subprocess.run(command, cwd='/tmp/dagger-filesync-snapshot-seeds',
                                stdout=out, stderr=subprocess.STDOUT)
    builds.append(dict(arm=arm, command=command, exit_code=result.returncode))
    (root/'builds.json').write_text(json.dumps(builds, indent=2)+'\n')
    assert result.returncode == 0, arm
(root/'binaries.json').write_text(json.dumps({arm: hashlib.sha256((root/(arm+'.test')).read_bytes()).hexdigest()
                                             for arm in ['baseline', 'candidate']}, indent=2)+'\n')
rows = []
for pair, order in enumerate([['baseline', 'candidate'], ['candidate', 'baseline']]*2):
    for arm in order:
        label = f'{pair}-{arm}'
        engine.idle(label)
        before = engine.pressure()
        started = time.monotonic()
        command = [str(root/(arm+'.test')), '-test.run=^$',
                   '-test.bench=^BenchmarkModuleHostFileReader$', '-test.benchtime=1000x', '-test.count=1']
        with (root/(label+'.log')).open('w') as out:
            result = subprocess.run(command, env=dict(os.environ, GOMAXPROCS='8'),
                                    stdout=out, stderr=subprocess.STDOUT)
        elapsed = time.monotonic()-started
        after = engine.pressure()
        output = (root/(label+'.log')).read_text()
        metrics = {}
        for line in output.splitlines():
            if line.startswith('BenchmarkModuleHostFileReader/'):
                words = line.split()
                name = words[0].split('/', 1)[1].rsplit('-', 1)[0]
                metrics[name] = {key: float(words[i-1]) for i, key in enumerate(words)
                                 if key in ['ns/op', 'B/op', 'allocs/op', 'requests/op']}
        row = dict(pair=pair, arm=arm, command=command, exit_code=result.returncode,
                   metrics=metrics, process_seconds=elapsed,
                   pressure={key: (after[key]-before[key])/(elapsed*1e6) for key in before})
        rows.append(row)
        (root/'samples.json').write_text(json.dumps(rows, indent=2)+'\n')
        print(label, json.dumps(metrics), flush=True)
        assert result.returncode == 0 and len(metrics)==3, (label, output[-2000:])
        expected = {'regular': 2 if arm=='baseline' else 1,
                    'missing': 1 if arm=='baseline' else 2,
                    'directory': 1 if arm=='baseline' else 2}
        assert all(metrics[name]['requests/op']==requests for name, requests in expected.items()), label
summary = {scenario: {arm: {key: statistics.median(row['metrics'][scenario][key] for row in rows if row['arm']==arm)
                           for key in ['ns/op', 'B/op', 'allocs/op', 'requests/op']}
                     for arm in ['baseline', 'candidate']}
           for scenario in rows[0]['metrics']}
(root/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2), flush=True)
