from pathlib import Path
import json,hashlib
D=Path(__file__).resolve().parent
p=Path('/tmp/collections-perf/ancestor-request-full-warm-profiles-v1/results-v1/03-1-fully-primed-profile-checks-candidate/run.wcprof.private')
with p.open() as f:
 h=json.loads(next(f));ops=[json.loads(l) for l in f if l.strip()]
ops=[o for o in ops if o.get('e')=='op'];by={o['id']:o for o in ops};origin=min(o['s'] for o in ops)
def name(o):return h['strings'][o.get('c',0)]
def union(seq):
 out=[]
 for a,b in sorted(seq):
  if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
  else:out.append([a,b])
 return sum(b-a for a,b in out)/1e6
def stat(xs):return {'count':len(xs),'sum_ms':sum(o['d']-o['s'] for o in xs)/1e6,'union_ms':union((o['s'],o['d'])for o in xs),'intervals':[{'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}for o in sorted(xs,key=lambda o:o['s'])]}
classes=[('call_exec','Workspace.artifacts'),('call_exec','Artifacts.__itemsJSON'),('internal','git.publicAdvertisement'),('internal','session.schemaBuild'),('internal','session.modulesLoad'),('internal','schema.forkPrepared'),('internal','dang.invoke'),('internal','dang.runSource'),('call_exec','ModuleSource.asModule')]
# Kinds of internal timers vary; names uniquely identify the static markers.
phases={cl:stat([o for o in ops if name(o)==cl and (k!='call_exec' or o['k']==k)]) for k,cl in classes}
processes=[];groups={'catalog_metadata':[],'authored_backend':[],'other':[]}
allowed={'ModuleSource.asModule','Query.moduleSource','Workspace.artifacts','Artifacts.__itemsJSON','Address.container','backend:Query.backend','backend:Backend.goTestBase'}
for o in sorted([o for o in ops if name(o)=='exec.processRun'],key=lambda o:o['s']):
 cur=o;seen=set();ancestry=[]
 while cur and cur['id']not in seen:
  seen.add(cur['id']);n=name(cur)
  if n in allowed and(not ancestry or ancestry[-1]!=n):ancestry.append(n)
  cur=by.get(cur.get('p'))
 group='catalog_metadata' if 'Workspace.artifacts'in ancestry else('authored_backend' if any(n.startswith('backend:')for n in ancestry)else'other')
 groups[group].append(o)
 processes.append({'start_ms':(o['s']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6,'fixed_label_parent_chain':ancestry,'classification':group})
result={'source_profile_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'cache_boundary':'Ordinary full listing immediately preceded this profile on a previously loaded engine. No Cloud. Diagnostic only.','open_operations':len(h.get('open_ops',[])),'dropped_events':h['dropped_events'],'phases':phases,'runtime_processes':processes,'process_groups':{k:stat(v)for k,v in groups.items()},'scope_limit':'Inclusive phases overlap and profiler markers do not cover every possible schema construction path. Process interval union is not attainable command savings.'}
(D/'catalog-numeric.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'runtime_processes':processes,'process_groups':{k:{kk:vv for kk,vv in stat(v).items()if kk!='intervals'}for k,v in groups.items()}}))
