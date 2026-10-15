import concurrent.futures
import collections
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'literal-display-crossover-profile'
root.mkdir(exist_ok=False)
# Run after the engine binaries have been swapped for the crossover.
engines = {'before': ('after', 16275, 16103, 'dagger-rust-checkpoint-snapshot-key-oct14'),
           'after': ('before', 16276, 16104, 'dagger-rust-parser-state-pool-oct14')}
summary = {}

def fetch(debug, path, destination):
    started = time.monotonic()
    with urllib.request.urlopen(f'http://127.0.0.1:{debug}/debug/{path}', timeout=45) as response:
        with destination.open('wb') as output:
            while data := response.read(1048576):
                output.write(data)
    return dict(started=started, ended=time.monotonic())

def control(debug, route, data=None):
    request = urllib.request.Request(f'http://127.0.0.1:{debug}/debug/wcprof/{route}', data=data)
    return urllib.request.urlopen(request, timeout=30)

for variant, (physical, port, debug, name) in engines.items():
    with control(debug, 'enabled') as response:
        assert not json.load(response)['global_enabled']
    record = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
    def pressure():
        result = {}
        for prefix, directory in [('host', Path('/proc/pressure')), ('engine', group)]:
            for kind in ['cpu', 'io', 'memory']:
                filename = kind if prefix == 'host' else kind + '.pressure'
                for line in (directory / filename).read_text().splitlines():
                    result[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
        return result

    fetch(debug, 'pprof/allocs', root / (variant + '-allocs-before.pb.gz'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        cpu = pool.submit(fetch, debug, 'pprof/profile?seconds=20', root / (variant + '-cpu.pb.gz'))
        time.sleep(.25)
        captures = []
        for i in range(4):
            label = f'{variant}-{i}'
            source = Path(f'/tmp/rust-native-literal-display-1026-{physical}')
            filename = source / 'leaf_1023/src/lib.rs'
            text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
            assert count == 1
            filename.write_text(text)
            control(debug, 'enabled', b'on').close()
            with control(debug, 'dump') as response:
                while response.read(1048576):
                    pass
            try:
                stalls = pressure()
                started = time.monotonic()
                with (root / (label + '.log')).open('w') as output:
                    result = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', 'rust:check'],
                        cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER=f'tcp://127.0.0.1:{port}'),
                        stdout=output, stderr=subprocess.STDOUT)
                ended = time.monotonic()
                after = pressure()
                assert not result.returncode, label
            finally:
                control(debug, 'enabled', b'off').close()
                fetch(debug, 'wcprof/dump', root / (label + '.ndjson'))
            with (root / (label + '.ndjson')).open() as stream:
                header = json.loads(next(stream))
                assert not header['dropped_events'] and not header.get('open_ops'), header
                names = header['strings']
                ops = [dict(op, cls=names[op.get('c', 0)]) for op in map(json.loads, stream) if op['e'] == 'op']
            classes = collections.defaultdict(lambda: [0, 0.0])
            for op in ops:
                value = classes[op['k'] + ' ' + op['cls']]
                value[0] += 1
                value[1] += (op['d'] - op['s']) / 1e6
            captures.append(dict(label=label, started=started, ended=ended, seconds=ended-started,
                events=header['event_count'], dropped_events=header['dropped_events'], open_ops=header.get('open_ops', 0),
                io_stall_fraction={key: (after[key]-stalls[key])/((ended-started)*1e6) for key in stalls},
                classes={key: dict(count=value[0], total_ms=value[1]) for key, value in classes.items()}))
            print(label, round(ended-started, 3), 'seconds; complete wcprof capture', flush=True)
        window = cpu.result()
    fetch(debug, 'pprof/allocs', root / (variant + '-allocs-after.pb.gz'))
    summary[variant] = dict(physical=physical, engine_port=port, cpu_profile_window=window,
        cpu_profile_covers_all_commands=window['started'] <= captures[0]['started'] and window['ended'] >= captures[-1]['ended'], captures=captures)
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(variant, 'CPU coverage:', summary[variant]['cpu_profile_covers_all_commands'], flush=True)
print('PASS: fresh-edited commands, telemetry enabled; profiling is separate from latency samples', flush=True)
