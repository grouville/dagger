#!/usr/bin/env python3
"""Prepare exact commands and source guards. Does not run Go or engines."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/home/dagger/dag')
LAB = Path(__file__).resolve().parent
PARENT = Path('/tmp/collections-perf/catalog-next-levers-v1/git-http/builds')
OUT = LAB / 'recipes-v3'
OUT.mkdir(exist_ok=True)

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + '\n')

parent = json.loads((PARENT / 'recipe.json').read_text())
old = json.loads((PARENT / 'manifest.json').read_text())
own = json.loads((LAB / 'manifest.json').read_text())
for p, want in parent['inputs'].items():
    assert digest(p) == want, p
assert old['engine']['sha256'] == 'ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'
assert parent['source_head'] == own['head']
base = json.loads((PARENT / 'engine-overlay.json').read_text())['Replace']

# Both arms use exactly the same newly compiled heavy helper. It understands
# both old /.init and new /.dagger-session names. Only PID1/mount wiring differs.
common = dict(base)
for name in ['cmd/init/main.go', 'engine/distconsts/consts.go']:
    common[str(ROOT / name)] = str(LAB / 'source' / name)
candidate = dict(common)
for name in ['cmd/init-lite/main.go', 'engine/engineutil/executor_spec.go']:
    candidate[str(ROOT / name)] = str(LAB / 'source' / name)
tests = dict(candidate)
for name in ['cmd/init-lite/main_test.go', 'engine/engineutil/init_split_test.go']:
    tests[str(ROOT / name)] = str(LAB / 'source' / name)
write('baseline-overlay.json', {'Replace': common})
write('candidate-overlay.json', {'Replace': candidate})
write('test-overlay.json', {'Replace': tests})

go = parent['build_command'][0]
modfile = '-modfile=' + str(PARENT / 'engine.mod')
commonflags = [go, '-mod=readonly', modfile]
build_env = parent['environment']
test_env = dict(build_env, CGO_ENABLED='1')
test_commands = []
for race in [False, True]:
    for pkg, pattern in [('./cmd/init-lite', '^TestSplitInit'), ('./engine/engineutil', '^TestSplitInitMounts$')]:
        test_commands.append({'name': ('race' if race else 'normal') + '-' + pkg.replace('/', '-'), 'argv': [go, 'test', '-mod=readonly', modfile, '-overlay=' + str(OUT / 'test-overlay.json'), *(['-race'] if race else []), pkg, '-run=' + pattern, '-count=1', '-v', '-timeout=90s'], 'environment': test_env})

builds = []
for label, overlay, pkg, flags in [
    ('engine-baseline', 'baseline-overlay.json', './cmd/engine', []),
    ('engine-candidate', 'candidate-overlay.json', './cmd/engine', []),
    ('dagger-init-common', 'baseline-overlay.json', './cmd/init', ['-tags=dfexcludepatterns,dfparents', '-ldflags=-s -w']),
    ('dagger-init-lite', 'candidate-overlay.json', './cmd/init-lite', ['-tags=dfexcludepatterns,dfparents', '-ldflags=-s -w']),
]:
    builds.append({'name': label, 'argv': [go, 'build', '-mod=readonly', modfile, '-buildvcs=true', '-overlay=' + str(OUT / overlay), *flags, '-o', str(OUT / label), pkg], 'environment': build_env})

inputs = dict(parent['inputs'])
for p in [PARENT / 'manifest.json', PARENT / 'recipe.json', LAB / 'manifest.json', LAB / 'prototype.patch', LAB / 'tests.patch', Path(__file__)]:
    inputs[str(p)] = digest(p)
for name in own['inputs']:
    p = LAB / 'source' / name
    inputs[str(p)] = digest(p)
for name in ['baseline-overlay.json', 'candidate-overlay.json', 'test-overlay.json']:
    inputs[str(OUT / name)] = digest(OUT / name)

recipe = {
    'status': 'prepared only; commands not run', 'source_head': own['head'],
    'cwd': str(ROOT), 'parent_engine': old['engine'],
    'parent_recipe_sha256': digest(PARENT / 'recipe.json'),
    'expected_core_version': old['expected_core_version'],
    'inputs': inputs, 'source_guards': {str(ROOT / p): meta['before_sha256'] for p, meta in own['inputs'].items() if meta['before_sha256']},
    'validation_commands': test_commands, 'build_commands': builds,
    'privileged_gate': {'status': 'not run; separate task-owned privileged environment required', 'environment': dict(test_env, DAGGER_TEST_INIT_PID_NAMESPACE='1'), 'argv': [go, 'test', '-mod=readonly', modfile, '-overlay=' + str(OUT / 'test-overlay.json'), './cmd/init-lite', '-run=^TestSplitInitPIDNamespaceReaping$', '-count=1', '-timeout=60s']},
    'packaging': {'common_host_artifacts': {'/usr/local/bin/dagger-init': str(OUT / 'dagger-init-common'), '/usr/local/bin/dagger-init-lite': str(OUT / 'dagger-init-lite')}, 'baseline_mount': {'/.init': '/usr/local/bin/dagger-init'}, 'candidate_mounts': {'/.init': '/usr/local/bin/dagger-init-lite', '/.dagger-session': '/usr/local/bin/dagger-init'}, 'sdk_payload': 'unchanged frozen ec6 experimental stack, same image and content payloads in both arms', 'engine_binary_only_swap_is_insufficient': True},
    'runtime_preconditions': ['Normal/race and explicitly privileged PID1 gate must pass before runtime.', 'Root must review and grant each build/runtime slot separately.', 'Compare the same newly built heavy binary in both arms, not the existing image helper.', 'Record actual binary SHA256 and Go build info after builds.', 'Verify both readonly mounts and nested Go/Python/TypeScript calls.', 'Use distinct first-seen input contents to force uncached exec, keeping result identity and fixtures controlled.', 'Include full CLI cleanup; ordinary measurements have profiling disabled.'],
    'cloud_calls': 0, 'runtime_calls': 0,
}
write('recipe.json', recipe)
