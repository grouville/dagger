from pathlib import Path
import hashlib,json,os,subprocess,time
r=Path(__file__).parent;go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
assert all(x['exit_code']==0 for x in json.loads((r/'checks.json').read_text()))
cmd=[go,'build','-p','2','-buildvcs=false','-modfile',str(r/'engine.go.mod'),'-overlay',str(r/'engine-overlay.json'),'-o',str(r/'dagger-engine'),'./cmd/engine']
tick=time.monotonic()
with (r/'engine-build.log').open('w') as out:result=subprocess.run(cmd,cwd='/tmp/dagger-filesync-snapshot-seeds',env=dict(os.environ,GOMAXPROCS='4',GOTOOLCHAIN='local'),stdout=out,stderr=subprocess.STDOUT)
row=dict(command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode)
if result.returncode==0:row['sha256']=hashlib.sha256((r/'dagger-engine').read_bytes()).hexdigest()
(r/'engine-build.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row));assert result.returncode==0
