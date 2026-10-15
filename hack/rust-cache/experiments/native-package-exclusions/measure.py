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
parser.add_argument('--actions', type=int, default=130)
parser.add_argument('--pairs', type=int, default=8)
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = base / f'native-batched-root-projections-{args.actions}-paired'
root.mkdir(exist_ok=False)
modules = {'before': '/tmp/dagger-rust-worker-dependency-index', 'after': '/tmp/dagger-rust-batched-package-exclusions', 'cargo': '/tmp/dagger-rust-worker-dependency-index'}
sources = {}
for variant, module in modules.items():
    source = Path(f'/tmp/rust-native-batched-root-{args.actions}-{variant}')
    shutil.copytree(f'/tmp/rust-native-root-projection-{args.actions}', source, ignore=shutil.ignore_patterns('.git', 'target', 'dagger.lock'))
    subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
    config = source / 'dagger.toml'
    text, n = re.subn(r'source = "[^"]+"', f'source = "{module}"', config.read_text(), count=1)
    assert n == 1
    text, n = re.subn(r'cacheKey = "[^"]+"', f'cacheKey = "native-batched-root-{args.actions}-{variant}"', text, count=1)
    assert n == 1
    config.write_text(text)
    main = source / 'src/main.rs'
    text = main.read_text()
    assert 'let mut value = 0u64;' in text
    main.write_text('pub const ROOT_EDIT: u64 = 0;\n' + text.replace('let mut value = 0u64;', 'let mut value = ROOT_EDIT;'))
    sources[variant] = source

with urllib.request.urlopen('http://127.0.0.1:16104/debug/wcprof/enabled', timeout=10) as f:
    assert not json.load(f)['global_enabled']
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
collector = Path('/tmp/rust-cache-oct13-filter/local-receiver/address.txt').read_text().strip()
env.update(DAGGER_CLOUD_URL='http://' + collector + ':43183', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')


def pressure():
    result = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                result[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return result


def edit(kind):
    relative = {'leaf': f'leaf_{args.actions - 3:04d}/src/lib.rs', 'shared': 'shared/src/lib.rs', 'root': 'src/main.rs'}[kind]
    constant = 'ROOT_EDIT' if kind == 'root' else 'EDIT'
    for source in sources.values():
        p = source / relative
        text, n = re.subn(r'pub const ' + constant + r': u64 = \d+;', f'pub const {constant}: u64 = {secrets.randbits(48)};', p.read_text())
        assert n == 1
        p.write_text(text)


def invoke(kind, variant, label):
    if variant == 'cargo':
        run_env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'), CARGO_INCREMENTAL='1', CARGO_TARGET_DIR=str(base / f'native-batched-root-{args.actions}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            run_env.pop(key, None)
        command = [str(toolchain / 'cargo'), 'check', '--workspace', '--locked', '--offline']
    else:
        run_env = env
        command = ['/tmp/native-hash-verification-bin/dagger', 'check', 'rust:check']
    before, started = pressure(), time.monotonic()
    with (root / (label + '.log')).open('w') as out:
        proc = subprocess.run(command, cwd=sources[variant], env=run_env, stdout=out, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    after = pressure()
    assert not proc.returncode, (label, proc.returncode)
    log = (root / (label + '.log')).read_text()
    if variant != 'cargo':
        assert '1 passed' in log, label
    elif label.startswith('edited'):
        count = len(set(re.findall(r'Checking ([\w-]+) v', log)))
        assert count == {'leaf': 2, 'shared': args.actions, 'root': 1}[kind], (label, count)
    with (root / 'pressure.jsonl').open('a') as out:
        out.write(json.dumps({'label': label, 'seconds': elapsed, 'stall_fraction': {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}}) + '\n')
    return elapsed


(root / 'metadata.json').write_text(json.dumps({'base_module': 'b4b8ffd', 'engine': 'primitive array response candidate on 16276', 'actions': args.actions, 'root_package': True, 'telemetry_enabled': True, 'wcprof_enabled': False, 'fresh_unique_edit_per_variant': True, 'timer': 'blocking waitpid without timeout polling'}, indent=2) + '\n')
for i in range(2):
    for kind in ['shared', 'leaf', 'root']:
        edit(kind)
        for variant in sources:
            elapsed = invoke(kind, variant, f'prepare-{i}-{kind}-{variant}')
            print('prepare', i, kind, variant, elapsed, flush=True)

rows = {kind: [] for kind in ['leaf', 'shared', 'root']}
orders = [['before', 'after', 'cargo'], ['cargo', 'after', 'before'], ['after', 'cargo', 'before'], ['before', 'cargo', 'after'], ['cargo', 'before', 'after'], ['after', 'before', 'cargo']]
for i in range(args.pairs):
    for kind in rows:
        edit(kind)
        row = {v: invoke(kind, v, f'edited-{i}-{kind}-{v}') for v in orders[i % len(orders)]}
        rows[kind].append(row)
        (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(kind, i, row, flush=True)
summary = {kind: {'median_seconds': {v: statistics.median(r[v] for r in samples) for v in sources}, 'median_paired_saving_ms': statistics.median(r['before'] - r['after'] for r in samples) * 1000, 'faster_pairs': sum(r['after'] < r['before'] for r in samples)} for kind, samples in rows.items()}
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary), flush=True)
print('PASS: fresh root-package workspace edits with native Cargo rebuild sets checked', flush=True)
