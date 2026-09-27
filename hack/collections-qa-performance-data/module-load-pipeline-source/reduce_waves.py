"""Read private wcprof and emit only fixed operation labels and numeric timings."""
from pathlib import Path
import json, hashlib
D=Path(__file__).resolve().parent
profiles={
'unix':Path('/tmp/collections-perf/direct-unix-transport-v1/results-v1/53-5-diagnostic-checks-unix/run.wcprof.private'),
'docker':Path('/tmp/collections-perf/direct-unix-transport-v1/results-v1/55-6-diagnostic-checks-docker/run.wcprof.private')}
result={}
for label,path in profiles.items():
 with path.open()as f:h=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
 ops=[o for o in ops if o.get('e')=='op'];by={o['id']:o for o in ops};origin=min(o['s']for o in ops)
 def name(o):return h['strings'][o.get('c',0)]
 def parents(o):
  cur=by.get(o.get('p'));seen=set()
  while cur and cur['id']not in seen:
   seen.add(cur['id']);yield cur;cur=by.get(cur.get('p'))
 def sources(o):return [p for p in parents(o) if name(p)=='Query.moduleSource' and p['k']=='call_exec']
 def record(o):return {'start_ms':(o['s']-origin)/1e6,'end_ms':(o['d']-origin)/1e6,'duration_ms':(o['d']-o['s'])/1e6}
 roots=sorted([o for o in ops if name(o)=='Query.moduleSource' and o['k']=='call_exec' and not sources(o)],key=lambda o:o['s'])
 root_ord={o['id']:i for i,o in enumerate(roots)}
 ads=[]
 for ad in sorted([o for o in ops if name(o)=='git.publicAdvertisement'],key=lambda o:o['s']):
  ss=sources(ad);near=ss[0] if ss else None;root=ss[-1]if ss else None
  gs=[o for o in parents(ad)if name(o)=='Query.git'and o['k']=='call_exec']
  ad_row={'ordinal':len(ads),**record(ad),'top_source_ordinal':root_ord.get(root['id'])if root else None,'source_depth':len(ss),'since_nearest_source_start_ms':(ad['s']-near['s'])/1e6 if near else None,'since_top_source_start_ms':(ad['s']-root['s'])/1e6 if root else None,'first_ancestor_git_start_ms':(gs[-1]['s']-origin)/1e6 if gs else None}
  ads.append(ad_row)
 conversions=sorted([o for o in ops if name(o)=='ModuleSource.asModule'and o['k']=='call_exec'and not any(name(p)=='ModuleSource.asModule'and p['k']=='call_exec'for p in parents(o))],key=lambda o:o['s'])
 result[label]={'profile_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'open':len(h.get('open_ops',[])),'drops':h['dropped_events'],'top_sources':[{'ordinal':i,**record(o)}for i,o in enumerate(roots)],'advertisements':ads,'top_as_module':[{'ordinal':i,**record(o)}for i,o in enumerate(conversions)],'notes':['Ordinals are temporal, not module identities.','No job/permit marker exists: eight-root batching and one delayed ninth source are observed, but their precise ready/enqueue times are not.','Nested source admissions are dependent on configuration/dependency discovery; they are not all queued top-level roots.','Top-level source to asModule identity is not reconstructed from timing.']}
(D/'wave-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{'roots':len(v['top_sources']),'ads':len(v['advertisements']),'ninth_start_ms':v['top_sources'][8]['start_ms'],'nested_ads':sum(a['source_depth']>1 for a in v['advertisements'])}for k,v in result.items()}))
