"""Freeze one diagnostic engine: effective 38711 + Dang/readiness labels only."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil
import subprocess

H = Path(__file__).resolve().parent
B = H / 'combined-build'
R = Path('/home/dagger/dag')
P = Path('/tmp/collections-perf/go-base-address-v1/builds')
READINESS = Path('/tmp/collections-perf/warm-audit/module-load-overlap/prototype.patch')
EXPECTED_PARENT = 'a792a80404bbc94bd681f5634a551879c0a69c061f006d2f22abe212540769ac'
EXPECTED_READINESS = '3f1ed07fe392933abf4a6d70267d445db5f1a3a774376551095b6fd7511c5e67'
EXPECTED_HEAD = 'b0fda131f2dd9f035c46405dd4e57a4b1f16f2c1'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n')


assert not (B / 'build-recipe.json').exists(), 'already frozen'
assert sha(P / 'runtime-builds.json') == EXPECTED_PARENT
assert sha(READINESS) == EXPECTED_READINESS
parent = json.loads((P / 'build-recipe.json').read_text())
parent_manifest = json.loads((P / 'runtime-builds.json').read_text())
assert sha(P / 'build-recipe.json') == parent_manifest['recipe_sha256']
assert parent_manifest['engine']['sha256'] == '38711bd2b42e410f9fbf601d4260b47718e8169f7ff1d2caa29313adfba4569c'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()
assert head == EXPECTED_HEAD
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=normal'], cwd=R, text=True).splitlines()
assert all(line[3:].startswith('hack/') for line in status), status
B.mkdir(exist_ok=True)
(B / 'inputs').mkdir(exist_ok=True)
replace = {}
inputs = {}
origins = {}
parent_overlay = json.loads((P / 'source-overlay.json').read_text())['Replace']
for i, (logical, physical) in enumerate(parent_overlay.items()):
    if not physical:
        replace[logical] = ''
        continue
    assert sha(physical) == parent['inputs'][physical]
    target = B / 'inputs' / ('base-%02d-' % i + Path(logical).name)
    shutil.copyfile(physical, target)
    replace[logical] = str(target)
    inputs[str(target)] = sha(target)
    origins[str(target)] = {'path': physical, 'sha256': sha(physical)}

# Every committed production difference since the 38711 build is already
# replaced by its frozen effective source. New tests/docs do not enter a build.
changed = subprocess.check_output(['git', 'diff', '--name-only', parent['source_head'], head], cwd=R, text=True).splitlines()
for name in changed:
    assert name.startswith('hack/') or name.endswith('_test.go') or str(R / name) in parent_overlay, name

dang_manifest = json.loads((H / 'manifest.json').read_text())
assert dang_manifest['parent_engine_manifest_sha256'] == EXPECTED_PARENT
assert sha(H / 'prototype.patch') == dang_manifest['patch_sha256']
diagnostic_sources = json.loads((H / 'source-overlay.json').read_text())['Replace']
for logical, physical in diagnostic_sources.items():
    original = dang_manifest['effective_originals'][str(Path(logical).relative_to(R))]
    effective = parent_overlay.get(logical, logical)
    assert effective and sha(effective) == original['sha256']
    assert sha(physical) == dang_manifest['sources'][logical]
    target = B / 'inputs' / ('diagnostic-' + str(Path(logical).relative_to(R)).replace('/', '-'))
    shutil.copyfile(physical, target)
    replace[logical] = str(target)
    inputs[str(target)] = sha(target)
    origins[str(target)] = {'path': physical, 'sha256': sha(physical)}

logical = str(R / 'engine/server/session_workspaces.go')
original = Path(parent_overlay[logical]).read_text()
source = original.replace('"github.com/dagger/dagger/engine/telemetryattrs"', '"github.com/dagger/dagger/engine/telemetryattrs"\n\t"github.com/dagger/dagger/engine/wcprof"', 1)
needle = '\t\t\tresolved, err := srv.resolveModuleLoad(ctx, client.dag, load)\n'
assert source.count(needle) == 1
marker = '''\t\t\t// Resolve readiness is distinct from publication: the batch still
\t\t\t// arbitrates and installs successful modules after all jobs finish.
\t\t\tvar loadOp *wcprof.Op
\t\t\tif wcprof.Enabled(ctx) {
\t\t\t\tctx, loadOp = wcprof.BeginOp(ctx, wcprof.OpKindSessionPhase, "workspace.moduleLoad", wcprof.OpOpts{
\t\t\t\t\tIdent:    pendingModuleCliName(load.mod),
\t\t\t\t\tClientID: client.clientID,
\t\t\t\t})
\t\t\t}
'''
source = source.replace(needle, marker + needle + '\t\t\tloadOp.EndErr(err)\n', 1)
target = B / 'inputs' / 'diagnostic-session_workspaces.go'
target.write_text(source)
replace[logical] = str(target)
inputs[str(target)] = sha(target)
origins[str(target)] = {'path': parent_overlay[logical], 'sha256': sha(parent_overlay[logical]), 'readiness_marker_patch_sha256': EXPECTED_READINESS}
readiness_diff = ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile='a/engine/server/session_workspaces.go', tofile='b/engine/server/session_workspaces.go'))
(B / 'readiness-only.patch').write_text(readiness_diff)
(B / 'diagnostic.patch').write_text((H / 'prototype.patch').read_text() + readiness_diff)

for name in ('engine.mod', 'engine.sum'):
    assert sha(P / name) == parent['inputs'][str(P / name)]
    shutil.copyfile(P / name, B / name)
    inputs[str(B / name)] = sha(B / name)
save(B / 'source-overlay.json', {'Replace': replace})
for p in (B / 'source-overlay.json', B / 'readiness-only.patch', B / 'diagnostic.patch'):
    inputs[str(p)] = sha(p)
command = [parent['go']['path'], 'build', '-mod=readonly', '-modfile=' + str(B / 'engine.mod'), '-buildvcs=true', '-overlay=' + str(B / 'source-overlay.json'), '-o', str(B / 'engine-diagnostic'), './cmd/engine']
recipe = {
    'status': 'prepared only; not built or run',
    'source_head': head,
    'source_dirty_state': status,
    'allowed_dirty_prefixes': ['hack/'],
    'behavior_engine': parent_manifest['engine'],
    'behavior_source_head': parent['source_head'],
    'parent_recipe_path': str(P / 'build-recipe.json'),
    'parent_recipe_sha256': sha(P / 'build-recipe.json'),
    'parent_manifest_path': str(P / 'runtime-builds.json'),
    'parent_manifest_sha256': EXPECTED_PARENT,
    'dang_profile_manifest_sha256': sha(H / 'manifest.json'),
    'readiness_origin_patch_sha256': EXPECTED_READINESS,
    'post_parent_changed_paths': changed,
    'inputs': inputs,
    'origins': origins,
    'external_dependency_inputs': parent['external_dependency_inputs'],
    'go': parent['go'],
    'cli': parent['cli'],
    'environment': parent['environment'],
    'command': command,
    'scope': 'Effective 38711 plus seven fixed-label Dang boundaries and the canonical workspace.moduleLoad readiness-only marker. No scheduling, cache, authority, lifetime, API or session behavior changes. New build uses its own current VCS stamp, not the original 2088 stamp.',
    'privacy': 'Raw wcprof module Ident and client IDs remain private. Public reductions allowlist known public aliases and emit no operation/client/source IDs or arbitrary names.',
    'runtime_commands': 0,
    'cloud_commands': 0,
}
save(B / 'build-recipe.json', recipe)
print(json.dumps({'recipe': str(B / 'build-recipe.json'), 'recipe_sha256': sha(B / 'build-recipe.json'), 'diagnostic_patch_sha256': sha(B / 'diagnostic.patch'), 'source_head': head, 'overlay_entries': len(replace)}))
