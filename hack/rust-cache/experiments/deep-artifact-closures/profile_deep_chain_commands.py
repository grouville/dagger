from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'deep-chain-512-profiles'
root.mkdir(exist_ok=False)
modules = {'before': '/tmp/dagger-rust-native-worker-request-current',
           'after': '/tmp/dagger-rust-native-deep-artifact-closures'}
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
relative = Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
engine_group = Path('/sys/fs/cgroup')/relative
groups = {'engine': engine_group, 'docker_total': engine_group.parent, 'exec': engine_group.parent/'exec'}
configs = {}
results = []


def debug(route, data=None, timeout=30):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route, data=data), timeout=timeout)


def mode(name, value):
    with debug(name+'?enabled='+str(value).lower(), b'') as response:
        assert json.load(response)['enabled'] == value


def source_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', 'dagger-rust-parser-state-pool-oct14', 'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'],
                   input=b'on\n' if enabled else b'off\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def cpu():
    return {name: next(int(line.split()[1]) for line in (path/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec '))
            for name, path in groups.items()}


def capture_cpu(label, seconds):
    with debug('pprof/profile?seconds='+str(seconds), timeout=seconds+10) as response:
        (root/(label+'-engine.pprof')).write_bytes(response.read())


def run(kind, arm, history, index):
    label = f'{kind}-{index}-{arm}'
    source = Path('/tmp/rust-native-deep-chain-512-'+history)
    config = source/'dagger.toml'
    if config not in configs:
        configs[config] = config.read_text()
    updated, count = re.subn(r'source = "[^"]+"', 'source = '+json.dumps(modules[arm]), configs[config], count=1)
    assert count == 1
    config.write_text(updated)
    filename = source/f"pkg_{510 if kind == 'tail' else 256:04d}/src/lib.rs"
    updated, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
    assert count == 1
    filename.write_text(updated)
    while True:
        with debug('client-lifecycle') as response:
            state = json.load(response)
        if not state.get('sessions') and not state['active_requests']:
            break
        time.sleep(.2)
    time.sleep(1)
    with debug('wcprof/enabled', b'on'):
        pass
    with debug('wcprof/dump') as response:
        while response.read(1048576):
            pass
    before = cpu()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(capture_cpu, label, 30 if kind == 'shared' else 10)
            time.sleep(.05)
            with (root/(label+'.log')).open('w') as output:
                process = subprocess.run(['python3', str(base/'local_cli_collector.py'), 'check', 'rust:packages/check'],
                                         cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
            wall = time.monotonic()-started
            after = cpu()
            with debug('wcprof/enabled', b'off'):
                pass
            future.result()
    finally:
        with debug('wcprof/enabled', b'off'):
            pass
        with debug('wcprof/dump') as response, (root/(label+'.ndjson')).open('wb') as output:
            while chunk := response.read(1048576):
                output.write(chunk)
    assert process.returncode == 0 and 'passed' in (root/(label+'.log')).read_text(), label
    with (root/(label+'.ndjson')).open() as stream:
        header = json.loads(next(stream))
        strings = header['strings']
        ops = [json.loads(line) for line in stream]
    assert not header['dropped_events'] and not header.get('open_ops'), label
    selected = []
    for op in ops:
        cls = strings[op.get('c', 0)]
        if op.get('e') == 'op' and op.get('k') in ['call_exec', 'internal', 'exec_phase'] and any(term in cls for term in [
                'RustCompiler.compile', 'Check.sync', 'Host.directory', 'Directory.glob', 'Directory.digests', 'Directory.checkpoint',
                'Directory.withDirectory', 'directory.withDirectory', 'collectSnapshotOwnerLinks', 'snapshotLeaseLockHeld',
                'withExec.prepareMounts', 'exec.workload', 'withExec.applyOutputs']):
            selected.append(dict(cls=cls, kind=op['k'], milliseconds=(op['d']-op['s'])/1e6,
                                 instance=strings[op.get('i', 0)], id=op['id'], parent=op.get('p')))
    results.append(dict(label=label, kind=kind, arm=arm, history=history, diagnostic_only=True,
                        seconds=wall, cpu_seconds={name: (after[name]-before[name])/1e6 for name in groups},
                        cpu_scope_paths={name: str(path) for name, path in groups.items()},
                        dropped_events=header['dropped_events'], open_ops=header.get('open_ops', 0), selected=selected))
    (root/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
    print('PASS', label, round(wall, 3), 'diagnostic seconds', results[-1]['cpu_seconds'], flush=True)


try:
    source_mode(True)
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('direct-span-protobuf', False)
    mode('snapshot-completions', False)
    for index, order in [(0, ['before', 'after']), (1, ['after', 'before'])]:
        for kind in ['tail', 'shared']:
            for arm in order:
                run(kind, arm, 'before' if index == 0 else 'after', index)
finally:
    source_mode(False)
    with debug('wcprof/enabled', b'off'):
        pass
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
    for config, original in configs.items():
        config.write_text(original)
