"""Verify/freeze provenance, then build the one reviewed diagnostic engine."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time

H = Path(__file__).resolve().parent
B = H / 'combined-build'
R = Path('/home/dagger/dag')
parser = argparse.ArgumentParser()
parser.add_argument('--run', action='store_true')
args = parser.parse_args()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
recipe = json.loads((B / 'build-recipe.json').read_text())
recipe_sha = sha(B / 'build-recipe.json')


def save(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n')


def verify():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip() == recipe['source_head']
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=normal'], cwd=R, text=True).splitlines()
    assert all(any(line[3:].startswith(prefix) for prefix in recipe['allowed_dirty_prefixes']) for line in status), status
    for group in ('inputs', 'external_dependency_inputs'):
        for path, expected in recipe[group].items():
            assert sha(path) == expected, 'input changed: ' + path
    assert sha(recipe['go']['path']) == recipe['go']['sha256']
    assert sha(recipe['parent_manifest_path']) == recipe['parent_manifest_sha256']
    assert sha(recipe['parent_recipe_path']) == recipe['parent_recipe_sha256']
    return status


if not args.run:
    print(json.dumps({'prepared_only': True, 'recipe_sha256': recipe_sha, 'command': recipe['command'], 'scope': recipe['scope']}))
    raise SystemExit

assert not (B / 'build-results.json').exists(), 'results already exist; preserve prior run'
status = verify()
started = time.monotonic()
log = B / 'build.private.log'
result = {'recipe_sha256': recipe_sha, 'runner_sha256': sha(__file__), 'preflight_status': status, 'runtime_commands': 0, 'cloud_commands': 0}
try:
    with log.open('wb') as output:
        process = subprocess.run(recipe['command'], cwd=R, env={**os.environ, **recipe['environment']}, stdout=output, stderr=subprocess.STDOUT, timeout=300)
    result['exit_code'] = process.returncode
finally:
    result['seconds'] = time.monotonic() - started
    result['log_sha256'] = sha(log) if log.exists() else None
    save(B / 'build-results.json', result)
assert result.get('exit_code') == 0, 'diagnostic engine build failed'
verify()
binary = B / 'engine-diagnostic'
info = subprocess.check_output([recipe['go']['path'], 'version', '-m', str(binary)], text=True)
settings = {}
for line in info.splitlines():
    fields = line.strip().split('\t')
    if len(fields) == 2 and fields[0] == 'build' and '=' in fields[1]:
        key, value = fields[1].split('=', 1)
        if key in ('vcs.revision', 'vcs.time', 'vcs.modified', 'GOOS', 'GOARCH', 'CGO_ENABLED'):
            settings[key] = value
assert settings['vcs.revision'] == recipe['source_head']
version = (R / 'internal/version/VERSION').read_text().strip().removeprefix('v')
expected = 'v' + version + '+' + settings['vcs.revision'][:8] + ('.dirty' if settings['vcs.modified'] == 'true' else '')
manifest = {
    'engine': {'path': str(binary), 'sha256': sha(binary), 'exit_code': 0},
    'expected_core_version': expected,
    'recipe_path': str(B / 'build-recipe.json'),
    'recipe_sha256': recipe_sha,
    'build_results_sha256': sha(B / 'build-results.json'),
    'source_head': recipe['source_head'],
    'behavior_engine_sha256': recipe['behavior_engine']['sha256'],
    'cli': recipe['cli'],
    'build_info': settings,
    'scope': recipe['scope'],
    'runtime_commands': 0,
    'cloud_commands': 0,
}
save(B / 'runtime-builds.json', manifest)
print(json.dumps(manifest), flush=True)
