from pathlib import Path
import json,statistics
b=Path('/tmp/collections-perf/half-second');result={}
for name,d in [('transforms',b),('node-compile',b/'node-compile'),('combined',b/'combined')]:
 rows=[r for r in json.loads((d/'warm-summary.json').read_text()) if r['iteration']>=0]
 stats={v:{'median':statistics.median(r['seconds'] for r in rows if r['variant']==v),'min':min(r['seconds'] for r in rows if r['variant']==v),'max':max(r['seconds'] for r in rows if r['variant']==v)} for v in ['control','candidate']}
 xs=[json.loads(l) for l in (d/'host.jsonl').read_text().splitlines()];xs=[s for s in xs if min(r['start_unix_ns'] for r in rows)<=s['time_ns']<=max(r['end_unix_ns'] for r in rows)];a,z=xs[0],xs[-1];us=(z['monotonic_ns']-a['monotonic_ns'])/1000
 host={'sample_count':len(xs),'sampled_seconds':us/1e6,'window':'Measured series only; driver start/end timestamps, 250 ms host sampling.'}
 for n in ['cpu','io','memory']:
  for k in ['some','full']:
   def total(s):return int(next(l for l in s['pressure/'+n].splitlines() if l.startswith(k+' ')).split('total=')[1])
   host[n+'_'+k+'_fraction']=(total(z)-total(a))/us
 result[name]={'stats':stats,'host':host}
profiles={}
for name,d in [('before',b/'control-wcprof'),('transforms',b/'candidate-wcprof'),('transforms-repeat',b/'node-compile/control-wcprof'),('combined',b/'node-compile/candidate-wcprof')]:
 with (d/'runs.wcprof').open() as f:h=json.loads(next(f));ops=[e for l in f if (e:=json.loads(l))['e']=='op']
 strings=h['strings'];t0=min(e['s'] for e in ops)
 profiles[name]={'command_seconds':json.loads((d/'results.json').read_text())['median_seconds'],'dropped_events':h['dropped_events'],'open_ops':len(h.get('open_ops',[])),'trace_seconds':(max(e['d'] for e in ops)-t0)/1e9,'boundary_ops':[{'class':strings[e.get('c',0)],'kind':e.get('k'),'start_ms':(e['s']-t0)/1e6,'end_ms':(e['d']-t0)/1e6,'metadata':strings[e.get('m',0)]} for e in sorted(ops,key=lambda e:e['s']) if e.get('k')=='call_exec' and strings[e.get('c',0)] in ['Workspace.artifacts','Artifacts.__itemsJSON'] or strings[e.get('c',0)]=='exec.processRun' and 'tsx' in strings[e.get('m',0)]]}
result['profiles']=profiles
(b/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
