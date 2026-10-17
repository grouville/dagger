from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
module = root.parent/'otel-evicted-queue/engine.go.mod'
jobs = []
for arm, race in [('before', False), ('after', False), ('after', True)]:
    cmd = [go, 'test', '-p', '2', '-buildvcs=false', '-modfile', str(module), '-overlay', str(root/f'overlay-{arm}.json'), '-count=1']
    if race:
        cmd.append('-race')
    jobs.append((arm+('-race' if race else '-tests'), [*cmd, './core/workspace']))
for index, arm in enumerate(['before', 'after', 'after', 'before']):
    cmd = [go, 'test', '-p', '2', '-buildvcs=false', '-modfile', str(module), '-overlay', str(root/f'overlay-{arm}.json'),
           '-run', '^$', '-bench', '^BenchmarkParseConfigAt$', '-benchmem', '-benchtime=100ms', '-count=2', './core/workspace']
    jobs.append((f'{index}-{arm}-benchmark', cmd))
rows = []
for label, cmd in jobs:
    tick = time.monotonic()
    with (root/f'{label}.log').open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, GOMAXPROCS='4', GOTOOLCHAIN='local'), stdout=out, stderr=subprocess.STDOUT)
    row = dict(label=label, command=cmd, seconds=time.monotonic()-tick, exit_code=result.returncode)
    rows.append(row)
    (root/'checks.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, label
