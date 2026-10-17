from pathlib import Path
import json
import os
import subprocess
import time

root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
rows=[]
for arm in ['baseline','candidate']:
    command=[go,'test','-v','-p','2','-buildvcs=false','-overlay',str(root/(arm+'-overlay.json')),'-race','-count=1','-run','^TestTrivialScalarProjectionKeepsOwnedScalarAttached$','./dagql']
    begin=time.monotonic()
    with (root/(arm+'-owned-scalar-probe.log')).open('w') as stream:result=subprocess.run(command,cwd='/tmp/dagger-compaction-ownership-only',env=env,stdout=stream,stderr=subprocess.STDOUT)
    log=(root/(arm+'-owned-scalar-probe.log')).read_text()
    rows.append(dict(arm=arm,command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,log=log))
    (root/'owned-scalar-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(arm,result.returncode,flush=True)
    if arm=='baseline':assert result.returncode==0 and '--- PASS: TestTrivialScalarProjectionKeepsOwnedScalarAttached' in log,log
    else:assert result.returncode!=0 and 'cannot implement OnReleaser' in log,log
