"""Freeze matched engines from actual retained 6a82 source; no build/runtime."""
from pathlib import Path
import hashlib, json, shutil, subprocess

H = Path(__file__).resolve().parent
B = H / 'engine-builds-v2'
R = Path('/home/dagger/dag')
P = Path('/tmp/collections-perf/dang-admission-profile-v1/combined-build')
D = Path('/tmp/collections-perf/syntax-isolated/dang')
F = Path('/tmp/collections-perf/dang-trace-log-barrier-v1/profiling-6a82')
HEAD = '4f2ef6d70018b81f41d9b51140e76c82fe2fabab'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, v): p.write_text(json.dumps(v, indent=2) + '\n')

assert not B.exists(), 'preserve frozen recipes/results'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip() == HEAD
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=normal'], cwd=R, text=True).splitlines()
assert all(x[3:].startswith('hack/') for x in status), status
parent = json.loads((P/'build-recipe.json').read_text())
manifest = json.loads((P/'runtime-builds.json').read_text())
assert sha(P/'build-recipe.json') == manifest['recipe_sha256']
assert manifest['engine']['sha256'] == '6a82b8b305b8415e42cc451e3ec5bd56208ab20eadc87b6a1a8de2a9c6685b4a'
assert sha(H/'parse_cache.baseline.go') == 'b0f575ce0e8c7acc803e9aa7ae73e2a4da5d7b55ba21b2d02cdb04a0805258a0'
assert sha(H/'parse_cache.go') == '7b0a1e382973d482ab68ac16e82e369323e44e5f37c9914f7c97f83c8166836e'
assert all(sha(p) == expected for p, expected in parent['external_dependency_inputs'].items())
original = json.loads((P/'source-overlay.json').read_text())['Replace']
changed = subprocess.check_output(['git', 'diff', '--name-only', parent['source_head'], HEAD], cwd=R, text=True).splitlines()
assert all(p.startswith('hack/') or p.endswith('_test.go') or p in ('internal/cmd/dagger/artifacts.go','sdk/go/artifacts.go') for p in changed), changed
B.mkdir(); (B/'inputs').mkdir()
inputs, origins, replace = {}, {}, {}
def copy(source, dest):
    source, dest = Path(source), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    inputs[str(dest)] = sha(dest)
    origins[str(dest)] = {'path':str(source), 'sha256':sha(source)}

# Freeze the complete local module's Go sources and embedded inputs. Both arms
# use this same path and replacement; the shared syntax-isolated tree is never
# changed. All effective engine overrides are preserved separately below.
dependency_paths = set(Path(p) for p in parent['external_dependency_inputs'])
dependency_paths.update(D.glob('pkg/dang/prelude/*.dang'))
dependency_paths.update(p for p in (D/'.agents/skills').rglob('*') if p.is_file())
dependency_paths.add(D/'tests/gqlserver/schema.graphqls')
dependency_paths.update([D/'pkg/dang/highlights.scm', D/'pkg/introspection/introspection.graphql', D/'pkg/introspection/introspection_dagger.graphql'])
for source in sorted(dependency_paths): copy(source, B/'dependency/dang'/source.relative_to(D))
for i, (logical, physical) in enumerate(original.items()):
    destlogical = str(B/'dependency/dang'/Path(logical).relative_to(D)) if Path(logical).is_relative_to(D) else logical
    if not physical:
        replace[destlogical] = ''; continue
    assert sha(physical) == parent['inputs'][physical]
    dest = B/'inputs'/('base-%02d-'%i + Path(logical).name)
    copy(physical, dest); replace[destlogical] = str(dest)

# Preserve the effective parent for post-build committed CLI/SDK source changes
# too, even when no reachable engine code is expected to call those helpers.
for name in changed:
    if name.startswith('hack/') or name.endswith('_test.go'): continue
    logical = str(R/name)
    if logical in original: continue
    dest = B/'inputs'/('post-parent-'+name.replace('/','-'))
    found = subprocess.run(['git','show',parent['source_head']+':'+name],cwd=R,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if found.returncode:
        assert name == 'sdk/go/artifacts.go'
        replace[logical] = ''
        continue
    dest.write_bytes(found.stdout)
    inputs[str(dest)] = sha(dest)
    origins[str(dest)] = {'git_ref':parent['source_head'], 'git_path':name, 'sha256':sha(dest)}
    replace[logical] = str(dest)

fm = json.loads((F/'manifest.json').read_text())
session = str(R/'engine/server/session.go')
assert sha(original[session]) == fm['base_sha256']
assert sha(F/'session.go') == fm['candidate_sha256']
copy(F/'session.go', B/'inputs/session-flush-profile.go')
replace[session] = str(B/'inputs/session-flush-profile.go')
copy(F/'profiling-only.patch' if (F/'profiling-only.patch').exists() else F.parent/'profiling-only.patch', B/'common-profile-only.patch')

copy(P/'engine.mod', B/'engine.mod')
mod = (B/'engine.mod').read_text()
needle = 'replace github.com/vito/dang/v2 => ' + str(D)
assert mod.count(needle) == 1
(B/'engine.mod').write_text(mod.replace(needle, 'replace github.com/vito/dang/v2 => '+str(B/'dependency/dang')))
inputs[str(B/'engine.mod')] = sha(B/'engine.mod')
copy(P/'engine.sum', B/'engine.sum')
copy(H/'parse_cache.baseline.go', B/'inputs/parse_cache.baseline.go')
copy(H/'parse_cache.go', B/'inputs/parse_cache.candidate.go')
commands, overlays = {}, {}
key = str(B/'dependency/dang/pkg/dang/parse_cache.go')
assert sha(replace[key]) == sha(H/'parse_cache.baseline.go')
for variant in ('baseline', 'candidate'):
    mapping = dict(replace); mapping[key] = str(B/'inputs'/('parse_cache.'+variant+'.go'))
    overlay = B/(variant+'-overlay.json'); save(overlay, {'Replace':mapping})
    inputs[str(overlay)] = sha(overlay); overlays[variant] = str(overlay)
    commands[variant] = [parent['go']['path'], 'build', '-mod=readonly', '-modfile='+str(B/'engine.mod'), '-buildvcs=true', '-overlay='+str(overlay), '-o', str(B/('engine-'+variant)), './cmd/engine']
a, b = (json.loads(Path(overlays[v]).read_text())['Replace'] for v in ('baseline','candidate'))
assert [k for k in a if a[k] != b[k]] == [key]
recipe = {
    'source_head':HEAD, 'source_dirty_state':status, 'allowed_dirty_prefixes':['hack/'],
    'parent_recipe_path':str(P/'build-recipe.json'), 'parent_recipe_sha256':sha(P/'build-recipe.json'),
    'parent_manifest_path':str(P/'runtime-builds.json'), 'parent_manifest_sha256':sha(P/'runtime-builds.json'),
    'effective_parent_engine':manifest['engine'], 'post_parent_changed_paths':changed,
    'inputs':inputs, 'origins':origins, 'external_dependency_origins':parent['external_dependency_inputs'],
    'overlays':overlays, 'commands':commands, 'go':parent['go'], 'cli':parent['cli'], 'environment':parent['environment'],
    'sole_variant_source':key, 'baseline_source_sha256':sha(H/'parse_cache.baseline.go'), 'candidate_source_sha256':sha(H/'parse_cache.go'),
    'common_profile_source_sha256':fm['candidate_sha256'], 'common_profile_patch_sha256':sha(B/'common-profile-only.patch'),
    'scope':'Actual retained 6a82 stack plus identical fixed-label telemetry flush profiling in both arms. Sole behavior difference: cloneSyntax in-place copying versus retained leaf-fastpath baseline. Same new VCS stamp and local dependency path, no module/SDK/evaluation/cache-policy changes.',
    'runtime_commands':0, 'cloud_commands':0,
}
save(B/'build-recipe.json',recipe)
print(json.dumps({'recipe':str(B/'build-recipe.json'), 'sha256':sha(B/'build-recipe.json'), 'overlays':len(replace), 'frozen_dependency_files':len(dependency_paths), 'commands':commands}))
