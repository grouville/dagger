from pathlib import Path
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
import urllib.request

root = Path('/tmp/rust-cache-sipsma-review/containerd-mark-graph')
output = root / 'paired'
output.mkdir(exist_ok=False)


def write(name, value):
    (output / name).write_text(json.dumps(value, indent=2) + '\n')


def pressure():
    return {kind + '.' + line.split()[0]: int(line.split('total=')[1])
            for kind in ['cpu', 'io', 'memory']
            for line in Path('/proc/pressure', kind).read_text().splitlines()}


def admit(label):
    started = time.monotonic()
    while True:
        before = pressure()
        now = time.monotonic()
        time.sleep(1)
        elapsed = time.monotonic() - now
        after = pressure()
        fractions = {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle', timeout=10) as response:
            state = json.load(response)
        ok = not state.get('sessions') and state['active_requests'] == 0 and fractions['io.some'] < .02
        with (output / 'admission.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(label=label, admitted=ok, stall_fraction=fractions)) + '\n')
        if ok: return
        assert time.monotonic() - started < 90, 'admission timeout; retain completed observations'


with (root / 'containerdmeta.db').open('rb') as stream:
    database_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
write('metadata.json', dict(
    source_version='containerd v2.2.5', toolchain=subprocess.check_output(['go', 'version'], text=True).strip(),
    gomaxprocs=8, pairs=6, database_sha256=database_hash,
    original_gc_sha256=hashlib.sha256((root / 'gc-before.go').read_bytes()).hexdigest(),
    candidate_gc_sha256=hashlib.sha256(Path('/tmp/containerd-gc-source/pkg/gc/gc.go').read_bytes()).hexdigest(),
    binary_sha256={name: hashlib.sha256((root / (name + '.test')).read_bytes()).hexdigest()
                   for name in ['metadata-before', 'metadata-after', 'gc-before', 'gc-after']},
    benchmark_source_sha256=hashlib.sha256(Path('/tmp/containerd-gc-source/core/metadata/retained_mark_bench_test.go').read_bytes()).hexdigest(),
    scope='Read-only mark phase on a consistent copy of the retained engine metadata database. Graph loading and independent oracle validation excluded from timer. No snapshot or content deletion; no complete-command claim.',
    graph=json.loads((root / 'graph-statistics.json').read_text()),
))

env = dict(os.environ, GOMAXPROCS='8', DAGGER_GC_GRAPH_ROOT=str(root))
rows = []
pattern = re.compile(r'^(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op(?:\s+([\d.]+) retained)?\s+(\d+) B/op\s+(\d+) allocs/op$', re.M)
for pair in range(6):
    for arm in (['before', 'after'] if pair % 2 == 0 else ['after', 'before']):
        label = f'{pair}-{arm}'
        admit(label)
        before = pressure()
        started = time.monotonic()
        benchmarks = {}
        for package, name, duration in [('metadata', '^BenchmarkDaggerRetainedMark$', '1x'),
                                         ('gc', '^BenchmarkTricolorUniqueRoots$', '150ms')]:
            logfile = output / (label + '-' + package + '.log')
            with logfile.open('w') as stream:
                result = subprocess.run([str(root / f'{package}-{arm}.test'), '-test.run=^$',
                                         '-test.bench=' + name, '-test.benchtime=' + duration,
                                         '-test.count=1'], env=env, stdout=stream, stderr=subprocess.STDOUT)
            matches = pattern.findall(logfile.read_text())
            assert result.returncode == 0 and len(matches) == (1 if package == 'metadata' else 2), (label, package, result.returncode, matches)
            for name, n, ns, retained, allocated, allocations in matches:
                if retained: assert int(float(retained)) == 77772
                benchmarks[name] = dict(iterations=int(n), ns_per_op=float(ns), bytes_per_op=int(allocated),
                                        allocations_per_op=int(allocations), retained=int(float(retained)) if retained else None)
        elapsed = time.monotonic() - started
        after = pressure()
        rows.append(dict(pair=pair, arm=arm, process_seconds=elapsed, benchmarks=benchmarks,
                         stall_fraction={k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}))
        write('runs.json', rows)
        print(label, json.dumps(benchmarks), flush=True)

summary = {}
for name in rows[0]['benchmarks']:
    values = {arm: [r['benchmarks'][name] for r in rows if r['arm'] == arm] for arm in ['before', 'after']}
    savings = [values['before'][i]['ns_per_op'] - values['after'][i]['ns_per_op'] for i in range(6)]
    summary[name] = {arm: {metric: statistics.median(r[metric] for r in observations)
                           for metric in ['ns_per_op', 'bytes_per_op', 'allocations_per_op']}
                     for arm, observations in values.items()}
    summary[name].update(median_paired_saving_ns=statistics.median(savings), faster_pairs=sum(n > 0 for n in savings))
with (root / 'containerdmeta.db').open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == database_hash, 'database copy changed'
write('summary.json', summary)
print(json.dumps(summary, indent=2))
