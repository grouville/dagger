"""Freeze and sequentially build matched ordinary engines; no runtime actions."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time
H=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');B=H/'builds';PARENT=H.parent/'cli-typedef-json-v1';DEMAND=H.parent/'root-demand-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args();assert a.prepare!=a.run
if a.prepare:
 assert not(B/'build-recipe.json').exists();B.mkdir(exist_ok=True);(B/'inputs').mkdir(exist_ok=True)
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();assert head==json.loads((H/'source-provenance.json').read_text())['head']
 changes=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=R,text=True).splitlines();assert set(changes).issubset({'hack/collections-bootstrap-performance.md'}),changes
 previous=json.loads((PARENT/'build-recipe.json').read_text());common={};mapping=[]
 for index,(original,source)in enumerate(json.loads((DEMAND/'engine-overlay.json').read_text())['Replace'].items()):
  assert Path(source).is_file();target=B/'inputs'/f'{index:02d}-{Path(source).name}';shutil.copyfile(source,target);common[original]=str(target)
  mapping.append({'original':original,'source':source,'frozen':str(target),'sha256':sha(target),'matches_current_shared':Path(original).is_file()and sha(original)==sha(source)})
 baseline={'Replace':common.copy()};candidate={'Replace':common.copy()}
 for name,original in [('module.go','core/schema/module.go'),('coremod.go','core/schema/coremod.go'),('module_typedef_bulk.go','core/schema/module_typedef_bulk.go')]:
  target=B/'inputs'/('bulk-'+name);shutil.copyfile(H/name,target);candidate['Replace'][str(R/original)]=str(target)
 for name in ['engine.mod','engine.sum']:shutil.copyfile(PARENT/name,B/name)
 save(B/'baseline-overlay.json',baseline);save(B/'candidate-overlay.json',candidate)
 commands={v:[previous['commands']['engine-json'][0],'build','-mod=readonly','-modfile='+str(B/'engine.mod'),'-buildvcs=true','-overlay='+str(B/(v+'-overlay.json')),'-o',str(B/('engine-'+v)),'./cmd/engine']for v in ['baseline','candidate']}
 source_inputs={str(f):sha(f)for f in (B/'inputs').iterdir()}
 source_inputs.update({str(B/f):sha(B/f)for f in ['engine.mod','engine.sum','baseline-overlay.json','candidate-overlay.json']})
 external=previous['external_sources'];assert all(sha(f['path'])==f['sha256']for f in external)
 save(B/'build-recipe.json',{'source_head':head,'permitted_nonbuild_changes':['hack/collections-bootstrap-performance.md'],'tracked_nonbuild_changes':changes,'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=R,text=True).strip(),'environment':previous['environment'],'commands':commands,'inputs':source_inputs,'external_sources':external,'inherited_overlay_mapping':mapping,'parent_frozen_stack_sha256':sha(DEMAND/'engine-overlay.json'),'validation_sha256':sha(H/'validation-v1/results.json'),'benchmark_sha256':sha(H/'benchmark-v1/results.json'),'ordinary':True,'difference':'Candidate adds private object/interface __withFunctions and batches only core object-like function attachment. Baseline is committed source plus unchanged historical SDK/Dang/collections overlay. Same frozen experimental stack and dependency pins in both. No held span/log/interner candidates.'})
 print(json.dumps({'recipe':str(B/'build-recipe.json'),'sha256':sha(B/'build-recipe.json'),'engines':['baseline','candidate'],'source_head':head}),flush=True);raise SystemExit
r=json.loads((B/'build-recipe.json').read_text());assert json.loads((H/'validation-v1/results.json').read_text())['all_expected_results'];env=os.environ.copy();env.update(r['environment']);results=[]
for variant,cmd in r['commands'].items():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==r['source_head']
 changes=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=R,text=True).splitlines();assert changes==r['tracked_nonbuild_changes'],changes
 for f,h in r['inputs'].items():assert sha(f)==h,f
 for f in r['external_sources']:assert sha(f['path'])==f['sha256'],f['path']
 start=time.monotonic()
 with(B/('build-'+variant+'.log')).open('w')as f:proc=subprocess.run(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
 row={'variant':variant,'exit_code':proc.returncode,'seconds':time.monotonic()-start,'path':str(B/('engine-'+variant))}
 if proc.returncode==0:row['sha256']=sha(row['path'])
 results.append(row);save(B/'build-results.json',results);print(json.dumps(row),flush=True);assert proc.returncode==0
save(B/'runtime-builds.json',{'source_head':r['source_head'],'recipe_sha256':sha(B/'build-recipe.json'),'variants':{v['variant']:{'path':v['path'],'sha256':v['sha256']}for v in results},'profiling':False,'difference':r['difference']})
