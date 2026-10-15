import os
from pathlib import Path
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276')
cases = [
    ('control-130-post-crossover', '/tmp/dagger-rust-worker-dependency-index',
     '/tmp/rust-native-batched-root-130-after', 'native-batched-root-130-after', 130, 1),
    ('batched-130-post-crossover', '/tmp/dagger-rust-batched-package-exclusions',
     '/tmp/rust-native-batched-root-130-before', 'native-batched-root-130-before', 130, 1),
    ('batched-1026', '/tmp/dagger-rust-batched-package-exclusions',
     '/tmp/rust-native-root-projection-1026', 'native-root-projection-1026', 1026, 1026),
]
for label, module, source, key, actions, batch in cases:
    cmd = ['python3', str(base / 'local_cli.py'), 'api', 'with-session', '--',
           str(base / 'native-batch-runtime-inspect'), '-automatic-cache',
           '-cache-key', key, '-expected-actions', str(actions), '-expected-hits', str(actions),
           '-expected-batch-actions', str(batch), '-source', source, 'check',
           str(base / 'root-projection-no-host-state')]
    log = base / ('root-projection-' + label + '-verify.log')
    with log.open('w') as out:
        proc = subprocess.run(cmd, cwd=module, env=env, stdout=out, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, (label, proc.returncode, str(log))
    print(label, 'PASS', flush=True)
