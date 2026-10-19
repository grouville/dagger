from pathlib import Path
import hashlib,json,os,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19');source=out/'span-main'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off')
variants={'runtime-main':out/'dang-main','runtime-typed':Path('/tmp/go-collection-clean-branches/remaining-verification/dang-typed-methods'),'runtime-callback':Path('/tmp/go-collection-clean-branches/remaining-verification/dang-callback-caller')}
rows=[]
for name,dang in variants.items():
 mod=out/(name+'.mod');mod.write_bytes((source/'go.mod').read_bytes());mod.with_suffix('.sum').write_bytes((source/'go.sum').read_bytes())
 subprocess.run([go,'mod','edit','-modfile='+str(mod),'-replace=github.com/vito/dang/v2='+str(dang)],cwd=source,env=env,check=True)
 start=time.monotonic();command=[go,'build','-p=2','-mod=mod','-modfile='+str(mod),'-buildvcs=false','-o',str(out/(name+'-engine')),'./cmd/engine']
 print(json.dumps(dict(event='build',name=name)),flush=True)
 with (out/(name+'-build.log')).open('w') as log:r=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 row=dict(name=name,command=command,exit_code=r.returncode,seconds=time.monotonic()-start,engine_base='c5456d9cbf47e432b89aba43e35211425e8e1f03',dang_base='bf649b8dd99f321984bc9cd9d1a3494acf2c0c39');rows.append(row)
 if r.returncode:print((out/(name+'-build.log')).read_text()[-3000:],flush=True)
 else:row['binary_sha256']=hashlib.sha256((out/(name+'-engine')).read_bytes()).hexdigest()
 (out/'runtime-builds.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 assert r.returncode==0
