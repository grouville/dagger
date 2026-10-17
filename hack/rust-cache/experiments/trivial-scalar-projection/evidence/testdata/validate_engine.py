from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
rows=[]
steps=[
 ('upstream-dagql-race','/tmp/dagger-compaction-ownership-only',[go,'test','-p','2','-buildvcs=false','-overlay',str(root/'candidate-overlay.json'),'-race','-count=1','./dagql']),
 ('engine-build','/tmp/dagger-filesync-snapshot-seeds',[go,'build','-p','2','-buildvcs=false','-modfile','/tmp/rust-cache-sipsma-review/otel-evicted-queue/engine.go.mod','-overlay',str(root/'engine-overlay.json'),'-o',str(root/'dagger-engine'),'./cmd/engine']),
]
for label,work,command in steps:
    begin=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:result=subprocess.run(command,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT)
    row=dict(label=label,workdir=work,command=command,seconds=time.monotonic()-begin,exit_code=result.returncode)
    if label=='engine-build' and result.returncode==0:row['sha256']=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
    rows.append(row);(root/'engine-validation.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,result.returncode,flush=True)
    assert result.returncode==0,(label,(root/(label+'.log')).read_text()[-6000:])
