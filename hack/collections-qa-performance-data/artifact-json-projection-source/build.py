#!/usr/bin/env python3
"""Run only the reviewed two frozen offline CLI builds when --run is present."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
P=Path(__file__).resolve().parent;B=P/'builds-v1';R=Path('/home/dagger/dag')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def guard(recipe):
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip()==recipe['current_build_vcs_head']
 for name,want in recipe['source_guards'].items():assert(sha(name)if Path(name).exists()else None)==want,name
 changed=subprocess.check_output(['git','diff','--no-renames','--name-only',recipe['historical_effective_source'],'--',':!hack/**'],cwd=R).decode().splitlines()
 assert set(changed)==set(recipe['post_historical_source_differences'])
 for section in ('inputs','external_local_dependencies'):
  for path,want in recipe[section].items():assert sha(path)==want,path
 assert sha(recipe['validation_path'])==recipe['validation_sha256']
 assert sha(recipe['parent_cli']['path'])==recipe['parent_cli']['sha256']
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
recipe=json.loads((B/'build-recipe.json').read_text());guard(recipe)
if not a.run:print(json.dumps({'execute':False,'commands':recipe['commands'],'engine_calls':0,'cloud_calls':0}));raise SystemExit(0)
assert not(B/'build-results.json').exists();rows=[]
env={**os.environ,**recipe['environment'],'GOSUMDB':'off'}
for variant,command in recipe['commands'].items():
 guard(recipe);begin=time.monotonic()
 with(B/('build-'+variant+'.private.log')).open('wb')as out:proc=subprocess.run(command,cwd=R,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=300)
 binary=B/('dagger-'+variant)
 row={'variant':variant,'exit_code':proc.returncode,'build_seconds':time.monotonic()-begin,'path':str(binary),'sha256':sha(binary)if proc.returncode==0 else None,'log_sha256':sha(B/('build-'+variant+'.private.log'))};rows.append(row);save(B/'build-results.json',{'builds':rows,'recipe_sha256':sha(B/'build-recipe.json'),'build_driver_sha256':sha(__file__)})
 print(json.dumps(row),flush=True);assert proc.returncode==0
 row['go_build_info']=subprocess.check_output([recipe['toolchain'],'version','-m',str(binary)],cwd=R,env=env).decode();guard(recipe)
save(B/'build-results.json',{'builds':rows,'recipe_sha256':sha(B/'build-recipe.json'),'build_driver_sha256':sha(__file__)})
save(B/'runtime-builds.json',{'baseline':{k:rows[0][k]for k in ('path','sha256','exit_code')},'candidate':{k:rows[1][k]for k in ('path','sha256','exit_code')},'historical_effective_source':recipe['historical_effective_source'],'build_vcs_head':recipe['current_build_vcs_head'],'parent_cli':recipe['parent_cli'],'recipe_path':str(B/'build-recipe.json'),'recipe_sha256':sha(B/'build-recipe.json'),'results_sha256':sha(B/'build-results.json'),'scope':recipe['scope'],'runtime_calls':0,'cloud_calls':0})
