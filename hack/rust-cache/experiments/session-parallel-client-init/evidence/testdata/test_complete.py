from pathlib import Path
import json,os,subprocess,time
root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base=['-p','2','-buildvcs=false','-modfile',str(root.parent/'otel-evicted-queue/engine.go.mod')]
jobs=[('after-package','after',[],None),('after-race','after',['-race'],None)]
rows=[]
for name,arm,extra,mode in jobs:
 cmd=[go,'test',*base,'-overlay',str(root/('overlay-'+arm+'.json')),*extra,'-count=1','-timeout=180s','./engine/server']
 tick=time.monotonic()
 with (root/(name+'.log')).open('w') as out:
  result=subprocess.run(cmd,cwd='/tmp/dagger-filesync-snapshot-seeds',env=dict(os.environ,GOMAXPROCS='4',GOTOOLCHAIN='local'),stdout=out,stderr=subprocess.STDOUT)
 row=dict(label=name,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode)
 rows.append(row);(root/'checks-complete.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 assert result.returncode==0,name
