from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root=Path(__file__).parent
work='/tmp/dagger-compaction-ownership-only'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
common=['-p','2','-buildvcs=false','-overlay',str(root/'candidate-overlay.json')]
steps=[('final-dagql-race',work,[go,'test',*common,'-race','-count=1','./dagql']),
 ('final-core-retention-race',work,[go,'test','-v','-p','1','-buildvcs=false','-overlay',str(root/'candidate-overlay.json'),'-race','-count=1','-run','^Test(ModuleObject|LazyStoredResultsWithoutBacking)','./core','./core/schema'])]
for arm in ['baseline','candidate']:
    steps.append(('final-'+arm+'-build',work,[go,'test','-c','-p','2','-buildvcs=false','-overlay',str(root/(arm+'-overlay.json')),'-o',str(root/(arm+'.test')),'./dagql']))
steps.append(('final-engine-build','/tmp/dagger-filesync-snapshot-seeds',[go,'build','-p','2','-buildvcs=false','-modfile','/tmp/rust-cache-sipsma-review/otel-evicted-queue/engine.go.mod','-overlay',str(root/'engine-overlay.json'),'-o',str(root/'dagger-engine'),'./cmd/engine']))
rows=[]
for label,cwd,command in steps:
    begin=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:result=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
    record=dict(label=label,workdir=cwd,command=command,seconds=time.monotonic()-begin,exit_code=result.returncode)
    if label.endswith('-build') and result.returncode==0:
        binary=Path(command[command.index('-o')+1]);record['sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    rows.append(record);(root/'final-validation.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,result.returncode,flush=True)
    assert result.returncode==0,(label,(root/(label+'.log')).read_text()[-6000:])
