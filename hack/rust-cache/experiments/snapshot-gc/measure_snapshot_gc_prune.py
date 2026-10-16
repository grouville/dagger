"""Six alternating fresh-process comparisons of the actual server prune path."""

import hashlib
import json
import re
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path('/tmp/rust-cache-sipsma-review/snapshot-gc-causal')
OUTPUT = ROOT / 'upstream-prune-pairs'
ENGINE = 'dagger-rust-parser-state-pool-oct14'
WORK = Path('/tmp/dagger-coalesce-snapshot-gc-upstream')
OUTPUT.mkdir(exist_ok=False)


def write(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2) + '\n')


def pressure():
    result = {}
    for kind in ['cpu', 'io', 'memory']:
        for line in Path('/proc/pressure', kind).read_text().splitlines():
            result[kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return result


def admit(label):
    start = time.monotonic()
    while True:
        before = pressure()
        now = time.monotonic()
        time.sleep(1)
        elapsed = time.monotonic() - now
        after = pressure()
        fractions = {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle', timeout=10) as response:
            state = json.load(response)
        ok = fractions['io.some'] < .02 and not state.get('sessions') and state['active_requests'] == 0
        with (OUTPUT / 'admission.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(label=label, admitted=ok, stall_fraction=fractions)) + '\n')
        if ok:
            return
        assert time.monotonic() - start < 90, 'admission timeout; retain completed samples'


for arm in ['before', 'after']:
    subprocess.run(['docker', 'cp', str(ROOT / f'upstream-{arm}.test'), f'{ENGINE}:/tmp/prune-{arm}.test'], check=True)

cpu_model = next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
write('metadata.json', dict(
    upstream='717589c9ccacbba7d3cf902647aa5c9ca68085e8',
    production_change='engine/server/server.go: snapshotGarbage.Collect -> CollectIfPending',
    source_sha256={name: hashlib.sha256((WORK / name).read_bytes()).hexdigest() for name in [
        'engine/server/server.go', 'engine/server/cache_gc_wiring_test.go', 'engine/server/cache_gc_wiring_bench_test.go']},
    binary_sha256={arm: hashlib.sha256((ROOT / f'upstream-{arm}.test').read_bytes()).hexdigest() for arm in ['before', 'after']},
    engine=json.loads(subprocess.check_output(['docker', 'inspect', ENGINE]))[0]['Id'],
    go=subprocess.check_output(['go', 'version'], text=True).strip(), cpu=cpu_model,
    gomaxprocs=8, pairs=6, benchtime='150ms',
    scope='Warm metadata-only explicit prune; real server initialization, fixture insertion and retained snapshot construction excluded from timer. All snapshots remain leased and are checked after each sub-benchmark.',
    fixture_environment_unset='_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT',
    full_command_benefit_measured=False,
))

rows = []
pattern = re.compile(r'(\d+)\s+([\d.]+) ns/op\s+([\d.]+) collections/op\s+(\d+) B/op\s+(\d+) allocs/op')
for pair in range(6):
    order = ['before', 'after'] if pair % 2 == 0 else ['after', 'before']
    for arm in order:
        label = f'{pair}-{arm}'
        admit(label)
        before = pressure()
        start = time.monotonic()
        with (OUTPUT / (label + '.log')).open('w') as stream:
            process = subprocess.run([
                'docker', 'exec', ENGINE, 'env', '-u', '_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT',
                'GOMAXPROCS=8', f'/tmp/prune-{arm}.test', '-test.run=^$',
                '-test.bench=^BenchmarkLocalCacheMetadataPrune$', '-test.benchtime=150ms', '-test.count=1',
            ], stdout=stream, stderr=subprocess.STDOUT)
        elapsed = time.monotonic() - start
        after = pressure()
        # Production logs can appear between testing's benchmark name and its
        # numeric result; keep the name while scanning the complete raw log.
        matches = []
        name = None
        for line in (OUTPUT / (label + '.log')).read_text().splitlines():
            named = re.match(r'^(BenchmarkLocalCacheMetadataPrune/\S+)', line)
            if named:
                name = named.group(1)
            metrics = pattern.search(line)
            if metrics:
                assert name
                matches.append((name, *metrics.groups()))
        assert process.returncode == 0 and len(matches) == 2, (label, process.returncode, matches)
        row = dict(pair=pair, arm=arm, process_seconds=elapsed,
                   stall_fraction={k: (after[k] - before[k]) / (elapsed * 1e6) for k in before},
                   benchmarks={name: dict(iterations=int(n), ns_per_op=float(ns), collections_per_op=float(gc),
                                         bytes_per_op=int(alloc_bytes), allocations_per_op=int(allocs))
                               for name, n, ns, gc, alloc_bytes, allocs in matches})
        rows.append(row)
        write('runs.json', rows)
        print(label, json.dumps(row['benchmarks']), flush=True)

summary = {}
for name in rows[0]['benchmarks']:
    arms = {arm: [r['benchmarks'][name] for r in rows if r['arm'] == arm] for arm in ['before', 'after']}
    savings = [arms['before'][i]['ns_per_op'] - arms['after'][i]['ns_per_op'] for i in range(6)]
    summary[name] = dict(
        **{arm: {metric: statistics.median(r[metric] for r in values)
                 for metric in ['ns_per_op', 'collections_per_op', 'bytes_per_op', 'allocations_per_op']}
           for arm, values in arms.items()},
        median_paired_saving_ns=statistics.median(savings), faster_pairs=sum(n > 0 for n in savings),
    )
write('summary.json', summary)
print(json.dumps(summary, indent=2))
