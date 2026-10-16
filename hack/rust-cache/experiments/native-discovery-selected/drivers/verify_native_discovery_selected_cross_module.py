from pathlib import Path
import json
import os
import subprocess
import tomllib

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'native-discovery-selected/cross-module'
root.mkdir(exist_ok=False)
source = base / 'native-discovery-selected-compile/workspace'
config = tomllib.loads((source / 'dagger.toml').read_text())
key = config['modules']['rust']['settings']['cacheKey']
env = dict(os.environ,
    RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
    RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'),
    _EXPERIMENTAL_DAGGER_CLI_BIN=str(base / 'dagger-artifact-workspace-before'),
    RUST_CACHE_BENCH_COLLECTOR='http://' + (base / 'otlp-null-address.txt').read_text().strip() + ':43184')
rows = []
for label, module in [
    ('old-module-reads-candidate-results', base.parent / 'dagger-rust-native-fused-artifact-inputs'),
    ('candidate-reads-same-results', base.parent / 'dagger-rust-native-discovery-current'),
    ('old-module-reads-them-again', base.parent / 'dagger-rust-native-fused-artifact-inputs'),
]:
    command = ['python3', str(base / 'local_cli_collector.py'), 'api', 'with-session', '--',
        str(base / 'native-batch-runtime-inspect'), '-automatic-cache', '-cache-key', key,
        '-expected-actions', '2', '-expected-hits', '2', '-inspect-cache', str(root / (label + '.cache.json')),
        '-source', str(source), 'check', str(base / 'root-projection-no-host-state')]
    with (root / (label + '.log')).open('w') as output:
        result = subprocess.run(command, cwd=module, env=env, stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, label
    rows.append(dict(label=label, module=str(module), revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=module, text=True).strip(), actions=2, hits=2, source_edited=False))
    (root / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print('PASS', label, '2/2 hits without preparing or recompiling the source', flush=True)
