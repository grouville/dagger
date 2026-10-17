from pathlib import Path
import hashlib,json,os,subprocess,time
root=Path(__file__).parent
work='/tmp/dagger-filesync-snapshot-seeds'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common=['-p','2','-buildvcs=false','-modfile','/tmp/rust-cache-sipsma-review/otel-evicted-queue/engine.go.mod','-overlay',str(root/'engine-overlay.json')]
rows=[]
for mode in ['off','on']:
 for package in ['github.com/vito/dang/v2/pkg/dang','./core/sdk/dang/v2']:
  label=mode+('-library' if package.startswith('github') else '-sdk')
  command=[go,'test',*common,'-race','-count=1',package]
  started=time.monotonic()
  with (root/(label+'-race.log')).open('w') as out:r=subprocess.run(command,cwd=work,env=dict(os.environ,DAGGER_BUILTIN_RECEIVERS_TEST_MODE=mode),stdout=out,stderr=subprocess.STDOUT)
  rows.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'engine-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,flush=True);assert r.returncode==0,label
command=[go,'build',*common,'-o',str(root/'dagger-engine'),'./cmd/engine']
started=time.monotonic()
with (root/'engine-build.log').open('w') as out:r=subprocess.run(command,cwd=work,stdout=out,stderr=subprocess.STDOUT)
rows.append(dict(label='engine-build',command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'engine-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print('engine-build',r.returncode,flush=True);assert r.returncode==0
(root/'engine-binary.json').write_text(json.dumps(dict(sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),bytes=(root/'dagger-engine').stat().st_size),indent=2)+'\n')
