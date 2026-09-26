"""Own the trial relay; prove crash replay before measuring CLI handoff."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.request

B = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True)
parser.add_argument('--port', required=True)
parser.add_argument('--workspace', required=True)
parser.add_argument('--trial', required=True)
parser.add_argument('--repetitions', default='8')
args = parser.parse_args()
dest = B / args.trial
dest.mkdir(mode=0o700, exist_ok=False)
spool = B / ('private-spool-' + args.trial)
assert not spool.exists()
config = json.loads((B / 'config.json').read_text())
admin = (B / 'admin-token').read_text().strip()
relay = None
relay_log = (dest / 'relay.log').open('ab')


def request(path, method='GET'):
    req = urllib.request.Request(config['endpoint'] + path, method=method,
                                 headers={'X-Relay-Admin': admin})
    with urllib.request.urlopen(req, timeout=5) as r:
        body = r.read()
    return json.loads(body) if body else None


def healthy(stats):
    assert stats.get('Failed', 0) == 0, stats
    assert stats.get('StorageErrors', 0) == 0, stats


def start():
    process = subprocess.Popen([str(B / 'relay'), '--listen', config['listen'],
                                '--target', config['target'], '--spool', str(spool),
                                '--paused', '--admin-file', str(B / 'admin-token')],
                               stdout=relay_log, stderr=relay_log)
    for _ in range(100):
        assert process.poll() is None, 'relay failed to start'
        try:
            request('/relay/stats')
            return process
        except OSError:
            time.sleep(.05)
    raise RuntimeError('relay did not become ready')


try:
    relay = start()
    request('/relay/mode?value=async', 'POST')
    env = dict(os.environ)
    for key in ['SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE',
                'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN']:
        env.pop(key, None)
    env['DAGGER_CLOUD_URL'] = config['endpoint']
    started = time.monotonic()
    result = subprocess.run(['/tmp/collections-perf/rebase-main/dagger', '--engine',
                             'container://' + args.engine, 'check', '-l', '--all'],
                            env=env, cwd=args.workspace, capture_output=True, timeout=180)
    elapsed = time.monotonic() - started
    expected = Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
    (dest / 'recovery-check.out').write_bytes(result.stdout)
    (dest / 'recovery-check.err').write_bytes(result.stderr)
    assert result.returncode == 0 and result.stdout == expected, 'recovery listing failed'
    before = request('/relay/stats')
    healthy(before)
    assert before['Pending'] > 0 and before['Delivered'] == 0, before
    (dest / 'before-crash.json').write_text(json.dumps(before, indent=2) + '\n')
    relay.kill()
    relay.wait(timeout=5)
    # A producer can finish another POST between the stats response and SIGKILL.
    # Observe the now-quiescent disk without reading or recording payloads/names.
    records = list(spool.glob('*.json'))
    crash_disk = {'records': len(records), 'bytes': sum(path.stat().st_size for path in records)}
    (dest / 'crash-disk-counts.json').write_text(json.dumps(crash_disk, indent=2) + '\n')
    relay = start()
    after = request('/relay/stats')
    healthy(after)
    (dest / 'recovered.json').write_text(json.dumps(after, indent=2) + '\n')
    assert after['Pending'] >= before['Pending'] and after['Bytes'] >= before['Bytes'], (before, after)
    # These counters freeze at startup, before the listener admits more exports.
    assert after['Recovered'] == crash_disk['records'] and after['RecoveredBytes'] == crash_disk['bytes'], (crash_disk, after)
    assert after['Pending'] >= after['Recovered'] and after['Bytes'] >= after['RecoveredBytes'], after
    request('/relay/resume', 'POST')
    drain_started = time.monotonic()
    while True:
        drained = request('/relay/stats')
        healthy(drained)
        if drained['Pending'] == 0 and drained['Bytes'] == 0 and drained.get('CleanupPending', 0) == 0:
            break
        assert time.monotonic() - drain_started < 60, drained
        time.sleep(.05)
    assert drained['Delivered'] == drained['Accepted'] >= after['Accepted'], drained
    recovery = {'cli_seconds': elapsed, 'correct': True, 'paused_before_crash': before,
                'crash_disk_counts': crash_disk, 'recovered_after_sigkill': after, 'drained': drained,
                'replay_seconds': time.monotonic() - drain_started,
                'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()}
    (dest / 'recovery.json').write_text(json.dumps(recovery, indent=2) + '\n')
    print(json.dumps({'recovery': recovery}), flush=True)
    subprocess.run(['python3', str(B / 'benchmark.py'), '--engine', args.engine,
                    '--port', args.port, '--workspace', args.workspace,
                    '--output', str(dest / 'measurements'), '--repetitions', args.repetitions,
                    '--profile'], check=True)
finally:
    if relay is not None and relay.poll() is None:
        current = request('/relay/stats')
        if current['Pending'] == 0 and current.get('CleanupPending', 0) == 0:
            relay.terminate()
            relay.wait(timeout=5)
        else:
            print(json.dumps({'relay_retained_for_pending_delivery': relay.pid, 'stats': current}), flush=True)
    relay_log.close()
