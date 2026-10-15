import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True, choices=[
    'dagger-rust-parser-state-pool-oct14', 'dagger-rust-checkpoint-snapshot-key-oct14'])
parser.add_argument('--debug-port', required=True, type=int)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--binary', type=Path, help='optional engine binary to copy while stopped')
args = parser.parse_args()
args.output.mkdir(exist_ok=True)
debug = f'http://127.0.0.1:{args.debug_port}'
deadline = time.monotonic() + 30
while True:
    with urllib.request.urlopen(debug + '/debug/client-lifecycle', timeout=3) as response:
        state = json.load(response)
    if not state.get('sessions') and state['active_requests'] == 0:
        break
    assert time.monotonic() < deadline, 'engine has not finished session teardown'
    time.sleep(.25)

started = time.monotonic()
process = subprocess.Popen(['docker', 'stop', '--timeout', '-1', args.engine],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
next_capture = 15
while process.poll() is None:
    elapsed = time.monotonic() - started
    if elapsed >= next_capture:
        print('Graceful stop:', round(elapsed, 1), 'seconds; no SIGKILL deadline', flush=True)
        try:
            with urllib.request.urlopen(debug + '/debug/pprof/goroutine?debug=2', timeout=3) as response:
                (args.output / f'goroutines-{next_capture}.txt').write_bytes(response.read())
        except OSError as err:
            print('debug endpoint unavailable during stop:', type(err).__name__, flush=True)
        next_capture += 15
    time.sleep(.25)
seconds = time.monotonic() - started
output = process.communicate()[0]
assert not process.returncode, output
state = json.loads(subprocess.check_output(['docker', 'inspect', args.engine]))[0]['State']
assert not state['Running'] and state['ExitCode'] == 0, state
(args.output / 'stop.json').write_text(json.dumps(dict(
    seconds=seconds, exit_code=state['ExitCode'], oom_killed=state['OOMKilled'],
    timeout='indefinite; no forced termination'), indent=2) + '\n')
print('PASS: graceful exit 0 after', round(seconds, 3), 'seconds', flush=True)
if args.binary is not None:
    assert args.binary.is_file(), args.binary
    subprocess.run(['docker', 'cp', str(args.binary), args.engine + ':/usr/local/bin/dagger-engine'], check=True)
subprocess.run(['docker', 'start', args.engine], check=True)
deadline = time.monotonic() + 45
while True:
    try:
        with urllib.request.urlopen(debug + '/debug/wcprof/enabled', timeout=2) as response:
            assert not json.load(response)['global_enabled']
        break
    except OSError:
        assert time.monotonic() < deadline, 'engine did not become ready'
        time.sleep(.25)
print('PASS: same owned engine restarted; volume preserved', flush=True)
