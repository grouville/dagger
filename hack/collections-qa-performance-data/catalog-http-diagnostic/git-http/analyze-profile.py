"""Numeric-only reduction of Git HTTP and source/SDK wcprof hooks.
Raw wcprof input is private; outputs contain fixed labels, times, counts, hashes.
"""
from pathlib import Path
import argparse,json,hashlib
P='git.publicAdvertisement'
HTTP=['getConn','connectionNew','connectionReused','dns','connect','tls','requestWritten','writeToFirstByte','firstByte','lastFirstByteToParsed','firstByteBeforeWrite','writePairingAmbiguous']
ALLOWED=[P,P+'.readAndDecode',P+'.validateAllReferences',P+'.materializeAndSort',*[P+'.http.'+s for s in HTTP],'moduleSource.loadContext','moduleSource.loadSDK','Workspace.artifacts','Artifacts.__itemsJSON','filesync.syncParentDirs','session.query']
def union(seq):
 out=[]
 for a,b in sorted(seq):
  if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
  else:out.append([a,b])
 return sum(b-a for a,b in out)/1e6
def main():
 ap=argparse.ArgumentParser();ap.add_argument('profile',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
 with a.profile.open()as f:h=json.loads(next(f));ops=[json.loads(l)for l in f if l.strip()]
 ops=[o for o in ops if o.get('e')=='op'];by={o['id']:o for o in ops};origin=min(o['s']for o in ops)
 def name(o):return h['strings'][o.get('c',0)]
 def eligible(o,n):return name(o)==n and(n not in ['Workspace.artifacts','Artifacts.__itemsJSON']or o['k']=='call_exec')
 def stat(xs):return {'count':len(xs),'sum_ms':sum(o['d']-o['s']for o in xs)/1e6,'union_ms':union((o['s'],o['d'])for o in xs),'maximum_ms':max([o['d']-o['s']for o in xs],default=0)/1e6,'error_count':sum(o.get('o')=='error'for o in xs)}
 def has_parent(o,p):
  seen=set()
  while o and o['id']not in seen:
   if o['id']==p['id']:return True
   seen.add(o['id']);o=by.get(o.get('p'))
  return False
 ads=[]
 for ad in sorted([o for o in ops if name(o)==P],key=lambda o:o['s']):
  children=[o for o in ops if name(o)in ALLOWED and has_parent(o,ad)]
  phases={n:stat([o for o in children if eligible(o,n)])for n in ALLOWED if n.startswith(P+'.')}
  source_ancestors=[];cur=by.get(ad.get('p'));seen=set()
  while cur and cur['id']not in seen:
   seen.add(cur['id'])
   if name(cur)in ['moduleSource.loadContext','moduleSource.loadSDK']:source_ancestors.append(name(cur))
   cur=by.get(cur.get('p'))
  ads.append({'ordinal':len(ads),'start_ms':(ad['s']-origin)/1e6,'duration_ms':(ad['d']-ad['s'])/1e6,'source_stage_ancestors':source_ancestors,'phases':phases,'write_pairing_ambiguous':any(phases[P+'.http.'+k]['count']for k in ['firstByteBeforeWrite','writePairingAmbiguous'])})
 stages=[]
 for stage in sorted([o for o in ops if name(o)in ['moduleSource.loadContext','moduleSource.loadSDK']],key=lambda o:o['s']):
  descendants=[o for o in ops if name(o)==P and has_parent(o,stage)]
  stages.append({'phase':name(stage),'start_ms':(stage['s']-origin)/1e6,'duration_ms':(stage['d']-stage['s'])/1e6,'advertisements':stat(descendants)})
 pairs=[]
 for c in [o for o in ops if name(o)=='moduleSource.loadContext']:
  candidates=[o for o in ops if name(o)=='moduleSource.loadSDK'and o.get('p')==c.get('p') and o['s']>=c['d']]
  if candidates:
   sdk=min(candidates,key=lambda o:o['s']);pairs.append({'context_ms':(c['d']-c['s'])/1e6,'sdk_ms':(sdk['d']-sdk['s'])/1e6,'gap_ms':(sdk['s']-c['d'])/1e6})
 slowest=max([o for o in ops if name(o)=='moduleSource.loadSDK'],key=lambda o:o['d']-o['s'],default=None)
 nested={}
 if slowest:
  for cl in ['exec.processRun','ModuleSource.asModule']:
   nested[cl]=stat([o for o in ops if name(o)==cl and (cl!='ModuleSource.asModule'or o['k']=='call_exec')and has_parent(o,slowest)])
 result={'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest(),'open_operations':len(h.get('open_ops',[])),'dropped_events':h['dropped_events'],'phases':{n:stat([o for o in ops if eligible(o,n)])for n in ALLOWED},'advertisements':ads,'source_stages':stages,'paired_source_stages':pairs,'slowest_sdk_children':nested,'interpretation':'Fixed labels only. Nested interval sums overlap; getConn includes DNS/connect/TLS. Last-first-byte-to-parsed includes response headers/body/decode, not server time. Callback pairing ambiguity suppresses derived write intervals. Completed losing connection attempts can outlive the parent request. No wall-time saving follows from these diagnostics.'}
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'output':str(a.output),'advertisements':len(ads),'open':result['open_operations'],'drops':result['dropped_events']}))
if __name__=='__main__':main()
