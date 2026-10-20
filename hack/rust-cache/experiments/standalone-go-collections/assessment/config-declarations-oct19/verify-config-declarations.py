"""Check behavior and both reuse/miss costs on current upstream main."""
from pathlib import Path
import json
import argparse
import os
import re
import statistics
import subprocess
import time

out = Path('/tmp/go-collection-upstream-review-oct19')
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ, GOMAXPROCS='8', GOTOOLCHAIN='local', GOWORK='off', GOPROXY='off', GOSUMDB='off')
sources = {'main': out / 'engine-config-main', 'candidate': out / 'engine-config-review'}
parser = argparse.ArgumentParser()
parser.add_argument('--bench-only', action='store_true')
args = parser.parse_args()
records = [row for row in json.loads((out / 'config-review-checks.json').read_text()) if row['label'] in ['main-race', 'main-build', 'candidate-race', 'candidate-build']] if args.bench_only else []


def command(label, args, cwd):
    started = time.monotonic()
    log = out / ('config-review-' + label + '.log')
    with log.open('w') as output:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=300)
    record = dict(label=label, command=args, cwd=str(cwd), log=str(log),
                  seconds=time.monotonic() - started, exit_code=result.returncode)
    records.append(record)
    (out / 'config-review-checks.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps(record), flush=True)
    assert result.returncode == 0, log.read_text()[-4000:]
    return log


for arm, source in ([] if args.bench_only else sources.items()):
    command(arm + '-race', [go, 'test', '-p=2', '-race', '-count=1', './core/workspace'], source)
    command(arm + '-build', [go, 'test', '-p=2', '-c', '-o', str(out / ('config-review-' + arm + '.test')), './core/workspace'], source)

samples = []
for scenario in ['repeated-content', 'parallel-repeated-content', 'distinct-content']:
    for pair in range(4):
        for arm in (['main', 'candidate'] if pair % 2 == 0 else ['candidate', 'main']):
            log = command(f'{scenario}-{pair}-{arm}', [str(out / ('config-review-' + arm + '.test')),
                          '-test.run=^$', '-test.bench=^BenchmarkGitClientDeclarations$/^' + scenario + '$',
                          '-test.benchtime=5000x', '-test.count=1', '-test.cpu=8', '-test.benchmem'], sources[arm] / 'core/workspace')
            match = re.search(r'^BenchmarkGitClientDeclarations/[^\s]+\s+\d+\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op', log.read_text(), re.M)
            assert match, log.read_text()
            samples.append(dict(scenario=scenario, pair=pair, arm=arm, nanoseconds=float(match[1]),
                                bytes=float(match[2]), allocations=float(match[3]), log=str(log)))
            (out / 'config-review-samples.json').write_text(json.dumps(samples, indent=2) + '\n')

summary = []
for scenario in dict.fromkeys(row['scenario'] for row in samples):
    rows = [row for row in samples if row['scenario'] == scenario]
    before = sorted((row for row in rows if row['arm'] == 'main'), key=lambda row: row['pair'])
    after = sorted((row for row in rows if row['arm'] == 'candidate'), key=lambda row: row['pair'])
    item = dict(scenario=scenario, pairs=len(before), faster_pairs=sum(a['nanoseconds'] < b['nanoseconds'] for b, a in zip(before, after)))
    for field in ['nanoseconds', 'bytes', 'allocations']:
        item['before_' + field] = statistics.median(row[field] for row in before)
        item['after_' + field] = statistics.median(row[field] for row in after)
    summary.append(item)
(out / 'config-review-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(dict(event='complete', summary=summary)), flush=True)
