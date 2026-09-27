#!/usr/bin/env python3
"""Offline numeric reduction only. No engine calls or raw record publication."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,statistics
P=Path(__file__).resolve().parent
KINDS=('call','call_exec','phase','internal','session_phase','exec_phase','io')
LABELS=(
 'session.query','Workspace.artifacts','Artifacts.__itemsJSON',
 'artifact.moduleTree','artifact.coreTree','artifact.batch',
 'Address.container','Query.typeDef','TypeDef.withOptional','Module._implementationScoped',
 'backend:Query.backend','backend:Backend.goTestBase',
 'go:Query.go','go:Go.modules','go:GoModule.tests',
 'gomod:Gomod.modules','gomod:Gomod.workspaceRootPath',
 'Workspace.findRoots','Workspace.file','Host.directory',
 'filesync.syncParentDirs','git.publicAdvertisement','exec.processRun',
 'dang.invoke','dang.runSource','dang.flushTelemetry',
)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def union_ns(intervals):
 merged=[]
 for lo,hi in sorted(intervals):
  if merged and lo<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],hi)
  else:merged.append([lo,hi])
 return sum(hi-lo for lo,hi in merged)
def stats(ops):
 return {'count':len(ops),'inclusive_sum_ms':sum(o['d']-o['s']for o in ops)/1e6,'union_ms':union_ns((o['s'],o['d'])for o in ops)/1e6,'max_ms':max((o['d']-o['s']for o in ops),default=0)/1e6,'hits':sum(o.get('o')in('hit','cache_hit')for o in ops),'errors':sum(o.get('o')=='error'for o in ops)}
def reduce_profile(path):
 with path.open()as stream:
  head=json.loads(next(stream));ops=[v for line in stream if line.strip()for v in [json.loads(line)]if v.get('e')=='op']
 children=defaultdict(list)
 for o in ops:children[o.get('p')].append(o)
 def label(o):return head['strings'][o.get('c',0)]
 def descendants(root):
  todo=[root];seen=set();result=[]
  while todo:
   o=todo.pop()
   if o['id']in seen:continue
   seen.add(o['id']);result.append(o);todo.extend(children[o['id']])
  return result
 def aggregate(xs):
  grouped=defaultdict(list)
  for o in xs:
   name=label(o)
   if name in LABELS and o['k']in KINDS:grouped[(name,o['k'])].append(o)
  return [{'class':name,'kind':kind,**stats(grouped[(name,kind)])}for name in LABELS for kind in KINDS if(name,kind)in grouped]
 expansions=[o for o in ops if label(o)=='Artifacts.__itemsJSON'and o['k']=='call_exec']
 assert len(expansions)==1,'profile must cover exactly the requested expanded listing'
 expansion=expansions[0];nested=descendants(expansion)
 addresses=sorted((o for o in nested if label(o)=='Address.container'and o['k']=='call_exec'),key=lambda o:o['s'])
 processes=sorted((o for o in ops if label(o)=='exec.processRun'),key=lambda o:o['s'])
 # No raw identifiers, function arguments, remote URLs, environment or payloads.
 return {'profile_sha256':sha(path),'operations':len(ops),'open_operations':len(head.get('open_ops',[])),'dropped_events':head.get('dropped_events',0),'whole':aggregate(ops),'expansion':{'duration_ms':(expansion['d']-expansion['s'])/1e6,'nested':aggregate(nested)},'addresses':[{'ordinal':i,'relative_to_expansion_ms':(o['s']-expansion['s'])/1e6,'duration_ms':(o['d']-o['s'])/1e6,'nested':aggregate(descendants(o))}for i,o in enumerate(addresses)],'runtime_process_intervals':[{'ordinal':i,'relative_to_expansion_ms':(o['s']-expansion['s'])/1e6,'duration_ms':(o['d']-o['s'])/1e6}for i,o in enumerate(processes)],'interpretation':'Inclusive sums overlap; unions are within each fixed class, not additive across labels. Tree markers cover tree construction, not later traversal. Runtime process names/arguments are deliberately omitted.'}
def main():
 rows=json.loads((P/'results-numeric.json').read_text());summary=json.loads((P/'summary-v1.json').read_text());restored=json.loads((P/'results-v1/lifecycle-restoration.json').read_text())
 assert len(rows)==28 and all(r['correct']for r in rows)and summary['validated_commands']==28
 assert summary['copied_fixture_restored']and summary['original_fixture_untouched']
 assert restored['validated_commands']==28 and not restored['cleanup_error_types']and all(restored[k]for k in ('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))
 out=P/'evidence-v1';assert not out.exists();out.mkdir()
 groups=[]
 for phase,flow in [('warm','checks'),('fresh-edit','checks'),('warm-after-check-primer','artifacts')]:
  values={v:[r for r in rows if r['phase']==phase and r['flow']==flow and r['variant']==v]for v in ('control','candidate')}
  paired=[]
  for bb,cb in ((0,1),(3,2)):
   a=[r for r in values['control']if r['block']==bb];b=[r for r in values['candidate']if r['block']==cb];assert len(a)==len(b)
   paired.extend((q['seconds']-p['seconds'])*1000 for p,q in zip(a,b))
  med={v:statistics.median(r['seconds']for r in vals)*1000 for v,vals in values.items()}
  groups.append({'phase':phase,'flow':flow,'milliseconds':{v:[r['seconds']*1000 for r in vals]for v,vals in values.items()},'median_ms':med,'aligned_block_differences_ms':paired,'median_aligned_difference_ms':statistics.median(paired),'median_change_percent':100*(med['candidate']/med['control']-1),'pairing':'Correlated aligned ABBA positions; not independently randomized pairs.'})
 columns=('variant','flow','phase','block','profile','app_main_sha256','module_sha256','config_sha256','seconds','exit_code','correct','stdout_sha256','process_tree_user_seconds','process_tree_system_seconds','engine_written_bytes')
 safe=[{k:r[k]for k in columns}for r in rows]
 save(out/'runtime-numeric.json',{'groups':groups,'commands':safe,'local_commands':28,'cloud_commands':0,'restoration':restored,'scope':summary['scope'],'ordinary_excludes':['all primers','profiled commands']})
 profiles={}
 for r in rows:
  if not r['profile']:continue
  path=P/'results-v1'/f"{r['index']:02d}-{r['label']}"/'run.wcprof.private';profiles[r['variant']]=reduce_profile(path)
 assert set(profiles)=={'control','candidate'}
 save(out/'profile-numeric.json',profiles)
 print(json.dumps({'groups':groups,'profiles':{k:{'operations':v['operations'],'expansion_ms':v['expansion']['duration_ms'],'address_calls':len(v['addresses']),'runtime_processes':len(v['runtime_process_intervals'])}for k,v in profiles.items()}},indent=2))
if __name__=='__main__':main()
