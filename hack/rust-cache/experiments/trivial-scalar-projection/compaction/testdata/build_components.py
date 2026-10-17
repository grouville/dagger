from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ, GOMAXPROCS='8', GOTOOLCHAIN='local', GOWORK='off', CGO_ENABLED='1')
rows = []
for arm in ['baseline', 'digests', 'owned']:
    target = root / (arm + '.test')
    command = [go, 'test', '-c', '-p', '2', '-buildvcs=false', '-overlay',
        str(root / (arm + '-overlay.json')), '-o', str(target), './dagql']
    tick = time.monotonic()
    with (root / (arm + '-build.log')).open('w') as output:
        result = subprocess.run(command, cwd='/tmp/dagger-compaction-ownership-only', env=env,
            stdout=output, stderr=subprocess.STDOUT)
    rows.append(dict(arm=arm, command=command, seconds=time.monotonic()-tick,
        exit_code=result.returncode, sha256=hashlib.sha256(target.read_bytes()).hexdigest() if result.returncode==0 else None))
    (root / 'component-builds.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(arm, result.returncode, flush=True)
    assert result.returncode == 0
