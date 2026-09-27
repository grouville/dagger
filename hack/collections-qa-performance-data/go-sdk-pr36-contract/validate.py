from pathlib import Path
import hashlib,json,os,signal,subprocess,time
H=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads((H/'recipe.json').read_text())
for rel,want in r['source_sha256'].items():assert sha(H/rel)==want,rel
for path,want in r['schema_prepare']['production_source_sha256'].items():assert sha(path)==want,path
results=[]
def run(label,cmd,cwd,env,timeout):
 start=time.monotonic();log=H/(label+'.private.log')
 with log.open('wb')as f:
  p=subprocess.Popen(cmd,cwd=cwd,env=os.environ|env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout=timeout)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();rc=124
 events=[]
 for line in log.read_text().splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  if x.get('Action')in('pass','fail')and x.get('Test'):events.append({'test':x['Test'],'action':x['Action']})
 row={'label':label,'exit_code':rc,'seconds':time.monotonic()-start,'tests':events};results.append(row)
 (H/'validation.json').write_text(json.dumps({'recipe_sha256':sha(H/'recipe.json'),'results':results,'engine_calls':0,'network_calls':0,'cloud_calls':0},indent=2)+'\n')
 print(json.dumps(row),flush=True)
 if rc:raise SystemExit(rc)
f=r['schema_prepare'];run('schema-fixture',f['command'],f['cwd'],f['env'],f['timeout_seconds'])
(H/'schema-manifest.json').write_text(json.dumps({'views':{p.name:sha(p)for p in (H/'schema').glob('*.json')},'schema_recipe_sha256':sha(H/'recipe.json'),'source_head_observed':f['source_head_observed'],'source':'production schema installer and serializer; no manual type/field additions','engine_calls':0},indent=2)+'\n')
for s in r['steps']:run(s['label'],s['command'],r['cwd'],r['env'],s['timeout_seconds'])
