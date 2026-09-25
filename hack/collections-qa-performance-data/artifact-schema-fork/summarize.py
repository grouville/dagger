from pathlib import Path
import json,statistics,hashlib
b=Path('/tmp/collections-perf/discovery-next')
rows=json.loads((b/'warm-summary.json').read_text())
r={'warm':{}}
for k in ['control','candidate']:
 s=[v['seconds'] for v in rows if v['iteration']>=0 and v['variant']==k]
 r['warm'][k]={'n':len(s),'median_seconds':statistics.median(s),'min_seconds':min(s),'max_seconds':max(s),'raw_seconds':s}
r['warm']['improvement_fraction']=1-r['warm']['candidate']['median_seconds']/r['warm']['control']['median_seconds']
r['warm']['candidate_faster_pairs']=sum(next(v['seconds'] for v in rows if v['variant']=='candidate' and v['iteration']==i)<next(v['seconds'] for v in rows if v['variant']=='control' and v['iteration']==i) for i in range(8))
start=min(v['start_unix_ns'] for v in rows if v['iteration']>=0);end=max(v['end_unix_ns'] for v in rows if v['iteration']>=0)
x=[json.loads(l) for l in (b/'host.jsonl').read_text().splitlines() if start<json.loads(l)['time_ns']<end]
def metric(d,k,n):return int(next(l for l in d['pressure/'+k].splitlines() if l.startswith(n+' ')).split('total=')[1])
us=(x[-1]['monotonic_ns']-x[0]['monotonic_ns'])/1000
r['warm']['measured_host_pressure_fraction']={k:(metric(x[-1],k,n)-metric(x[0],k,n))/us for k,n in [('cpu','some'),('io','full'),('memory','full')]}
r['edits']=json.loads((b/'invalidation/edit-summary.json').read_text())
r['profiles']={}
for label in ['control','candidate']:
 d=b/(label+'-wcprof')
 with (d/'runs.wcprof').open() as f:h=json.loads(next(f));ops=[e for l in f if (e:=json.loads(l))['e']=='op']
 strings=h['strings'];t0=min(e['s'] for e in ops)
 r['profiles'][label]={'command_seconds':json.loads((d/'results.json').read_text())['median_seconds'],'dropped_events':h['dropped_events'],'open_ops':len(h.get('open_ops',[])),'trace_seconds':(max(e['d'] for e in ops)-t0)/1e9,'boundary_ops':[]}
 for e in sorted(ops,key=lambda e:e['s']):
  c=strings[e.get('c',0)]
  if e['k']=='call_exec' and c in ['Workspace.artifacts','Artifacts.__itemsJSON'] or c=='exec.processRun' and 'tsx' in strings[e.get('m',0)]:
   r['profiles'][label]['boundary_ops'].append({'class':c,'start_ms':(e['s']-t0)/1e6,'duration_ms':(e['d']-e['s'])/1e6})
if (b/'cold/summary.json').exists():
 r['cold']=[{'variant':v['variant'],'iteration':v['iteration'],'seconds':v['results']['median_seconds'],'status':v['status']} for v in json.loads((b/'cold/summary.json').read_text())]
if 'cold' in r:
 h=[json.loads(l) for l in (b/'cold/host.jsonl').read_text().splitlines()]
 for row, raw in zip(r['cold'], json.loads((b/'cold/summary.json').read_text())):
  samples=[v for v in h if raw['start_unix_ns']<v['time_ns']<raw['end_unix_ns']]
  us=(samples[-1]['time_ns']-samples[0]['time_ns'])/1000
  row['host_pressure_fraction']={k:(metric(samples[-1],k,n)-metric(samples[0],k,n))/us for k,n in [('cpu','some'),('io','full'),('memory','full')]}
r['core_query_diagnostic']=json.loads((b/'cli-floor/summary.json').read_text())
(b/'summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
