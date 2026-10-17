from pathlib import Path
import json
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
jobs = [
    ('baseline-final-guards', root.parent/'dang-module-blueprint-content-key',
     [go, 'test', '-p', '2', '-race', '-overlay', str(root/'baseline-tests-overlay.json'),
      '-count=1', '-run', '^TestBuiltinReceiver', './pkg/dang']),
    ('pure-final-race', Path('/tmp/dang-direct-builtin-receivers'),
     [go, 'test', '-p', '2', '-race', '-count=1', './pkg/dang']),
    ('final-activation', root,
     ['python3', str(root/'json-compatibility/activate.py')]),
]
rows = []
for label, cwd, command in jobs:
    started = time.monotonic()
    with (root/(label+'.log')).open('w') as out:
        result = subprocess.run(command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT)
    rows.append(dict(label=label, cwd=str(cwd), command=command,
                     exit_code=result.returncode, seconds=time.monotonic()-started))
    (root/'final-validation.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(label, result.returncode, flush=True)
    assert result.returncode == 0, label
