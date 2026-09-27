from pathlib import Path
from collections import defaultdict
import hashlib
import json
import re
import statistics

H = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows = []
runs = json.loads((H / 'benchmark-runs.json').read_text())
assert len(runs) == 6 and all(row['exit_code'] == 0 for row in runs)
pattern = re.compile(r'^(Benchmark\S+)-4\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op$')
for run in runs:
    path = H / ('bench-%d-%s.log' % (run['cycle'], run['variant']))
    assert sha(path) == run['log_sha256']
    parsed = 0
    for line in path.read_text().splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        name, iterations, ns, bytes_, allocs = match.groups()
        rows.append({'case': name, 'cycle': run['cycle'], 'variant': run['variant'], 'iterations': int(iterations), 'ns_per_op': float(ns), 'bytes_per_op': int(bytes_), 'allocations_per_op': int(allocs)})
        parsed += 1
    assert parsed == 11, parsed
summary = []
for name in sorted({row['case'] for row in rows}):
    item = {'case': name}
    for variant in ('baseline', 'candidate'):
        samples = [row for row in rows if row['case'] == name and row['variant'] == variant]
        assert len(samples) == 3
        item[variant] = {key: statistics.median(row[key] for row in samples) for key in ('ns_per_op', 'bytes_per_op', 'allocations_per_op')}
    item['percent_change'] = {key: (item['candidate'][key] / item['baseline'][key] - 1) * 100 for key in item['baseline']}
    item['paired_ns_delta'] = [next(row['ns_per_op'] for row in rows if row['case'] == name and row['variant'] == 'candidate' and row['cycle'] == cycle) - next(row['ns_per_op'] for row in rows if row['case'] == name and row['variant'] == 'baseline' and row['cycle'] == cycle) for cycle in range(3)]
    summary.append(item)
result = {'reducer_sha256': sha(__file__), 'n_per_variant': 3, 'order': ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate'], 'GOMAXPROCS': 4, 'benchtime': '200ms', 'samples': rows, 'summary': summary, 'scope': 'Warm-host local library microbenchmarks only. No cold-engine, inference, whole CLI or end-to-end speedup claim.'}
(H / 'numeric-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(summary, indent=2))
