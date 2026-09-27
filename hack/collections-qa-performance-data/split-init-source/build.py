#!/usr/bin/env python3
"""Execute only the four reviewed matched build commands; no engine execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

LAB = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--run', action='store_true')
args = parser.parse_args()
recipe_path = LAB / 'recipes-v3/recipe.json'
recipe = json.loads(recipe_path.read_text())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

for path, expected in {**recipe['inputs'], **recipe['source_guards']}.items():
    assert digest(path) == expected, path
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=recipe['cwd'], text=True).strip() == recipe['source_head']
gates_path = LAB / 'validation-v4/results.json'
gates = json.loads(gates_path.read_text())
assert gates['recipe_sha256'] == digest(recipe_path)
assert len(gates['stages']) == 4 and all(s['exit_code'] == 0 for s in gates['stages'])
if not args.run:
    print(json.dumps(recipe['build_commands'], indent=2))
    raise SystemExit(0)
out = LAB / 'build-results-v1'
out.mkdir(exist_ok=False)
manifest = {'source_head': recipe['source_head'], 'recipe_path': str(recipe_path), 'recipe_sha256': digest(recipe_path), 'runner_sha256': digest(__file__), 'validation_sha256': digest(gates_path), 'builds': {}, 'engine_calls': 0, 'cloud_calls': 0, 'privileged_pid1_gate': 'not run'}
for stage in recipe['build_commands']:
    env = dict(os.environ)
    env.update(stage['environment'])
    log = out / (stage['name'] + '.log')
    start = time.monotonic()
    with log.open('wb') as f:
        proc = subprocess.run(stage['argv'], cwd=recipe['cwd'], env=env, stdout=f, stderr=subprocess.STDOUT, timeout=900)
    row = {'exit_code': proc.returncode, 'seconds': time.monotonic()-start, 'log_sha256': digest(log), 'command': stage['argv']}
    if proc.returncode == 0:
        binary = Path(stage['argv'][stage['argv'].index('-o')+1])
        info = subprocess.check_output([stage['argv'][0], 'version', '-m', str(binary)], cwd=recipe['cwd'], env=env, text=True)
        infofile = out / (stage['name'] + '-build-info.txt')
        infofile.write_text(info)
        row.update(path=str(binary), sha256=digest(binary), bytes=binary.stat().st_size, build_info_sha256=digest(infofile))
    manifest['builds'][stage['name']] = row
    (out / 'runtime-builds.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'name': stage['name'], 'exit_code': proc.returncode, 'seconds': round(row['seconds'],3), 'sha256': row.get('sha256')}), flush=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)
