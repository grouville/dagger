"""Profile actual Go module processes during freshly edited normal checks."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--sizes', nargs='+', default=['130', '1026', 'small'])
parser.add_argument('--rounds', type=int, default=2)
parser.add_argument('--module', default='/tmp/dagger-rust-profile-compiler-helper')
parser.add_argument('--collector', default='http://172.17.0.18:43184')
parser.add_argument('--telemetry', default='/tmp/rust-cache-sipsma-review/compiler-helper-profile-receiver/telemetry.jsonl')
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = base / args.root
root.mkdir(exist_ok=False)
module = args.module
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR=args.collector)
configs = {}
results = []


def debug(route, data=None):
    return urllib.request.urlopen(urllib.request.Request(
        'http://127.0.0.1:16104/debug/'+route, data=data), timeout=30)


def mode(name, value):
    with debug(name+'?enabled='+str(value).lower(), b'') as response:
        assert json.load(response)['enabled'] == value


def source_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', 'dagger-rust-parser-state-pool-oct14',
                    'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'],
                   input=b'on\n' if enabled else b'off\n', check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def run(size, index):
    label = size+'-'+str(index)
    source = Path('/tmp/rust-native-config-entry-'+size+'-before')
    config = source/'dagger.toml'
    if config not in configs:
        configs[config] = config.read_text()
    updated, count = re.subn(r'source = "[^"]+"', f'source = "{module}"', configs[config], count=1)
    assert count == 1
    config.write_text(updated)
    relative = {'130': 'leaf_0127/src/lib.rs', '1026': 'leaf_1023/src/lib.rs',
                'small': 'app/src/lib.rs'}[size]
    filename = source/relative
    pattern = r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if size == 'small' else r'pub const EDIT: u64 = \d+;'
    replacement = f'pub fn edited_value() -> u64 {{ {secrets.randbits(48)} }}' if size == 'small' else f'pub const EDIT: u64 = {secrets.randbits(48)};'
    updated, count = re.subn(pattern, replacement, filename.read_text())
    assert count == 1
    filename.write_text(updated)
    while True:
        with debug('client-lifecycle') as response:
            state = json.load(response)
        if not state.get('sessions') and not state['active_requests']:
            break
        time.sleep(.2)
    with debug('wcprof/enabled', b'on'):
        pass
    with debug('wcprof/dump') as response:
        while response.read(1048576):
            pass
    selection = {'130': 'rust:check', '1026': 'rust:packages/check', 'small': 'rust:packages/test'}[size]
    started = time.monotonic()
    telemetry = Path(args.telemetry)
    offset = telemetry.stat().st_size if telemetry.exists() else 0
    try:
        with (root/(label+'.log')).open('w') as output:
            process = subprocess.run(['python3', str(base/'local_cli_collector.py'), '-vv', 'check', selection],
                                     cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
    finally:
        with debug('wcprof/enabled', b'off'):
            pass
        with debug('wcprof/dump') as response, (root/(label+'.ndjson')).open('wb') as output:
            while chunk := response.read(1048576):
                output.write(chunk)
    wall = time.monotonic()-started
    assert process.returncode == 0, (label, process.returncode)
    text = (root/(label+'.log')).read_text()
    assert 'passed' in text, label
    with telemetry.open('rb') as stream:
        stream.seek(offset)
        raw = stream.read(128*1024*1024)
        assert not stream.read(1), 'diagnostic telemetry exceeded capture budget'
    (root/(label+'-telemetry.jsonl')).write_bytes(raw)
    bodies = {}
    for line in raw.splitlines():
        event = json.loads(line)
        if event.get('kind') == 'log' and isinstance(event.get('body'), str):
            bodies.setdefault(event.get('spanId'), []).append(event['body'])
    text += '\n'+'\n'.join(''.join(parts) for parts in bodies.values())
    profiles = []
    seen = set()
    for match in re.finditer('RUST_COMPILER_PROFILE ', text):
        value, _ = json.JSONDecoder().raw_decode(text[match.end():])
        key = hashlib.sha256(value['cpu'].encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        index = len(profiles)
        for kind in ['cpu', 'block']:
            (root/(label+'-'+str(index)+'-'+kind+'.pprof')).write_bytes(base64.b64decode(value.pop(kind)))
        profiles.append(value)
    with (root/(label+'.ndjson')).open() as stream:
        header = json.loads(next(stream))
    result = dict(label=label, diagnostic_only=True, wall_seconds=wall, profiles=profiles,
                  dropped_events=header['dropped_events'], open_ops=header.get('open_ops', 0))
    results.append(result)
    (root/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
    print(label, 'profiles', [(p['operation'], round(p['nanos']/1e6, 2)) for p in profiles],
          'wall', round(wall, 3), flush=True)
    assert profiles and any(p['operation'].endswith('.Compile') for p in profiles), 'Compile profile missing'
    assert not result['dropped_events'] and not result['open_ops'], label


try:
    source_mode(True)
    mode('direct-span-protobuf', False)
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('snapshot-completions', False)
    with debug('scalar-array-restore') as response:
        assert json.load(response)['enabled']
    for index in range(args.rounds):
        for size in args.sizes:
            run(size, index)
finally:
    source_mode(False)
    with debug('wcprof/enabled', b'off'):
        pass
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
    for config, original in configs.items():
        config.write_text(original)
