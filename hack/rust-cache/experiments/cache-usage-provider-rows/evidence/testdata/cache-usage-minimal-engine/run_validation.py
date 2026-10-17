from pathlib import Path
import json,subprocess,time
root=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
command=[go,'test','-p','2','-race','-buildvcs=false','-count=1','./dagql']
started=time.monotonic()
with (root/'production-full-dagql-race.log').open('w') as out:r=subprocess.run(command,cwd='/tmp/dagger-cache-usage-sampler-only',stdout=out,stderr=subprocess.STDOUT)
(root/'production-validation.json').write_text(json.dumps(dict(command=command,exit_code=r.returncode,seconds=time.monotonic()-started),indent=2)+'\n')
print('production full race',r.returncode,flush=True);assert r.returncode==0
r=subprocess.run(['python3',str(root/'validate_engine.py')]);assert r.returncode==0
