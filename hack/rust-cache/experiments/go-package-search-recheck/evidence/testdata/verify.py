from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import urllib.request

root = Path(__file__).parent
base = root.parent
module = Path('/tmp/dagger-go-package-search-recheck')
source = module / 'go.dang'
candidate = source.read_bytes()
original = (root / 'before-go.dang').read_bytes()

def get(route, data=None):
    with urllib.request.urlopen(urllib.request.Request(
        'http://127.0.0.1:16104/debug/'+route, data=data), timeout=30) as response:
        return json.load(response)

routes = ['reusable-declarations', 'telemetry-flush-coalescing', 'callback-caller-reuse',
    'interface-candidate-pruning', 'interface-field-snapshots', 'parallel-client-admission',
    'single-toml-parse', 'restored-posting-removal']
flags = {route: get(route)['enabled'] for route in routes}
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
    RUST_CACHE_BENCH_CLI=str(base/'filesync-literal-pathwalk/dagger-after'),
    RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
    _EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15')
rows = []
try:
    for route in routes:
        enabled = route in ['reusable-declarations', 'restored-posting-removal']
        assert get(route+'?enabled='+str(enabled).lower(), b'')['enabled'] == enabled
    for arm, data in [('original', original), ('candidate', candidate)]:
        source.write_bytes(data)
        check = 'go-dev:tests-collection-check'
        started = time.monotonic()
        with (root/(arm+'-collection-check.log')).open('w') as output:
            result = subprocess.run(['python3', str(base/'local_cli_collector.py'), 'check', check],
                cwd=module, env=env, stdout=output, stderr=subprocess.STDOUT)
        row = dict(arm=arm, check=check, seconds=time.monotonic()-started,
            source_sha256=hashlib.sha256(data).hexdigest(), exit_code=result.returncode)
        rows.append(row)
        (root/'correctness.json').write_text(json.dumps(rows, indent=2)+'\n')
        print(json.dumps(row), flush=True)
        assert result.returncode == 0, arm
finally:
    source.write_bytes(candidate)
    for route, enabled in flags.items():
        assert get(route+'?enabled='+str(enabled).lower(), b'')['enabled'] == enabled
