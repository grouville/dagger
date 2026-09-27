from pathlib import Path
import hashlib, json, difflib
D=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');B=Path('/tmp/collections-perf/catalog-next-levers-v1/git-http/builds')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
base=json.loads((B/'recipe.json').read_text())
for p,h in base['inputs'].items():
 if sha(p)!=h:raise RuntimeError('changed baseline: '+p)
source=json.loads((B/'engine-overlay.json').read_text());test=json.loads((B/'test-overlay.json').read_text())
for n in ['session_workspaces.go','module_load_pipeline.go']:
 target=str(R/'engine/server'/n);source['Replace'][target]=str(D/n);test['Replace'][target]=str(D/n)
test['Replace'][str(R/'engine/server/module_load_pipeline_test.go')]=str(D/'module_load_pipeline_test.go')
write(D/'engine-overlay.json',source);write(D/'test-overlay.json',test)
patch=[]
for n in ['session_workspaces.go','module_load_pipeline.go','module_load_pipeline_test.go']:
 old=D/'session_workspaces.baseline.go' if n=='session_workspaces.go' else R/'engine/server'/n
 patch.extend(difflib.unified_diff(old.read_text().splitlines(True)if old.exists()else[],(D/n).read_text().splitlines(True),fromfile='a/engine/server/'+n,tofile='b/engine/server/'+n))
(D/'prototype.patch').write_text(''.join(patch))
regex='^(TestModuleLoadPipeline.*|TestGatherModuleLoadRequests|TestModuleLoadParallelism|TestModuleLoadErr|TestDedupeResolvedModuleLoads.*|TestResolvedModuleLoadIdentity|TestArbitrateSameSourceEntrypointNominations|TestArbitrateResolvedModuleLoads)$'
common=[base['build_command'][0],'test','-json','-mod=readonly','-modfile='+str(B/'engine.mod'),'-overlay='+str(D/'test-overlay.json'),'-count=1','-timeout=90s','-run',regex,'./engine/server']
inputs={p:sha(p)for p in sorted(set(source['Replace'].values())|set(test['Replace'].values()))}
inputs.update({str(D/n):sha(D/n)for n in ['freeze.py','prepare_source.py','run_validation.py','engine-overlay.json','test-overlay.json','prototype.patch','session_workspaces.baseline.go']})
cmd=[('-overlay='+str(D/'engine-overlay.json'))if a.startswith('-overlay=')else str(D/'engine-candidate')if a==str(B/'engine-diagnostic')else a for a in base['build_command']]
write(D/'recipe.json',{'status':'prepared only: no test/build/runtime executed','baseline_recipe':str(B/'recipe.json'),'baseline_recipe_sha256':sha(B/'recipe.json'),'baseline_engine':json.loads((B/'manifest.json').read_text())['engine'],'source_head':base['source_head'],'frozen_parent_source_head':base['frozen_parent_source_head'],'environment':base['environment'],'test_environments':base['test_environments'],'test_commands':{'normal':common,'race':common[:2]+['-race']+common[2:]},'build_command':cmd,'inputs':inputs,'limits':{'whole_jobs_before':8,'whole_jobs_after':16,'source_after':8,'registration_after':8,'nested_work':'unchanged, not bounded by these top-level permits'},'scope':'Only workspace batch scheduling and source/asModule factoring. Same cache keys, contexts, source legacy policies and final publication barrier. Existing diagnostic Git/context instrumentation is common to control and candidate.'})
print(json.dumps({'recipe_sha256':sha(D/'recipe.json'),'source_sha256':sha(D/'session_workspaces.go'),'patch_sha256':sha(D/'prototype.patch')}))
