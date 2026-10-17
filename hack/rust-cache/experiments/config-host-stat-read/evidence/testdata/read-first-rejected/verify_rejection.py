from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).parent
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
subprocess.run([str(Path(go).parent / 'gofmt'), '-w', str(root / 'module_host_file_metadata_test.go')], check=True)
rows = []
for arm in ['baseline', 'candidate']:
    command = [go, 'test', '-p', '2', '-buildvcs=false', '-overlay',
               str(root / ('metadata-' + arm + '-overlay.json')), '-race', '-count=1',
               '-run', '^TestModuleHostFileReaderPreservesMetadataErrors$', './core']
    tick = time.monotonic()
    with (root / ('metadata-' + arm + '.log')).open('w') as output:
        result = subprocess.run(command, cwd='/tmp/dagger-filesync-snapshot-seeds',
            env=dict(os.environ, GOTOOLCHAIN='local', GOMAXPROCS='8', CGO_ENABLED='1'),
            stdout=output, stderr=subprocess.STDOUT)
    log = (root / ('metadata-' + arm + '.log')).read_text()
    expected = result.returncode == 0 if arm == 'baseline' else (
        result.returncode != 0 and 'TestModuleHostFileReaderPreservesMetadataErrors' in log
        and 'expected: 0x7' in log and 'actual  : 0x0' in log)
    rows.append(dict(arm=arm, command=command, exit_code=result.returncode,
        seconds=time.monotonic() - tick, expected_outcome=expected))
    (root / 'metadata-rejection-tests.json').write_text(json.dumps(rows, indent=2) + '\n')
    assert expected, (arm, result.returncode, log)
    print(arm, result.returncode, 'expected outcome', flush=True)
