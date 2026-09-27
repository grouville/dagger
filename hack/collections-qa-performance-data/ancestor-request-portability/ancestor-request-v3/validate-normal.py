from pathlib import Path
import json,os,subprocess,hashlib,time
p=Path(__file__).resolve().parent;repo=Path('/home/dagger/dag');v=p/'validation';v.mkdir(exist_ok=True)
cmd=['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go','test','-mod=readonly','-overlay='+str(p/'test-overlay.json'),'-count=1','-run=^Test(ParentDirectoryMetadata|ParentMetadata)','-json','./engine','./internal/fsutil','./engine/client','./engine/filesync']
env=os.environ.copy();env.update({'GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local','GOOS':'linux','GOARCH':'amd64','CGO_ENABLED':'1'})
start=time.monotonic()
with (v/'normal.log').open('wb') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
es=[]
for l in (v/'normal.log').read_text().splitlines():
 try:es.append(json.loads(l))
 except ValueError:pass
result={'command':cmd,'dependency_mode':'ordinary checkout go.mod, no -modfile or dependency replacement overrides','exit_code':r.returncode,'seconds':time.monotonic()-start,'dependency_hashes':{s:hashlib.sha256((repo/s).read_bytes()).hexdigest()for s in ('go.mod','go.sum','sdk/go/go.mod')},'log_sha256':hashlib.sha256((v/'normal.log').read_bytes()).hexdigest(),'passed_top_level_tests':[e['Test']for e in es if e.get('Action')=='pass'and e.get('Test')and '/'not in e['Test']],'failures':[{'Package':e.get('Package'),'Test':e.get('Test')}for e in es if e.get('Action')=='fail'],'env':{k:env[k]for k in ('GOMAXPROCS','GOPROXY','GOTOOLCHAIN','GOOS','GOARCH','CGO_ENABLED')}}
(v/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ('exit_code','seconds','passed_top_level_tests','failures')}));raise SystemExit(r.returncode)
