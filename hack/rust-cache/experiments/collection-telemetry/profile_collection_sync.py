from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'rust-collection-sync-profile'
root.mkdir(exist_ok=False)
source = Path('/tmp/rust-native-config-entry-1026-after')
config = source / 'dagger.toml'
original = config.read_text()

def set_decoder(enabled):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/attribute-array-decode?enabled=' + str(enabled).lower(), data=b'', method='POST')
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response)['enabled'] == enabled

def capture_trace(label, ready):
    started = time.monotonic()
    ready.set()
    with urllib.request.urlopen('http://127.0.0.1:16104/debug/pprof/trace?seconds=10', timeout=30) as response:
        (root / (label + '.trace')).write_bytes(response.read())
    return started, time.monotonic()

try:
    text, count = re.subn(r'source = "[^"]+"', 'source = "/tmp/dagger-rust-metadata-toolchain"', original, count=1)
    assert count == 1
    config.write_text(text)
    from threading import Event
    with ThreadPoolExecutor(max_workers=1) as pool:
        for label, enabled in [('legacy', False), ('decoded', True)]:
            set_decoder(enabled)
            path = source / 'leaf_1023/src/lib.rs'
            text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {secrets.randbits(48)};', path.read_text())
            assert count == 1
            path.write_text(text)
            ready = Event()
            capture = pool.submit(capture_trace, label, ready)
            ready.wait()
            env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276', RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'), CPUPROFILE=str(root / (label + '-cli.pprof')))
            command_started = time.monotonic()
            with (root / (label + '.log')).open('w') as output:
                run = subprocess.run(['python3', str(base / 'local_cli.py'), 'check', '--list', '--all', 'rust:packages/check'], cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
            command_ended = time.monotonic()
            assert run.returncode == 0, label
            names = re.findall(r'^rust\s+(\S+)\s+check$', (root / (label + '.log')).read_text(), re.M)
            assert len(names) == 1026 and len(set(names)) == 1026, label
            trace_started, trace_ended = capture.result()
            (root / (label + '-window.json')).write_text(json.dumps(dict(command_seconds=command_ended-command_started, trace_seconds=trace_ended-trace_started, command_ended_during_engine_capture=command_ended<=trace_ended, telemetry_enabled=True, cli_cpu_and_runtime_trace=True, diagnostic_only=True), indent=2)+'\n')
            print('PASS complete edited collection and engine runtime trace', label, flush=True)
finally:
    config.write_text(original)
    set_decoder(False)
