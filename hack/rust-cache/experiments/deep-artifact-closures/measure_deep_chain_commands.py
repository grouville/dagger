import argparse
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, default=512)
parser.add_argument('--pairs', type=int, default=8)
parser.add_argument('--crossover', action='store_true')
parser.add_argument('--output-root', required=True)
parser.add_argument('--kinds', nargs='+', choices=['tail', 'shared'], default=['tail', 'shared'])
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = Path(args.output_root)
root.mkdir(exist_ok=False)
cli = str(base/'dagger-artifact-list-buffered')
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
modules = {'before': '/tmp/dagger-rust-native-worker-request-current', 'after': '/tmp/dagger-rust-native-deep-artifact-closures'}
physical = {'before': 'after', 'after': 'before', 'cargo': 'cargo'} if args.crossover else {a: a for a in ['before', 'after', 'cargo']}
fixtures = {a: Path(f'/tmp/rust-native-deep-chain-{args.size}-{a}') for a in physical}
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
           DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',
           NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
group = Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')


def debug(route, data=None):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route, data=data), timeout=10)


def mode(name, enabled):
    with debug(name+'?enabled='+str(enabled).lower(), b'') as response:
        assert json.load(response)['enabled'] == enabled


def source_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', 'dagger-rust-parser-state-pool-oct14', 'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'],
                   input=b'on\n' if enabled else b'off\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def pressure():
    result = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path/(kind if prefix == 'host' else kind+'.pressure')).read_text().splitlines():
                result[prefix+'.'+kind+'.'+line.split()[0]] = int(line.split('total=')[1])
    return result


def cpu():
    return next(int(line.split()[1]) for line in (group/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec '))


def wait_for_idle(label):
    waiting = time.monotonic()
    while True:
        before = pressure()
        started = time.monotonic()
        time.sleep(1)
        after = pressure()
        seconds = time.monotonic()-started
        fractions = {key: (after[key]-before[key])/(seconds*1e6) for key in before}
        with debug('client-lifecycle') as response:
            state = json.load(response)
        idle = not state.get('sessions') and not state['active_requests']
        admitted = idle and fractions['host.io.some'] < .05 and fractions['engine.io.some'] < .01
        elapsed = time.monotonic()-waiting
        with (root/'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, seconds=elapsed, window=seconds, stall_fraction=fractions, idle=idle, admitted=admitted))+'\n')
        if admitted:
            return
        print('waiting for idle', label, round(elapsed, 1), flush=True)
        assert elapsed < 60, 'quiet-start admission timed out; no measured samples excluded'


def edit(kind):
    index = args.size-2 if kind == 'tail' else args.size//2
    for source in fixtures.values():
        filename = source/f'pkg_{index:04d}/src/lib.rs'
        text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
        assert count == 1
        filename.write_text(text)


def invoke(kind, arm, label):
    source = fixtures[physical[arm]]
    run_env = dict(env)
    if arm == 'cargo':
        run_env.update(RUSTC=str(toolchain/'rustc'), RUSTDOC=str(toolchain/'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8',
                       CARGO_TARGET_DIR=str(base/f'deep-chain-{args.size}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            run_env.pop(key, None)
        command = [str(toolchain/'cargo'), 'check', '--workspace', '--locked', '--offline']
    else:
        command = [cli, 'check', 'rust:packages/check']
    wait_for_idle(label)
    before, cpu_before, started = pressure(), cpu(), time.monotonic()
    with (root/(label+'.log')).open('w') as output:
        result = subprocess.run(command, cwd=source, env=run_env, stdout=output, stderr=subprocess.STDOUT)
    seconds = time.monotonic()-started
    after, cpu_after = pressure(), cpu()
    assert result.returncode == 0, (label, result.returncode)
    text = (root/(label+'.log')).read_text()
    if arm != 'cargo':
        assert 'passed' in text, label
    elif label.startswith('edited-'):
        count = len(set(re.findall(r'Checking ([\w-]+) v', text)))
        expected = 2 if kind == 'tail' else args.size-args.size//2
        assert count == expected, (label, 'Cargo compiler actions', count, expected)
    with (root/'pressure.jsonl').open('a') as output:
        output.write(json.dumps(dict(label=label, seconds=seconds, engine_cpu_seconds=(cpu_after-cpu_before)/1e6,
                                     stall_fraction={key: (after[key]-before[key])/(seconds*1e6) for key in before}))+'\n')
    return seconds


configs = {}
try:
    for arm in modules:
        config = fixtures[physical[arm]]/'dagger.toml'
        configs[config] = config.read_text()
        text, count = re.subn(r'source = "[^"]+"', 'source = '+json.dumps(modules[arm]), configs[config], count=1)
        assert count == 1
        config.write_text(text)
    with debug('wcprof/enabled') as response:
        assert not json.load(response)['global_enabled']
    with debug('scalar-array-restore') as response:
        assert json.load(response)['enabled']
    source_mode(True)
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('direct-span-protobuf', False)
    mode('snapshot-completions', False)
    (root/'metadata.json').write_text(json.dumps(dict(size=args.size, before='e63b6a2', after='f73c561', modules=modules,
        physical=physical, cli=cli, engine_sha256='a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa',
        selection='rust:packages/check', source_snapshot_seeds=True, compact_scalar_restore=True,
        batch_metadata=True, attribute_array_decode=True, telemetry_enabled=True, collector=env['DAGGER_CLOUD_URL'],
        wcprof_enabled=False, cpu_profile_enabled=False, fresh_unique_edit_per_variant=True,
        worker_binary_and_compiler_keys_unchanged=True, physical_histories_exchanged=args.crossover,
        cargo_incremental=True, rust_version='1.77.2', workers=8, warm_engine=True,
        initial_project_history='new for first cohort; two preparation rounds excluded',
        timer='blocking waitpid without timeout polling', max_idle_admission_seconds=60,
        post_launch_stalls_excluded=False, engine_restarted=False), indent=2)+'\n')
    for index in range(2):
        for kind in args.kinds:
            edit(kind)
            for arm in ['before', 'after', 'cargo']:
                print('prepare', index, kind, arm, invoke(kind, arm, f'prepare-{index}-{kind}-{arm}'), flush=True)
    rows = {kind: [] for kind in args.kinds}
    orders = [['before', 'after', 'cargo'], ['cargo', 'after', 'before'], ['after', 'cargo', 'before'],
              ['before', 'cargo', 'after'], ['cargo', 'before', 'after'], ['after', 'before', 'cargo']]
    for index in range(args.pairs):
        for kind in args.kinds:
            edit(kind)
            row = {arm: invoke(kind, arm, f'edited-{index}-{kind}-{arm}') for arm in orders[index % len(orders)]}
            rows[kind].append(row)
            (root/'samples.json').write_text(json.dumps(rows, indent=2)+'\n')
            print(kind, index, row, flush=True)
    summary = {kind: dict(median_seconds={arm: statistics.median(row[arm] for row in values) for arm in ['before', 'after', 'cargo']},
                         median_paired_saving_ms=statistics.median(row['before']-row['after'] for row in values)*1000,
                         faster_pairs=sum(row['after'] < row['before'] for row in values)) for kind, values in rows.items()}
    (root/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)
finally:
    source_mode(False)
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
    for config, text in configs.items():
        config.write_text(text)
