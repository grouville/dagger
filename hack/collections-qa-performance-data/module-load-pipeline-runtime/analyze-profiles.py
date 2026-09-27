"""Reduce private saved wcprof to fixed-label numeric scheduling evidence only."""
from pathlib import Path
import json,hashlib
D=Path(__file__).resolve().parent;O=D/'profile-evidence';O.mkdir(exist_ok=True)
paths={'baseline':D/'results-v1/39-4-diagnostic-checks-baseline/run.wcprof.private','candidate':D/'results-v1/41-5-diagnostic-checks-candidate/run.wcprof.private'}
labels=['Workspace.artifacts','Artifacts.__itemsJSON','Query.moduleSource','ModuleSource.asModule','exec.processRun','git.publicAdvertisement','git.publicAdvertisement.http.writeToFirstByte','git.publicAdvertisement.http.connectionNew','git.publicAdvertisement.http.connectionReused','moduleSource.loadContext','moduleSource.loadSDK','session.query']
def union(xs):
 out=[]
 for a,b in sorted(xs):
  if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
  else:out.append([a,b])
 return sum(b-a for a,b in out)/1e6
def stat(xs):return {'count':len(xs),'sum_ms':sum(o['d']-o['s']for o in xs)/1e6,'union_ms':union((o['s'],o['d'])for o in xs),'maximum_ms':max([o['d']-o['s']for o in xs],default=0)/1e6,'error_count':sum(o.get('o')=='error'for o in xs)}
results={}
for arm,path in paths.items():
 with path.open()as f:h=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
 ops=[o for o in ops if o.get('e')=='op'];by={o['id']:o for o in ops};origin=min(o['s']for o in ops)
 def name(o):return h['strings'][o.get('c',0)]
 def parents(o):
  cur=by.get(o.get('p'));seen=set()
  while cur and cur['id']not in seen:
   seen.add(cur['id']);yield cur;cur=by.get(cur.get('p'))
 def sources(o):return[p for p in parents(o)if name(p)=='Query.moduleSource'and p['k']=='call_exec']
 def rec(o):return {'start_ms':(o['s']-origin)/1e6,'end_ms':(o['d']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}
 def eligible(o,n):return name(o)==n and(n not in ['Workspace.artifacts','Artifacts.__itemsJSON','Query.moduleSource','ModuleSource.asModule']or o['k']=='call_exec')
 roots=sorted([o for o in ops if eligible(o,'Query.moduleSource')and not sources(o)],key=lambda o:o['s']);ordinals={o['id']:i for i,o in enumerate(roots)}
 ads=[]
 for ad in sorted([o for o in ops if name(o)=='git.publicAdvertisement'],key=lambda o:o['s']):
  ss=sources(ad);root=ss[-1]if ss else None;near=ss[0]if ss else None
  ads.append({'ordinal':len(ads),**rec(ad),'source_depth':len(ss),'top_source_ordinal':ordinals.get(root['id'])if root else None,'since_nearest_source_start_ms':(ad['s']-near['s'])/1e6 if near else None})
 catalog=[o for o in ops if eligible(o,'Workspace.artifacts')];assert len(catalog)==1
 expansion=[o for o in ops if eligible(o,'Artifacts.__itemsJSON')];assert len(expansion)==1
 execs=[o for o in ops if name(o)=='exec.processRun']
 results[arm]={'profile_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'open':len(h.get('open_ops',[])),'dropped_events':h['dropped_events'],'phases':{n:stat([o for o in ops if eligible(o,n)])for n in labels},'catalog':rec(catalog[0]),'expansion':rec(expansion[0]),'top_sources':[{'ordinal':i,**rec(o)}for i,o in enumerate(roots)],'advertisements':ads,'processes_temporally_enclosed_in_catalog':stat([o for o in execs if o['s']>=catalog[0]['s']and o['d']<=catalog[0]['d']]),'processes_temporally_enclosed_in_expansion':stat([o for o in execs if o['s']>=expansion[0]['s']and o['d']<=expansion[0]['d']])}
assert all(r['open']==r['dropped_events']==0 for r in results.values())
notes=['One separately profiled sample per arm after full primer, baseline then candidate; no causal wall-time claim from profile delta alone.','Ordinals represent start order, not matched module identities.','No root job/permit marker exists; full source-to-registration critical branch cannot be reconstructed by neighboring timestamps.','Nested sums overlap; unions are interval unions within each label, not additive savings.','These profiles do not measure peak memory or engine-wide process concurrency.']
(O/'numeric.json').write_text(json.dumps({'arms':results,'notes':notes},indent=2)+'\n')
for arm,r in results.items():
 print(json.dumps({'arm':arm,'roots':len(r['top_sources']),'ninth_source_start_ms':r['top_sources'][8]['start_ms'],'catalog_ms':r['catalog']['duration_ms'],'expansion_ms':r['expansion']['duration_ms'],'query_union_ms':r['phases']['session.query']['union_ms'],'git_union_ms':r['phases']['git.publicAdvertisement']['union_ms'],'process_count':r['phases']['exec.processRun']['count'],'git_count':r['phases']['git.publicAdvertisement']['count']}))
