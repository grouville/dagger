from pathlib import Path
import json,subprocess,time
family=Path(__file__).parent
root=family/'capture'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
engine=family.parent/'session-parallel-client-init/dagger-engine'
cli=family.parent/'filesync-literal-pathwalk/dagger-after'
profile=root/'wcprof-complete.ndjson'
jobs=[]
for process,binary in [('engine',engine),('cli',cli)]:
 windows=sorted(root.glob(process+'-cpu-*.pprof'))
 assert windows,process
 for cumulative in [False,True]:
  name=process+'-cpu-'+('cumulative' if cumulative else 'flat')+'.txt'
  cmd=[go,'tool','pprof','-top','-nodecount=65']
  if cumulative:cmd.append('-cum')
  cmd += [str(binary),*map(str,windows)]
  jobs.append((name,cmd))
 if process=='cli':
  allocs=sorted(p for p in root.glob('cli-allocs-*.pprof') if p.name!='cli-allocs-before.pprof')
  assert allocs
  after=allocs[-1]
 else:after=root/'engine-allocs-after.pprof'
 for metric in ['alloc_space','alloc_objects']:
  name=process+'-'+metric+'.txt'
  jobs.append((name,[go,'tool','pprof','-top','-nodecount=45','-sample_index='+metric,'-base',str(root/(process+'-allocs-before.pprof')),str(binary),str(after)]))
for kind in ['internal','call','session_phase']:
 jobs.append(('wcprof-'+kind+'.txt',['/tmp/rust-cache-wcprof-report','-view','classes','-kind',kind,'-sort','self','-top','35',str(profile)]))
with profile.open() as inp:
 header=json.loads(next(inp));strings=header['strings'];queries=[]
 for line in inp:
  e=json.loads(line)
  if e.get('e')=='op' and strings[e['c']]=='session.serveQuery':queries.append(e)
queries.sort(key=lambda e:e['d']-e['s'],reverse=True)
(root/'largest-queries.json').write_text(json.dumps(queries[:6],indent=2)+'\n')
for rank,query in enumerate(queries[:6]):
 jobs.append(('wcprof-query-'+str(rank)+'-critical.txt',['/tmp/rust-cache-wcprof-report','-view','critpath','-op',str(query['id']),str(profile)]))
rows=[]
for name,cmd in jobs:
 tick=time.monotonic()
 with (root/name).open('w') as out:result=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
 row=dict(output=name,command=cmd,seconds=time.monotonic()-tick,exit_code=result.returncode)
 rows.append(row);(root/'analysis-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,result.returncode,flush=True)
 assert result.returncode==0,name
