from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ, GOMAXPROCS='8', GOTOOLCHAIN='local', GOWORK='off', CGO_ENABLED='1')
rows = []
for arm in ['baseline', 'owned']:
    command = [go, 'test', '-v', '-p', '2', '-buildvcs=false', '-overlay', str(root / (arm + '-overlay.json')),
        '-race', '-count=1', '-run', '^TestCompactionPreservesSnapshotsAcrossLaterMerges$', './dagql']
    tick = time.monotonic()
    with (root / (arm + '-snapshot-race.log')).open('w') as output:
        result = subprocess.run(command, cwd='/tmp/dagger-compaction-ownership-only', env=env,
            stdout=output, stderr=subprocess.STDOUT)
    log = (root / (arm + '-snapshot-race.log')).read_text()
    executed = '--- PASS: TestCompactionPreservesSnapshotsAcrossLaterMerges' in log
    rows.append(dict(arm=arm, command=command, seconds=time.monotonic()-tick,
        exit_code=result.returncode, test_executed_and_passed=executed))
    (root / 'validation.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(arm, result.returncode, 'executed', executed, flush=True)
    assert result.returncode == 0 and executed, (arm, log)
