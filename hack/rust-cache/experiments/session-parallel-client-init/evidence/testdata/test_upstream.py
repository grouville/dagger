from pathlib import Path
import hashlib,json,os,subprocess,time
root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
source='/tmp/dagger-go-real-repository-main'
base=['-p','2','-buildvcs=false','-modfile',str(root.parent/'otel-evicted-queue/engine.go.mod')]
jobs=[
 ('upstream-before-regression','before',[],1,'TestNestedClientRuntimeInitializationsCanOverlap$'),
 ('upstream-after-race','after',['-race'],0,'Test(NestedClientRuntimeInitializationsCanOverlap|InitializeSessionEngineClientConcurrent|NestedTransport|ClientInitialization|ClientMetadata|GetOrInit|SessionLifecycleObserverConcurrency|Reap|SameIDConnect|FailedSessionInitialization)'),
]
rows=[]
for name,arm,extra,expected,pattern in jobs:
 cmd=[go,'test',*base,'-overlay',str(root/('upstream-overlay-'+arm+'.json')),*extra,'-count=1','-timeout=180s','-run',pattern,'./engine/server']
 tick=time.monotonic()
 with (root/(name+'.log')).open('w') as out:
  result=subprocess.run(cmd,cwd=source,env=dict(os.environ,GOMAXPROCS='4',GOTOOLCHAIN='local'),stdout=out,stderr=subprocess.STDOUT)
 row=dict(label=name,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode,expected_exit_code=expected,source=source,
  files_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['upstream-before-session.go','upstream-after-session.go','parallel_client_init_test.go']})
 rows.append(row);(root/'checks-upstream.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 assert result.returncode==expected,name
 if expected:assert 'unrelated client initializations were serialized' in (root/(name+'.log')).read_text()
