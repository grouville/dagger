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
root = base / 'primitive-array-codec-idle-crossover-confirmation'
root.mkdir(exist_ok=False)
modules = {variant: '/tmp/dagger-rust-bulk-package-digests' for variant in ['before', 'after', 'cargo']}
physical = {'before': 'after', 'after': 'before', 'cargo': 'cargo'} if args.crossover else {v: v for v in modules}
fixtures = {}
for size, original in [('130', '/tmp/rust-native-root-projection-130'), ('1026', '/tmp/rust-native-worker-index-1026-before'), ('small', '/tmp/rust-native-rustdoc-small-after')]:
    fixtures[size] = {}
    for variant in modules:
        source = Path(f'/tmp/rust-native-literal-display-{size}-{variant}')
        if not source.exists():
            shutil.copytree(original, source, ignore=shutil.ignore_patterns('.git', 'target', 'dagger.lock'))
            subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
            config = source / 'dagger.toml'
            text, count = re.subn(r'source = "[^"]+"', f'source = "{modules[variant]}"', config.read_text(), count=1)
            assert count == 1
            text, count = re.subn(r'cacheKey = "[^"]+"', f'cacheKey = "native-literal-display-{size}-{variant}"', text, count=1)
            assert count == 1
            config.write_text(text)
        fixtures[size][variant] = source
engines = {'before': (16276, 16104, 'dagger-rust-parser-state-pool-oct14'), 'after': (16275, 16103, 'dagger-rust-checkpoint-snapshot-key-oct14')}
groups = {}
for variant, (_, debug, name) in engines.items():
    with urllib.request.urlopen(f'http://127.0.0.1:{debug}/debug/wcprof/enabled', timeout=5) as response:
        assert not json.load(response)['global_enabled']
    record = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    groups[variant] = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {key: value for key, value in os.environ.items() if key not in removed and not key.startswith('OTEL_EXPORTER_')}
collector = Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()
env.update(DAGGER_CLOUD_URL='http://' + collector + ':43183', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16275')
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')

def pressure():
    values = {}
    for prefix, path in [('host', Path('/proc/pressure')), *[(variant, group) for variant, group in groups.items()]]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                values[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return values

def wait_for_idle(label):
    admission_started = time.monotonic()
    while True:
        start = pressure()
        began = time.monotonic()
        time.sleep(2)
        end = pressure()
        window = time.monotonic() - began
        fractions = {key: (end[key]-start[key])/(window*1e6) for key in start}
        idle = True
        for _, debug, _ in engines.values():
            with urllib.request.urlopen(f'http://127.0.0.1:{debug}/debug/client-lifecycle', timeout=5) as response:
                state = json.load(response)
            idle = idle and not state.get('sessions') and state['active_requests'] == 0
        admitted = idle and fractions['host.io.some'] < .05 and all(fractions[variant+'.io.some'] < .01 for variant in engines)
        waited = time.monotonic() - admission_started
        with (root/'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, seconds=waited, window=window, stall_fraction=fractions, engines_idle=idle, admitted=admitted))+'\n')
        if admitted:
            return
        print('waiting for idle', label, round(waited,1), 'seconds', flush=True)
        assert waited < 60, 'idle admission timed out; retain all existing observations'

def edit(kind):
    size = 'small' if kind == 'collection' else ('1026' if kind == 'large_leaf' else '130')
    relative = {'collection': 'app/src/lib.rs', 'leaf': 'leaf_0127/src/lib.rs', 'large_leaf': 'leaf_1023/src/lib.rs', 'shared': 'shared/src/lib.rs'}[kind]
    pattern = r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if kind == 'collection' else r'pub const EDIT: u64 = \d+;'
    for source in fixtures[size].values():
        value = secrets.randbits(48)
        replacement = f'pub fn edited_value() -> u64 {{ {value} }}' if kind == 'collection' else f'pub const EDIT: u64 = {value};'
        filename = source / relative
        text, count = re.subn(pattern, replacement, filename.read_text())
        assert count == 1
        filename.write_text(text)

def invoke(kind, variant, label):
    size = 'small' if kind == 'collection' else ('1026' if kind == 'large_leaf' else '130')
    source = fixtures[size][physical[variant]]
    if variant == 'cargo':
        run_env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8', CARGO_TARGET_DIR=str(base / f'native-literal-display-{size}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            run_env.pop(key, None)
        command = [str(toolchain / 'cargo'), 'test' if kind == 'collection' else 'check', '--workspace', '--locked', '--offline']
    else:
        run_env = dict(env, _EXPERIMENTAL_DAGGER_RUNNER_HOST=f'tcp://127.0.0.1:{engines[physical[variant]][0]}')
        command = ['/tmp/native-hash-verification-bin/dagger', 'check', 'rust:packages/test' if kind == 'collection' else 'rust:check']
    wait_for_idle(label)
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
        assert len(set(re.findall(r'Checking ([\w-]+) v', log))) == (2 if kind in ['leaf', 'large_leaf'] else 130), label
    with (root / 'pressure.jsonl').open('a') as output:
        output.write(json.dumps(dict(label=label, seconds=seconds, stall_fraction={key: (after[key] - before[key]) / (seconds * 1e6) for key in before})) + '\n')
    return seconds

(root / 'metadata.json').write_text(json.dumps(dict(module='28dab90', experimental_source_digest_paths=True, grouped_directory_digests=True, primitive_array_owner_fast_path=True, engines=engines, engine_control='literal-display', engine_candidate='same overlay plus primitive-array-codec', existing_fixture_histories_reused=True, prepare_rounds=1, admission=dict(quiet_window_seconds=2, host_io_some_fraction_below=.05, each_engine_io_some_fraction_below=.01, both_engines_without_sessions=True, max_wait_seconds=60, post_sample_exclusion=False), cadence='idle interactive commands; admission time is recorded and excluded from command latency', telemetry_enabled=True, wcprof_enabled=False, warm=True, fresh_unique_edit_per_variant=True, timer='blocking waitpid without timeout polling', crossover=args.crossover, logical_to_physical=physical, engine_restart='clean exit zero with preserved volumes; binaries swapped for crossover'), indent=2) + '\n')
for i in range(1):
    for kind in ['large_leaf']:
        edit(kind)
        for variant in modules:
            print('prepare', i, kind, variant, invoke(kind, variant, f'prepare-{i}-{kind}-{variant}'), flush=True)
rows = {kind: [] for kind in ['large_leaf']}
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
