from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common=['-p','2','-buildvcs=false','-modfile','/tmp/rust-cache-sipsma-review/otel-evicted-queue/engine.go.mod','-overlay',str(root/'engine-overlay.json')]
jobs=[
 ('engine-transport-race','/tmp/dagger-filesync-snapshot-seeds',[go,'test',*common,'-race','-count=1','-run','^TestCallerHostStatAndRead','./engine/engineutil']),
 ('engine-core','/tmp/dagger-filesync-snapshot-seeds',[go,'test',*common,'-race','-count=1','-run','^TestModuleTreeReaderWithoutTree$','./core']),
 ('cli-filesync-race','/tmp/dagger-filesync-literal-pathwalk',[go,'test','-p','2','-buildvcs=false','-overlay',str(root/'cli-overlay.json'),'-race','-count=1','-run','^Test(Glob|Search|Host|FileSync|Filesync)','./engine/client']),
 ('engine-build','/tmp/dagger-filesync-snapshot-seeds',[go,'build',*common,'-o',str(root/'dagger-engine'),'./cmd/engine']),
 ('cli-build','/tmp/dagger-filesync-literal-pathwalk',[go,'build','-p','1','-buildvcs=false','-overlay',str(root/'cli-overlay.json'),'-o',str(root/'dagger'),'./cmd/dagger']),
]
rows=[]
for label,cwd,command in jobs:
 started=time.monotonic()
 with (root/(label+'.log')).open('w') as out:
  result=subprocess.run(command,cwd=cwd,env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='1',_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.15'),stdout=out,stderr=subprocess.STDOUT)
 rows.append(dict(label=label,cwd=cwd,command=command,exit_code=result.returncode,seconds=time.monotonic()-started))
 (root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,result.returncode,flush=True);assert result.returncode==0,label
(root/'binaries.json').write_text(json.dumps({name:dict(sha256=hashlib.sha256((root/name).read_bytes()).hexdigest(),bytes=(root/name).stat().st_size) for name in ['dagger-engine','dagger']},indent=2)+'\n')
