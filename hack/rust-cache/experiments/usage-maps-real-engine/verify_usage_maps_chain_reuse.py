from pathlib import Path
import json
import os
import subprocess
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'usage-maps-real-engine/chain-post-restart-reuse'
root.mkdir(exist_ok=False)
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))


def mode(name, enabled):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/'+name+'?enabled='+str(enabled).lower(), data=b'')
    with urllib.request.urlopen(request, timeout=10) as response:
        assert json.load(response)['enabled'] == enabled


try:
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    for history in ['before', 'after']:
        command = ['python3', str(base/'local_cli_collector.py'), 'api', 'with-session', '--',
                   str(base/'native-batch-runtime-inspect'), '-automatic-cache',
                   '-cache-key', 'native-deep-chain-512-'+history, '-expected-actions', '512',
                   '-expected-hits', '512', '-expected-batch-actions', '256',
                   '-inspect-cache', str(root/(history+'.cache.json')),
                   '-source', '/tmp/rust-native-deep-chain-512-'+history, 'check', str(root)]
        with (root/(history+'.log')).open('w') as output:
            result = subprocess.run(command, cwd='/tmp/dagger-rust-native-deep-artifact-closures', env=env,
                                    stdout=output, stderr=subprocess.STDOUT)
        assert result.returncode == 0, history
        print('PASS', history, '512/512 results retained; preceding batch ran256 actions', flush=True)
finally:
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
