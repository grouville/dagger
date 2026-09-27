from pathlib import Path
import hashlib,json,subprocess
D=Path(__file__).resolve().parent;R=Path('/home/dagger/dag')
PROFILES={"unix":"/tmp/collections-perf/direct-unix-transport-v1/results-v1/53-5-diagnostic-checks-unix/run.wcprof.private","docker":"/tmp/collections-perf/direct-unix-transport-v1/results-v1/55-6-diagnostic-checks-docker/run.wcprof.private"}
def union(rows):
 merged=[]
 for a,b in sorted(rows):
  if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
  else:merged.append([a,b])
 return sum(b-a for a,b in merged)/1e6
def summarize(path):
 with Path(path).open() as f:h=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
 ops=[o for o in ops if o.get('e')=='op'];by={o['id']:o for o in ops};name=lambda o:h['strings'][o.get('c',0)]
 def parents(o):
  seen=set()
  while o and o['id']not in seen:
   seen.add(o['id']);yield o;o=by.get(o.get('p'))
 ads=sorted([o for o in ops if name(o)=='git.publicAdvertisement'],key=lambda o:o['s'])
 git=[o for o in ops if name(o)=='Query.git'and o['k']=='call_exec']
 def stat(n,k=None):
  xs=[o for o in ops if name(o)==n and(k is None or o['k']==k)]
  return {'count':len(xs),'sum_ms':sum(o['d']-o['s']for o in xs)/1e6,'union_ms':union((o['s'],o['d'])for o in xs),'errors':sum(o.get('o')=='error'for o in xs)}
 chains=[list(parents(o))for o in ads]
 nearest=[next(o for o in chain if name(o)=='Query.git'and o['k']=='call_exec')for chain in chains]
 roots=[next((o['id']for o in chain if name(o)=='session.serveQuery'),None)for chain in chains]
 return {'profile_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'open_operations':len(h.get('open_ops',[])),'dropped_events':h['dropped_events'],'phases':{n:stat(n,'call_exec'if n=='Query.git'else None)for n in ['Query.git','git.publicAdvertisement','git.lsRemote','git.publicAdvertisement.http.connectionReused','git.publicAdvertisement.http.connectionNew','git.publicAdvertisement.http.writeToFirstByte']},'ad_nearest_git_call_unique_opaque_identities':len(set(o.get('i')for o in nearest)),'ad_query_roots':len(set(roots)),'all_ads_under_module_source':all(any(name(o)=='Query.moduleSource'for o in chain)for chain in chains),'direct_network_marker_remotes_recorded':False,'advertisement_calls_per_nearest_git_identity':sorted([sum(o.get('i')==i for o in nearest)for i in set(o.get('i')for o in nearest)])}
files=['core/schema/git.go','core/schema/git_visibility_test.go','core/git_remote.go','core/modulerefs.go','util/gitutil/url.go','dagql/cache_arbitrary.go']
res={'scope':'Read-only retained-profile/source audit; no tests, builds or network calls. Call identities are opaque and are not repository names.','profiles':{k:summarize(v)for k,v in PROFILES.items()},'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'source_sha256':{f:hashlib.sha256((R/f).read_bytes()).hexdigest()for f in files},'measured_and_current_git_schema_source_equal':subprocess.check_output(['git','show','0d1c32e29f:core/schema/git.go'],cwd=R)==(R/'core/schema/git.go').read_bytes()}
(D/'numeric.json').write_text(json.dumps(res,indent=2)+'\n')
print(json.dumps(res['profiles'],indent=2))
