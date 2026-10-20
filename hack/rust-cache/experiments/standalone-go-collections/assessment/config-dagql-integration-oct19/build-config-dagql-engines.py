from pathlib import Path
import hashlib,json,os,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off',CGO_ENABLED='0')
rows=[]
for name,source,target in [('main-engine',out/'engine-config-main','./cmd/engine'),('dagql-engine',out/'engine-config-dagql','./cmd/engine'),('cli',out/'engine-config-main','./cmd/dagger')]:
 binary=out/('config-dagql-'+name)
 command=[go,'build','-p=2','-buildvcs=false','-o',str(binary),target]
 print(json.dumps(dict(event='build-start',name=name)),flush=True)
 start=time.monotonic()
 with (out/('config-dagql-'+name+'-build.log')).open('w') as log:
  result=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 row=dict(name=name,command=command,source=str(source),base='ce6dc9f9403b52067f5831149eab4871f857185d',seconds=time.monotonic()-start,exit_code=result.returncode)
 if result.returncode==0: row['sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
 rows.append(row)
 (out/'config-dagql-builds.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 assert result.returncode==0
