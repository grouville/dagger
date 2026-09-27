"""Verify frozen composite sources and build two matched engines sequentially."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, time
H=Path(__file__).resolve().parent; B=H/'engine-builds-v2'; R=Path('/home/dagger/dag')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');a=p.parse_args()
r=json.loads((B/'build-recipe.json').read_text()); rh=sha(B/'build-recipe.json')
def verify():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==r['source_head']
 status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=normal'],cwd=R,text=True).splitlines()
 assert all(any(line[3:].startswith(p)for p in r['allowed_dirty_prefixes'])for line in status),status
 for group in ('inputs','external_dependency_origins'):
  for path,want in r[group].items():assert sha(path)==want,'changed input: '+path
 assert sha(r['go']['path'])==r['go']['sha256']
 assert sha(r['parent_recipe_path'])==r['parent_recipe_sha256']
 assert sha(r['parent_manifest_path'])==r['parent_manifest_sha256']
 return status
if not a.run:
 print(json.dumps({'prepared_only':True,'recipe_sha256':rh,'commands':r['commands'],'scope':r['scope']}));raise SystemExit
assert not(B/'build-results.json').exists(),'preserve previous attempt'
results={'recipe_sha256':rh,'runner_sha256':sha(__file__),'preflight_status':verify(),'variants':{},'runtime_commands':0,'cloud_commands':0}
for variant in ('baseline','candidate'):
 verify();log=B/(variant+'.build.private.log');started=time.monotonic();row={}
 try:
  with log.open('wb')as f:proc=subprocess.run(r['commands'][variant],cwd=R,env={**os.environ,**r['environment']},stdout=f,stderr=subprocess.STDOUT,timeout=300)
  row['exit_code']=proc.returncode
 finally:
  row.update(seconds=time.monotonic()-started,log_sha256=sha(log)if log.exists()else None)
  results['variants'][variant]=row;save(B/'build-results.json',results)
 assert row.get('exit_code')==0,'build failed: '+variant
 verify();binary=B/('engine-'+variant)
 info=subprocess.check_output([r['go']['path'],'version','-m',str(binary)],text=True);settings={}
 for line in info.splitlines():
  f=line.strip().split('\t')
  if len(f)==2 and f[0]=='build'and'='in f[1]:
   k,v=f[1].split('=',1)
   if k in ('vcs.revision','vcs.time','vcs.modified','GOOS','GOARCH','CGO_ENABLED'):settings[k]=v
 assert settings['vcs.revision']==r['source_head']
 version='v'+(R/'internal/version/VERSION').read_text().strip().removeprefix('v')+'+'+settings['vcs.revision'][:8]+('.dirty'if settings['vcs.modified']=='true'else'')
 row.update(path=str(binary),sha256=sha(binary),build_info=settings,expected_core_version=version);save(B/'build-results.json',results)
assert results['variants']['baseline']['build_info']==results['variants']['candidate']['build_info']
runtime={'source_head':r['source_head'],'recipe_path':str(B/'build-recipe.json'),'recipe_sha256':rh,'build_results_sha256':sha(B/'build-results.json'),'cli':r['cli'],'scope':r['scope'],'variants':{}}
for variant,row in results['variants'].items():
 m={'engine':{k:row[k]for k in ('path','sha256','exit_code')},'expected_core_version':row['expected_core_version'],'recipe_path':str(B/'build-recipe.json'),'recipe_sha256':rh,'source_head':r['source_head'],'effective_parent_engine_sha256':r['effective_parent_engine']['sha256'],'cli':r['cli'],'build_info':row['build_info'],'variant':variant,'runtime_commands':0,'cloud_commands':0}
 # The ancestry value is read from the reviewed parent lineage, not guessed.
 ancestry=json.loads(Path('/tmp/collections-perf/go-base-address-v1/builds/runtime-builds.json').read_text())
 m['baseline_ancestry_engine_sha256']=ancestry['baseline_ancestry_engine_sha256']
 save(B/(variant+'-runtime-builds.json'),m);runtime['variants'][variant]={'manifest_path':str(B/(variant+'-runtime-builds.json')),'manifest_sha256':sha(B/(variant+'-runtime-builds.json')),**m}
save(B/'runtime-builds.json',runtime)
print(json.dumps(runtime),flush=True)
