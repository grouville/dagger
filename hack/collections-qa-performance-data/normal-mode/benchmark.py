from pathlib import Path
import json, os, shutil, statistics, subprocess, sys, time, urllib.request

root = Path('/tmp/collections-perf/normal-baseline')
root.mkdir(exist_ok=True)
source = Path('/tmp/collections-perf/published-baseline/greetings-pristine')
candidate = root / 'greetings-split'
if not candidate.exists():
    shutil.copytree(source, candidate)
    sdk = Path('.dagger/modules/frontend/sdk')
    for name in ['core.js', 'core-node-imports.js']:
        shutil.copyfile(Path('/tmp/collections-perf/next-final/workspace') / sdk / name, candidate / sdk / name)

variants = {
    'original': ('dagger-engine.collections-kyle-original', 'dagger-engine.collections-normal-original', 6103, '/tmp/collections-perf/untouched-pr/engine', '/tmp/collections-perf/untouched-pr/dagger', source),
    'committed': ('dagger-engine.collections-committed-candidate-0', 'dagger-engine.collections-normal-committed', 6105, '/tmp/collections-perf/committed/engine', '/tmp/collections-perf/committed/dagger', source),
    'experimental': ('dagger-engine.collections-kyle-syntax', 'dagger-engine.collections-normal-syntax', 6104, '/tmp/collections-perf/syntax-isolated/engine', '/tmp/collections-perf/committed/dagger', candidate),
}

def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout

for name, (old, engine, port, binary, cli, workspace) in variants.items():
    exists = subprocess.run(['docker', 'inspect', engine], capture_output=True).returncode == 0
    if not exists:
        command(['docker', 'stop', '--time', '15', old])
        command(['docker', 'create', '--name', engine, '--privileged', '--security-opt', 'label=disable',
                 '-v', old + ':/var/lib/dagger', '-p', f'127.0.0.1:{port}:6060',
                 'localhost/dagger-engine.collections-perf:latest', '--debugaddr=0.0.0.0:6060'])
        command(['docker', 'cp', binary, engine + ':/usr/local/bin/dagger-engine'])
        command(['docker', 'start', engine])
    deadline = time.monotonic() + 30
    while True:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/', timeout=1).close()
            break
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(.2)
    (root / (name + '-engine.json')).write_text(command(['docker', 'inspect', engine]))
    print('ready ' + name, flush=True)

expected = Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
runner = '/home/dagger/dag/hack/bench-artifact-discovery.py'
os.environ.pop('SSH_AUTH_SOCK', None)
rows = []

def run(label, name, profile=False):
    old, engine, port, binary, cli, workspace = variants[name]
    dest = root / label
    args = [sys.executable, runner, '--runs', '1', '--warmups', '0', '--timeout', '600', '--output', str(dest)]
    if profile:
        args += ['--wcprof-url', f'http://127.0.0.1:{port}']
    args += ['--', cli, '--engine', 'container://' + engine, 'check', '-l', '--all']
    result = subprocess.run(args, cwd=workspace, capture_output=True, text=True)
    (dest / 'driver.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    assert (dest / 'run-0.out').read_bytes() == expected, label + ' incomplete listing'
    data = json.loads((dest / 'results.json').read_text())
    row = {'label': label, 'variant': name, 'seconds': data['median_seconds'], 'correct': True}
    rows.append(row)
    (root / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    if profile:
        with (dest / 'analysis.txt').open('w') as output:
            subprocess.run(['/tmp/wcprof-analyze', '-top', '40', str(dest / 'runs.wcprof')], stdout=output, check=True)

for i in range(2):
    for name in variants:
        run(f'warmup/{name}-{i}', name)
for i in range(5):
    for name in list(variants)[::1 if i % 2 == 0 else -1]:
        run(f'warm/{name}-{i}', name)
summary = {name: statistics.median(row['seconds'] for row in rows if row['variant'] == name and row['label'].startswith('warm/')) for name in variants}
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary), flush=True)
for name in variants:
    run('profile/' + name, name, True)
