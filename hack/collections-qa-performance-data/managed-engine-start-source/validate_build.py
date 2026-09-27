"""Prepare/validate/build the isolated running-state CLI; no engine or Cloud calls."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time
H=Path(__file__).parent;R=Path('/home/dagger/dag');B=H/'builds';P=Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds')
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';HEAD='0d1c32e29f2f31cdb95f0b5f17f7daed7305bc87'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def git(*args):return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
def source_guard():
 assert git('rev-parse','HEAD')==HEAD
 for name in git('diff','--name-only').splitlines():assert name.startswith('hack/'),name
 for name in git('ls-files','--others','--exclude-standard').splitlines():assert name.startswith('hack/')or not name.endswith(('.go','.s','.c','.h','.syso')),name
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--validate',action='store_true');p.add_argument('--build',action='store_true');a=p.parse_args();assert sum([a.prepare,a.validate,a.build])<=1
if not any([a.prepare,a.validate,a.build]):print(json.dumps({'execute':False,'tests':3,'cli_builds':1,'engine_calls':0,'cloud_calls':0}));raise SystemExit
if a.prepare:
 source_guard();assert not B.exists();B.mkdir();(B/'inputs').mkdir()
 replace={}
 for name in ['container.go','docker.go','container_state.go']:
  shutil.copyfile(H/name,B/'inputs'/name);replace[str(R/'engine/client/drivers'/name)]=str(B/'inputs'/name)
 write(B/'overlay.json',{'Replace':replace})
 for n in ['cli.mod','cli.sum']:shutil.copyfile(P/n,B/n)
 parent=json.loads((P/'runtime-builds.json').read_text())['variants']['original'];assert sha(parent['path'])==parent['sha256']=='d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
 prior=json.loads((P/'build-recipe.json').read_text());external=prior['external_sources']
 for path,want in external.items():assert sha(path)==want,path
 originals=json.loads((H/'source-provenance.json').read_text())['originals'];guards={str(R/name):want for name,want in originals.items()}
 guards[str(R/'engine/client/client.go')]=sha(R/'engine/client/client.go')
 inputs={str(path):sha(path)for path in B.rglob('*')if path.is_file()}
 for name in ['container_state_test.go','prototype.patch','test-overlay.json','baseline-overlay.json']:inputs[str(H/name)]=sha(H/name)
 command=[GO,'build','-mod=readonly','-modfile='+str(B/'cli.mod'),'-buildvcs=true','-overlay='+str(B/'overlay.json'),'-o',str(B/'dagger-managed-start'),'./cmd/dagger']
 recipe={'source_head':HEAD,'script_sha256':sha(__file__),'source_guards':guards,'inputs':inputs,'external_sources':external,'command':command,'build_environment':{'CGO_ENABLED':'0','GOOS':'linux','GOARCH':'amd64','GOAMD64':'v1','GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local'},'parent_cli':parent,'parent_recipe_sha256':sha(P/'build-recipe.json'),'scope':'Only managed image-driver running-state probe/start elision. No socket, HTTP sharing, admission bypass, cache or engine change.'}
 write(B/'recipe.json',recipe);print(json.dumps({'prepared':True,'recipe_sha256':sha(B/'recipe.json')}));raise SystemExit
recipe=json.loads((B/'recipe.json').read_text())
def guard():
 source_guard();assert sha(__file__)==recipe['script_sha256']
 for path,want in(recipe['source_guards']|recipe['inputs']|recipe['external_sources']).items():assert sha(path)==want,path
guard()
if a.validate:
 out=H/'validation-v1';assert not out.exists();out.mkdir();result={'recipe_sha256':sha(B/'recipe.json'),'runs':[]}
 regex='^(TestImageDriverSkipsStartForRunningContainer|TestImageDriverStateFallbacks|TestContainerStateLegacyBackend|TestContainerRunningProtocol|TestDockerContainerStateCommand|TestImageDriverCreate.*|TestContainerConnector.*)$'
 for label,overlay,match,race in [('baseline-negative','baseline-overlay.json','^TestImageDriverSkipsStartForRunningContainer$',False),('candidate','test-overlay.json',regex,False),('candidate-race','test-overlay.json',regex,True)]:
  cmd=[GO,'test','-json','-mod=readonly','-modfile='+str(B/'cli.mod'),'-overlay='+str(H/overlay)]
  if race:cmd+=['-race']
  cmd+=['./engine/client/drivers','-run',match,'-count=1','-timeout=60s'];log=out/(label+'.jsonl');start=time.monotonic()
  with log.open('w')as f:r=subprocess.run(cmd,cwd=R,env=os.environ|{'GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local'},stdout=f,stderr=subprocess.STDOUT,timeout=300)
  events=[]
  for line in log.read_text().splitlines():
   try:events.append(json.loads(line))
   except json.JSONDecodeError:pass
  row={'label':label,'argv':cmd,'exit_code':r.returncode,'seconds':time.monotonic()-start,'log_sha256':sha(log),'passes':[e['Test']for e in events if e.get('Action')=='pass'and'Test'in e],'failures':[e['Test']for e in events if e.get('Action')=='fail'and'Test'in e]};result['runs'].append(row);write(out/'results.json',result);print(json.dumps({k:row[k]for k in ['label','exit_code','seconds','failures']}),flush=True)
  if label=='baseline-negative':assert r.returncode!=0 and row['failures']==['TestImageDriverSkipsStartForRunningContainer']
  else:assert r.returncode==0
 guard();result['all_expected_results']=True;write(out/'results.json',result);raise SystemExit
validation=json.loads((H/'validation-v1/results.json').read_text());assert validation['all_expected_results'];assert not(B/'build-result.json').exists()
start=time.monotonic()
with(B/'build.log').open('w')as f:r=subprocess.run(recipe['command'],cwd=R,env=os.environ|recipe['build_environment'],stdout=f,stderr=subprocess.STDOUT,timeout=300)
row={'exit_code':r.returncode,'seconds':time.monotonic()-start,'log_sha256':sha(B/'build.log'),'validation_sha256':sha(H/'validation-v1/results.json')}
if r.returncode==0:row|={'path':str(B/'dagger-managed-start'),'sha256':sha(B/'dagger-managed-start')}
write(B/'build-result.json',row);print(json.dumps(row),flush=True);assert r.returncode==0;guard()
write(H/'runtime-builds.json',{'source_head':HEAD,'baseline':recipe['parent_cli'],'candidate':{k:row[k]for k in ['path','sha256']},'recipe_path':str(B/'recipe.json'),'recipe_sha256':sha(B/'recipe.json'),'validation_sha256':sha(H/'validation-v1/results.json'),'cloud_calls':0})
