from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent
work = Path('/tmp/dagger-compaction-ownership-only')
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
rows = []
for arm in ['baseline','candidate']:
    command = [go,'test','-v','-p','2','-buildvcs=false','-overlay',str(root/(arm+'-overlay.json')),'-race','-count=1','-run','^TestTrivialScalarProjectionKeepsObjectAndArrayIdentity$','./dagql']
    begin = time.monotonic()
    with (root/(arm+'-focused-race.log')).open('w') as stream:
        result = subprocess.run(command,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT)
    log = (root/(arm+'-focused-race.log')).read_text()
    executed = '--- PASS: TestTrivialScalarProjectionKeepsObjectAndArrayIdentity' in log
    rows.append(dict(arm=arm,kind='focused-race',command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,test_executed_and_passed=executed))
    (root/'validation-builds.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(arm,'focused-race',result.returncode,executed,flush=True)
    assert result.returncode==0 and executed,log[-8000:]
for arm in ['baseline','candidate']:
    binary=root/(arm+'.test')
    command=[go,'test','-c','-p','2','-buildvcs=false','-overlay',str(root/(arm+'-overlay.json')),'-o',str(binary),'./dagql']
    begin=time.monotonic()
    with (root/(arm+'-build.log')).open('w') as stream:
        result=subprocess.run(command,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT)
    rows.append(dict(arm=arm,kind='component-build',command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,sha256=hashlib.sha256(binary.read_bytes()).hexdigest() if result.returncode==0 else None))
    (root/'validation-builds.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(arm,'component-build',result.returncode,flush=True)
    assert result.returncode==0
