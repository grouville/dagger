"""Prepared local-only service lifetime A/B; run only with the runtime slot.

Two fresh Git fixtures, ordinary tag, no initial lock. Fourteen unprofiled
commands: first up, three warm reruns, three distinct real input edits for each CLI.
Two subsequent profiled runs are diagnostics outside the timing series.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
import tomllib
import urllib.error
import urllib.request

lab = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--run', action='store_true')
p.add_argument('--workspace', type=Path, default=lab / 'vertical-local-disk-v3/workspace')
p.add_argument('--baseline-cli', type=Path, default=Path('/tmp/collections-perf/sparse-export/production/dagger-production'))
p.add_argument('--candidate-cli', type=Path, default=Path('/tmp/collections-perf/attachables-lifetime/dagger-attachables'))
p.add_argument('--trial', default='service-lifetime-ab-v1')
args = p.parse_args()
assert '/' not in args.trial and args.trial not in ('', '.', '..')
clis = {'baseline': args.baseline_cli, 'candidate': args.candidate_cli}
plan = [('first/' + v, v, 'warm\n', False) for v in clis]
for phase in ('warm', 'edit'):
    for i in range(3):
        for variant in (('baseline', 'candidate') if i % 2 == 0 else ('candidate', 'baseline')):
            marker = 'warm\n' if phase == 'warm' else f'edited-{i}-{variant[0]}\n'
            plan.append((f'{phase}/{i}-{variant}', variant, marker, False))
plan += [(f'profile/{v}', v, 'profile\n', True) for v in clis]
if not args.run:
    print(json.dumps({'status': 'prepared, not run', 'command_count': len(plan),
                      'unprofiled_first': 2, 'unprofiled_warm': 6, 'unprofiled_real_edits': 6,
                      'separate_profiles': 2, 'clis': {v: str(p) for v, p in clis.items()},
                      'workspace': str(args.workspace), 'telemetry': 'local only',
                      'mutation': 'two fresh copied Git fixtures; ordinary lock writes, no manual pin'}, indent=2))
    raise SystemExit()

source = args.workspace.resolve()
assert (source.parent / 'summary.json').is_file(), 'requires completed vertical v3 fixture'
inputs = {rel: (source / rel).read_bytes() for rel in
          ('dagger.toml', 'input.txt', 'module/main.dang', 'module/dagger.json')}
config = tomllib.loads(inputs['dagger.toml'].decode())
assert config['modules']['perf-flows'] == {'source': './module', 'entrypoint': True}
assert len(config['ports']) == 1
port_text, mapping = next(iter(config['ports'].items()))
assert mapping == {'backendService': 'web', 'backendPort': 8080}
port = int(port_text)
assert 1024 <= port <= 65535
assert b'.from("busybox:1.37")' in inputs['module/main.dang']
inputs['input.txt'] = b'warm\n'
engine = 'dagger-engine.collections-disk-abba-2'
out = lab / args.trial
out.mkdir(exist_ok=False)
(out / 'driver.py.txt').write_text(Path(__file__).read_text())
empty_config = out / 'empty-config'
empty_config.mkdir(mode=0o700)
env = dict(os.environ)
for key in ('SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE'):
    env.pop(key, None)
for key in list(env):
    if key.startswith(('OTEL_', 'DAGGER_SESSION_', 'DAGGER_CLOUD_')) or key in (
        'DAGGER_CONFIG', 'TRACEPARENT', 'TRACESTATE', 'BAGGAGE',
        '_EXPERIMENTAL_DAGGER_CACHE_CONFIG', '_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG',
        '_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG', '_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT',
    ):
        env.pop(key, None)
env.update(XDG_CONFIG_HOME=str(empty_config), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1')
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
rows = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def hashes(ws):
    return {rel: sha((ws / rel).read_bytes()) for rel in inputs}

def lock_state(ws):
    result = []
    for rel in ('dagger.lock', '.dagger/lock', 'module/dagger.lock', 'module/.dagger/lock'):
        path = ws / rel
        item = {'scope_path': rel, 'exists': path.is_file()}
        if path.is_file():
            data = path.read_bytes()
            entries, selected = 0, []
            for line in data.decode().splitlines():
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                entry = json.loads(line)
                if isinstance(entry, list) and len(entry) >= 4 and isinstance(entry[0], str):
                    entries += 1
                    if entry[1] == 'oci-sha' and isinstance(entry[2], list) and any(
                        isinstance(value, str) and 'busybox' in value for value in entry[2]
                    ):
                        selected.append({'namespace': entry[0], 'operation': entry[1],
                                         'inputs': entry[2], 'digest': entry[3]})
            item.update(bytes=len(data), sha256=sha(data), total_entries=entries,
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

def port_closed():
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.1):
            return False
    except OSError:
        return True

def body_matches(expected_body):
    try:
        with http.open(f'http://127.0.0.1:{port}/', timeout=.1) as response:
            return response.read() == expected_body
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False

workspaces = {}
for variant in clis:
    ws = out / 'workspaces' / variant
    (ws / 'module').mkdir(parents=True)
    for rel, data in inputs.items():
        (ws / rel).write_bytes(data)
    subprocess.run(['git', 'init', '--quiet'], cwd=ws, check=True)
    subprocess.run(['git', 'add', 'dagger.toml', 'input.txt', 'module'], cwd=ws, check=True)
    subprocess.run(['git', '-c', 'user.name=Dagger performance fixture', '-c', 'user.email=perf-fixture@localhost',
                    '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '--quiet',
                    '-m', 'Fresh synthetic service lifetime fixture'], cwd=ws, check=True)
    assert not any(item['exists'] for item in lock_state(ws))
    workspaces[variant] = ws

def run(label, variant, marker, profile):
    dest = out / label
    dest.mkdir(parents=True)
    ws = workspaces[variant]
    expected_body = marker.encode()
    before_input = (ws / 'input.txt').read_bytes()
    if before_input != expected_body:
        (ws / 'input.txt').write_bytes(expected_body)
    alive_seconds = 0
    before = lock_state(ws)
    assert port_closed(), 'fixture port already has a listener'
    if profile:
        dump(dest / 'prior.wcprof')
    command = [str(clis[variant]), '--engine', 'container://' + engine] + (['--profile'] if profile else []) + ['up', 'web']
    finished, observed = threading.Event(), {}
    ready = stop = None
    at_ready = before_cancel = None
    with (dest / 'stdout.txt').open('wb') as stdout, (dest / 'stderr.txt').open('wb') as stderr:
        wall_start, start = time.time_ns(), time.monotonic()
        proc = subprocess.Popen(command, cwd=ws, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        def waiter():
            observed['status'] = proc.wait()
            observed['monotonic'] = time.monotonic()
            observed['unix_ns'] = time.time_ns()
            finished.set()
        thread = threading.Thread(target=waiter, daemon=True)
        thread.start()
        try:
            if alive_seconds is not None:
                deadline = start + 90
                while time.monotonic() < deadline:
                    if finished.is_set():
                        raise RuntimeError('up exited before readiness: ' + (dest / 'stderr.txt').read_text()[-2000:])
                    if body_matches(expected_body):
                        ready = time.monotonic()
                        break
                    time.sleep(.005)
                if ready is None:
                    raise TimeoutError('HTTP readiness timeout')
                at_ready = lock_state(ws)
                if alive_seconds:
                    if finished.wait(alive_seconds):
                        raise RuntimeError('up exited before intentional cancellation')
                    assert body_matches(expected_body), 'service body changed while alive'
                before_cancel = lock_state(ws)
                stop = time.monotonic()
                proc.send_signal(signal.SIGINT)
            if not finished.wait(90):
                raise TimeoutError('CLI exit timeout')
        finally:
            if not finished.is_set():
                try:
                    proc.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
                if not finished.wait(10):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if not finished.wait(10):
                        raise RuntimeError('CLI failed to exit after kill')
            thread.join(timeout=5)
            (dest / 'lock-state-after-cleanup.json').write_text(json.dumps(lock_state(ws), indent=2) + '\n')
    status = observed['status']
    stdout_data = (dest / 'stdout.txt').read_bytes()
    assert status in ((0, 2) if alive_seconds is not None else (0,)), (label, status)
    assert ready is not None and stop is not None
    deadline = time.monotonic() + 3
    while not port_closed():
        if time.monotonic() > deadline:
            raise RuntimeError('up left a listening tunnel after exit')
        time.sleep(.02)
    after = lock_state(ws)
    row = {'label': label, 'flow': 'up' if alive_seconds is not None else 'image-ref',
           'variant': variant, 'profile': profile, 'command': command, 'workspace': str(ws),
           'correct': True, 'exit_code': status, 'seconds': observed['monotonic'] - start,
           'started_unix_ns': wall_start, 'exited_unix_ns': observed['unix_ns'],
           'locks_before': before, 'locks_at_http_ready': at_ready,
           'locks_before_cancel': before_cancel, 'locks_after': after,
           'input_changed_before_command': before_input != expected_body, 'source_sha256': hashes(ws),
           'stdout_bytes': len(stdout_data), 'stdout_sha256': sha(stdout_data),
           'exit_observation': 'dedicated thread blocking waitpid; includes observer scheduling'}
    if alive_seconds is not None:
        row.update(http_ready_seconds=ready - start, cancel_to_exit_seconds=observed['monotonic'] - stop,
                   requested_alive_seconds=alive_seconds, actual_alive_seconds=stop - ready,
                   expected_http_bytes=len(expected_body), expected_http_sha256=sha(expected_body),
                   readiness_poll_interval_ms=5, tunnel_closed_after_exit=True)
    assert hashes(ws) == {rel: sha(expected_body if rel == 'input.txt' else data) for rel, data in inputs.items()}
    row['busybox_lock_persisted'] = any(item.get('busybox_oci_entries') for item in after)
    if profile:
        dump(dest / 'run.wcprof')
    rows.append(row)
    (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    if variant == 'candidate':
        assert row['busybox_lock_persisted'], 'candidate did not persist ordinary OCI lock after cancellation'

original_hashes = {rel: sha((source / rel).read_bytes()) for rel in inputs}
original_lock = lock_state(source)
(out / 'provenance.json').write_text(json.dumps({
    'command_count': len(plan), 'engine': engine, 'clis': {v: str(p) for v, p in clis.items()},
    'cli_sha256': {v: sha(p.read_bytes()) for v, p in clis.items()},
    'source_workspace': str(source), 'source_input_sha256': original_hashes,
    'case_input_sha256': {rel: sha(data) for rel, data in inputs.items()},
    'driver_sha256': sha(Path(__file__).read_bytes()), 'port': port,
    'telemetry_mode': 'local only: empty credentials, no Cloud/OTLP exporters or analytics',
    'boundary': 'retained engine with warm image; initial workspace lock empty; fourteen unprofiled new CLI commands and two separate profiles; not cold engine/image claims',
    'same_for_all_cases': 'same module bytes, image tag, config, equal-length distinct edit markers and engine; separate Git roots/lock states; CLI differs only by attachables lifetime fix',
    'edit_order': 'B/C, C/B, B/C within warm and edit phases; unique equal-length edit bytes per variant; each edit is immediately followed by up',
}, indent=2) + '\n')
try:
    for case in plan:
        run(*case)
    import statistics
    summary = []
    for phase in ('first', 'warm', 'edit'):
        row = {'phase': phase}
        for variant in clis:
            selected = [r for r in rows if r['label'].startswith(phase + '/') and r['variant'] == variant]
            row[variant] = {metric: {'samples': [r[metric] for r in selected],
                                    'median': statistics.median(r[metric] for r in selected)}
                            for metric in ('http_ready_seconds', 'seconds', 'cancel_to_exit_seconds')}
            row[variant]['locks_persisted'] = sum(r['busybox_lock_persisted'] for r in selected)
        summary.append(row)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
finally:
    final = {rel: sha((source / rel).read_bytes()) for rel in inputs}
    (out / 'source-preserved.json').write_text(json.dumps({
        'unchanged': final == original_hashes and lock_state(source) == original_lock,
        'source_before': original_hashes, 'source_after': final,
        'lock_before': original_lock, 'lock_after': lock_state(source)}, indent=2) + '\n')
    assert final == original_hashes and lock_state(source) == original_lock
