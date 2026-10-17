from pathlib import Path
import json
import os
import subprocess
import time

root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
command=[go,'test','-v','-p','1','-buildvcs=false','-overlay',str(root/'candidate-overlay.json'),'-race','-count=1','-run','^Test(ModuleObject|LazyStoredResultsWithoutBacking)','./core','./core/schema']
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOMAXPROCS='8',CGO_ENABLED='1')
begin=time.monotonic()
with (root/'core-retention-race.log').open('w') as stream:result=subprocess.run(command,cwd='/tmp/dagger-compaction-ownership-only',env=env,stdout=stream,stderr=subprocess.STDOUT)
log=(root/'core-retention-race.log').read_text()
record=dict(command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,executed_passed_tests=sum(line.startswith('--- PASS: Test') for line in log.splitlines()))
(root/'core-retention-validation.json').write_text(json.dumps(record,indent=2)+'\n')
print(record,flush=True)
assert result.returncode==0 and '--- PASS: TestModuleObject' in log and '--- PASS: TestLazyStoredResultsWithoutBacking' in log,log[-8000:]
