#!/usr/bin/env python3
"""Recompute recorded paired statistics; this does not rerun the benchmark."""
import json
from pathlib import Path
import statistics

data = json.loads(Path(__file__).with_name('measurements.json').read_text())
assert len(data) == 2
pairs = []
for cohort in data:
    rows = cohort['rows']
    assert [row['side'] for row in rows] == list('ABBAAB')
    assert [row['index'] for row in rows] == list(range(6))
    for i in range(0, 6, 2):
        a = next(row for row in rows[i:i+2] if row['side'] == 'A')
        b = next(row for row in rows[i:i+2] if row['side'] == 'B')
        pairs.append(dict(cohort=cohort['cohort'], pair=i//2,
            cli_ms=a['cli_ms']-b['cli_ms'],
            overhead_ms=(a['cli_ms']-a['native_ms'])-(b['cli_ms']-b['native_ms']),
            provision_overhead_ms=(a['provision_check_ms']-a['native_ms'])-(b['provision_check_ms']-b['native_ms']),
            cargo_ms=a['cargo_ms']-b['cargo_ms'], delivery_ms=a['delivery_ms']-b['delivery_ms'],
            dpkg_ms=a['dpkg_ms']-b['dpkg_ms'], rustup_ms=a['rustup_ms']-b['rustup_ms']))
assert len(pairs) == 6
summary = {}
for key in ('cli_ms', 'overhead_ms', 'provision_overhead_ms', 'cargo_ms', 'delivery_ms', 'dpkg_ms', 'rustup_ms'):
    values = [pair[key] for pair in pairs]
    summary[key] = dict(median=statistics.median(values), minimum=min(values), maximum=max(values),
                        favorable_pairs=sum(value > 0 for value in values))
print(json.dumps(dict(scope=__doc__, pairs=pairs, summary=summary), indent=2))
