from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
rows = []
for i, arm in enumerate(['before', 'after', 'after', 'before']):
    args = [go, 'test', '-p', '2', '-buildvcs=false', '-modfile', str(root / 'engine.go.mod'),
            '-overlay', str(root / f'overlay-{arm}.json'), '-run', '^$',
            '-bench', '^Benchmark(EvictedQueue(Snapshot|ShortSpan)|SpanAddLinkFull)$',
            '-benchmem', '-benchtime=100ms', '-count=2', 'go.opentelemetry.io/otel/sdk/trace']
    tick = time.monotonic()
    with (root / f'bounds-{i}-{arm}.log').open('w') as out:
        result = subprocess.run(args, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local'),
            stdout=out, stderr=subprocess.STDOUT)
    row = dict(command=args, seconds=time.monotonic()-tick, exit_code=result.returncode,
               test_sha256=hashlib.sha256((root / 'evictedqueue_ring_test.go').read_bytes()).hexdigest())
    rows.append(row)
    (root / 'bounds-checks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, arm
