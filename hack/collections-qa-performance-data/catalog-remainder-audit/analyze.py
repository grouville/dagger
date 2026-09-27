#!/usr/bin/env python3
"""Read saved wcprof; publish only fixed classes, interval unions and hashes."""
from pathlib import Path
from collections import defaultdict
import json,hashlib
HERE=Path(__file__).resolve().parent
CASES={
 'cold-control':Path('/tmp/collections-perf/go-base-address-cold-profile-v1/results-v1/0-control/run.wcprof.private'),
 'cold-candidate':Path('/tmp/collections-perf/go-base-address-cold-profile-v1/results-v1/1-candidate/run.wcprof.private'),
 'warm-control':Path('/tmp/collections-perf/go-base-address-timing-v1/results-v1/25-4-control-diagnostic-checks/run.wcprof.private'),
 'warm-candidate':Path('/tmp/collections-perf/go-base-address-timing-v1/results-v1/27-5-candidate-diagnostic-checks/run.wcprof.private'),
}
LABELS=('Workspace.artifacts','Artifacts.__itemsJSON','ModuleSource.asModule','Query.moduleSource',
 'builtinImage.copyContent','builtinImage.importRootfs','image.importLayer','image.applyLayer','image.commitSnapshot',
 'dang.selfTypes','dang.runSource','dang.invoke','dang.decodeSchema','dagql.publishResult',
 'git.publicAdvertisement','git.publicAdvertisement.http.writeToFirstByte','moduleSource.loadSDK','moduleSource.loadContext')
def merged(xs):
 out=[]
 for a,b in sorted(xs):
  if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
  else:out.append([a,b])
 return out
def subtract(xs,ys):
 out=[]
 for a,b in merged(xs):
  for c,d in merged(ys):
   if c>=b:break
   if d<=a:continue
   if c>a:out.append((a,c))
   a=max(a,d)
  if a<b:out.append((a,b))
 return out
def millis(xs):return sum(b-a for a,b in merged(xs))/1e6
def reduce(path):
 data=path.read_bytes();lines=data.splitlines();h=json.loads(lines[0]);ops=[v for line in lines[1:]if(v:=json.loads(line)).get('e')=='op'];label=lambda o:h['strings'][o.get('c',0)]
 catalog=next(o for o in ops if label(o)=='Workspace.artifacts'and o['k']=='call_exec');window=(catalog['s'],catalog['d'])
 builds=[(o['s'],o['d'])for o in ops if label(o)=='exec.processRun'and o.get('m')and json.loads(h['strings'][o['m']])[:2]==['go','build']]
 groups=defaultdict(list)
 for o in ops:
  if o['k']=='call' or label(o)not in LABELS:continue
  a,b=max(window[0],o['s']),min(window[1],o['d'])
  if a<b:groups[(label(o),o['k'])].append((a,b))
 return {'profile_sha256':hashlib.sha256(data).hexdigest(),'open':len(h.get('open_ops',[])),'dropped':h.get('dropped_events',0),
  'catalog_ms':(window[1]-window[0])/1e6,'build_intervals_in_catalog_ms':millis([(max(window[0],a),min(window[1],b))for a,b in builds if a<window[1]and b>window[0]]),
  'catalog_outside_build_ms':millis(subtract([window],builds)),
  'outside_build_segments_relative_to_catalog_ms':[[ (a-window[0])/1e6,(b-window[0])/1e6]for a,b in subtract([window],builds)],
  'classes_in_catalog':[{'class':name,'kind':kind,'count':len(xs),'inclusive_sum_ms':sum(b-a for a,b in xs)/1e6,'union_ms':millis(xs),'max_ms':max(b-a for a,b in xs)/1e6,'union_outside_build_ms':millis(subtract(xs,builds))}for(name,kind),xs in sorted(groups.items())],
  'scope':'Temporal clipping and interval subtraction; classes overlap. Excludes raw metadata, identities, source paths and process arguments. Not a causal counterfactual.'}
if __name__=='__main__':
 v={name:reduce(path)for name,path in CASES.items()};(HERE/'numeric.json').write_text(json.dumps(v,indent=2)+'\n')
 print(json.dumps({n:{'catalog_ms':x['catalog_ms'],'outside_build_ms':x['catalog_outside_build_ms'],'self_types':[r for r in x['classes_in_catalog']if r['class']=='dang.selfTypes']}for n,x in v.items()},indent=2))
