from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base = ['-p', '2', '-buildvcs=false', '-modfile', str(root / 'engine.go.mod'),
        '-overlay', str(root / 'overlay-controlled.json')]
rows = []
jobs = [
    ('controlled-before', ['test', *base, '-count=1', 'go.opentelemetry.io/otel/sdk/trace'], 'off'),
    ('controlled-after-race', ['test', *base, '-race', '-count=1', 'go.opentelemetry.io/otel/sdk/trace'], 'on'),
    ('engine-build', ['build', *base, '-o', str(root / 'dagger-engine'), './cmd/engine'], 'off'),
]
for label, args, mode in jobs:
    tick = time.monotonic()
    cmd = [go, *args]
    with (root / f'{label}.log').open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local', DAGGER_TEST_RING_QUEUE=mode),
            stdout=out, stderr=subprocess.STDOUT)
    row = dict(label=label, command=cmd, seconds=time.monotonic()-tick, exit_code=result.returncode)
    if label == 'engine-build' and result.returncode == 0:
        row['sha256'] = hashlib.sha256((root / 'dagger-engine').read_bytes()).hexdigest()
    rows.append(row)
    (root / 'controlled-checks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, label
