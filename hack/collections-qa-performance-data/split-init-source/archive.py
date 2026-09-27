#!/usr/bin/env python3
"""Copy an explicit safe allowlist; no binaries, raw inittrace or runtime logs."""
from pathlib import Path
import hashlib
import json
import shutil

LAB = Path(__file__).resolve().parent
OUT = LAB / 'evidence-v2'
OUT.mkdir(exist_ok=True)
names = [
    'result-report.md', 'README.md', 'prepare.py', 'freeze.py', 'prepare-recipes.py',
    'validate.py', 'build.py', 'startup-micro.py', 'privileged-gate.py', 'archive.py',
    'prototype.patch', 'tests.patch', 'source-overlay.json', 'test-overlay.json',
    'manifest.json', 'independent-review.md', 'independent-review-inputs.json',
    'recipes-v3/recipe.json', 'recipes-v3/baseline-overlay.json',
    'recipes-v3/candidate-overlay.json', 'recipes-v3/test-overlay.json',
    'build-results-v1/runtime-builds.json',
    'validation-v1/results.json', 'validation-v2/results.json',
    'validation-v3/results.json', 'validation-v4/results.json',
    'privileged-gate-v1/results.json', 'startup-micro-v1/numeric.json',
]
for name in names:
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LAB / name, target)

manifest = json.loads((LAB / 'manifest.json').read_text())
source_names = {}
for name in manifest['inputs']:
    archived = 'source/' + name + '.txt'
    target = OUT / archived
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LAB / 'source' / name, target)
    source_names[archived] = name
    names.append(archived)
(OUT / 'archive-source-names.json').write_text(json.dumps(source_names, indent=2) + '\n')
names.append('archive-source-names.json')
checksums = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in names}
(OUT / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
names += ['checksums.json','allowlist.txt']
(OUT / 'allowlist.txt').write_text('\n'.join(names)+'\n')
print(json.dumps({'safe_files': len(names), 'allowlist': str(OUT / 'allowlist.txt')}))
