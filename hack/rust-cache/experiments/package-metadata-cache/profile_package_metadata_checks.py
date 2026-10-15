import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'package-metadata-edited-check-profile'
root.mkdir(exist_ok=False)
sources = {size: Path(f'/tmp/rust-native-config-entry-{size}-after')
           for size in ['130', '1026']}
originals = {source / 'dagger.toml': (source / 'dagger.toml').read_text()
             for source in sources.values()}


def debug(route, data=None):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/' + route, data=data)
    return urllib.request.urlopen(request, timeout=30)


def mode(name, enabled):
    with debug(name + '?enabled=' + str(enabled).lower(), b'') as response:
        assert json.load(response)['enabled'] == enabled


try:
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('snapshot-completions', False)
    for size, source in sources.items():
        config = source / 'dagger.toml'
        updated, count = re.subn(r'source = "[^"]+"',
                                'source = "/tmp/dagger-rust-package-metadata-cache"',
                                originals[config], count=1)
        assert count == 1
        config.write_text(updated)
        leaf = '0127' if size == '130' else '1023'
        filename = source / f'leaf_{leaf}/src/lib.rs'
        updated, count = re.subn(r'pub const EDIT: u64 = \d+;',
                                f'pub const EDIT: u64 = {secrets.randbits(48)};',
                                filename.read_text())
        assert count == 1
        filename.write_text(updated)
        with debug('wcprof/enabled', b'on'):
            pass
        with debug('wcprof/dump') as response:
            while response.read(1048576):
                pass
        label = size + '-edited-check'
        env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
                   RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'),
                   CPUPROFILE=str(root / (label + '-cli.pprof')),
                   RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
        started = time.monotonic()
        with (root / (label + '.log')).open('w') as output:
            result = subprocess.run(
                ['python3', str(base / 'local_cli_collector.py'), 'check',
                 'rust:check' if size == '130' else 'rust:packages/check'],
                cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
        seconds = time.monotonic() - started
        with debug('wcprof/enabled', b'off'):
            pass
        with debug('wcprof/dump') as response, (root / (label + '.ndjson')).open('wb') as output:
            while chunk := response.read(1048576):
                output.write(chunk)
        assert result.returncode == 0 and 'passed' in (root / (label + '.log')).read_text(), label
        with (root / (label + '.ndjson')).open() as stream:
            header = json.loads(next(stream))
        assert not header['dropped_events'] and not header.get('open_ops'), label
        summary = dict(command_seconds=seconds, diagnostic_only=True,
                       wcprof=True, cli_cpu_and_runtime_profile=True,
                       metadata_reuse=True, attribute_array_decoder=True,
                       source_snapshot_seeds=False, module='perf/package-metadata-cache', package_metadata_reuse=True,
                       native_compiler_cache=True, fresh_used_rust_edit=True,
                       events=header['event_count'], dropped_events=header['dropped_events'],
                       open_ops=header.get('open_ops', 0))
        (root / (label + '-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
        print('PASS', label, round(seconds, 3), 'seconds under profiling', flush=True)
finally:
    with debug('wcprof/enabled', b'off'):
        pass
    for config, original in originals.items():
        config.write_text(original)
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
