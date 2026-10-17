from pathlib import Path
import json
import subprocess
import time

family = Path(__file__).parent
root = family / 'capture'
profile = root / 'wcprof-complete.ndjson'
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
cpu = sorted(root.glob('engine-cpu-*.pprof'))
jobs = [
    ('wcprof-critical.txt', ['/tmp/rust-cache-wcprof-report', '-view', 'critpath', str(profile)]),
    ('wcprof-internal.txt', ['/tmp/rust-cache-wcprof-report', '-view', 'classes', '-kind', 'internal', '-sort', 'self', '-top', '35', str(profile)]),
    ('wcprof-calls.txt', ['/tmp/rust-cache-wcprof-report', '-view', 'classes', '-kind', 'call', '-sort', 'self', '-top', '30', str(profile)]),
    ('cpu-flat.txt', [go, 'tool', 'pprof', '-top', '-nodecount=50', str(family/'dagger-engine'), *map(str, cpu)]),
    ('cpu-cumulative.txt', [go, 'tool', 'pprof', '-top', '-cum', '-nodecount=50', str(family/'dagger-engine'), *map(str, cpu)]),
]
assert cpu, 'no CPU windows were retained'
rows = []
for name, cmd in jobs:
    tick = time.monotonic()
    with (root/name).open('w') as out:
        result = subprocess.run(cmd, cwd='/tmp/dagger-filesync-snapshot-seeds', stdout=out, stderr=subprocess.STDOUT)
    row = dict(command=cmd, output=name, seconds=time.monotonic()-tick, exit_code=result.returncode)
    rows.append(row)
    (root/'analysis-commands.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, name
