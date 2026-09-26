"""Twelve bounded production-Cloud listing calls, only with explicit --run.

Five ordinary alternating warm pairs precede one separate profiled pair. Engines,
workspace bytes, normal login and listing UX stay unchanged; no extra auth smoke,
warmup, edit, engine start/stop or retry is performed. Raw outputs stay private.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import threading
import time

import experiment as x

LAB = Path(__file__).resolve().parent
OUT = LAB / 'withfile-cloud-warm-v1'
FLOW = x.FLOWS['expanded']
LIMIT = 12


def snapshot(item):
    info = x.owned(item)
    assert info['State']['Running'], 'owned engine must already be running'
    pid = info['State']['Pid']
    groups = [line[3:] for line in Path('/proc', str(pid), 'cgroup').read_text().splitlines() if line.startswith('0::')]
    assert len(groups) == 1, 'cgroup v2 required'
    group = Path('/sys/fs/cgroup') / groups[0].lstrip('/')
    if group.name == 'init':
        group = group.parent
    cpu = {parts[0]: int(parts[1]) for line in (group / 'cpu.stat').read_text().splitlines() if (parts := line.split())}
    io = {parts[0]: {k: int(v) for k, v in (pair.split('=', 1) for pair in parts[1:])} for line in (group / 'io.stat').read_text().splitlines() if (parts := line.split())}
    psi = {kind: {parts[0]: int(parts[-1].split('=', 1)[1]) for line in Path('/proc/pressure', kind).read_text().splitlines() if (parts := line.split())} for kind in ('cpu', 'io', 'memory')}
    return {'sampled_monotonic_ns': time.monotonic_ns(), 'sampled_unix_ns': time.time_ns(), 'engine_cpu': cpu, 'engine_io': io, 'host_psi_total_us': psi, 'free_disk_bytes': shutil.disk_usage(LAB).free}


def delta(before, after):
    io = {device: {key: value - before['engine_io'].get(device, {}).get(key, 0) for key, value in fields.items()} for device, fields in after['engine_io'].items()}
    return {
        'engine_cpu_seconds': (after['engine_cpu']['usage_usec'] - before['engine_cpu']['usage_usec']) / 1e6,
        'engine_io_delta': io,
        'engine_written_bytes': sum(fields.get('wbytes', 0) for fields in io.values()),
        'host_psi_delta_us': {kind: {level: total - before['host_psi_total_us'][kind][level] for level, total in totals.items()} for kind, totals in after['host_psi_total_us'].items()},
        'counter_bracket_seconds': (after['sampled_monotonic_ns'] - before['sampled_monotonic_ns']) / 1e9,
    }


def normalized_rows(contents):
    return sorted(tuple(part.strip() for part in line.split(b'#', 1)) for line in contents.splitlines() if line.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'execute': False, 'commands_max': LIMIT, 'ordinary_warm_pairs': 5, 'separate_profiled_pairs': 1, 'cloud_endpoint': 'https://api.dagger.cloud', 'fixture_edits': 0, 'engine_mutations': 0, 'output': str(OUT)}))
        return

    os.umask(0o077)
    assert not OUT.exists(), 'never resume or overwrite a partial trial'
    state = json.loads((LAB / 'withfile-v1/prepared.json').read_text())
    assert (LAB / 'withfile-v1/summary.json').is_file(), 'local correctness prerequisite missing'
    assert (LAB / 'withfile-cloud-v1/summary.json').is_file(), 'previous Cloud series must be complete'
    previous = json.loads((LAB / 'withfile-cloud-v1/results.json').read_text())
    auth = [row for row in previous if row['phase'] == 'auth-control']
    assert len(auth) == 1 and auth[0]['correct'] and auth[0]['cloud_link_visible'], 'previous normal-login control missing'
    assert len(previous) == 17 and all(row.get('correct') for row in previous)
    app = LAB / 'greetings'
    assert x.fixture_hashes(app) == state['input_sha256'], 'full original fixture must be restored'
    assert x.sha(x.CLI) == state['cli_sha256'], 'CLI changed'
    assert shutil.disk_usage(LAB).free > 16 * 1024**3, 'free-space floor reached'
    for variant in ('base', 'candidate'):
        item = state[variant]
        info = x.owned(item)
        assert info['State']['Running'], 'no engine lifecycle changes permitted by this driver'
        actual = x.capture(['docker', 'exec', item['name'], 'sha256sum', '/usr/local/bin/dagger-engine']).split()[0]
        assert actual == item['sha256'], 'engine binary changed'

    OUT.mkdir(mode=0o700)
    (OUT / 'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    (OUT / 'experiment.py.txt').write_bytes((LAB / 'experiment.py').read_bytes())
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'DAGGER_CLOUD_TOKEN', 'XDG_CONFIG_HOME') if key in os.environ}
    env.update(DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0', DAGGER_CLOUD_URL='https://api.dagger.cloud')
    orders = [('base', 'candidate') if index % 2 == 0 else ('candidate', 'base') for index in range(6)]
    x.write(OUT / 'provenance.json', {
        'state': state, 'flow': FLOW, 'commands_max': LIMIT,
        'endpoint': 'https://api.dagger.cloud',
        'authorization': 'bounded continuation under prior approved Cloud matrix; parent owns cumulative command budget',
        'authentication': 'same allowlisted normal login environment as completed withfile-cloud.py; harness does not read or print credentials; prior core auth control verified normal Cloud link',
        'auth_control_source': str(LAB / 'withfile-cloud-v1/results.json'),
        'auth_control_results_sha256': x.sha(LAB / 'withfile-cloud-v1/results.json'),
        'listing_cloud_link': 'informational only; normal listing does not request a printed trace URL; absence is not an auth failure',
        'driver_sha256': x.sha(__file__), 'experiment_sha256': x.sha(LAB / 'experiment.py'),
        'pairs': [{'index': index, 'order': list(order), 'profile': index == 5} for index, order in enumerate(orders)],
        'cache_boundary': 'original fixture bytes throughout; retained warm engines with unequal prior history; no extra warming, invalidation, image/cache reset, forced GC or cold claim',
        'cli_boundary': 'fresh Popen through blocking waitpid; validation, cgroup/PSI snapshots and wcprof dumps outside timer; only final separate pair enables --profile',
        'counter_boundary': 'numeric engine process/cgroup and host PSI snapshots slightly bracket CLI timer; counters include background work and do not attribute latency to Cloud',
        'profile_boundary': 'prior wcprof flushed before final pair; new dump after CLI exit; one diagnostic pair is excluded from ordinary medians; correlate CLI wall timestamps with engine query span boundaries before interpreting exit tail',
        'inter_command_pause_seconds': 1,
        'privacy': 'raw stdout, stderr and profiles remain in this private task directory; no raw trace publication',
    })
    rows = []
    attempted = []
    expected = normalized_rows(x.WANT)
    assert len(expected) == 14

    def run(variant, index):
        profile = index == 5
        assert len(attempted) < LIMIT
        assert shutil.disk_usage(LAB).free > 16 * 1024**3, 'free-space floor reached'
        assert x.fixture_hashes(app) == state['input_sha256'], 'source changed before command'
        item = state[variant]
        dest = OUT / f'{"profile" if profile else "warm"}-{index}-{variant}'
        dest.mkdir()
        if profile:
            try:
                (dest / 'prior.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
            except x.HTTPError as error:
                if error.code != 503:
                    raise
        command = [str(x.CLI), '--engine', 'container://' + item['name']] + (['--profile'] if profile else []) + FLOW
        attempt = {'variant': variant, 'pair_index': index, 'profile': profile, 'command': command}
        attempted.append(attempt)
        x.write(OUT / 'attempts.json', attempted)
        done = threading.Event()
        observed = {}
        before = snapshot(item)
        with (dest / 'stdout.txt').open('wb') as stdout, (dest / 'stderr.txt').open('wb') as stderr:
            begin = time.monotonic()
            wall = time.time_ns()
            process = subprocess.Popen(command, cwd=app, env=env, stdout=stdout, stderr=stderr, start_new_session=True)

            def waiter():
                observed['status'] = process.wait()
                observed['time'] = time.monotonic()
                observed['wall'] = time.time_ns()
                done.set()

            worker = threading.Thread(target=waiter, daemon=True)
            worker.start()
            timed_out = False
            try:
                if not done.wait(240):
                    timed_out = True
            finally:
                if not done.is_set():
                    try:
                        process.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
                    if not done.wait(10):
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                worker.join(timeout=15)
                assert not worker.is_alive(), 'owned CLI did not terminate'
        after = snapshot(item)
        stdout = (dest / 'stdout.txt').read_bytes()
        stderr = (dest / 'stderr.txt').read_bytes()
        text = re.sub(rb'\x1b\[[0-9;]*m', b'', stdout + stderr)
        correct = not timed_out and observed['status'] == 0 and normalized_rows(stdout) == expected
        row = {
            'variant': variant, 'flow': 'expanded', 'pair_index': index, 'profile': profile,
            'seconds': observed['time'] - begin, 'started_unix_ns': wall, 'exited_unix_ns': observed['wall'],
            'exit_code': observed['status'], 'timed_out': timed_out, 'correct': correct,
            'row_count': len(normalized_rows(stdout)), 'stdout_sha256': x.sha(dest / 'stdout.txt'),
            'stderr_bytes': len(stderr), 'cloud_link_visible': bool(re.search(rb'https://[^\s]*dagger.cloud/', text)),
            'possible_export_error_messages': len(re.findall(rb'(?:failed|failure|error)[^\n]{0,80}(?:export|telemetry)|(?:export|telemetry)[^\n]{0,80}(?:failed|failure|error)', text, re.I)),
            'before': before, 'after': after, **delta(before, after),
        }
        rows.append(row)
        x.write(OUT / 'results.json', rows)
        attempt.update(exit_code=observed['status'], timed_out=timed_out, validated=correct)
        x.write(OUT / 'attempts.json', attempted)
        print(json.dumps({key: row[key] for key in ('variant', 'pair_index', 'profile', 'seconds', 'exit_code', 'correct', 'engine_cpu_seconds', 'engine_written_bytes')}), flush=True)
        if profile:
            (dest / 'run.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
        assert correct, ('listing failed or differs from exact 14-row expectation; inspect private output', dest.name)
        assert x.fixture_hashes(app) == state['input_sha256'], 'command changed fixture'
        assert row['engine_written_bytes'] < 32 * 1024**3, 'per-command write bound exceeded'
        time.sleep(1)

    try:
        for index, order in enumerate(orders):
            for variant in order:
                run(variant, index)
    finally:
        unchanged = x.fixture_hashes(app) == state['input_sha256']
        x.write(OUT / 'fixture-validation.json', {'original_fixture_unchanged': unchanged, 'fixture_writes_by_driver': 0, 'commands_attempted': len(attempted), 'commands_validated': sum(row['correct'] for row in rows)})
        assert unchanged, 'fixture changed; driver will not overwrite it'

    assert len(rows) == LIMIT and all(row['correct'] for row in rows)
    pairs = []
    for index in range(6):
        selected = {row['variant']: row for row in rows if row['pair_index'] == index}
        pairs.append({'pair_index': index, 'profile': index == 5, 'order': list(orders[index]), 'base_seconds': selected['base']['seconds'], 'candidate_seconds': selected['candidate']['seconds'], 'candidate_minus_base_seconds': selected['candidate']['seconds'] - selected['base']['seconds']})
    summary = {'commands': LIMIT, 'all_correct': True, 'pairs': pairs, 'ordinary': {}, 'ordinary_paired_delta_median_seconds': statistics.median(pair['candidate_minus_base_seconds'] for pair in pairs if not pair['profile']), 'claim_boundary': 'five additional retained-engine warm pairs plus one separate diagnostic pair; no cold, server-acceptance, network/server-time attribution, or steady-state claim'}
    for variant in ('base', 'candidate'):
        selected = [row for row in rows if row['variant'] == variant and not row['profile']]
        summary['ordinary'][variant] = {'n': len(selected), 'samples_seconds': [row['seconds'] for row in selected], 'median_seconds': statistics.median(row['seconds'] for row in selected), 'median_engine_cpu_seconds': statistics.median(row['engine_cpu_seconds'] for row in selected), 'median_engine_written_bytes': statistics.median(row['engine_written_bytes'] for row in selected)}
    x.write(OUT / 'summary.json', summary)


if __name__ == '__main__':
    main()
