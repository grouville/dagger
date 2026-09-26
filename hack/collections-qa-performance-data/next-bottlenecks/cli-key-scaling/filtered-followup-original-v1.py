"""Prepared local-only filtered-listing follow-up; no execution without --run.

Eight alternating pairs, two excluded warmups, and one separate diagnostic
capture per CLI. Existing workspace, credentials isolation, and engine stay fixed.
"""
from pathlib import Path
import argparse
import hashlib
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
parser.add_argument('--trial', default='filtered-followup-v1')
args = parser.parse_args()
plan = {'mode': 'local-only; Cloud/OTLP/analytics disabled', 'cli_commands': 20,
        'warmups': 2, 'measured_alternating_pairs': 8, 'separate_profiled_commands': 2,
        'operation': OPERATION, 'workspace': str(PRIOR / 'greetings'), 'engine': ENGINE}
if not args.run:
    print(json.dumps({'status': 'prepared, not run', **plan}, indent=2))
    raise SystemExit()
assert '/' not in args.trial and args.trial not in ('', '.', '..')
out = LAB / args.trial
out.mkdir(exist_ok=False)
(out / 'driver.py.txt').write_bytes(Path(__file__).read_bytes())
prior = json.loads((PRIOR / 'provenance.json').read_text())
app = PRIOR / 'greetings'
config = PRIOR / 'empty-config'
assert app.is_dir() and config.is_dir()
assert not (config / 'dagger' / 'credentials.json').exists()
assert not (config / 'dagger' / 'config.toml').exists()
clis = prior['selected_cli_paths']


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
assert binary_hashes == prior['selected_cli_sha256'], 'the previous trial binaries changed'
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


def snapshot():
    # These reads are outside the CLI wall interval; no sampling thread competes
    # with the measured command. Counters help separate host pressure from work.
    memory = kv(Path('/proc/meminfo'))
    return {
        'host_psi_us': {k: psi(Path('/proc/pressure') / k) for k in ('io', 'cpu', 'memory')},
        'engine_psi_us': {k: psi(cgroup / (k + '.pressure')) for k in ('io', 'cpu', 'memory')},
        'engine_cpu': kv(cgroup / 'cpu.stat'),
        'engine_memory_events': kv(cgroup / 'memory.events'),
        'engine_io': {line.split()[0]: {k: int(v) for k, v in (part.split('=') for part in line.split()[1:])}
                      for line in (cgroup / 'io.stat').read_text().splitlines()},
        'host_dirty_kib': memory['Dirty:'], 'host_writeback_kib': memory['Writeback:'],
    }


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
    'measurement': 'new CLI spawn through blocking waitpid observation; no profiler on measured pairs; outputs persisted after exit',
    'profile_boundary': 'separate --profile plus CLI CPUPROFILE/runtime trace; their wall times excluded from comparison',
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


try:
    for position, variant in enumerate(('baseline', 'candidate')):
        run(variant, 'warmup', 0, position)
    for index in range(8):
        order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
        for position, variant in enumerate(order):
            run(variant, 'warm', index, position)
    for position, variant in enumerate(('candidate', 'baseline')):
        run(variant, 'profile', 0, position, profile=True)
finally:
    source_after = source_hashes()
    (out / 'source-verification.json').write_text(json.dumps({'before': source_before, 'after': source_after,
        'unchanged': source_before == source_after}, indent=2) + '\n')
    assert source_before == source_after, 'the reused application source changed'
summary = {'cli_commands': len(rows), 'correct_outputs': sum(row['correct'] for row in rows),
           'metric': 'CLI exit seconds; unprofiled warm pairs only', 'variants': {}, 'pairs': []}
for variant in clis:
    selected = [r for r in rows if r['phase'] == 'warm' and r['variant'] == variant]
    summary['variants'][variant] = {'samples': [r['seconds'] for r in selected],
        'median_seconds': statistics.median(r['seconds'] for r in selected),
        'median_cpu_seconds': statistics.median(r['user_cpu_seconds'] + r['system_cpu_seconds'] for r in selected)}
for index in range(8):
    selected = [r for r in rows if r['phase'] == 'warm' and r['index'] == index]
    by_variant = {r['variant']: r for r in selected}
    summary['pairs'].append({'index': index, 'order': [r['variant'] for r in selected],
        'baseline_seconds': by_variant['baseline']['seconds'], 'candidate_seconds': by_variant['candidate']['seconds'],
        'candidate_minus_baseline_seconds': by_variant['candidate']['seconds'] - by_variant['baseline']['seconds']})
summary['median_paired_delta_seconds'] = statistics.median(r['candidate_minus_baseline_seconds'] for r in summary['pairs'])
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
