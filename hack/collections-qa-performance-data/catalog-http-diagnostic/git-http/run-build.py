from pathlib import Path
import json,hashlib,subprocess,os,time,argparse
D=Path(__file__).resolve().parent;B=D/'builds';R=Path('/home/dagger/dag');recipe=json.loads((B/'recipe.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==recipe['source_head']
 for p,h in recipe['inputs'].items():assert sha(p)==h,p
 for key in ('parent_engine','cli'):assert sha(recipe[key]['path'])==recipe[key]['sha256']
a=argparse.ArgumentParser();a.add_argument('stage',choices=['tests','build']);args=a.parse_args();verify()
if args.stage=='tests':
 rows=[]
 for stage,argv in recipe['test_commands'].items():
  begin=time.monotonic()
  with (B/f'test-{stage}.log').open('w')as log:proc=subprocess.run(argv,cwd=R,env=os.environ|recipe['test_environments'][stage],stdout=log,stderr=subprocess.STDOUT,timeout=300)
  row={'stage':stage,'exit_code':proc.returncode,'seconds':time.monotonic()-begin,'log_sha256':sha(B/f'test-{stage}.log')};rows.append(row);(B/'validation.json').write_text(json.dumps({'recipe_sha256':sha(B/'recipe.json'),'results':rows},indent=2)+'\n');print(json.dumps(row),flush=True)
  if proc.returncode:raise SystemExit(proc.returncode)
else:
 tests=json.loads((B/'validation.json').read_text());assert tests['recipe_sha256']==sha(B/'recipe.json') and len(tests['results'])==2 and all(r['exit_code']==0 for r in tests['results'])
 begin=time.monotonic()
 with (B/'engine-build.log').open('w')as log:proc=subprocess.run(recipe['build_command'],cwd=R,env=os.environ|recipe['environment'],stdout=log,stderr=subprocess.STDOUT,timeout=300)
 row={'exit_code':proc.returncode,'seconds':time.monotonic()-begin,'log_sha256':sha(B/'engine-build.log')};(B/'engine-build.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
 verify();manifest={'source_head':recipe['source_head'],'frozen_parent_source_head':recipe['frozen_parent_source_head'],'recipe_sha256':sha(B/'recipe.json'),'validation_sha256':sha(B/'validation.json'),'engine':{'path':str(B/'engine-diagnostic'),'sha256':sha(B/'engine-diagnostic')},'cli':recipe['cli'],'parent_engine':recipe['parent_engine'],'scope':recipe['scope'],'production_cloud_commands':0}
 (B/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest),flush=True)
verify()
