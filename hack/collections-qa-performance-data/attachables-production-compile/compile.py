from pathlib import Path
import hashlib,json,os,subprocess,time
root=Path('/home/dagger/dag');out=Path('/tmp/collections-perf/attachables-production-compile');out.mkdir(exist_ok=True)
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env={k:os.environ[k] for k in ('PATH','HOME') if k in os.environ};env.update(GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOWORK='off',CGO_ENABLED='0',GOOS='linux',GOARCH='amd64',GOMAXPROCS='4')
results=[]
for package,name in (('./cmd/dagger','dagger'),('./cmd/engine','dagger-engine')):
 command=[go,'build','-mod=readonly','-modfile=/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod','-tags=dfexcludepatterns,dfparents','-ldflags=-s -w','-o',str(out/name),package]
 begin=time.monotonic()
 with (out/(name+'.private.log')).open('w') as stream:
  result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
 record={'package':package,'exit_code':result.returncode,'seconds':time.monotonic()-begin,'command':command,'log_sha256':hashlib.sha256((out/(name+'.private.log')).read_bytes()).hexdigest()}
 if result.returncode==0:record['binary_sha256']=hashlib.sha256((out/name).read_bytes()).hexdigest()
 results.append(record);(out/'results.json').write_text(json.dumps({'scope':'Compilation of actual production CLI/engine consumers after exact extraction; no runtime or performance comparison','engine_calls':0,'cloud_calls':0,'results':results},indent=2)+'\n')
 print(json.dumps({k:record[k] for k in ('package','exit_code','seconds')}),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
