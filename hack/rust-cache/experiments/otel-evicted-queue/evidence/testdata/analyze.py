from pathlib import Path
from collections import defaultdict
import json
import re
import statistics

root = Path(__file__).parent
cases = defaultdict(lambda: defaultdict(list))
pattern = re.compile(r'^(Benchmark\S+)-\d+\s+\d+\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op')
for file in sorted(root.glob('*-benchmark.log')) + sorted(root.glob('bounds-*.log')):
    arm = 'before' if 'before' in file.name else 'after'
    for line in file.read_text().splitlines():
        if match := pattern.match(line):
            name, ns, size, count = match.groups()
            cases[name][arm].append(dict(ns=float(ns), bytes=int(size), allocs=int(count)))
components = {name: {arm: dict(samples=len(values), **{
    key: statistics.median(v[key] for v in values) for key in ['ns', 'bytes', 'allocs']
}) for arm, values in arms.items()} for name, arms in cases.items()}
(root / 'components.json').write_text(json.dumps(components, indent=2)+'\n')

rows = json.loads((root / 'full-command-paired/samples.json').read_text())
pairs = []
for pair in sorted({r['pair'] for r in rows if r['pair'] > 0}):
    arms = {r['arm']: r for r in rows if r['pair'] == pair}
    if len(arms) != 2:
        continue
    before, after = arms['before'], arms['after']
    pairs.append(dict(pair=pair, before_seconds=before['seconds'], after_seconds=after['seconds'],
        saving_seconds=before['seconds']-after['seconds'],
        both_succeeded=before['exit_code'] == after['exit_code'] == 0,
        same_rows=before['same_rows'] and after['same_rows']))
good = [p for p in pairs if p['both_succeeded'] and p['same_rows']]
valid = {arm: [r for r in rows if r['pair'] in {p['pair'] for p in good} and r['arm'] == arm]
         for arm in ['before', 'after']}
median = statistics.median
analysis = dict(pairs=pairs, successful_pairs=len(good),
    faster_successful_pairs=sum(p['saving_seconds'] > 0 for p in good),
    median_paired_saving_seconds=median(p['saving_seconds'] for p in good),
    median_seconds={arm: median(r['seconds'] for r in values) for arm, values in valid.items()},
    median_engine_cpu={arm: median(r['engine_cpu'] for r in values) for arm, values in valid.items()},
    median_allocated_bytes={arm: median(r['heap_delta']['TotalAlloc'] for r in values) for arm, values in valid.items()},
    median_peak_sampled_heap_bytes={arm: median(r['peak_sampled_heap'] for r in values) for arm, values in valid.items()},
    median_last_row_seconds={arm: median(r['last_row_seconds'] for r in values) for arm, values in valid.items()},
    all_commands_succeeded=all(r['exit_code'] == 0 for r in rows),
    same_rows=all(r['same_rows'] for r in rows),
    measured_attempts=[{k: r[k] for k in ['label', 'seconds', 'exit_code', 'listed_rows', 'same_rows', 'pressure']}
                       for r in rows if r['pair'] > 0])
(root / 'paired-analysis.json').write_text(json.dumps(analysis, indent=2)+'\n')
print(json.dumps({k: v for k, v in analysis.items() if k != 'measured_attempts'}, indent=2))
