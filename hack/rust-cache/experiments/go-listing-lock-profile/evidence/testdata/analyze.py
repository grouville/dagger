from pathlib import Path
import json
import subprocess
import time

family=Path(__file__).parent
root=family/'capture'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
profile=root/'wcprof-complete.ndjson'
jobs=[
 ('wcprof-internal.txt', ['/tmp/rust-cache-wcprof-report','-view','classes','-kind','internal','-sort','self','-top','40',str(profile)]),
 ('wcprof-calls.txt', ['/tmp/rust-cache-wcprof-report','-view','classes','-kind','call','-sort','self','-top','40',str(profile)]),
 ('wcprof-session-phases.txt', ['/tmp/rust-cache-wcprof-report','-view','classes','-kind','session_phase','-sort','self','-top','30',str(profile)]),
]
for kind in ['mutex','block']:
 for metric in ['delay','contentions']:
  for cumulative in [False,True]:
   name=f'{kind}-{metric}-{"cumulative" if cumulative else "flat"}.txt'
   cmd=[go,'tool','pprof','-top','-nodecount=65','-sample_index='+metric,'-base',str(root/(kind+'-before.pprof'))]
   if cumulative:cmd.append('-cum')
   cmd += [str(family/'dagger-engine'),str(root/(kind+'-after.pprof'))]
   jobs.append((name,cmd))
rows=[]
for name,cmd in jobs:
 tick=time.monotonic()
 with (root/name).open('w') as output:
  result=subprocess.run(cmd,cwd='/tmp/dagger-filesync-snapshot-seeds',stdout=output,stderr=subprocess.STDOUT)
 row=dict(output=name,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode)
 rows.append(row)
 (root/'analysis-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,result.returncode,flush=True)
 assert result.returncode==0,name
