from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
module = root.parent / 'otel-evicted-queue/engine.go.mod'
env = dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local')
common = ['-p', '2', '-buildvcs=false', '-modfile', str(module)]
jobs = [
    ('shared-tests', ['test', *common, '-overlay', str(root / 'test-overlay.json'), '-count=1', './core/sdk/dang/shared']),
    ('v2-tests', ['test', *common, '-overlay', str(root / 'test-overlay.json'), '-count=1', './core/sdk/dang/v2']),
    ('shared-race', ['test', *common, '-overlay', str(root / 'test-overlay.json'), '-race', '-count=1', './core/sdk/dang/shared']),
    ('engine-build', ['build', *common, '-overlay', str(root / 'engine-overlay.json'), '-o', str(root / 'dagger-engine'), './cmd/engine']),
]
rows = []
identity = json.loads((root / 'source-identity.json').read_text())
identity['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.go')}
(root / 'source-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
for label, args in jobs:
    tick = time.monotonic()
    cmd = [go, *args]
    with (root / f'{label}.log').open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds', env=env,
            stdout=out, stderr=subprocess.STDOUT)
    row = dict(label=label, command=cmd, seconds=time.monotonic()-tick, exit_code=result.returncode)
    if label == 'engine-build' and result.returncode == 0:
        row['sha256'] = hashlib.sha256((root / 'dagger-engine').read_bytes()).hexdigest()
    rows.append(row)
    (root / 'checks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, label
