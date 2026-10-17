import sys
import json
import os
from pathlib import Path
import subprocess
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / ('native-discovery-retained-'+sys.argv[1])
root.mkdir(exist_ok=False)
env = dict(os.environ,
           RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'),
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(base / 'dagger-artifact-workspace-before'), RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')


def mode(name, enabled):
    request = urllib.request.Request(
        f'http://127.0.0.1:16104/debug/{name}?enabled={str(enabled).lower()}',
        data=b'', method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        assert json.load(response)['enabled'] == enabled


try:
    mode('attribute-array-decode', True)
    mode('batch-metadata', True)
    for phase in ['prepare-current-input', 'strict-reuse']:
        for size, actions, batch in [('130', 130, 2), ('1026', 1026, 2), ('small', 6, 4)]:
            for side in ['before', 'after']:
                mode('direct-span-protobuf', False)
                hits = actions if phase == 'strict-reuse' else -1
                command = ['python3', str(base / 'local_cli_collector.py'), 'api', 'with-session', '--',
                           str(base / 'native-batch-runtime-inspect'), '-automatic-cache',
                           '-cache-key', f'native-config-entry-{size}-{side}',
                           '-expected-actions', str(actions), '-expected-hits', str(hits),
                           '-expected-batch-actions', '-1', '-inspect-cache', str(root / f'{size}-{side}.cache.json'), '-source',
                           f'/tmp/rust-native-config-entry-{size}-{side}']
                if size == 'small':
                    command += ['-native-test', '-compile-tests-only']
                command += ['check', str(base / 'root-projection-no-host-state')]
                with (root / f'{phase}-{size}-{side}.log').open('w') as output:
                    result = subprocess.run(command, cwd='/tmp/dagger-rust-native-discovery-current',
                                            env=env, stdout=output, stderr=subprocess.STDOUT)
                assert result.returncode == 0, (size, side, result.returncode)
                print(f'PASS {phase} {size} {side}: '+(f'{hits}/{actions} cached actions' if hits>=0 else 'current edited input compiled'), flush=True)
finally:
    mode('direct-span-protobuf', False)
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
