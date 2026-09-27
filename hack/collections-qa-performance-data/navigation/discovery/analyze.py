"""Offline numeric wcprof projection; excludes arguments, IDs and raw string tables."""
from pathlib import Path
from collections import Counter
import json, hashlib
D=Path(__file__).resolve().parent
T=Path('/tmp/collections-perf/engine-allocation-round2/navigation-generate-v1')
p=T/'diagnostic-0-artifacts/run.wcprof'
f=p.open(); h=json.loads(next(f)); ops=[json.loads(line) for line in f if line.strip()]; ops=[x for x in ops if x['e']=='op']
row=next(x for x in json.loads((T/'results.json').read_text()) if x['flow']=='artifacts' and x['phase']=='diagnostic')
assert h['dropped_events']==0 and not h.get('open_ops')
idx={x['id']:x for x in ops}; names=h['strings']; name=lambda x:names[x.get('c',0)]; epoch=h['epoch_unix_nano']; origin=row['started_unix_ns']
def union(rows):
 merged=[]
 for a,b in sorted((x['s'],x['d']) for x in rows):
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 return sum(b-a for a,b in merged)/1e6
def stats(rows):return {'count':len(rows),'inclusive_sum_ms':sum(x['d']-x['s'] for x in rows)/1e6,'union_ms':union(rows),'max_ms':max((x['d']-x['s'] for x in rows),default=0)/1e6}
def timing(x):return {'start_from_cli_ms':(epoch+x['s']-origin)/1e6,'end_from_cli_ms':(epoch+x['d']-origin)/1e6,'duration_ms':(x['d']-x['s'])/1e6}
def ancestry(x):
 out=[]
 while x.get('p') in idx:
  x=idx[x['p']]
  if x['k'] in ('call','internal'):out.append(name(x))
 return out
runtime=sorted([x for x in ops if name(x)=='exec.processRun'],key=lambda x:x['s']);registration=[];backend=[]
for x in runtime:
 assert json.loads(names[x['m']])[0]=='/runtime'
 a=ancestry(x)
 if a[0]=='ModuleSource.asModule':registration.append(x)
 else:
  assert a[0] in ('backend:Query.backend','backend:Backend.goTestBase')
  backend.append(x)
assert len(registration)==4 and len(backend)==2
phases={}
for kind,n in [('call','Workspace.artifacts'),('call','Artifacts.__itemsJSON'),('internal','git.publicAdvertisement'),('session_phase','session.schemaBuild'),('internal','typescript.staticMetadata'),('internal','dang.invoke'),('internal','schema.forkPrepared')]:
 xs=sorted([x for x in ops if x['k']==kind and name(x)==n],key=lambda x:x['s']); phases[n]={'kind':kind,**stats(xs),'intervals':[timing(x) for x in xs]}
module_calls=[x for x in ops if x['k']=='call' and name(x)=='ModuleSource.asModule']
artifact=next(x for x in ops if x['k']=='call' and name(x)=='Workspace.artifacts')
result={
 'status':'existing warm profile analysis only; no new runtime or performance trial',
 'command':['dagger','list','-a'],'profile_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'cli_ms':row['seconds']*1000,'dropped_events':0,'op_count':len(ops),
 'call_outcomes':dict(Counter(x.get('o','') for x in ops if x['k']=='call')),
 'phases':phases,
 'metadata_processes':{'classification':'legacy Go module definition registration; moduleDefViaRuntime ancestry',**stats(registration),'intervals':[timing(x) for x in registration]},
 'backend_processes':{'classification':'actual configured constructor and goTestBase invocation',**stats(backend),'intervals':[dict(timing(x),operation=ancestry(x)[0]) for x in backend]},
 'last_module_asModule_return_to_static_catalog_return_ms':(artifact['d']-max(x['d'] for x in module_calls))/1e6,
 'module_asModule_call_count':len(module_calls),
 'module_asModule_call_outcomes':dict(Counter(x.get('o','') for x in module_calls)),
 'limitations':['Inclusive durations overlap; process union is not a predicted removable CLI duration.','The complete snapshot uses a retained experimental engine; do not relabel it current unmodified main.','Registration source names cannot be inferred from /runtime argv or asModule ancestry alone.']}
(D/'numeric.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('cli_ms','metadata_processes','backend_processes','last_module_asModule_return_to_static_catalog_return_ms')},indent=2))
