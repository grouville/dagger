from pathlib import Path
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, '/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
from bench_engine import BenchEngine

family = Path(__file__).parent
root = family / 'toml-host-read-probe'
root.mkdir(exist_ok=False)
engine = BenchEngine(root)
source = Path('/tmp/dagger-go-real-repository-main')
module = Path('/tmp/dagger-go-module-test-name-index')
cli = family.parent / 'filesync-literal-pathwalk/dagger-after'
config = module / 'dagger.toml'
edit = source / 'dagql/types.go'
original = edit.read_bytes()
saved = {name: (source/name).read_bytes() if (source/name).exists() else None
         for name in ['dagger.toml', 'dagger.lock']}
routes = ['batch-metadata', 'attribute-array-decode', 'usage-sampling',
          'restored-posting-removal', 'span-lookup-fanout', 'builtin-receivers']
flags = {route: engine.get(route)['enabled'] for route in routes}
before_config = config.read_bytes()
env = {key: value for key, value in os.environ.items()
       if key not in {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK',
                      'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE',
                      'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                      'http_proxy', 'https_proxy', 'all_proxy'}
       and not key.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(family.parent/'otlp-null-address.txt').read_text().strip()+':43184',
           DAGGER_CLOUD_TOKEN='local-benchmark-token', NO_PROXY='*',
           XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',
           _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(family.parent/'dagger-artifact-workspace-before'),
           _EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15')
command = ['strace', '-f', '-qq', '-ttt', '-T', '-s', '256',
           '-e', 'trace=openat,newfstatat,statx', '-P', str(config),
           '-o', str(root/'config-host.strace'), '--', str(cli),
           'check', '--module', 'go', '--check', 'test', '--list', '--all']
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'protocol.json').write_text(json.dumps(dict(command=command,
    diagnostic_only=True, not_a_latency_benchmark=True,
    note='Trace one public module configuration path. Count host syscalls, not parser calls. Retain fresh file reads and normal telemetry/GC.',
    config_sha256_before=hashlib.sha256(before_config).hexdigest(),
    config_bytes=len(before_config), initial_modes=flags), indent=2)+'\n')
try:
    assert not engine.get('wcprof/enabled')['global_enabled']
    assert not engine.get('snapshot-collection')['deferred']
    assert engine.get('lock-profiler') == dict(mutex_fraction=0, block_profile_rate_ns=0)
    for route in routes:
        engine.mode(route, True)
    edit.write_bytes(original+f'\n// Config host-read diagnostic {time.time_ns()}\n'.encode())
    (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    engine.idle('toml-host-read-probe')
    started = time.monotonic()
    with (root/'stdout').open('w') as out, (root/'stderr').open('w') as err:
        process = subprocess.Popen(command, cwd=source, env=env, stdout=out, stderr=err,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGINT)
            code = process.wait()
    elapsed = time.monotonic()-started
    lines = [line for line in (root/'stdout').read_text().splitlines() if line.startswith('go ')]
    expected = [line for line in (family.parent/'glob-literal-prefix/full-command-paired/0-before.stdout').read_text().splitlines() if line.startswith('go ')]
    trace = (root/'config-host.strace').read_text()
    calls = {name: len(re.findall(r'\b'+name+r'\(', trace))
             for name in ['openat', 'newfstatat', 'statx']}
    row = dict(exit_code=code, diagnostic_elapsed_seconds=elapsed,
               same_rows=lines==expected, rows=len(lines), host_calls=calls,
               config_unchanged=config.read_bytes()==before_config,
               config_sha256_after=hashlib.sha256(config.read_bytes()).hexdigest(),
               trace_bytes=len(trace.encode()), parser_call_count_not_measured=True)
    (root/'result.json').write_text(json.dumps(row, indent=2)+'\n')
    print(json.dumps(row, indent=2), flush=True)
    assert code == 0 and lines == expected and len(lines) == 4398, row
    assert row['config_unchanged'], row
finally:
    edit.write_bytes(original)
    for name, data in saved.items():
        if data is None:
            (source/name).unlink(missing_ok=True)
        else:
            (source/name).write_bytes(data)
    for route, enabled in flags.items():
        engine.mode(route, enabled)
