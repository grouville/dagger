import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request


base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'snapshot-completion-counter-probe'
root.mkdir(exist_ok=False)
source = Path('/tmp/rust-native-config-entry-1026-after')
filename = source / 'leaf_1023/src/lib.rs'
updated, count = re.subn(r'pub const EDIT: u64 = \d+;',
                         f'pub const EDIT: u64 = {secrets.randbits(48)};',
                         filename.read_text())
assert count == 1
filename.write_text(updated)


def diagnostic(name, query=None):
    request = urllib.request.Request(
        'http://127.0.0.1:16104/debug/' + name + ('?' + query if query else ''),
        data=b'' if query else None,
        method='POST' if query else 'GET',
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


env = dict(os.environ,
           RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'))
try:
    diagnostic('attribute-array-decode', 'enabled=true')
    diagnostic('snapshot-completions', 'enabled=true&record=true')
    started = time.monotonic()
    with (root / 'command.log').open('w') as output:
        result = subprocess.run(
            ['python3', str(base / 'local_cli.py'), 'check', '--list', '--all',
             'rust:packages/check'], cwd=source, env=env,
            stdout=output, stderr=subprocess.STDOUT,
        )
    seconds = time.monotonic() - started
    state = diagnostic('snapshot-completions')
    (root / 'counters.json').write_text(json.dumps(
        dict(seconds=seconds, returncode=result.returncode, counters=state),
        indent=2) + '\n')
    assert result.returncode == 0
    listed = re.findall(r'^rust\s+(\S+)\s+check$',
                        (root / 'command.log').read_text(), re.M)
    expected = {'app', 'shared'} | {f'leaf_{i:04d}' for i in range(1024)}
    assert len(listed) == 1026 and set(listed) == expected, len(listed)
    print(json.dumps(dict(seconds=seconds, listed=len(listed), counters=state)),
          flush=True)
finally:
    diagnostic('snapshot-completions', 'enabled=false')
    diagnostic('attribute-array-decode', 'enabled=false')
