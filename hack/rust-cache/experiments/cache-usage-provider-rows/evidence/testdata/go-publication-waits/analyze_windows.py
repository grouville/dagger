from pathlib import Path
import json,subprocess,time
root=Path(__file__).parent/'capture'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
binary='/tmp/rust-cache-sipsma-review/dang-prepared-schema/dagger-engine'
jobs=[]
for index in [1,2]:
 jobs.append((f'cpu-{index:03d}-cumulative.txt',[go,'tool','pprof','-top','-cum','-lines','-nodecount=45',binary,str(root/f'engine-cpu-{index:03d}.pprof')]))
for kind in ['mutex','block']:
 before=root/f'{kind}-001.pprof';after=root/f'{kind}-002.pprof'
 for view in ['top','traces']:
  cmd=[go,'tool','pprof','-'+view,'-sample_index=delay','-base',str(before)]
  if view=='top':cmd+=['-cum','-lines','-nodecount=50']
  else:cmd+=['-focus=dagql|slog|engine/server']
  jobs.append((f'{kind}-002-{view}.txt',cmd+[binary,str(after)]))
rows=[]
for name,command in jobs:
 start=time.monotonic()
 with (root/name).open('w') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
 rows.append(dict(name=name,command=command,seconds=time.monotonic()-start,exit_code=r.returncode))
 (root/'window-analysis-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,r.returncode,flush=True)
 assert r.returncode==0,name
