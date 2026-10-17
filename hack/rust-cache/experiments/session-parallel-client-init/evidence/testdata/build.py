from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
module = root.parent/'otel-evicted-queue/engine.go.mod'
base = ['-p', '2', '-buildvcs=false', '-modfile', str(module)]
rows = []
jobs = [
 ('controlled-before', ['test', *base, '-overlay', str(root/'overlay-controlled.json'), '-count=1', '-timeout=120s', '-run', 'Test(ClientMetadata|GetOrInit|NestedTransport|ClosedClient)', './engine/server'], 'off'),
 ('controlled-after-race', ['test', *base, '-overlay', str(root/'overlay-controlled.json'), '-race', '-count=1', '-timeout=180s', '-run', 'Test(NestedClientRuntimeInitializationsCanOverlap|InitializeSessionEngineClientConcurrent|NestedTransport|ClientInitialization)', './engine/server'], 'on'),
 ('engine-build', ['build', *base, '-overlay', str(root/'engine-overlay.json'), '-o', str(root/'dagger-engine'), './cmd/engine'], 'off'),
]
for label, args, mode in jobs:
    tick = time.monotonic()
    cmd = [go, *args]
    with (root/f'{label}.log').open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local', DAGGER_TEST_PARALLEL_CLIENT_ADMISSION=mode),
            stdout=out, stderr=subprocess.STDOUT)
    row = dict(label=label, command=cmd, seconds=time.monotonic()-tick, exit_code=result.returncode)
    if label == 'engine-build' and result.returncode == 0:
        row['sha256'] = hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
    rows.append(row)
    (root/'controlled-checks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, label
