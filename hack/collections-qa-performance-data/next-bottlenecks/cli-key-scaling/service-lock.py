"""Prepared local-only OCI-lock diagnostic. No manual digest pin or source edit.

Run only after vertical v3 completes and root grants the exclusive engine slot.
The finite root API request may write the workspace's ordinary dagger.lock.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import tomllib
import urllib.error
import urllib.request

lab = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--run', action='store_true')
parser.add_argument('--workspace', type=Path, default=lab / 'vertical-local-disk-v3' / 'workspace')
parser.add_argument('--cli', type=Path, default=Path('/tmp/collections-perf/sparse-export/production/dagger-production'))
parser.add_argument('--trial', default='service-lock-v3')
parser.add_argument('--repeats', type=int, default=3)
args = parser.parse_args()
assert '/' not in args.trial and args.trial not in ('', '.', '..')
assert 1 <= args.repeats <= 5
finite = ['-m', 'core', 'api', 'call', 'container', 'from', '--address', 'busybox:1.37', 'image-ref']
if not args.run:
    print(json.dumps({'status': 'prepared, not run', 'workspace': str(args.workspace),
                      'cli': str(args.cli), 'finite_command_suffix': finite,
                      'up_runs': args.repeats, 'separate_profiled_up_runs': 1,
                      'telemetry': 'audited local-only environment',
                      'mutation': 'ordinary Dagger lockfile writes only; no manual pin or module edits'}, indent=2))
    raise SystemExit()

ws = args.workspace.resolve()
assert (ws.parent / 'summary.json').is_file(), 'vertical v3 must complete before this diagnostic'
config_data = (ws / 'dagger.toml').read_bytes()
config = tomllib.loads(config_data.decode())
ports = config.get('ports', {})
assert len(ports) == 1, 'expected the original single-service fixture port'
port_text, mapping = next(iter(ports.items()))
assert mapping == {'backendService': 'web', 'backendPort': 8080}, mapping
port = int(port_text)
assert 1024 <= port <= 65535
assert config['modules']['perf-flows'] == {'source': './module', 'entrypoint': True}
assert '.from("busybox:1.37")' in (ws / 'module/main.dang').read_text()
expected_body = (ws / 'input.txt').read_bytes()
engine = 'dagger-engine.collections-disk-abba-2'
out = lab / args.trial
out.mkdir(exist_ok=False)
(out / 'driver.py.txt').write_text(Path(__file__).read_text())
empty_config = out / 'empty-config'
empty_config.mkdir(mode=0o700)
env = dict(os.environ)
for key in ('SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_CLOUD_URL', 'DAGGER_SESSION_PORT',
            'DAGGER_SESSION_TOKEN', 'DAGGER_PERF_TIMELINE'):
    env.pop(key, None)
for key in list(env):
    if key.startswith(('OTEL_', 'DAGGER_SESSION_', 'DAGGER_CLOUD_')) or key in (
        'DAGGER_CLOUD_TOKEN', 'DAGGER_CONFIG', 'DAGGER_CLOUD_AUTH_URL', 'TRACEPARENT',
        'TRACESTATE', 'BAGGAGE', '_EXPERIMENTAL_DAGGER_CACHE_CONFIG',
        '_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG', '_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG',
        '_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT',
    ):
        env.pop(key, None)
env.update(XDG_CONFIG_HOME=str(empty_config), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1')
# Local observers need no proxy and never send authentication headers.
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
rows = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def source_hashes():
    return {name: sha((ws / name).read_bytes()) for name in
            ('dagger.toml', 'input.txt', 'module/main.dang', 'module/dagger.json')}

def lock_state():
    result = []
    for rel in ('dagger.lock', '.dagger/lock', 'module/dagger.lock', 'module/.dagger/lock'):
        path = ws / rel
        item = {'scope_path': rel, 'exists': path.is_file()}
        if path.is_file():
            data = path.read_bytes()
            selected = []
            entry_count = 0
            for line in data.decode().splitlines():
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                entry = json.loads(line)
                if isinstance(entry, list) and len(entry) >= 4 and isinstance(entry[0], str):
                    entry_count += 1
                    if entry[1] == 'oci-sha' and isinstance(entry[2], list) and any(
                        isinstance(value, str) and 'busybox' in value for value in entry[2]
                    ):
                        selected.append({'namespace': entry[0], 'operation': entry[1],
                                         'inputs': entry[2], 'digest': entry[3]})
            item.update(bytes=len(data), sha256=sha(data), total_entries=entry_count,
                        busybox_oci_entries=selected)
        result.append(item)
    return result

def dump(path):
    try:
        with http.open('http://127.0.0.1:6172/debug/wcprof/dump?flush=true', timeout=20) as response:
            path.write_bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code != 503:
            raise

def port_is_closed():
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.1):
            return False
    except OSError:
        return True

def run(label, service=False, profile=False):
    dest = out / label
    dest.mkdir(parents=True)
    if service:
        assert port_is_closed(), 'fixture port already has a listener'
    command = [str(args.cli), '--engine', 'container://' + engine]
    if profile:
        dump(dest / 'prior.wcprof')
        command += ['--profile']
    command += ['up', 'web'] if service else finite
    locks_before = lock_state()
    exit_observation = {}
    finished = threading.Event()
    ready = stop = None
    with (dest / 'stdout.txt').open('wb') as stdout, (dest / 'stderr.txt').open('wb') as stderr:
        wall_start = time.time_ns()
        start = time.monotonic()
        process = subprocess.Popen(command, cwd=ws, env=env, stdout=stdout, stderr=stderr, start_new_session=True)

        def observe_exit():
            exit_observation['status'] = process.wait()
            exit_observation['monotonic'] = time.monotonic()
            exit_observation['unix_ns'] = time.time_ns()
            finished.set()

        observer = threading.Thread(target=observe_exit, daemon=True)
        observer.start()
        try:
            if service:
                deadline = start + 90
                while time.monotonic() < deadline:
                    if finished.is_set():
                        raise RuntimeError('up exited before readiness: ' + (dest / 'stderr.txt').read_text()[-2000:])
                    try:
                        with http.open(f'http://127.0.0.1:{port}/', timeout=.1) as response:
                            body = response.read()
                        if body == expected_body:
                            ready = time.monotonic()
                            break
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        pass
                    time.sleep(.005)
                if ready is None:
                    raise TimeoutError('HTTP body readiness timeout')
                stop = time.monotonic()
                process.send_signal(signal.SIGINT)
            if not finished.wait(90):
                raise TimeoutError('CLI exit timeout')
        finally:
            if not finished.is_set():
                try:
                    process.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
                if not finished.wait(10):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if not finished.wait(10):
                        raise RuntimeError('CLI failed to exit after kill')
            observer.join(timeout=5)
    status = exit_observation['status']
    stdout_data = (dest / 'stdout.txt').read_bytes()
    if service:
        assert ready is not None and stop is not None and status in (0, 2), (label, status)
        deadline = time.monotonic() + 3
        while not port_is_closed():
            if time.monotonic() > deadline:
                raise RuntimeError('up left its listening tunnel after exit')
            time.sleep(.02)
    else:
        assert status == 0, (label, status, (dest / 'stderr.txt').read_text()[-2000:])
        image_ref = stdout_data.decode().strip()
        assert re.fullmatch(r'(?:docker\.io/library/)?busybox(?::1\.37)?@sha256:[0-9a-f]{64}', image_ref), image_ref
    row = {
        'variant': 'production', 'flow': 'up' if service else 'image-ref', 'label': label,
        'command': command, 'profile': profile, 'correct': True, 'exit_code': status,
        'seconds': exit_observation['monotonic'] - start,
        'started_unix_ns': wall_start, 'exited_unix_ns': exit_observation['unix_ns'],
        'stdout_bytes': len(stdout_data), 'stdout_sha256': sha(stdout_data),
        'locks_before': locks_before, 'locks_after': lock_state(),
        'telemetry_mode': 'local only: empty credentials, no Cloud/OTLP exporters or analytics',
        'exit_observation': 'dedicated blocking waitpid thread; includes observer scheduling',
    }
    if service:
        row.update(http_ready_seconds=ready - start,
                   cancel_to_exit_seconds=exit_observation['monotonic'] - stop,
                   readiness_poll_interval_ms=5, readiness_request_timeout_ms=100,
                   expected_http_bytes=len(expected_body), expected_http_sha256=sha(expected_body),
                   tunnel_closed_after_exit=True)
    else:
        row['resolved_image_ref'] = image_ref
    if profile:
        dump(dest / 'run.wcprof')
    rows.append(row)
    (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(row), flush=True)

original = source_hashes()
(out / 'provenance.json').write_text(json.dumps({
    'engine': engine, 'cli': str(args.cli), 'cli_sha256': sha(args.cli.read_bytes()),
    'workspace': str(ws), 'port': port, 'source_sha256': original,
    'driver_sha256': sha(Path(__file__).read_bytes()), 'lock_state_before': lock_state(),
    'boundary': 'same completed v3 fixture, retained engine; finite root lookup then repeated service readiness; no cold claim or manual digest pin',
    'telemetry_mode': 'local only: empty credentials, no Cloud/OTLP exporters or analytics',
}, indent=2) + '\n')
try:
    run('finite/core-image-ref')
    for iteration in range(args.repeats):
        run(f'repeated/up-{iteration}', service=True)
    run('profile/up', service=True, profile=True)
finally:
    final = source_hashes()
    (out / 'preserved-inputs.json').write_text(json.dumps({
        'unchanged': final == original, 'before': original, 'after': final,
        'lock_state_after': lock_state(),
    }, indent=2) + '\n')
    assert final == original, 'fixture source/config/input changed during diagnostic'
