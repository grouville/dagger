from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common = ['-p', '2', '-buildvcs=false', '-modfile',
          '/tmp/rust-cache-sipsma-review/otel-evicted-queue/engine.go.mod',
          '-overlay', str(root/'engine-overlay.json')]
rows = []
for mode in ['off', 'on']:
    command = [go, 'test', *common, '-race', '-count=1', './core/workspace']
    started = time.monotonic()
    with (root/(mode+'-engine-workspace-race.log')).open('w') as out:
        result = subprocess.run(command, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, DAGGER_CONFIG_DECLARATIONS_TEST_MODE=mode),
            stdout=out, stderr=subprocess.STDOUT)
    rows.append(dict(label=mode+'-workspace', command=command, exit_code=result.returncode,
                     seconds=time.monotonic()-started))
    (root/'engine-validation.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(mode, result.returncode, flush=True)
    assert result.returncode == 0, mode
command = [go, 'build', *common, '-o', str(root/'dagger-engine'), './cmd/engine']
started = time.monotonic()
with (root/'engine-build.log').open('w') as out:
    result = subprocess.run(command, cwd='/tmp/dagger-filesync-snapshot-seeds',
                            stdout=out, stderr=subprocess.STDOUT)
rows.append(dict(label='engine-build', command=command, exit_code=result.returncode,
                 seconds=time.monotonic()-started))
(root/'engine-validation.json').write_text(json.dumps(rows, indent=2)+'\n')
print('engine-build', result.returncode, flush=True)
assert result.returncode == 0
(root/'engine-binary.json').write_text(json.dumps(dict(
    sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),
    bytes=(root/'dagger-engine').stat().st_size), indent=2)+'\n')
