import os
from pathlib import Path
import re
import secrets
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
source = Path('/tmp/rust-native-root-projection-1026')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276')
file = source / 'leaf_1023/src/lib.rs'
contents, count = re.subn(r'pub const EDIT: u64 = \d+;',
                        f'pub const EDIT: u64 = {secrets.randbits(48)};', file.read_text())
assert count == 1
file.write_text(contents)
config = source / 'dagger.toml'
original = config.read_text()
try:
    contents, count = re.subn(r'source = "[^"]+"',
        'source = "/tmp/dagger-rust-batched-package-exclusions"', original, count=1)
    assert count == 1
    config.write_text(contents)
    with (base / 'root-projection-1026-batched-edited-leaf.log').open('w') as output:
        process = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', 'rust:check'],
            cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
    assert not process.returncode, 'edited complete check'
finally:
    config.write_text(original)
cmd = ['python3', str(base / 'local_cli.py'), 'api', 'with-session', '--',
       str(base / 'native-batch-runtime-inspect'), '-automatic-cache',
       '-cache-key', 'native-root-projection-1026', '-expected-actions', '1026',
       '-expected-hits', '1026', '-expected-batch-actions', '2', '-source', str(source),
       'check', str(base / 'root-projection-no-host-state')]
with (base / 'root-projection-1026-batched-edited-leaf-verify.log').open('w') as output:
    process = subprocess.run(cmd, cwd='/tmp/dagger-rust-batched-package-exclusions',
        env=env, stdout=output, stderr=subprocess.STDOUT)
assert not process.returncode, 'edited leaf native cache verification'
print('PASS: 1026 native results recovered; leaf edit compiled exactly two actions', flush=True)
