#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,subprocess,time
P=Path(__file__).resolve().parent;ROOT=Path('/home/dagger/dag');GO=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((P/'manifest.json').read_text())
for name,expected in manifest['files'].items():assert sha(P/name)==expected,name
assert sha(ROOT/'go.mod')==manifest['root_go_mod_sha256']
assert sha(ROOT/'go.sum')==manifest['root_go_sum_sha256']
assert sha(ROOT/'core/sdk/dang/v2/helpers.go')==manifest['production_baseline_helpers_sha256']
out=P/'validation-v2';out.mkdir(exist_ok=False)
env=os.environ.copy();env.update({'GOTOOLCHAIN':'local','GOPROXY':'off','GOMAXPROCS':'4','GOOS':'linux','GOARCH':'amd64','CGO_ENABLED':'0'})
records=[]
def run(label,cmd,timeout,extra=None,expected=0):
 started=time.monotonic()
 with(out/(label+'.log')).open('w')as log:
  p=subprocess.run(cmd,cwd=ROOT,env=dict(env,**(extra or{})),stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 records.append({'label':label,'argv':cmd,'exit_code':p.returncode,'seconds':time.monotonic()-started,'expected_exit':expected,'correct':p.returncode==expected})
 (out/'validation.json').write_text(json.dumps({'manifest_sha256':sha(P/'manifest.json'),'records':records,'no_engine_or_cloud_calls':True},indent=2)+'\n')
 assert p.returncode==expected,label
common=[str(GO),'test','-mod=readonly','-overlay='+str(P/'test-overlay.json'),'-count=1']
regex='^(TestDangRegistrationMetadata.*|TestReportDangSourceError|TestDangSourceErrorKeepsGraphQLExtraction|TestDangSourceMessage.*|TestIsDangSourceErrorIgnoresInfrastructureErrors)$'
run('normal',common+['-timeout=120s','-run='+regex,'./core/sdk/dang/v2'],300)
run('race',common+['-race','-timeout=120s','-run='+regex,'./core/sdk/dang/v2'],300,{'CGO_ENABLED':'1'})
run('compile-micro',common+['-c','-o',str(out/'metadata.test'),'./core/sdk/dang/v2'],300)
for cycle in range(3):
 for mode in (('baseline','snapshot')if cycle%2==0 else('snapshot','baseline')):
  run(f'micro-{cycle}-{mode}',[str(out/'metadata.test'),'-test.run=^$','-test.bench=^BenchmarkDangRegistrationMetadata/(go.dang|gomod.dang|collection.dang)/'+mode+'$','-test.benchtime=200ms','-test.count=1','-test.timeout=60s'],90)
print(json.dumps({'records':len(records),'all_passed':True,'no_engine_or_cloud_calls':True}))
