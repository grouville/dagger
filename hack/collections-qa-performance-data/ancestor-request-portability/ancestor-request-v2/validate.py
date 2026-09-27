from pathlib import Path
import json,os,subprocess,hashlib,time
P=Path(__file__).resolve().parent
V=P/'validation'; V.mkdir(exist_ok=True)
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base=[GO,'test','-mod=readonly','-modfile=/tmp/collections-perf/ancestor-request-v1/builds/engine.mod','-overlay='+str(P/'test-overlay.json')]
pattern='^Test(ParentDirectoryMetadata|ParentMetadata)'
common=['-count=1','-run='+pattern,'-json','./engine','./internal/fsutil','./engine/client','./engine/filesync']
steps=[('normal',base+common,{'GOOS':'linux','GOARCH':'amd64','CGO_ENABLED':'1'}),('race',base+['-race']+common,{'GOOS':'linux','GOARCH':'amd64','CGO_ENABLED':'1'}),('windows-compile',base+['-c','-o',str(V/'fsutil-windows.test.exe'),'./internal/fsutil'],{'GOOS':'windows','GOARCH':'amd64','CGO_ENABLED':'0'})]
results=[]
for name,cmd,extra in steps:
 env=os.environ.copy();env.update({'GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local',**extra})
 out=V/(name+'.log');start=time.monotonic()
 with out.open('wb') as f:r=subprocess.run(cmd,cwd='/home/dagger/dag',env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 entry={'name':name,'command':cmd,'env':{k:env[k]for k in ('GOMAXPROCS','GOPROXY','GOTOOLCHAIN','GOOS','GOARCH','CGO_ENABLED')},'exit_code':r.returncode,'seconds':time.monotonic()-start,'log_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
 if name!='windows-compile':
  es=[]
  for line in out.read_text().splitlines():
   try:es.append(json.loads(line))
   except ValueError:pass
  entry['passed_top_level_tests']=[e['Test']for e in es if e.get('Action')=='pass' and e.get('Test')and '/'not in e['Test']]
  entry['failures']=[{'Package':e.get('Package'),'Test':e.get('Test')}for e in es if e.get('Action')=='fail']
 results.append(entry);(V/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps({'name':name,'exit_code':r.returncode,'seconds':round(entry['seconds'],2),'passed':entry.get('passed_top_level_tests')}),flush=True)
 if r.returncode and name!='windows-compile':break
