from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,signal
D=Path(__file__).resolve().parent;S=D/'source';GO=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go');A=Path('/tmp/collections-perf/warm-audit/go-sdk-pr36-adapter')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (D/'validation.json').exists()
M=D/'modfiles';M.mkdir(exist_ok=True)
for name,rel in [('codegen','codegen'),('contract-upstream','entrypoint-contract'),('contract-engine','entrypoint-contract')]:
 for ext in ('mod','sum'):shutil.copyfile(S/'helpers'/rel/('go.'+ext),M/(name+'.'+ext))
with (M/'contract-engine.mod').open('a') as f:f.write('\nreplace github.com/vito/dang/v2 => /tmp/collections-perf/syntax-isolated/dang\n')
env=dict(os.environ,PATH=str(GO.parent)+':'+os.environ.get('PATH','/usr/bin:/bin'),GOOS='linux',GOARCH='amd64',GOAMD64='v1',GOMAXPROCS='4',GOTOOLCHAIN='local',GOPROXY='off',GOSUMDB='off',GOWORK='off',CGO_ENABLED='1')
for k in list(env):
 if k.startswith(('OTEL','DAGGER_')) or k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(k)
recipe={'public_commit':'4dfd447d58344835a0d4692ec0c8e5683c18bd6f','adapter_patch_sha256':sha(A/'current-engine-json-contract.patch'),'go':str(GO),'go_version':subprocess.check_output([str(GO),'version'],text=True,env=env).strip(),'environment':{k:env[k]for k in ('GOOS','GOARCH','GOAMD64','GOMAXPROCS','GOTOOLCHAIN','GOPROXY','GOSUMDB','GOWORK','CGO_ENABLED')},'validation_driver_sha256':sha(__file__),'modfiles':{p.name:sha(p)for p in sorted(M.iterdir())},'exact_engine_dang_source':'/tmp/collections-perf/syntax-isolated/dang','remote_requests':0,'engine_calls':0,'cloud_calls':0,'steps':[]}
steps=[('templates','codegen','codegen','^Test(DeveloperArgEncoding|EntrypointContractSurface|GeneratedDispatchJSONMap)$','./generator/gogenerator/templates',False),('contract-upstream','entrypoint-contract','contract-upstream','^TestCheck','. ',False),('contract-engine','entrypoint-contract','contract-engine','^TestCheck','.',False),('templates-race','codegen','codegen','^Test(DeveloperArgEncoding|EntrypointContractSurface|GeneratedDispatchJSONMap)$','./generator/gogenerator/templates',True),('contract-engine-race','entrypoint-contract','contract-engine','^TestCheck','.',True)]
for label,rel,mod,pattern,pkg,race in steps:
 cmd=[str(GO),'test','-mod=readonly','-modfile='+str(M/(mod+'.mod')),'-json','-count=1','-timeout=90s','-run='+pattern]+(['-race']if race else[])+[pkg.strip()]
 recipe['steps'].append({'label':label,'command':cmd,'cwd':str(S/'helpers'/rel),'outer_timeout_seconds':180})
(D/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n');results=[]
for step in recipe['steps']:
 t=time.monotonic();log=D/(step['label']+'.private.log')
 with log.open('w')as f:
  proc=subprocess.Popen(step['command'],cwd=step['cwd'],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=proc.wait(timeout=step['outer_timeout_seconds'])
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait();code=124
 events=[]
 for line in log.read_text().splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 passed=[e['Test']for e in events if e.get('Action')=='pass'and e.get('Test')and'/'not in e['Test']]
 failed=[e.get('Test','package')for e in events if e.get('Action')=='fail']
 results.append({'label':step['label'],'exit_code':code,'elapsed_seconds':time.monotonic()-t,'passed_groups':passed,'failed':failed,'log_sha256':sha(log)})
 (D/'validation.json').write_text(json.dumps({'results':results,'remote_requests':0,'engine_calls':0,'cloud_calls':0,'recipe_sha256':sha(D/'recipe.json')},indent=2)+'\n')
 print(step['label'],code,'passed_groups',len(passed),flush=True)
 if code:raise SystemExit(code)
print('all focused gates passed',flush=True)
