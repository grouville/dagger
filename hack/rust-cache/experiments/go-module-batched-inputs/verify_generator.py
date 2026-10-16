from pathlib import Path
import json
import os
import subprocess
import time

root=Path(__file__).parent
repo=Path('/tmp/dagger-go-module-batched-inputs-upstream')
go=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
env=dict(os.environ,PATH=str(go.parent)+os.pathsep+os.environ['PATH'])
production=repo/'cmd/codegen/generator/go/templates/modules.go'
patched=production.read_bytes()
rows=[]
def run(label,args,success):
    start=time.time()
    with (root/(label+'.log')).open('w') as out:
        result=subprocess.run([str(go),'test','-count=1']+args,cwd=repo,env=env,stdout=out,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,exit_code=result.returncode,expected_success=success,unix_start=start,unix_end=time.time()))
    (root/'generator-tests.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert (result.returncode==0)==success,label
    print(label,result.returncode,flush=True)
try:
    run('dispatch-patched',['-run','^TestDispatchInputs$','./cmd/codegen/generator/go/templates'],True)
    production.write_bytes(subprocess.check_output(['git','show','HEAD:cmd/codegen/generator/go/templates/modules.go'],cwd=repo))
    run('dispatch-main-regression',['-run','^TestDispatchInputs$','./cmd/codegen/generator/go/templates'],False)
    assert 'metadata must be read in one request' in (root/'dispatch-main-regression.log').read_text()
finally:
    production.write_bytes(patched)
run('codegen-templates-race',['-race','./cmd/codegen/generator/go/templates'],True)
run('codegen-generator',['./cmd/codegen/generator/go'],True)
