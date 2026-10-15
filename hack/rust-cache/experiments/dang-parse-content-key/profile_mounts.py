import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'dang-content-key-mount-expiry'
root.mkdir(exist_ok=False)
variants = {
    'before': (16275, 16103, 'dagger-rust-checkpoint-snapshot-key-oct14', 'after'),
    'after': (16276, 16104, 'dagger-rust-parser-state-pool-oct14', 'before'),
}
rows = []
for stage in ['warm', 'expired']:
    if stage == 'expired':
        print('Waiting 31 seconds for the 30-second idle mount expiry; no timing benchmark is running.', flush=True)
        time.sleep(31)
    for label, (runner, port, engine, physical) in variants.items():
        source = Path('/tmp/rust-native-dang-content-130-' + physical)
        filename = source / 'leaf_0127/src/lib.rs'
        text, count = re.subn(r'pub const EDIT: u64 = \d+;',
            f'pub const EDIT: u64 = {secrets.randbits(48)};', filename.read_text())
        assert count == 1
        filename.write_text(text)

        def debug(route, data=None):
            return urllib.request.urlopen(urllib.request.Request(
                f'http://127.0.0.1:{port}/debug/wcprof/' + route, data=data), timeout=30)

        with debug('enabled') as response:
            assert not json.load(response)['global_enabled']
        debug('enabled', b'on').close()
        with debug('dump') as response:
            while response.read(1048576):
                pass
        prefix = stage + '-' + label
        try:
            with (root / (prefix + '.log')).open('w') as output:
                result = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', 'rust:check'],
                    cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER=f'tcp://127.0.0.1:{runner}'),
                    stdout=output, stderr=subprocess.STDOUT)
            assert not result.returncode, prefix
        finally:
            debug('enabled', b'off').close()
            with debug('dump') as response, (root / (prefix + '.ndjson')).open('wb') as output:
                while data := response.read(1048576):
                    output.write(data)
        with (root / (prefix + '.ndjson')).open() as data:
            header = json.loads(next(data))
            assert not header['dropped_events'] and not header.get('open_ops'), header
            names = header['strings']
            ops = [dict(op, cls=names[op.get('c', 0)]) for op in map(json.loads, data) if op['e'] == 'op']
        logs = subprocess.check_output(['docker', 'logs', '--tail', '2500', engine], stderr=subprocess.STDOUT, text=True)
        paths = [re.search(r' dir=(\S+)', line)[1] for line in logs.splitlines()
                 if 'directory type inference completed' in line and re.search(r' dir=(\S+)', line)]
        assert paths, prefix
        row = dict(stage=stage, variant=label, mount_path=paths[-1], dropped_events=header['dropped_events'],
                   open_ops=header.get('open_ops', 0), phases_ms={phase: [(op['d'] - op['s']) / 1e6 for op in ops if op['cls'] == phase]
                   for phase in ['dang.runSource.parse', 'dang.runSource.infer', 'dang.runSource.evaluate']})
        rows.append(row)
        (root / 'summary.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(row, flush=True)
for variant in variants:
    selected = [row for row in rows if row['variant'] == variant]
    assert selected[0]['mount_path'] != selected[1]['mount_path'], (variant, selected)
print('PASS: both engines remounted identical module source after expiry; all four edited checks pass', flush=True)
