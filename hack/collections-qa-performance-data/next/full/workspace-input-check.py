from pathlib import Path
import subprocess, os, json, uuid

base = Path('/tmp/collections-perf/next-final/workspace-input-check')
base.mkdir(exist_ok=True)
os.environ.pop('SSH_AUTH_SOCK', None)
workspaces = {
    'control': Path('/tmp/collections-perf/kyle-latest/greetings-api'),
    'full': Path('/tmp/collections-perf/next-final/workspace'),
}
filename = 'perf-runtime-marker.txt'
nonce = uuid.uuid4().hex
rows = []
for ws in workspaces.values():
    assert not (ws / 'website' / filename).exists()
try:
    for variant, ws in workspaces.items():
        (ws / 'website' / filename).write_text(variant + ':' + nonce + '\n')
    for i, variant in enumerate(['control', 'full', 'control']):
        ws = workspaces[variant]
        result = subprocess.run([
            '/tmp/collections-perf/committed/dagger', '--engine',
            'container://dagger-engine.collections-kyle-syntax', 'api', 'call',
            '-m', '.dagger/modules/frontend', 'build', 'file', '--path',
            filename, 'contents',
        ], cwd=ws, capture_output=True, timeout=180)
        (base / f'{i}-{variant}.out').write_bytes(result.stdout)
        (base / f'{i}-{variant}.err').write_bytes(result.stderr)
        result.check_returncode()
        assert result.stdout.rstrip(b'\n') == (variant + ':' + nonce).encode(), (
            'stale or wrong workspace', variant)
        rows.append({'variant': variant, 'iteration': i, 'correct': True})
finally:
    for ws in workspaces.values():
        (ws / 'website' / filename).unlink(missing_ok=True)
(base / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
