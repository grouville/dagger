from pathlib import Path
import hashlib,json
ROOT=Path('/tmp/collections-perf/go-base-address-timing-v1/results-v1');OUT=Path(__file__).resolve().parent
result={}
for variant,index in [('control',25),('candidate',27)]:
 path=next(ROOT.glob(f'{index:02d}-*-diagnostic-checks/run.wcprof.private'))
 with path.open()as stream:
  head=json.loads(next(stream));ops=[v for s in stream if s.strip()for v in [json.loads(s)]if v.get('e')=='op']
 name=lambda o:head['strings'][o.get('c',0)]
 cat=next(o for o in ops if name(o)=='Workspace.artifacts'and o['k']=='call_exec')
 exp=next(o for o in ops if name(o)=='Artifacts.__itemsJSON'and o['k']=='call_exec')
 rootloads=sorted([o for o in ops if name(o)=='ModuleSource.asModule'and o['k']=='call'and o.get('p')==cat['id']],key=lambda o:o['s'])
 assert len(rootloads)==9
 result[variant]={'profile_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'catalog_ms':(cat['d']-cat['s'])/1e6,'catalog_end_to_expansion_start_ms':(exp['s']-cat['d'])/1e6,'expansion_ms':(exp['d']-exp['s'])/1e6,'root_module_loads':[{'temporal_ordinal':i,'start_relative_to_catalog_ms':(o['s']-cat['s'])/1e6,'end_relative_to_catalog_ms':(o['d']-cat['s'])/1e6,'successful':o.get('o')in('ok','executed','hit','cache_hit','joined')}for i,o in enumerate(rootloads)],'last_root_resolution_to_catalog_end_ms':(cat['d']-max(o['d']for o in rootloads))/1e6,'unidentified_earliest_root_to_catalog_end_ms':(cat['d']-min(o['d']for o in rootloads))/1e6,'named_ready_markers_present':any(name(o).startswith('workspace.moduleLoad.')for o in ops),'identity_limit':'Ordinals reflect actual start order, not configured module names. The current dump lacks per-job canonical names; do not infer Go identity from duration, decode/process count or completion order.'}
(OUT/'numeric.json').write_text(json.dumps(result,indent=2)+'\n')
