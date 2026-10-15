from concurrent.futures import ThreadPoolExecutor
import collections
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from threading import Event
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'snapshot-publication-profile'
root.mkdir(exist_ok=False)
source = Path('/tmp/rust-native-config-entry-1026-after')
config = source / 'dagger.toml'
original = config.read_text()


def debug(name, query=None, data=None):
    request = urllib.request.Request(
        'http://127.0.0.1:16104/debug/' + name + ('?' + query if query else ''),
        data=data)
    return urllib.request.urlopen(request, timeout=60)


def switch(name, enabled):
    with debug(name, 'enabled=' + str(enabled).lower(), b'') as response:
        assert json.load(response)['enabled'] == enabled


def capture(label, kind, ready):
    started = time.monotonic()
    ready.set()
    with debug('pprof/' + kind, 'seconds=30') as response:
        with (root / (label + ('-engine.trace' if kind == 'trace' else '-engine.cpu.pprof'))).open('wb') as output:
            while chunk := response.read(1048576):
                output.write(chunk)
    return started, time.monotonic()


env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'))
try:
    updated, count = re.subn(r'source = "[^"]+"',
                            'source = "/tmp/dagger-rust-metadata-toolchain"',
                            original, count=1)
    assert count == 1
    config.write_text(updated)
    switch('attribute-array-decode', True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for label, enabled in [('legacy', False), ('no-import', True)]:
            switch('snapshot-completions', enabled)
            filename = source / 'leaf_1023/src/lib.rs'
            updated, count = re.subn(r'pub const EDIT: u64 = \d+;',
                                    f'pub const EDIT: u64 = {secrets.randbits(48)};',
                                    filename.read_text())
            assert count == 1
            filename.write_text(updated)
            with debug('wcprof/enabled', data=b'on'):
                pass
            with debug('wcprof/dump') as response:
                while response.read(1048576):
                    pass
            events = [Event(), Event()]
            captures = [pool.submit(capture, label, kind, ready)
                        for kind, ready in zip(['trace', 'profile'], events)]
            for ready in events:
                ready.wait()
            command_started = time.monotonic()
            with (root / (label + '.log')).open('w') as output:
                result = subprocess.run(
                    ['python3', str(base / 'local_cli.py'), 'check', '--list',
                     '--all', 'rust:packages/check'], cwd=source, env=env,
                    stdout=output, stderr=subprocess.STDOUT)
            command_ended = time.monotonic()
            with debug('wcprof/enabled', data=b'off'):
                pass
            with debug('wcprof/dump') as response, (root / (label + '.ndjson')).open('wb') as output:
                while chunk := response.read(1048576):
                    output.write(chunk)
            assert result.returncode == 0, label
            names = re.findall(r'^rust\s+(\S+)\s+check$', (root / (label + '.log')).read_text(), re.M)
            expected = {'app', 'shared'} | {f'leaf_{i:04d}' for i in range(1024)}
            assert len(names) == 1026 and set(names) == expected, label
            windows = [future.result() for future in captures]
            with (root / (label + '.ndjson')).open() as stream:
                header = json.loads(next(stream))
                classes = collections.defaultdict(lambda: dict(count=0, total_ms=0))
                for event in map(json.loads, stream):
                    if event['e'] == 'op':
                        row = classes[event['k'] + ' ' + header['strings'][event.get('c', 0)]]
                        row['count'] += 1
                        row['total_ms'] += (event['d'] - event['s']) / 1e6
            assert not header['dropped_events'] and not header.get('open_ops'), label
            summary = dict(command_seconds=command_ended-command_started,
                           complete_engine_captures=all(start <= command_started and end >= command_ended for start, end in windows),
                           capture_seconds=[end-start for start, end in windows],
                           classes=dict(classes), events=header['event_count'],
                           dropped_events=header['dropped_events'],
                           open_ops=header.get('open_ops', 0),
                           telemetry_enabled=True, attribute_array_decoder=True,
                           snapshot_completion_fast_path=enabled,
                           diagnostic_only=True)
            (root / (label + '-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
            assert summary['complete_engine_captures'], label
            print('PASS full engine trace, CPU profile and wcprof:', label,
                  round(summary['command_seconds'], 3), 'seconds', flush=True)
finally:
    with debug('wcprof/enabled', data=b'off'):
        pass
    config.write_text(original)
    switch('snapshot-completions', False)
    switch('attribute-array-decode', False)
