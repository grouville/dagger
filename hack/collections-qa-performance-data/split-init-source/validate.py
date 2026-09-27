#!/usr/bin/env python3
"""Run only reviewed focused normal/race tests. No engine builds or runtime."""
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
parser.add_argument('--output', required=True)
args = parser.parse_args()
recipepath = LAB / 'recipes-v3/recipe.json'
recipe = json.loads(recipepath.read_text())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

for path, expected in {**recipe['inputs'], **recipe['source_guards']}.items():
    assert digest(path) == expected, path
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=recipe['cwd'], text=True).strip() == recipe['source_head']
if not args.run:
    print(json.dumps(recipe['validation_commands'], indent=2))
    raise SystemExit(0)
out = Path(args.output)
out.mkdir(parents=True, exist_ok=False)
result = {'recipe_sha256': digest(recipepath), 'runner_sha256': digest(__file__), 'source_head': recipe['source_head'], 'stages': [], 'privileged_pid1_gate': 'not run; explicit privilege required', 'cloud_calls': 0, 'engine_calls': 0}
for stage in recipe['validation_commands']:
    env = dict(os.environ)
    env.update(stage['environment'])
    env.pop('DAGGER_TEST_INIT_PID_NAMESPACE', None)
    log = out / (stage['name'].replace('.', '_') + '.log')
    start = time.monotonic()
    with log.open('wb') as f:
        proc = subprocess.run(stage['argv'], cwd=recipe['cwd'], env=env, stdout=f, stderr=subprocess.STDOUT, timeout=900)
    text = log.read_text(errors='replace')
    row = {'name': stage['name'], 'exit_code': proc.returncode, 'seconds': time.monotonic()-start, 'log_sha256': digest(log), 'log': str(log), 'passed': [s for s in text.splitlines() if s.lstrip().startswith('--- PASS:')], 'skipped': [s for s in text.splitlines() if s.lstrip().startswith('--- SKIP:')], 'failed': [s for s in text.splitlines() if s.lstrip().startswith('--- FAIL:')]}
    result['stages'].append(row)
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'name': row['name'], 'exit_code': row['exit_code'], 'seconds': round(row['seconds'],3), 'passed_cases': len(row['passed']), 'skipped_cases': len(row['skipped']), 'failed_cases': len(row['failed'])}), flush=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)
