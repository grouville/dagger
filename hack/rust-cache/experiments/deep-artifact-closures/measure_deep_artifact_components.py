from pathlib import Path
import hashlib
import json
import os
import re
import statistics
import subprocess
import time

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'deep-artifact-components'
root.mkdir(exist_ok=False)
module = Path('/tmp/dagger-rust-native-deep-artifact-closures/compiler')
env = dict(os.environ, GOMAXPROCS='8')
overlay = {}
hashes = {}
for name in ['history.go', 'batch.go']:
    path = module/'replay'/name
    original = subprocess.check_output(['git', 'show', 'e63b6a2:compiler/replay/'+name], cwd=module)
    saved = root/('before-'+name)
    saved.write_bytes(original)
    overlay[str(path)] = str(saved)
    hashes[name] = {'before': hashlib.sha256(original).hexdigest(), 'after': hashlib.sha256(path.read_bytes()).hexdigest()}
(root/'baseline-overlay.json').write_text(json.dumps({'Replace': overlay}, indent=2)+'\n')
(root/'source-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
for arm in ['before', 'after']:
    command = ['/home/dagger/.local/bin/go', 'test', '-c', '-o', str(root/(arm+'.test'))]
    if arm == 'before':
        command += ['-overlay='+str(root/'baseline-overlay.json')]
    command += ['./replay']
    with (root/(arm+'-build.log')).open('w') as output:
        subprocess.run(command, cwd=module, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def pressure():
    return {kind: {line.split()[0]: int(line.split('total=')[1]) for line in Path('/proc/pressure', kind).read_text().splitlines()}
            for kind in ['cpu', 'io', 'memory']}


samples = []
for index in range(6):
    for arm in (['before', 'after'] if index % 2 == 0 else ['after', 'before']):
        before = pressure()
        started = time.monotonic()
        with (root/(str(index)+'-'+arm+'.log')).open('w') as output:
            subprocess.run([str(root/(arm+'.test')), '-test.run=^$', '-test.bench=^BenchmarkNativeHistoryGraph$',
                            '-test.benchmem', '-test.benchtime=150ms', '-test.count=1'],
                           cwd=module, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
        seconds = time.monotonic()-started
        after = pressure()
        values = {}
        for line in (root/(str(index)+'-'+arm+'.log')).read_text().splitlines():
            match = re.match(r'^BenchmarkNativeHistoryGraph/(.+)-8\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op$', line)
            if match:
                name, n, nanos, bytes_, allocs = match.groups()
                values[name] = dict(iterations=int(n), ns=float(nanos), bytes=int(bytes_), allocs=int(allocs))
        assert len(values) == 16, (arm, index, values.keys())
        samples.append(dict(pair=index, arm=arm, seconds=seconds, values=values,
                            host_pressure={kind: {key: (after[kind][key]-before[kind][key])/(seconds*1e6) for key in before[kind]} for kind in before}))
        (root/'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
        print('PASS', index, arm, round(seconds, 2), 'seconds', flush=True)
summary = {}
for name in samples[0]['values']:
    summary[name] = {arm: {key: statistics.median(s['values'][name][key] for s in samples if s['arm'] == arm)
                          for key in ['ns', 'bytes', 'allocs']} for arm in ['before', 'after']}
    summary[name]['faster_pairs'] = sum(next(s for s in samples if s['pair'] == i and s['arm'] == 'after')['values'][name]['ns'] <
                                       next(s for s in samples if s['pair'] == i and s['arm'] == 'before')['values'][name]['ns'] for i in range(6))
(root/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary), flush=True)
