from pathlib import Path
import json
import os
import subprocess
import time
import hashlib

root=Path(__file__).parent
record=[]
steps=[('route-before-retained',['python3',str(root/'verify_retained_first.py'),'scalar-projection-route-before-first'],None),
 ('route-engine-build',json.loads((root/'final-validation.json').read_text())[-1]['command'],'/tmp/dagger-filesync-snapshot-seeds')]
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
for label,command,cwd in steps:
    begin=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:result=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
    row=dict(label=label,command=command,seconds=time.monotonic()-begin,exit_code=result.returncode)
    if label=='route-engine-build' and result.returncode==0:row['sha256']=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
    record.append(row);(root/'route-build.json').write_text(json.dumps(record,indent=2)+'\n')
    print(label,result.returncode,flush=True)
    assert result.returncode==0,(root/(label+'.log')).read_text()[-6000:]
