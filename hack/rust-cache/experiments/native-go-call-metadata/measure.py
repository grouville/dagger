import argparse
from contextlib import contextmanager
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
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = base / ('go-call-batch-crossover' if args.crossover else 'go-call-batch-paired')
root.mkdir(exist_ok=False)
modules = {'before': '/tmp/dagger-rust-batched-package-exclusions', 'after': '/tmp/dagger-rust-call-metadata-batch', 'cargo': '/tmp/dagger-rust-batched-package-exclusions'}
physical = {'before': 'after', 'after': 'before', 'cargo': 'cargo'} if args.crossover else {v: v for v in modules}
fixtures = {}
for size, original in [('130', '/tmp/rust-native-root-projection-130'), ('small', '/tmp/rust-native-rustdoc-small-after')]:
    fixtures[size] = {}
    for variant in modules:
        source = Path(f'/tmp/rust-native-go-call-{size}-{variant}')
        if not source.exists():
            shutil.copytree(original, source, ignore=shutil.ignore_patterns('.git', 'target', 'dagger.lock'))
            subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
            config = source / 'dagger.toml'
            text, count = re.subn(r'source = "[^"]+"', f'source = "{modules[variant]}"', config.read_text(), count=1)
            assert count == 1
            text, count = re.subn(r'cacheKey = "[^"]+"', f'cacheKey = "native-go-call-{size}-{variant}"', text, count=1)
            assert count == 1
            config.write_text(text)
        fixtures[size][variant] = source
with urllib.request.urlopen('http://127.0.0.1:16104/debug/wcprof/enabled', timeout=5) as response:
    assert not json.load(response)['global_enabled']
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {key: value for key, value in os.environ.items() if key not in removed and not key.startswith('OTEL_EXPORTER_')}
collector = Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()
env.update(DAGGER_CLOUD_URL='http://' + collector + ':43183', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')

def pressure():
    values = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                values[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return values

def edit(kind):
    size = 'small' if kind == 'collection' else '130'
    relative = {'collection': 'app/src/lib.rs', 'leaf': 'leaf_0127/src/lib.rs', 'shared': 'shared/src/lib.rs'}[kind]
    pattern = r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if kind == 'collection' else r'pub const EDIT: u64 = \d+;'
    for source in fixtures[size].values():
        value = secrets.randbits(48)
        replacement = f'pub fn edited_value() -> u64 {{ {value} }}' if kind == 'collection' else f'pub const EDIT: u64 = {value};'
        filename = source / relative
        text, count = re.subn(pattern, replacement, filename.read_text())
        assert count == 1
        filename.write_text(text)

def invoke(kind, variant, label):
    size = 'small' if kind == 'collection' else '130'
    source = fixtures[size][physical[variant]]
    if variant == 'cargo':
        run_env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8', CARGO_TARGET_DIR=str(base / f'native-go-call-{size}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            run_env.pop(key, None)
        command = [str(toolchain / 'cargo'), 'test' if kind == 'collection' else 'check', '--workspace', '--locked', '--offline']
    else:
        run_env = env
        command = ['/tmp/native-hash-verification-bin/dagger', 'check', 'rust:packages/test' if kind == 'collection' else 'rust:check']
    before, started = pressure(), time.monotonic()
    with (root / (label + '.log')).open('w') as output:
        result = subprocess.run(command, cwd=source, env=run_env, stdout=output, stderr=subprocess.STDOUT)
    seconds = time.monotonic() - started
    after = pressure()
    assert not result.returncode, label
    log = (root / (label + '.log')).read_text()
    if variant != 'cargo':
        assert 'passed' in log, label
    elif kind != 'collection' and label.startswith('edited'):
        assert len(set(re.findall(r'Checking ([\w-]+) v', log))) == (2 if kind == 'leaf' else 130), label
    with (root / 'pressure.jsonl').open('a') as output:
        output.write(json.dumps(dict(label=label, seconds=seconds, stall_fraction={key: (after[key] - before[key]) / (seconds * 1e6) for key in before})) + '\n')
    return seconds

@contextmanager
def assign_modules():
    originals = {}
    try:
        for size in fixtures:
            for variant in ['before', 'after']:
                config = fixtures[size][physical[variant]] / 'dagger.toml'
                originals[config] = config.read_text()
                text, count = re.subn(r'source = "[^"]+"', f'source = "{modules[variant]}"', originals[config], count=1)
                assert count == 1
                config.write_text(text)
        yield
    finally:
        for config, text in originals.items():
            config.write_text(text)

with assign_modules():
    (root / 'metadata.json').write_text(json.dumps(dict(base_module='a8ede44', single_engine=16276, engine='scalar-array-decoded-schema', telemetry_enabled=True, wcprof_enabled=False, warm=True, fresh_unique_edit_per_variant=True, timer='blocking waitpid without timeout polling', crossover=args.crossover, logical_to_physical=physical, engine_restart=False), indent=2) + '\n')
    for i in range(2):
        for kind in ['shared', 'leaf', 'collection']:
            edit(kind)
            for variant in modules:
                print('prepare', i, kind, variant, invoke(kind, variant, f'prepare-{i}-{kind}-{variant}'), flush=True)
    rows = {kind: [] for kind in ['leaf', 'shared', 'collection']}
    orders = [['before', 'after', 'cargo'], ['cargo', 'after', 'before'], ['after', 'cargo', 'before'], ['before', 'cargo', 'after'], ['cargo', 'before', 'after'], ['after', 'before', 'cargo']]
    for i in range(args.pairs):
        for kind in rows:
            edit(kind)
            row = {variant: invoke(kind, variant, f'edited-{i}-{kind}-{variant}') for variant in orders[i % len(orders)]}
            rows[kind].append(row)
            (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(kind, i, row, flush=True)
    summary = {kind: dict(median_seconds={variant: statistics.median(row[variant] for row in samples) for variant in modules}, median_paired_saving_ms=statistics.median(row['before'] - row['after'] for row in samples) * 1000, faster_pairs=sum(row['after'] < row['before'] for row in samples)) for kind, samples in rows.items()}
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
