from pathlib import Path
import os, subprocess, socket, time, sys, json, hashlib

os.environ.pop('SSH_AUTH_SOCK', None)
base = Path('/tmp/collections-perf/cold-priority')
base.mkdir(exist_ok=True)
name = 'dagger-engine.collections-cold-priority'
port = 6109
for kind in ['container', 'volume']:
    assert subprocess.run(['docker', kind, 'inspect', name], capture_output=True).returncode != 0
subprocess.run(['docker', 'create', '--name', name, '--privileged', '-p', f'127.0.0.1:{port}:6060', '-v', name + ':/var/lib/dagger', 'localhost/dagger-engine.collections-perf:latest', '--debugaddr=0.0.0.0:6060'], check=True)
subprocess.run(['docker', 'cp', '/tmp/collections-perf/rebuilt-prototypes/engine', name + ':/usr/local/bin/dagger-engine'], check=True)
subprocess.run(['docker', 'start', name], check=True)
deadline = time.monotonic() + 30
while True:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1): break
    except OSError:
        if time.monotonic() > deadline: raise
        time.sleep(.1)
cmd = [sys.executable, '/home/dagger/dag/hack/bench-artifact-discovery.py', '--runs', '1', '--warmups', '0', '--timeout', '600', '--output', str(base / 'profile'), '--wcprof-url', f'http://127.0.0.1:{port}', '--cold-profile', '--', '/tmp/collections-perf/committed/dagger', '--engine', 'container://' + name, 'check', '-l', '--all']
p = subprocess.run(cmd, cwd='/tmp/collections-perf/normal-baseline/greetings-split')
with (base/'analysis.txt').open('w') as f:
    subprocess.run(['/tmp/wcprof-analyze', '-top', '60', str(base/'profile/runs.wcprof')], stdout=f, check=True)
actual=(base/'profile/run-0.out').read_bytes()
expected=Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
print(json.dumps({'status': p.returncode, 'correct': actual == expected, 'stdout_sha256': hashlib.sha256(actual).hexdigest()}), flush=True)
raise SystemExit(p.returncode)
