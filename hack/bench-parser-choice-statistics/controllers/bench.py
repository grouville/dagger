#!/usr/bin/env python3
"""Three AB/BA/AB process pairs on the identical pinned Rust module parser input.

Microbenchmark only. No engine/session/Cargo timing or E2E speedup claim.
Both test binaries default to no explicit statistics option; baseline retains
the old implicit counting behavior, candidate only counts on request.
"""
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import time

HERE = Path(__file__).resolve().parent

def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    assert not (HERE/'parse-results.json').exists()
    records = []
    paths = {'A':HERE/'dang-control.test', 'B':HERE/'dang-candidate.test'}
    for index, side in enumerate('ABBAAB'):
        command = [str(paths[side]), '-test.run=^$',
            '-test.bench=^BenchmarkRustModuleParseChoiceStatistics$/^counted=false$',
            '-test.benchtime=1s', '-test.count=1', '-test.benchmem']
        start = time.time_ns()
        result = subprocess.run(command, cwd=HERE/'dang', text=True, capture_output=True)
        end = time.time_ns()
        with (HERE/f'parse-{index}-{side}.log').open('x') as out:
            out.write(result.stdout+result.stderr)
        assert result.returncode == 0, 'retained failed benchmark'
        matches = re.findall(r'^BenchmarkRustModuleParseChoiceStatistics/counted=false-\d+\s+(\d+)\s+(\d+) ns/op\s+\S+ MB/s\s+(\d+) B/op\s+(\d+) allocs/op', result.stdout, re.M)
        assert len(matches) == 1, result.stdout
        n, ns, allocated, allocs = map(int, matches[0])
        records.append(dict(index=index, side=side, n=n, ns_per_op=ns, bytes_per_op=allocated,
            allocs_per_op=allocs, start_ns=start, end_ns=end, argv=command, binary_sha256=sha(paths[side])))
    pairs = []
    for i in range(0,len(records),2):
        pair = {r['side']:r for r in records[i:i+2]}
        pairs.append(dict(pair=i//2, saved_ns=pair['A']['ns_per_op']-pair['B']['ns_per_op'],
            saved_bytes=pair['A']['bytes_per_op']-pair['B']['bytes_per_op'],
            saved_allocations=pair['A']['allocs_per_op']-pair['B']['allocs_per_op']))
    report = dict(scope=__doc__,records=records,pairs=pairs,
        saved_ns_median=statistics.median(p['saved_ns'] for p in pairs),
        saved_ns_range=[min(p['saved_ns'] for p in pairs),max(p['saved_ns'] for p in pairs)],
        favorable_pairs=sum(p['saved_ns']>0 for p in pairs),
        input_sha256=sha('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/module/main.dang'))
    with (HERE/'parse-results.json').open('x') as out:
        json.dump(report,out,indent=2);out.write('\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
