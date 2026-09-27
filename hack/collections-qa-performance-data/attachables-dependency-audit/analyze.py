#!/usr/bin/env python3
"""Read the existing private inittrace; emit package names and numeric counters."""
from pathlib import Path
import collections
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
TRACE = Path('/tmp/collections-perf/split-init-prototype-v1/startup-micro-v1/private/28-heavy-inittrace.stderr')
rows = []
for line in TRACE.read_text().splitlines():
    match = re.match(r'^init ([A-Za-z0-9_./+@%-]+) @.*?, ([0-9.]+) ms clock, (\d+) bytes, (\d+) allocs', line)
    if match:
        rows.append({'package': match[1], 'reported_init_clock_ms': float(match[2]), 'reported_allocated_bytes': int(match[3]), 'reported_allocations': int(match[4])})
assert len(rows) == 505

def group(name):
    for prefix, label in [
        ('github.com/aws/', 'AWS'), ('github.com/hashicorp/vault/', 'Vault'),
        ('cloud.google.com/', 'Google Cloud'), ('google.golang.org/', 'Google RPC/API'),
        ('github.com/containerd/', 'containerd'), ('github.com/docker/', 'Docker'),
        ('github.com/distribution/', 'image reference'), ('github.com/go-git/', 'go-git'),
        ('github.com/charmbracelet/', 'terminal UI'), ('github.com/1password/', '1Password'),
        ('github.com/google/go-cmp/', 'go-cmp'), ('github.com/dagger/dagger/', 'Dagger'),
    ]:
        if name.startswith(prefix):
            return label
    return 'other dependencies' if '.' in name.split('/')[0] else 'standard library/runtime'

groups = collections.defaultdict(list)
for row in rows:
    groups[group(row['package'])].append(row)
totals = {name: {'init_records': len(items), **{field: round(sum(row[field] for row in items), 6) for field in ['reported_init_clock_ms', 'reported_allocated_bytes', 'reported_allocations']}} for name,items in groups.items()}
result = {
    'source_trace_sha256': hashlib.sha256(TRACE.read_bytes()).hexdigest(),
    'binary_sha256': 'e5157dc97821baef29e9518a169b50e16647b1bdc8b73132345c2fa04971f1e5',
    'scope': 'Existing single instrumented unmatched-argv0 startup capture; package prefix groups are observations, not exclusive dependency paths or removable-cost estimates.',
    'groups': totals,
    'largest_clock_records': sorted(rows,key=lambda r:r['reported_init_clock_ms'],reverse=True)[:20],
    'largest_allocation_records': sorted(rows,key=lambda r:r['reported_allocated_bytes'],reverse=True)[:20],
    'records': rows,
}
(HERE / 'numeric.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(totals, indent=2))
