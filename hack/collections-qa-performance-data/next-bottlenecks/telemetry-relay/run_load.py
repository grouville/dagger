#!/usr/bin/env python3
"""Instrumented relay paired latency and sustained-backlog experiment.

Archives only source hashes, integer counters, timings, and CLI outputs.
Private config/admin credentials are read by the process, never printed/copied.
The spool is outside the result directory and must never be archived.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request

BASE = Path(__file__).resolve().parent
GAUGES = {'Pending', 'Bytes', 'CleanupPending', 'Tombstones', 'LastStatus',
          'OldestPendingNS', 'ExportActive', 'ExportPeak'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pressure():
    return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=', 1)[1])


def delta(before, after):
    return {k: after[k] - before[k] for k in after
            if isinstance(after[k], int) and k not in GAUGES}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--engine', required=True)
    p.add_argument('--workspace', default='/tmp/collections-perf/sdk-edit-audit/ts-static/greetings')
    p.add_argument('--cli', default='/tmp/collections-perf/rebase-main/dagger')
    p.add_argument('--trial', required=True)
    p.add_argument('--pairs', type=int, default=8)
    p.add_argument('--burst', type=int, default=10)
    p.add_argument('--warmup-pairs', type=int, default=2)
    args = p.parse_args()
    if '/' in args.trial or args.trial in ['', '.', '..']:
        raise SystemExit('trial must be a fresh simple directory name')
    dest = BASE / args.trial
    dest.mkdir(mode=0o700, exist_ok=False)
    spool = BASE / ('private-spool-' + args.trial)
    assert not spool.exists(), 'spool must be fresh'
    config = json.loads((BASE / 'config.json').read_text())
    assert config['target'] == 'https://api.dagger.cloud', 'unexpected original Cloud target'
    validation = json.loads((BASE / 'relay-v2-validation.json').read_text())
    for name, want_hash in validation['sha256'].items():
        assert digest(BASE / name) == want_hash, 'relay source/binary differs from tested v2'
    admin = (BASE / 'admin-token').read_text().strip()
    want = Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
    env = dict(os.environ)
    for k in ['SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE',
              'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN']:
        env.pop(k, None)
    env['DAGGER_CLOUD_URL'] = config['endpoint']
    cmd = [args.cli, '--engine', 'container://' + args.engine, 'check', '-l', '--all']
    rows = []
    relay = None
    relay_log = (dest / 'relay.log').open('ab')

    def request(path, method='GET'):
        req = urllib.request.Request(config['endpoint'] + path, method=method,
                                     headers={'X-Relay-Admin': admin})
        with urllib.request.urlopen(req, timeout=5) as resp:
            b = resp.read()
        return json.loads(b) if b else None

    def healthy(s):
        for k in ['Failed', 'StorageErrors', 'Export4xx', 'Export5xx', 'ExportOther', 'ExportErrors']:
            if s.get(k, 0):
                raise RuntimeError('relay unhealthy: ' + json.dumps(s))

    def drained():
        start = time.monotonic()
        empty_since = None
        previous = None
        while True:
            s = request('/relay/stats')
            healthy(s)
            empty = s['Pending'] == 0 and s['Bytes'] == 0 and s['CleanupPending'] == 0 and s['ExportActive'] == 0
            if empty:
                current = (s['Accepted'], s['Delivered'], s['ExportRequests'], s['Export2xx'])
                if empty_since is None or previous != current:
                    empty_since = time.monotonic()
                elif time.monotonic() - empty_since >= .20:
                    return s, max(0., time.monotonic() - start - .20)
                previous = current
            else:
                empty_since = None
            if time.monotonic() - start > 120:
                raise RuntimeError('drain timeout: ' + json.dumps(s))
            time.sleep(.05)

    def cli(mode, phase, i, before, origin):
        io_before = pressure()
        started = time.monotonic()
        result = subprocess.run(cmd, cwd=args.workspace, env=env, capture_output=True, timeout=180)
        exited = time.monotonic()
        io_after = pressure()
        at_exit = request('/relay/stats')
        healthy(at_exit)
        name = f'{phase}-{mode}-{i}'
        (dest / (name + '.out')).write_bytes(result.stdout)
        (dest / (name + '.err')).write_bytes(result.stderr)
        row = {'phase': phase, 'mode': mode, 'iteration': i,
               'start_from_phase_seconds': started - origin,
               'exit_from_phase_seconds': exited - origin,
               'seconds': exited - started,
               'host_io_full_seconds': (io_after - io_before) / 1e6,
               'correct': result.returncode == 0 and result.stdout == want,
               'status': result.returncode,
               'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
               'relay_before': before, 'relay_at_exit': at_exit,
               'interval_delta_at_exit': delta(before, at_exit)}
        assert row['correct'], 'incorrect listing'
        return row

    def save(row):
        rows.append(row)
        (dest / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(row), flush=True)

    def ensure_delivery(before, after, mode):
        d = delta(before, after)
        assert d['ExportRequests'] == d['Export2xx'] > 0, 'incomplete upstream response accounting'
        if mode == 'async':
            assert d['Accepted'] == d['Delivered'] > 0, 'async accepted data not delivered'
        return d

    try:
        # Ownership comes from this fresh process and fresh spool. An occupied
        # endpoint makes this process exit and fails readiness, never taking over.
        relay = subprocess.Popen([str(BASE / 'relay'), '--listen', config['listen'],
                                  '--target', config['target'], '--spool', str(spool),
                                  '--admin-file', str(BASE / 'admin-token')],
                                 stdout=relay_log, stderr=relay_log)
        for _ in range(100):
            assert relay.poll() is None, 'relay failed to start'
            try:
                s = request('/relay/stats')
                assert s['Recovered'] == 0 and s['Accepted'] == 0 and s['ExportRequests'] == 0
                # Let a bind failure be observed even if a pre-existing endpoint answered.
                time.sleep(.1)
                assert relay.poll() is None, 'relay endpoint already occupied'
                break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('relay not ready')
        provenance = {'engine': args.engine, 'workspace': args.workspace,
                      'cli': args.cli, 'cli_sha256': digest(args.cli),
                      'relay_sha256': digest(BASE / 'relay'),
                      'relay_source_sha256': digest(BASE / 'main.go'),
                      'relay_tests_sha256': digest(BASE / 'main_test.go'),
                      'driver_sha256': digest(__file__),
                      'fixture_sha256': {name: digest(Path(args.workspace) / name)
                          for name in ['main_test.go', 'main.go', 'dagger.json',
                              '.dagger/modules/backend/main.go',
                              '.dagger/modules/frontend/.dagger-static-types/main.dang',
                              '.dagger/modules/frontend/.dagger-static-types/manifest.json']
                          if (Path(args.workspace) / name).is_file()},
                      'argv': ['check', '-l', '--all'], 'telemetry': True,
                      'pairs': args.pairs, 'burst_commands_per_mode': args.burst,
                      'timing': 'complete CLI through exit; final upstream drain separate',
                      'burst_note': 'No Cloud drain or intentional sleep between commands; local stats read and output bookkeeping remain between commands. Interval exports can belong to earlier commands; only final block totals have exact per-command averages.',
                      'pair_note': 'Balanced alternating sync/async order, full drain between isolated commands; two warm-up pairs excluded.'}
        (dest / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        for i in range(-args.warmup_pairs, args.pairs):
            for mode in (['sync', 'async'] if i % 2 == 0 else ['async', 'sync']):
                before, _ = drained()
                request('/relay/mode?value=' + mode, 'POST')
                row = cli(mode, 'pair', i, before, time.monotonic())
                after, lag = drained()
                row.update(relay_after_drain=after, relay_delta=ensure_delivery(before, after, mode),
                           delivery_wait_after_exit_seconds=lag)
                save(row)
        burst_summaries = []
        for mode in ['sync', 'async']:
            before, _ = drained()
            request('/relay/mode?value=' + mode, 'POST')
            previous = before
            started = time.monotonic()
            samples = []
            for i in range(args.burst):
                row = cli(mode, 'burst', i, previous, started)
                save(row)
                samples.append(row)
                previous = row['relay_at_exit']
            burst_exit = samples[-1]['exit_from_phase_seconds']
            after, lag = drained()
            d = ensure_delivery(before, after, mode)
            summary = {'mode': mode, 'commands': args.burst,
                       'seconds_to_last_cli_exit': burst_exit,
                       'delivery_wait_after_last_exit_seconds': lag,
                       'seconds_to_full_drain_including_settle': time.monotonic() - started,
                       'relay_before': before, 'relay_after_drain': after,
                       'relay_delta': d,
                       'average_export_requests_per_command': d['ExportRequests'] / args.burst,
                       'average_export_bytes_per_command': d['ExportRequestBytes'] / args.burst,
                       'pending_after_each_exit': [r['relay_at_exit']['Pending'] for r in samples],
                       'bytes_after_each_exit': [r['relay_at_exit']['Bytes'] for r in samples],
                       'oldest_pending_seconds_after_each_exit': [r['relay_at_exit']['OldestPendingNS'] / 1e9 for r in samples],
                       'export_requests_per_elapsed_second': d['ExportRequests'] / (time.monotonic() - started)}
            burst_summaries.append(summary)
            (dest / 'burst-summary.json').write_text(json.dumps(burst_summaries, indent=2) + '\n')
            print(json.dumps({'burst_summary': summary}), flush=True)
        summaries = {}
        for mode in ['sync', 'async']:
            measured = [r for r in rows if r['phase'] == 'pair' and r['mode'] == mode and r['iteration'] >= 0]
            summaries[mode] = {'n': len(measured), 'median_cli_seconds': statistics.median(r['seconds'] for r in measured),
                               'median_drain_after_exit_seconds': statistics.median(r['delivery_wait_after_exit_seconds'] for r in measured),
                               'median_export_requests': statistics.median(r['relay_delta']['ExportRequests'] for r in measured),
                               'median_export_bytes': statistics.median(r['relay_delta']['ExportRequestBytes'] for r in measured),
                               'median_log_requests': statistics.median(r['relay_delta']['LogRequests'] for r in measured),
                               'median_trace_requests': statistics.median(r['relay_delta']['TraceRequests'] for r in measured)}
        (dest / 'paired-summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
        print(json.dumps({'paired_summary': summaries}), flush=True)
    finally:
        if relay is not None and relay.poll() is None:
            try:
                s = request('/relay/stats')
                if s['Pending'] == 0 and s['CleanupPending'] == 0 and s['ExportActive'] == 0:
                    relay.terminate()
                    relay.wait(timeout=5)
                else:
                    print(json.dumps({'relay_retained_for_pending_delivery': relay.pid, 'stats': s}), flush=True)
            except Exception:
                print(json.dumps({'relay_retained_due_to_unknown_delivery_state': relay.pid}), flush=True)
        relay_log.close()


if __name__ == '__main__':
    main()
