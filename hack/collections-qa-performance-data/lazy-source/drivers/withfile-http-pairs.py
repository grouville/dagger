"""Four local-only strict HTTP checks on retained, hash-verified engines.

Pair 0 is ordinary (base then candidate). Pair 1 reverses order and is profiled.
Each pair gets novel response-header bytes, identical for both variants. This
is an edited execution diagnosis, not a matched cold-start measurement.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time

import experiment as x

LAB = Path(__file__).resolve().parent
OUT = LAB / 'withfile-http-v1'
FLOW = ['check', '--generated=false', 'go/modules/tests/run', '--go-module=.', '--go-test=TestE2ERandomGreeting']


def snapshot(item):
    """Numeric counters only; no expvar allocation or telemetry payload dump."""
    info = x.owned(item)
    assert info['State']['Running'], 'owned engine stopped'
    pid = info['State']['Pid']
    lines = Path('/proc', str(pid), 'cgroup').read_text().splitlines()
    unified = [line[3:] for line in lines if line.startswith('0::')]
    assert len(unified) == 1, 'cgroup v2 required for this diagnostic'
    group = Path('/sys/fs/cgroup') / unified[0].lstrip('/')
    if group.name == 'init':
        group = group.parent
    cpu = {parts[0]: int(parts[1]) for line in (group / 'cpu.stat').read_text().splitlines() if (parts := line.split())}
    io = {parts[0]: {k: int(v) for k, v in (pair.split('=', 1) for pair in parts[1:])} for line in (group / 'io.stat').read_text().splitlines() if (parts := line.split())}
    psi = {kind: {parts[0]: int(parts[-1].split('=', 1)[1]) for line in Path('/proc/pressure', kind).read_text().splitlines() if (parts := line.split())} for kind in ('cpu', 'io', 'memory')}
    return {'sampled_monotonic_ns': time.monotonic_ns(), 'sampled_unix_ns': time.time_ns(), 'engine_cpu': cpu, 'engine_io': io, 'host_psi_total_us': psi, 'free_disk_bytes': shutil.disk_usage(LAB).free}


def counter_delta(before, after):
    io = {device: {key: value - before['engine_io'].get(device, {}).get(key, 0) for key, value in fields.items()} for device, fields in after['engine_io'].items()}
    return {
        'engine_cpu_seconds': (after['engine_cpu']['usage_usec'] - before['engine_cpu']['usage_usec']) / 1e6,
        'engine_io_delta': io,
        'engine_written_bytes': sum(fields.get('wbytes', 0) for fields in io.values()),
        'host_psi_delta_us': {kind: {level: total - before['host_psi_total_us'][kind][level] for level, total in totals.items()} for kind, totals in after['host_psi_total_us'].items()},
        'counter_bracket_seconds': (after['sampled_monotonic_ns'] - before['sampled_monotonic_ns']) / 1e9,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'execute': False, 'commands': 4, 'ordinary_pairs': 1, 'profiled_pairs': 1, 'cloud_enabled': False, 'output': str(OUT)}))
        return

    os.umask(0o077)
    state = json.loads((LAB / 'withfile-v1/prepared.json').read_text())
    assert (LAB / 'withfile-v1/summary.json').is_file(), 'complete previous local correctness first'
    assert not OUT.exists(), 'never reuse a partially completed trial'
    assert shutil.disk_usage(LAB).free > 16 * 1024**3
    app = LAB / 'greetings'
    assert x.fixture_hashes(app) == state['input_sha256'], 'full fixture differs before HTTP diagnostic'
    assert x.sha(x.CLI) == state['cli_sha256'], 'CLI changed'
    for variant in ('base', 'candidate'):
        x.start(state[variant])  # checks exact container identity, label and binary hash
    OUT.mkdir(mode=0o700)
    config = OUT / 'empty-config'
    config.mkdir(mode=0o700)
    (OUT / 'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    original = {name: (app / name).read_bytes() for name in ('main.go', 'e2e_test.go')}
    trial_nonce = f'{time.time_ns():x}'
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR') if key in os.environ}
    env.update(XDG_CONFIG_HOME=str(config), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
    rows = []
    attempted = []
    x.write(OUT / 'provenance.json', {
        'engines': state,
        'commands_max': 4,
        'flow': FLOW,
        'telemetry': 'local only: fresh empty config and no Cloud/OTLP/auth overrides in allowlisted environment',
        'nonce': trial_nonce,
        'pairs': [{'index': 0, 'order': ['base', 'candidate'], 'profile': False}, {'index': 1, 'order': ['candidate', 'base'], 'profile': True}],
        'cache_boundary': 'retained warmed volumes; each pair has fresh response-header and E2E assertion bytes; no prelisting; no cold claim',
        'cli_boundary': 'fresh CLI Popen through blocking waitpid; correctness reads, counters and profile dumps outside timer',
        'counter_boundary': 'host PSI and engine cgroup counters immediately before Popen and immediately after CLI wait; slightly wider than CLI and process-wide/background-inclusive',
        'driver_sha256': x.sha(__file__),
        'prior_validator_source_sha256': x.sha(LAB / 'withfile-v1/driver.py.txt'),
    })

    def run(variant, index, profile):
        assert len(attempted) < 4
        assert shutil.disk_usage(LAB).free > 16 * 1024**3
        item = state[variant]
        dest = OUT / f'pair-{index}-{variant}'
        dest.mkdir()
        if profile:
            try:
                (dest / 'prior.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
            except x.HTTPError as error:
                if error.code != 503:
                    raise
        before = snapshot(item)
        source_hashes = {name: x.sha(app / name) for name in original}
        command = [str(x.CLI), '--engine', 'container://' + item['name']] + (['--profile'] if profile else []) + FLOW
        done = threading.Event()
        observed = {}
        attempt = {'index': index, 'variant': variant, 'profile': profile, 'source_sha256': source_hashes}
        attempted.append(attempt)
        x.write(OUT / 'attempts.json', attempted)
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
        expected_check = b'dag://go/modules/tests/run?go-module=.&go-test=TestE2ERandomGreeting'
        correct = (not timed_out and observed['status'] == 0 and re.search(rb'\b1 passed\b', text) is not None and expected_check in text and re.search(rb'\bSKIP(?:PED)?\b', text, re.I) is None)
        row = {
            'variant': variant, 'pair_index': index, 'profile': profile,
            'seconds': observed['time'] - begin, 'started_unix_ns': wall, 'exited_unix_ns': observed['wall'],
            'exit_code': observed['status'], 'timed_out': timed_out, 'correct': correct,
            'source_sha256': source_hashes, 'stdout_sha256': x.sha(dest / 'stdout.txt'),
            'before': before, 'after': after, **counter_delta(before, after),
        }
        rows.append(row)
        x.write(OUT / 'results.json', rows)
        attempt.update(exit_code=observed['status'], timed_out=timed_out, validated=correct)
        x.write(OUT / 'attempts.json', attempted)
        print(json.dumps({key: row[key] for key in ('variant','pair_index','profile','seconds','exit_code','correct','engine_cpu_seconds','engine_written_bytes')}), flush=True)
        # Capture separate diagnostics after the command's counters and output.
        time.sleep(.3)
        if profile:
            (dest / 'run.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
        assert correct, ('strict fresh HTTP test failed; see private output', dest.name)
        assert source_hashes == {name: x.sha(app / name) for name in original}, 'command changed source'

    try:
        request = b'\tresp, err := client.Do(req)\n\tassert.NilError(t, err)\n'
        header = b'\t\tw.Header().Set("Content-Type", "application/json")'
        assert original['e2e_test.go'].count(b't.Skip(') == 1
        assert original['e2e_test.go'].count(request) == 1
        assert original['main.go'].count(header) == 2
        for index, order in enumerate((('base', 'candidate'), ('candidate', 'base'))):
            nonce = f'{trial_nonce}-pair-{index}'
            strict = original['e2e_test.go'].replace(b't.Skip(', b't.Fatal(').replace(request, request + f'\tassert.Equal(t, resp.Header.Get("X-Dagger-Perf-Revision"), "{nonce}", "fresh HTTP sentinel mismatch")\n'.encode())
            live = original['main.go'].replace(header, header + f'\n\t\tw.Header().Set("X-Dagger-Perf-Revision", "{nonce}")'.encode())
            (app / 'e2e_test.go').write_bytes(strict)
            (app / 'main.go').write_bytes(live)
            for variant in order:
                run(variant, index, profile=index == 1)
    finally:
        for name, contents in original.items():
            (app / name).write_bytes(contents)
        assert x.fixture_hashes(app) == state['input_sha256'], 'full fixture not restored'
        x.write(OUT / 'restoration.json', {'full_fixture_restored': True, 'commands_attempted': len(attempted), 'commands_validated': sum(row['correct'] for row in rows), 'source_sha256': {name: x.sha(app / name) for name in original}})

    assert len(rows) == 4 and all(row['correct'] for row in rows)
    pairs = []
    for index in range(2):
        selected = {row['variant']: row for row in rows if row['pair_index'] == index}
        assert selected['base']['source_sha256'] == selected['candidate']['source_sha256']
        pairs.append({'pair_index': index, 'profile': index == 1, 'base_seconds': selected['base']['seconds'], 'candidate_seconds': selected['candidate']['seconds'], 'candidate_minus_base_seconds': selected['candidate']['seconds'] - selected['base']['seconds'], 'same_source_bytes': True})
    x.write(OUT / 'summary.json', {'commands': 4, 'all_correct': True, 'pairs': pairs, 'claim_boundary': 'one ordinary pair and one separately profiled reverse-order pair; do not pool them or call this cold; engine volumes have unequal prior history'})


if __name__ == '__main__':
    main()
