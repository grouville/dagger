from pathlib import Path
import hashlib,json,os,subprocess,time
P=Path(__file__).resolve().parent
GO=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
MOD=Path('/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (P/'validation.json').exists()
subprocess.run([str(GO.parent/'gofmt'),'-w',str(P/'main.go'),str(P/'main_test.go')],check=True,timeout=20)
env=dict(os.environ,GOOS='linux',GOARCH='amd64',GOAMD64='v1',GOMAXPROCS='4',GOTOOLCHAIN='local',GOPROXY='off',GOSUMDB='off',CGO_ENABLED='0')
for key in list(env):
 if key.startswith('OTEL') or key in ('DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_CONFIG','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(key)
common=[str(GO),'-mod=readonly','-modfile='+str(MOD)]
recipe={'kind':'standalone local HTTP harness, not engine behavior','source':{n:sha(P/n)for n in ('main.go','main_test.go','validate.py')},'go':str(GO),'modfile':str(MOD),'modfile_sha256':sha(MOD),'sum_sha256':sha(MOD.with_suffix('.sum')),'environment':{k:env[k]for k in ('GOOS','GOARCH','GOAMD64','GOMAXPROCS','GOTOOLCHAIN','GOPROXY','GOSUMDB')},'remote_requests':0,'cloud_requests':0,'tests':[]}
(P/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
results=[]
for mode in ('normal','race'):
 e=env.copy();e['CGO_ENABLED']='1'if mode=='race'else'0'
 cmd=[str(GO),'test','-mod=readonly','-modfile='+str(MOD),'-json','-count=1','-timeout=60s']+(['-race']if mode=='race'else[])+[str(P/'main.go'),str(P/'main_test.go')]
 start=time.monotonic()
 with (P/(mode+'.private.log')).open('w') as f:r=subprocess.run(cmd,env=e,cwd='/home/dagger/dag',stdout=f,stderr=subprocess.STDOUT,timeout=180)
 events=[]
 for line in (P/(mode+'.private.log')).read_text().splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 top=[x['Test']for x in events if x.get('Action')=='pass'and x.get('Test')and'/'not in x['Test']]
 failures=[x.get('Test','package')for x in events if x.get('Action')=='fail']
 results.append({'mode':mode,'command':cmd,'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-start,'passed_groups':top,'failures':failures})
 (P/'validation.json').write_text(json.dumps({'results':results,'remote_requests':0,'cloud_requests':0},indent=2)+'\n')
 print(mode,r.returncode,'groups',len(top),flush=True)
 if r.returncode:raise SystemExit(r.returncode)
cmd=[str(GO),'build','-mod=readonly','-modfile='+str(MOD),'-buildvcs=false','-o',str(P/'git-advertisement-probe'),str(P/'main.go')]
start=time.monotonic()
with (P/'build.private.log').open('w')as f:r=subprocess.run(cmd,env=env,cwd='/home/dagger/dag',stdout=f,stderr=subprocess.STDOUT,timeout=180)
results.append({'mode':'build','command':cmd,'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-start})
(P/'validation.json').write_text(json.dumps({'results':results,'remote_requests':0,'cloud_requests':0},indent=2)+'\n')
if r.returncode:raise SystemExit(r.returncode)
manifest={'recipe_sha256':sha(P/'recipe.json'),'validation_sha256':sha(P/'validation.json'),'source':recipe['source'],'binary':{'path':str(P/'git-advertisement-probe'),'sha256':sha(P/'git-advertisement-probe')},'remote_requests':0,'cloud_requests':0,'status':'local gates passed; live execution still requires parent review'}
(P/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('build passed',manifest['binary']['sha256'],flush=True)
