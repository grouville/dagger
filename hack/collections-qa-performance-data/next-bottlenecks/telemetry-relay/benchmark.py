"""Compare direct export, persistent connections, and durable handoff.

Only timings/counters and CLI output are recorded. Never copies the private
spool or authentication token. Every async run must drain successfully before
the next measured run; this deliberately measures isolated commands first.
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
REPO = Path('/home/dagger/dag')
parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--workspace', default='/tmp/collections-perf/normal-baseline/greetings-split')
parser.add_argument('--cli', default='/tmp/collections-perf/rebase-main/dagger')
parser.add_argument('--output', required=True)
parser.add_argument('--repetitions', type=int, default=8)
parser.add_argument('--profile', action='store_true')
args = parser.parse_args()
dest = Path(args.output)
dest.mkdir(exist_ok=False)
config = json.loads((BASE / 'config.json').read_text())
admin = (BASE / 'admin-token').read_text().strip()
want = (REPO / 'hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
env = dict(os.environ)
for key in ['SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE',
            'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN']:
    env.pop(key, None)


def request(path, method='GET'):
    req = urllib.request.Request(config['endpoint'] + path, method=method,
                                 headers={'X-Relay-Admin': admin})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = resp.read()
    return json.loads(data) if data else None


def healthy(stats):
    for key in ['Failed', 'TerminalFailures', 'DurabilityErrors', 'ReadErrors', 'StorageErrors']:
        if stats.get(key, 0):
            raise RuntimeError('relay unhealthy: ' + json.dumps(stats))


def drained():
    start = time.monotonic()
    empty_since = None
    while True:
        stats = request('/relay/stats')
        healthy(stats)
        if stats['Pending'] == 0 and stats['Bytes'] == 0 and stats.get('CleanupPending', 0) == 0:
            if empty_since is None:
                empty_since = time.monotonic()
            elif time.monotonic() - empty_since >= .10:
                return stats, time.monotonic() - start - .10
        else:
            empty_since = None
        if time.monotonic() - start > 45:
            raise RuntimeError('relay delivery timeout: ' + json.dumps(stats))
        time.sleep(.05)


def pressure():
    return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=', 1)[1])


rows = []
modes = ['direct', 'sync', 'async']
for iteration in range(-2, args.repetitions):
    # Balanced rotations and reversed rotations across successive triples.
    order = modes[iteration % 3:] + modes[:iteration % 3]
    if (iteration // 3) % 2:
        order.reverse()
    for mode in order:
        before, _ = drained()
        if mode != 'direct':
            request('/relay/mode?value=' + mode, 'POST')
        runenv = dict(env)
        runenv['DAGGER_CLOUD_URL'] = config['target'] if mode == 'direct' else config['endpoint']
        cmd = [args.cli, '--engine', 'container://' + args.engine, 'check', '-l', '--all']
        io_before = pressure()
        start = time.monotonic()
        result = subprocess.run(cmd, cwd=args.workspace, env=runenv, capture_output=True, timeout=180)
        elapsed = time.monotonic() - start
        io_after = pressure()
        at_exit = request('/relay/stats')
        after, drain = drained()
        row = {'mode': mode, 'iteration': iteration, 'seconds': elapsed,
               'delivery_wait_after_exit_seconds': drain,
               'host_io_full_seconds': (io_after - io_before) / 1e6,
               'status': result.returncode, 'correct': result.returncode == 0 and result.stdout == want,
               'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
               'relay_at_exit': at_exit,
               'relay_delta': {k: after[k] - before[k] for k in after
                               if isinstance(after[k], int) and k != 'LastStatus'},
               'relay_last_status': after['LastStatus']}
        rows.append(row)
        (dest / f'{iteration}-{mode}.out').write_bytes(result.stdout)
        (dest / f'{iteration}-{mode}.err').write_bytes(result.stderr)
        (dest / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        assert row['correct'], 'incorrect CLI listing'
        if mode == 'async':
            assert row['relay_delta']['Accepted'] > 0, 'async export was not exercised'
            assert row['relay_delta']['Accepted'] == row['relay_delta']['Delivered'], 'incomplete delivery'

summary = {}
for mode in modes:
    measured = [row for row in rows if row['mode'] == mode and row['iteration'] >= 0]
    seconds = [row['seconds'] for row in measured]
    summary[mode] = {'n': len(seconds), 'median': statistics.median(seconds),
                     'min': min(seconds), 'max': max(seconds),
                     'median_delivery_wait_after_exit_seconds': statistics.median(
                         row['delivery_wait_after_exit_seconds'] for row in measured)}
(dest / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary), flush=True)

if args.profile:
    for mode in modes:
        drained()
        if mode != 'direct':
            request('/relay/mode?value=' + mode, 'POST')
        runenv = dict(env)
        runenv['DAGGER_CLOUD_URL'] = config['target'] if mode == 'direct' else config['endpoint']
        runenv['CPUPROFILE'] = str(dest / f'{mode}.cpu')
        result = subprocess.run([args.cli, '--engine', 'container://' + args.engine,
                                 '--profile', 'check', '-l', '--all'],
                                cwd=args.workspace, env=runenv, capture_output=True, timeout=180)
        (dest / f'{mode}-profile.err').write_bytes(result.stderr)
        assert result.returncode == 0 and result.stdout == want
        drained()
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/debug/wcprof/dump', timeout=60) as resp:
            (dest / f'{mode}.wcprof').write_bytes(resp.read())

(dest / 'provenance.json').write_text(json.dumps({
    'engine': args.engine, 'workspace': args.workspace, 'cli': args.cli,
    'cli_sha256': hashlib.sha256(Path(args.cli).read_bytes()).hexdigest(),
    'relay_sha256': hashlib.sha256((BASE / 'relay').read_bytes()).hexdigest(),
    'relay_source_sha256': hashlib.sha256((BASE / 'main.go').read_bytes()).hexdigest(),
    'argv': ['check', '-l', '--all'], 'telemetry': True,
    'timing': 'new CLI through process exit; durable relay drain measured separately',
}, indent=2) + '\n')
