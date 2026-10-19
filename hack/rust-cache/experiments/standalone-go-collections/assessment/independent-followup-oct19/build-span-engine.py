from pathlib import Path
import hashlib,json,os,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19');go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
command=[go,'build','-p=2','-mod=readonly','-modfile='+str(out/'runtime-main.mod'),'-buildvcs=false','-o',str(out/'runtime-span-engine'),'./cmd/engine']
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off')
start=time.monotonic();print(json.dumps(dict(event='build',name='runtime-span')),flush=True)
with (out/'runtime-span-build.log').open('w') as log:r=subprocess.run(command,cwd=out/'span-index',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
row=dict(command=command,exit_code=r.returncode,seconds=time.monotonic()-start)
if r.returncode==0:row['binary_sha256']=hashlib.sha256((out/'runtime-span-engine').read_bytes()).hexdigest()
(out/'runtime-span-build.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row),flush=True)
assert r.returncode==0
