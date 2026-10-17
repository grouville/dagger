from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root=Path(__file__).parent
work=Path('/tmp/dagger-trivial-scalar-fields-only')
source=(work/'dagql/objects.go').read_text()
new='// they merely return. Builtin scalar values are returned directly; object,\n\t// array and custom value results keep their existing cache policy.\n\tTrivial bool'
assert source.replace(new,'// they merely return.\n\tTrivial bool')==(root/'candidate-objects.go').read_text()
(root/'standalone-source-comparison.json').write_text(json.dumps(dict(production_implementation_identical=True,difference='FieldSpec.Trivial comment documents scalar caching policy; concurrency assertions run on the testing goroutine in the standalone tests.',production_sha256=hashlib.sha256(source.encode()).hexdigest(),base='ff0b029a4d270a651b9a8c7286babc79089066e4'),indent=2)+'\n')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
command=[go,'test','-v','-p','2','-buildvcs=false','-race','-count=1','-run','^TestTrivialScalarProjection','./dagql']
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
begin=time.monotonic()
with (root/'standalone-race.log').open('w') as stream:result=subprocess.run(command,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT)
log=(root/'standalone-race.log').read_text()
(root/'standalone-validation.json').write_text(json.dumps(dict(command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,test_executed_and_passed='--- PASS: TestTrivialScalarProjectionKeepsOwnedScalarAttached' in log and '--- PASS: TestTrivialScalarProjectionKeepsObjectAndArrayIdentity' in log),indent=2)+'\n')
assert result.returncode==0 and '--- PASS: TestTrivialScalarProjectionKeepsOwnedScalarAttached' in log and '--- PASS: TestTrivialScalarProjectionKeepsObjectAndArrayIdentity' in log,log[-8000:]
print('PASS: standalone upstream-based behavior tests under the race detector; production logic matches the measured candidate.',flush=True)
