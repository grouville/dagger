import os
from pathlib import Path
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16275', _EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
for physical, module in [('before', '/tmp/dagger-rust-bulk-package-digests'), ('after', '/tmp/dagger-rust-batched-package-digests')]:
    for size, actions, batch in [('130',130,130),('1026',1026,2),('small',6,4)]:
        cmd = ['python3', str(base/'local_cli.py'), 'api', 'with-session', '--', str(base/'native-batch-runtime-inspect'), '-automatic-cache', '-cache-key', f'native-bulk-digests-{size}-{physical}', '-expected-actions', str(actions), '-expected-hits', str(actions), '-expected-batch-actions', str(batch), '-source', f'/tmp/rust-native-bulk-digests-{size}-{physical}']
        if size == 'small': cmd.extend(['-native-test','-compile-tests-only'])
        cmd.extend(['check', str(base/'root-projection-no-host-state')])
        log = base/f'primitive-owners-{size}-{physical}-verify.log'
        with log.open('w') as output: result = subprocess.run(cmd,cwd=module,env=env,stdout=output,stderr=subprocess.STDOUT)
        assert not result.returncode,str(log)
        print('PASS', physical, size, 'hits', actions, 'batch', batch, flush=True)
