from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local')
module = str(root / 'engine.go.mod')
package = 'go.opentelemetry.io/otel/sdk/trace'
jobs = []
for arm, race in [('before', False), ('after', False), ('after', True)]:
    args = ['test', '-p', '2', '-buildvcs=false', '-modfile', module,
            '-overlay', str(root / f'overlay-{arm}.json'), '-count=1']
    if race:
        args += ['-race']
    jobs.append((arm + ('-race' if race else '-tests'), args + [package]))
for i, arm in enumerate(['before', 'after', 'after', 'before']):
    args = ['test', '-p', '2', '-buildvcs=false', '-modfile', module,
            '-overlay', str(root / f'overlay-{arm}.json'), '-run', '^$',
            '-bench', '^BenchmarkEvictedQueue(Full|BatchSnapshot)$', '-benchmem',
            '-benchtime=100ms', '-count=2', package]
    jobs.append((f'{i}-{arm}-benchmark', args))
rows = []
for label, args in jobs:
    tick = time.monotonic()
    cmd = [go, *args]
    with (root / f'{label}.log').open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds',
                                env=env, stdout=out, stderr=subprocess.STDOUT)
    row = dict(label=label, command=cmd, seconds=time.monotonic()-tick,
               exit_code=result.returncode)
    rows.append(row)
    (root / 'checks.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, label
