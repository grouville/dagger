from pathlib import Path
import json,os,subprocess,time
root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base=['-p','2','-buildvcs=false','-modfile',str(root.parent/'otel-evicted-queue/engine.go.mod')]
jobs=[
 ('before-regression','before','TestNestedClientRuntimeInitializationsCanOverlap',1),
 ('after-regression','after','Test(NestedClientRuntimeInitializationsCanOverlap|ClientInitializationDoesNotHoldScopeLock)$',0),
]
rows=[]
for name,arm,pattern,expected in jobs:
 cmd=[go,'test',*base,'-overlay',str(root/('overlay-'+arm+'.json')),'-count=1','-timeout=120s','-run',pattern,'./engine/server']
 tick=time.monotonic()
 with (root/(name+'.log')).open('w') as out:
  result=subprocess.run(cmd,cwd='/tmp/dagger-filesync-snapshot-seeds',env=dict(os.environ,GOMAXPROCS='4',GOTOOLCHAIN='local'),stdout=out,stderr=subprocess.STDOUT)
 row=dict(label=name,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode,expected_exit_code=expected)
 rows.append(row);(root/'checks-initial.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 assert result.returncode==expected,name
 if expected:assert 'unrelated client initializations were serialized' in (root/(name+'.log')).read_text()
