#!/usr/bin/env python3
"""Freeze prepared source/test evidence only, without compiling or executing it."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

ROOT = Path('/home/dagger/dag')
LAB = Path(__file__).resolve().parent
SRC = LAB / 'source'
AUDIT = LAB.parent / 'init-startup-audit-v1'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

tests = ['cmd/init-lite/main_test.go', 'engine/engineutil/init_split_test.go']
overlay = json.loads((LAB / 'source-overlay.json').read_text())
manifest = json.loads((LAB / 'manifest.json').read_text())
patch = []
for name in tests:
    overlay['Replace'][str(ROOT / name)] = str(SRC / name)
    manifest['inputs'][name] = {'before_sha256': None, 'after_sha256': digest(SRC / name), 'kind': 'test; not run'}
    patch.extend(difflib.unified_diff([], (SRC / name).read_text().splitlines(True), fromfile='/dev/null', tofile='b/' + name))
(LAB / 'test-overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
(LAB / 'tests.patch').write_text(''.join(patch))
old = (ROOT / 'cmd/init/main.go').read_text()
new = (SRC / 'cmd/init-lite/main.go').read_text()
def init_body(s):
    return s[s.index('func mainInit() error {'):s.index('func startSessionSubprocess() error {')]
assert init_body(old) == init_body(new), 'PID1 behavior body changed'
manifest['mainInit_byte_identical_to_original'] = True
manifest['validation'] = {'formatting': 'gofmt only', 'tests': 'not run', 'builds': 'not run', 'engine_calls': 0, 'cloud_calls': 0}
(LAB / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

source_refs = [
    'cmd/init/main.go', 'engine/engineutil/executor_spec.go', 'engine/engineutil/executor.go',
    '.dagger/modules/engine-dev/build/builder.go', 'engine/distconsts/consts.go',
    'engine/server/session.go', 'engine/server/session_attachables.go',
    'engine/session/git/git_credential.go', 'engine/client/secretprovider/cmd.go',
]
audit_manifest = {'head': manifest['head'], 'status': 'source only; no new runtime evidence', 'sources': {p: digest(ROOT / p) for p in source_refs}}
prior = LAB.parent / 'collection-expansion-audit-v1/runtime-summary.json'
audit_manifest['prior_numeric_summary_sha256'] = digest(prior)
shutil.copyfile(prior, AUDIT / 'prior-runtime-summary.json')
(AUDIT / 'sources.json').write_text(json.dumps(audit_manifest, indent=2) + '\n')
(AUDIT / 'allowlist.txt').write_text('review.md\nsources.json\nprior-runtime-summary.json\nallowlist.txt\n')

out = LAB / 'evidence-v1'
out.mkdir(exist_ok=True)
allow = []
for name in ['README.md', 'prepare.py', 'freeze.py', 'prototype.patch', 'tests.patch', 'source-overlay.json', 'test-overlay.json', 'manifest.json']:
    shutil.copyfile(LAB / name, out / name)
    allow.append(name)
names = {}
for original in manifest['inputs']:
    archive = 'source/' + original + '.txt'
    target = out / archive
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC / original, target)
    allow.append(archive)
    names[archive] = original
(out / 'archive-source-names.json').write_text(json.dumps(names, indent=2) + '\n')
allow.append('archive-source-names.json')
checksums = {name: digest(out / name) for name in allow}
(out / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
allow += ['checksums.json', 'allowlist.txt']
(out / 'allowlist.txt').write_text('\n'.join(allow) + '\n')
