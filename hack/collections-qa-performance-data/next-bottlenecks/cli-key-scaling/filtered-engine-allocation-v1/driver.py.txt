"""Prepared local-only filtered-listing follow-up; no execution without --run.

Separate engine allocation and CPU diagnosis, using one unchanged production
CLI. Existing workspace, credentials isolation, GC settings, and engine stay fixed.
"""
from pathlib import Path
import argparse
import hashlib
import http.client
import json
import os
import resource
import signal
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request

LAB = Path(__file__).resolve().parent
PRIOR = LAB / 'ux-local-production-v2'
ENGINE = 'dagger-engine.collections-disk-abba-2'
ENGINE_ID = 'e7457765f81a0dde504642bdd20304d48f045d995853e3dcdd2a5c3f85ad3abc'
ENGINE_SHA = 'a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5'
OPERATION = ['check', '-l', '--all', 'go/modules/tests/run', '--go-module=.', '--go-test=TestFormatResponse']

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', action='store_true')
parser.add_argument('--trial', default='filtered-engine-allocation-v1')
parser.add_argument('--commands', type=int, default=8)
args = parser.parse_args()
assert 1 <= args.commands <= 10
args.identical_bin = True
args.memstats = True
plan = {'mode': 'local-only; Cloud/OTLP/analytics disabled', 'cli_commands': args.commands,
        'warmups': 0, 'main_benchmark': False, 'identical_binary_labels': True, 'memstats': True,
        'operation': OPERATION, 'workspace': str(PRIOR / 'greetings'), 'engine': ENGINE,
        'diagnostic_profiles': '5 second idle CPU, 35 second loop CPU; allocation snapshots before/after each block',
        'profile_policy': 'no gc query parameter, no /debug/gc, no GC/environment setting changes; raw profiles private'}
if not args.run:
    print(json.dumps({'status': 'prepared, not run', **plan}, indent=2))
    raise SystemExit()
assert '/' not in args.trial and args.trial not in ('', '.', '..')
out = LAB / args.trial
out.mkdir(mode=0o700, exist_ok=False)
os.umask(0o077)
private = out / 'private'
private.mkdir(mode=0o700)
(out / 'driver.py.txt').write_bytes(Path(__file__).read_bytes())
prior = json.loads((PRIOR / 'provenance.json').read_text())
app = PRIOR / 'greetings'
config = PRIOR / 'empty-config'
assert app.is_dir() and config.is_dir()
assert not (config / 'dagger' / 'credentials.json').exists()
assert not (config / 'dagger' / 'config.toml').exists()
clis = dict(prior['selected_cli_paths'])
if args.identical_bin:
    clis = {label: prior['selected_cli_paths']['candidate'] for label in ('baseline', 'candidate')}


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_hashes():
    names = ['main.go', 'main_test.go', 'dagger.toml', 'dagger.lock']
    return {name: sha_file(app / name) for name in names if (app / name).is_file()}


source_before = source_hashes()
for name, want in prior['source_hashes'].items():
    assert source_before[name] == want, ('workspace was not restored', name)
binary_hashes = {key: sha_file(path) for key, path in clis.items()}
wanted_hashes = ({label: prior['selected_cli_sha256']['candidate'] for label in clis}
                 if args.identical_bin else prior['selected_cli_sha256'])
assert binary_hashes == wanted_hashes, 'the previous trial binaries changed'
# Read-only inspection: retain only selected public configuration fields, never env.
inspect = json.loads(subprocess.check_output(['docker', 'inspect', ENGINE], text=True))[0]
assert inspect['Id'] == ENGINE_ID and inspect['State']['Running']
engine_binary = subprocess.check_output(['docker', 'exec', ENGINE, 'sha256sum', '/usr/local/bin/dagger-engine'], text=True).split()[0]
assert engine_binary == ENGINE_SHA, 'frozen engine binary changed'
engine_info = {'name': ENGINE, 'id': inspect['Id'], 'image_id': inspect['Image'], 'sha256': engine_binary}
pid = inspect['State']['Pid']
cgroup = Path('/sys/fs/cgroup') / Path('/proc', str(pid), 'cgroup').read_text().split('::')[1].strip().lstrip('/')
if cgroup.name == 'init':
    cgroup = cgroup.parent
expected = (PRIOR / 'warmup' / 'filtered-checks-baseline' / 'stdout.txt').read_bytes()
assert len(expected.splitlines()) == 1 and b'TestFormatResponse' in expected
assert expected == (PRIOR / 'warmup' / 'filtered-checks-candidate' / 'stdout.txt').read_bytes()

# This is the independently source-audited local-only environment, not a redirect.
env = dict(os.environ)
for key in list(env):
    if key.startswith(('OTEL_', 'DAGGER_SESSION_', 'DAGGER_CLOUD_')) or key in (
        'DAGGER_CONFIG', 'TRACEPARENT', 'TRACESTATE', 'BAGGAGE', 'SSH_AUTH_SOCK',
        'CPUPROFILE', 'DAGGER_PERF_TIMELINE', '_DAGGER_CLI_TIMING_DIAG',
        '_EXPERIMENTAL_DAGGER_CACHE_CONFIG', '_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG',
        '_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG', '_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT'):
        env.pop(key, None)
env.update(XDG_CONFIG_HOME=str(config), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1')


def psi(path):
    return {line.split()[0]: int(line.rsplit('=', 1)[1]) for line in path.read_text().splitlines()}


def kv(path):
    return {line.split()[0]: int(line.split()[1]) for line in path.read_text().splitlines()}


def engine_memstats():
    # expvar includes unrelated fields such as cmdline; never persist the raw
    # response. Only this fixed numeric MemStats allowlist is retained.
    start = time.monotonic()
    with urllib.request.urlopen('http://127.0.0.1:6172/debug/vars', timeout=10) as response:
        document = json.load(response)
    mem = document['memstats']
    names = ('NumGC', 'NumForcedGC', 'TotalAlloc', 'Mallocs', 'Frees', 'HeapAlloc',
             'HeapInuse', 'HeapObjects', 'NextGC', 'PauseTotalNs', 'GCCPUFraction', 'LastGC')
    retained = {name: mem[name] for name in names}
    assert all(isinstance(value, (int, float)) for value in retained.values())
    return {'values': retained, 'read_seconds': time.monotonic() - start}


def snapshot():
    # These reads are outside the CLI wall interval; no sampling thread competes
    # with the measured command. Counters help separate host pressure from work.
    memory = kv(Path('/proc/meminfo'))
    result = {
        'host_psi_us': {k: psi(Path('/proc/pressure') / k) for k in ('io', 'cpu', 'memory')},
        'engine_psi_us': {k: psi(cgroup / (k + '.pressure')) for k in ('io', 'cpu', 'memory')},
        'engine_cpu': kv(cgroup / 'cpu.stat'),
        'engine_memory_events': kv(cgroup / 'memory.events'),
        'engine_io': {line.split()[0]: {k: int(v) for k, v in (part.split('=') for part in line.split()[1:])}
                      for line in (cgroup / 'io.stat').read_text().splitlines()},
        'host_dirty_kib': memory['Dirty:'], 'host_writeback_kib': memory['Writeback:'],
    }
    if args.memstats:
        result['engine_memstats'] = engine_memstats()
    return result


def dump(path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:6172/debug/wcprof/dump?flush=true', timeout=20) as response:
            path.write_bytes(response.read())
    except urllib.error.HTTPError as err:
        if err.code != 503:
            raise


rows = []
(out / 'provenance.json').write_text(json.dumps({**plan, 'engine_proof': engine_info,
    'prior_trial': str(PRIOR), 'selected_cli_paths': clis, 'selected_cli_sha256': binary_hashes,
    'source_before': source_before, 'empty_config_reused': str(config),
    'driver_sha256': sha_file(__file__), 'expected_stdout_sha256': hashlib.sha256(expected).hexdigest(),
    'measurement': 'diagnostic commands under engine CPU sampling; spawn through blocking waitpid; do not combine with unprofiled timings',
    'profile_boundary': 'separate process-wide engine CPU and sampled allocation profiles; raw profiles remain private',
}, indent=2) + '\n')


def run(variant, phase, index, position, profile=False):
    label = f'{phase}/{index:02d}-{position}-{variant}'
    dest = out / label
    dest.mkdir(parents=True, exist_ok=False)
    cmd = [clis[variant], '--engine', 'container://' + ENGINE] + (['--profile'] if profile else []) + OPERATION
    run_env = dict(env)
    if profile:
        dump(dest / 'prior.wcprof')
        run_env['CPUPROFILE'] = str(dest / 'cli.cpu')
    before = snapshot()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    stdout_parts, stderr_parts = [], []
    finished = threading.Event()
    observed = {}
    wall_start = time.time_ns()
    start = time.monotonic()
    process = subprocess.Popen(cmd, cwd=app, env=run_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

    def read_pipe(pipe, parts):
        try:
            parts.append(pipe.read())
        finally:
            pipe.close()

    def observe_exit():
        observed['status'] = process.wait()
        observed['monotonic'] = time.monotonic()
        observed['unix_ns'] = time.time_ns()
        finished.set()

    readers = [threading.Thread(target=read_pipe, args=(process.stdout, stdout_parts), daemon=True),
               threading.Thread(target=read_pipe, args=(process.stderr, stderr_parts), daemon=True)]
    observer = threading.Thread(target=observe_exit, daemon=True)
    observer.start()
    for reader in readers:
        reader.start()
    try:
        if not finished.wait(120):
            raise TimeoutError(label + ': CLI did not exit')
    finally:
        if not finished.is_set():
            process.send_signal(signal.SIGINT)
            if not finished.wait(10):
                os.killpg(process.pid, signal.SIGKILL)
                assert finished.wait(10), 'owned CLI did not terminate'
        observer.join()
        for reader in readers:
            reader.join(timeout=5)
            assert not reader.is_alive(), 'stdout/stderr inherited beyond CLI lifetime'
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    after = snapshot()
    stdout, stderr = b''.join(stdout_parts), b''.join(stderr_parts)
    (dest / 'stdout.txt').write_bytes(stdout)
    (dest / 'stderr.txt').write_bytes(stderr)
    assert observed['status'] == 0, (label, observed['status'], stderr[-2000:].decode(errors='replace'))
    assert stdout == expected, (label, 'exact filtered listing mismatch')
    row = {'variant': variant, 'flow': 'filtered-checks', 'phase': phase, 'index': index,
           'pair_position': position, 'label': label, 'profile': profile,
           'seconds': observed['monotonic'] - start, 'started_unix_ns': wall_start,
           'exited_unix_ns': observed['unix_ns'], 'exit_code': observed['status'], 'correct': True,
           'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'command': cmd,
           'user_cpu_seconds': usage_after.ru_utime - usage_before.ru_utime,
           'system_cpu_seconds': usage_after.ru_stime - usage_before.ru_stime,
           'minor_faults': usage_after.ru_minflt - usage_before.ru_minflt,
           'major_faults': usage_after.ru_majflt - usage_before.ru_majflt,
           'voluntary_context_switches': usage_after.ru_nvcsw - usage_before.ru_nvcsw,
           'involuntary_context_switches': usage_after.ru_nivcsw - usage_before.ru_nivcsw,
           'before': before, 'after': after, 'telemetry_mode': 'local-only',
           'exit_observation': 'dedicated blocking waitpid thread; includes observer scheduling'}
    rows.append(row)
    (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({k: row[k] for k in ('label', 'seconds', 'profile', 'user_cpu_seconds', 'system_cpu_seconds', 'correct')}), flush=True)
    if profile:
        dump(dest / 'run.wcprof')



def allocation_profile(name):
    # The allocs endpoint does not request or force a GC. These samples can lag
    # completed allocations by two GC cycles; TotalAlloc supplies exact totals.
    target = private / (name + '.allocs.pprof')
    started = time.time_ns()
    with urllib.request.urlopen('http://127.0.0.1:6172/debug/pprof/allocs', timeout=30) as response:
        data = response.read()
    target.write_bytes(data)
    return {'path': str(target), 'started_unix_ns': started, 'finished_unix_ns': time.time_ns(),
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def cpu_profile(name, seconds):
    # HTTP request-send acknowledgement is not a server start acknowledgement.
    # Record it honestly; profile embedded timestamps determine final coverage.
    state = {'requested_seconds': seconds, 'request_launched_unix_ns': time.time_ns()}
    sent = threading.Event()
    def capture():
        connection = http.client.HTTPConnection('127.0.0.1', 6172, timeout=seconds + 20)
        try:
            connection.request('GET', '/debug/pprof/profile?seconds=' + str(seconds))
            state['request_sent_unix_ns'] = time.time_ns()
            sent.set()
            response = connection.getresponse()
            data = response.read()
            assert response.status == 200, ('CPU profile response', response.status)
            target = private / (name + '.cpu.pprof')
            target.write_bytes(data)
            state.update(path=str(target), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        except BaseException as error:
            state['error'] = repr(error)
            sent.set()
        finally:
            state['finished_unix_ns'] = time.time_ns()
            connection.close()
    thread = threading.Thread(target=capture, daemon=True)
    thread.start()
    assert sent.wait(10), 'CPU profile request not sent'
    assert 'error' not in state, state.get('error')
    return thread, state


profiles = {}
try:
    profiles['idle_before_counters'] = snapshot()
    profiles['idle_before_allocations'] = allocation_profile('idle-before')
    thread, state = cpu_profile('idle', 5)
    thread.join(timeout=30)
    assert not thread.is_alive() and 'error' not in state, state
    profiles['idle_cpu'] = state
    profiles['idle_after_allocations'] = allocation_profile('idle-after')
    profiles['idle_after_counters'] = snapshot()
    (out / 'profile-metadata.json').write_text(json.dumps(profiles, indent=2) + '\n')

    profiles['loop_before_counters'] = snapshot()
    profiles['loop_before_allocations'] = allocation_profile('loop-before')
    thread, state = cpu_profile('loop', 35)
    # Leave a short setup margin outside command timing. This is not a claim
    # that HTTP delivery guarantees the server profiler has already started.
    time.sleep(0.25)
    for index in range(args.commands):
        run('candidate', 'diagnostic', index, 0)
    profiles['loop_after_commands_counters'] = snapshot()
    profiles['loop_after_commands_allocations'] = allocation_profile('loop-after-commands')
    thread.join(timeout=55)
    assert not thread.is_alive() and 'error' not in state, state
    profiles['loop_cpu'] = state
    profiles['loop_after_profile_allocations'] = allocation_profile('loop-after-profile')
    profiles['loop_after_profile_counters'] = snapshot()
finally:
    if 'thread' in globals() and thread.is_alive():
        thread.join(timeout=55)
        assert not thread.is_alive(), 'owned CPU capture did not finish'
    (out / 'profile-metadata.json').write_text(json.dumps(profiles, indent=2) + '\n')
    source_after = source_hashes()
    (out / 'source-verification.json').write_text(json.dumps({'before': source_before, 'after': source_after,
        'unchanged': source_before == source_after}, indent=2) + '\n')
    assert source_before == source_after, 'the reused application source changed'
    summary = {'cli_commands': len(rows), 'correct_outputs': sum(row['correct'] for row in rows),
        'main_benchmark': False, 'diagnostic_only': True,
        'all_forced_gc_deltas_zero': all(row['after']['engine_memstats']['values']['NumForcedGC'] ==
            row['before']['engine_memstats']['values']['NumForcedGC'] for row in rows),
        'allocation_profile_caveat': 'sampled process-wide stacks can lag by up to two GC cycles',
        'profile_coverage': 'verify embedded TimeNanos/DurationNanos before attributing the loop CPU profile'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
