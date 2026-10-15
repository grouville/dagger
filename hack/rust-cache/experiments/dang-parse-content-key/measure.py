import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import statistics
import subprocess
import time
import urllib.request


parser = argparse.ArgumentParser()
parser.add_argument('--crossover', action='store_true')
parser.add_argument('--pairs', type=int, default=8)
parser.add_argument('--prepare-rounds', type=int, default=2)
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = base / ('dang-content-key-crossover' if args.crossover else 'dang-content-key-paired')
root.mkdir(exist_ok=False)
module = '/tmp/dagger-rust-batched-package-exclusions'
fixtures = {}
for size, original in [('130', '/tmp/rust-native-root-projection-130'), ('small', '/tmp/rust-native-rustdoc-small-after')]:
    fixtures[size] = {}
    for variant in ['before', 'after', 'cargo']:
        source = Path(f'/tmp/rust-native-dang-content-{size}-{variant}')
        if not source.exists():
            shutil.copytree(original, source, ignore=shutil.ignore_patterns('.git', 'target', 'dagger.lock'))
            subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
            config = source / 'dagger.toml'
            text, n = re.subn(r'source = "[^"]+"', f'source = "{module}"', config.read_text(), count=1)
            assert n == 1
            text, n = re.subn(r'cacheKey = "[^"]+"', f'cacheKey = "native-dang-content-{size}-{variant}"', text, count=1)
            assert n == 1
            config.write_text(text)
        fixtures[size][variant] = source

physical = {'before': 'after', 'after': 'before', 'cargo': 'cargo'} if args.crossover else {v: v for v in ['before', 'after', 'cargo']}
engines = {'before': (16276, 16104, 'dagger-rust-parser-state-pool-oct14'), 'after': (16275, 16103, 'dagger-rust-checkpoint-snapshot-key-oct14')}
groups = {}
for variant, (_, debug, name) in engines.items():
    with urllib.request.urlopen(f'http://127.0.0.1:{debug}/debug/wcprof/enabled', timeout=10) as f:
        assert not json.load(f)['global_enabled']
    record = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    pid = record['State']['Pid']
    groups[variant] = Path('/sys/fs/cgroup') / Path(f'/proc/{pid}/cgroup').read_text().split(':', 2)[2].strip().lstrip('/')

removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
dag_env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
collector = Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()
dag_env.update(DAGGER_CLOUD_URL='http://' + collector + ':43183', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*')
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')


def pressure():
    result = {}
    for prefix, path in [('host', Path('/proc/pressure')), *[(v, g) for v, g in groups.items()]]:
        for kind in ['cpu', 'io', 'memory']:
            p = path / (kind if prefix == 'host' else kind + '.pressure')
            for line in p.read_text().splitlines():
                result[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return result


def edit(kind):
    size = 'small' if kind == 'collection' else '130'
    relative = {'collection': 'app/src/lib.rs', 'leaf': 'leaf_0127/src/lib.rs', 'shared': 'shared/src/lib.rs'}[kind]
    pattern = r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if kind == 'collection' else r'pub const EDIT: u64 = \d+;'
    for source in fixtures[size].values():
        value = secrets.randbits(48)
        replacement = f'pub fn edited_value() -> u64 {{ {value} }}' if kind == 'collection' else f'pub const EDIT: u64 = {value};'
        p = source / relative
        text, n = re.subn(pattern, replacement, p.read_text())
        assert n == 1
        p.write_text(text)


def invoke(kind, variant, label):
    size = 'small' if kind == 'collection' else '130'
    test = kind == 'collection'
    source = fixtures[size][physical[variant]]
    if variant == 'cargo':
        env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8', CARGO_TARGET_DIR=str(base / f'native-dang-content-{size}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            env.pop(key, None)
        command = [str(toolchain / 'cargo'), 'test' if test else 'check', '--workspace', '--locked', '--offline']
    else:
        env = dict(dag_env, _EXPERIMENTAL_DAGGER_RUNNER_HOST=f'tcp://127.0.0.1:{engines[physical[variant]][0]}')
        command = ['/tmp/native-hash-verification-bin/dagger', 'check', 'rust:packages/test' if test else 'rust:check']
    before, start = pressure(), time.monotonic()
    with (root / (label + '.log')).open('w') as output:
        proc = subprocess.run(command, cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    after = pressure()
    assert not proc.returncode, (label, proc.returncode)
    log = (root / (label + '.log')).read_text()
    if variant != 'cargo':
        assert 'passed' in log, label
    elif not test and label.startswith('edited'):
        count = len(set(re.findall(r'Checking ([\w-]+) v', log)))
        assert count == (2 if kind == 'leaf' else 130), (label, count)
    with (root / 'pressure.jsonl').open('a') as output:
        output.write(json.dumps({'label': label, 'seconds': elapsed, 'stall_fraction': {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}}) + '\n')
    return elapsed


(root / 'metadata.json').write_text(json.dumps({'worker_module': 'a8ede44', 'root_package': True, 'engine_control': 'scalar-array-decoded-schema', 'engine_candidate': 'same overlay plus content-key syntax library', 'telemetry_enabled': True, 'wcprof_enabled': False, 'logical_to_physical': physical, 'engines': engines, 'warm': True, 'prepare_rounds': args.prepare_rounds, 'timer': 'blocking waitpid without timeout polling', 'fresh_edit_every_command': True}, indent=2) + '\n')
for i in range(args.prepare_rounds):
    for kind in ['shared', 'leaf', 'collection']:
        edit(kind)
        for variant in ['before', 'after', 'cargo']:
            elapsed = invoke(kind, variant, f'prepare-{i}-{kind}-{variant}')
            print('prepare', i, kind, variant, elapsed, flush=True)

rows = {kind: [] for kind in ['leaf', 'shared', 'collection']}
orders = [['before', 'after', 'cargo'], ['cargo', 'after', 'before'], ['after', 'cargo', 'before'], ['before', 'cargo', 'after'], ['cargo', 'before', 'after'], ['after', 'before', 'cargo']]
for i in range(args.pairs):
    for kind in rows:
        edit(kind)
        row = {v: invoke(kind, v, f'edited-{i}-{kind}-{v}') for v in orders[i % len(orders)]}
        rows[kind].append(row)
        (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(kind, i, row, flush=True)
summary = {kind: {'median_seconds': {v: statistics.median(r[v] for r in samples) for v in ['before', 'after', 'cargo']}, 'median_paired_saving_ms': statistics.median(r['before'] - r['after'] for r in samples) * 1000, 'faster_pairs': sum(r['after'] < r['before'] for r in samples)} for kind, samples in rows.items()}
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary), flush=True)
print('PASS: fresh Rust edits, actual package collection, telemetry enabled, host and engine pressure retained', flush=True)
