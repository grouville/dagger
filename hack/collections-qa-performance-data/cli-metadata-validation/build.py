from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, time
HERE=Path(__file__).resolve().parent
CLOSURE=HERE.parent/'collection-closure-v1'
REPO=Path('/home/dagger/dag')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x): Path(p).write_text(json.dumps(x,indent=2)+'\n')
p=argparse.ArgumentParser(); p.add_argument('--prepare',action='store_true'); p.add_argument('--run',action='store_true'); a=p.parse_args(); assert a.prepare != a.run
if a.prepare:
    parent_path=CLOSURE/'build-recipe.json'; parent=json.loads(parent_path.read_text())
    frozen=HERE/'session_workspaces.frozen.go'; shutil.copyfile(HERE/'session_workspaces.go',frozen)
    overlay=json.loads((CLOSURE/'engine-overlay.json').read_text())
    overlay['Replace'][str(REPO/'engine/server/session_workspaces.go')]=str(frozen)
    save(HERE/'engine-overlay.json',overlay)
    cmd=[('-overlay='+str(HERE/'engine-overlay.json')) if v.startswith('-overlay=') else str(HERE/'engine-json-demand') if v==str(CLOSURE/'engine-json-closure') else v for v in parent['command']]
    save(HERE/'build-recipe.json',{'parent_recipe':str(parent_path),'parent_recipe_sha256':sha(parent_path),'head':parent['head'],'environment':parent['environment'],'command':cmd,'inputs':{str(frozen):sha(frozen),str(HERE/'engine-overlay.json'):sha(HERE/'engine-overlay.json')},'difference':'The internal JSON metadata field now follows exactly the existing scoped and unscoped workspace module demand rules. All frozen JSON, collection closure, lazy core and SDK inputs retained; matched CLI binaries unchanged.'})
    print(HERE/'build-recipe.json'); raise SystemExit
recipe=json.loads((HERE/'build-recipe.json').read_text()); chain=[recipe]
while 'parent_recipe' in chain[-1]:
    child=chain[-1]; assert sha(child['parent_recipe'])==child['parent_recipe_sha256']
    chain.append(json.loads(Path(child['parent_recipe']).read_text()))
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==recipe['head']
changes=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=REPO,text=True).splitlines()
assert set(changes).issubset(chain[-1]['permitted_nonbuild_changes']),changes
for item in chain:
    for f,h in item['inputs'].items(): assert sha(f)==h,f
    for f in item.get('external_sources',[]): assert sha(f['path'])==f['sha256'],f['path']
validation=json.loads((HERE/'validation.json').read_text())
assert validation['baseline_expected_failures'] and len(validation['candidate'])==2 and all(x['exit_code']==0 for x in validation['candidate'])
env=os.environ.copy(); env.update(recipe['environment']); started=time.monotonic()
with (HERE/'engine-build.log').open('w') as f:
    result=subprocess.run(recipe['command'],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
row={'command':recipe['command'],'source_head':recipe['head'],'seconds':time.monotonic()-started,'exit_code':result.returncode,'recipe_sha256':sha(HERE/'build-recipe.json'),'profiling':False}
if result.returncode==0: row.update(binary=str(HERE/'engine-json-demand'),sha256=sha(HERE/'engine-json-demand'))
save(HERE/'build-results.json',row); print(json.dumps(row),flush=True)
if result.returncode: raise SystemExit(result.returncode)
runtime=json.loads((CLOSURE/'runtime-builds.json').read_text())
for key in ('baseline','candidate'): assert sha(runtime[key]['path'])==runtime[key]['sha256']
runtime['engine']={'path':row['binary'],'sha256':row['sha256']}; runtime['recipe_sha256']=row['recipe_sha256']; runtime['difference']+='; JSON endpoint participates in existing scoped/unscoped request module demand'; save(HERE/'runtime-builds.json',runtime)
