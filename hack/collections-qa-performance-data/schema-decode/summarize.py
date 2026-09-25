from pathlib import Path
import json,statistics
b=Path('/tmp/collections-perf/schema-decode');result={};allrows=[]
for series in ['warm','warm-repeat']:
 rows=[r for r in json.loads((b/series/'results.json').read_text()) if r['label'].startswith('warm/')];allrows+=rows
 stats={v:{'median':statistics.median(r['seconds'] for r in rows if r['variant']==v),'min':min(r['seconds'] for r in rows if r['variant']==v),'max':max(r['seconds'] for r in rows if r['variant']==v)} for v in ['control','candidate']}
 start=min((b/series/r['label']/'results.json').stat().st_mtime_ns-int(r['seconds']*1e9) for r in rows);end=max((b/series/r['label']/'results.json').stat().st_mtime_ns for r in rows)
 xs=[json.loads(l) for l in (b/(series+'-host.jsonl')).read_text().splitlines()];xs=[s for s in xs if start<=s['time_ns']<=end];a,z=xs[0],xs[-1];us=(z['monotonic_ns']-a['monotonic_ns'])/1000
 host={'sample_count':len(xs),'sampled_seconds':us/1e6,'window':'Measured series only, excluding warmups. Approximate bounds use result-file mtime minus CLI elapsed duration; sampling resolution 250 ms.'}
 for name in ['cpu','io','memory']:
  for kind in ['some','full']:
   def total(s):return int(next(l for l in s['pressure/'+name].splitlines() if l.startswith(kind+' ')).split('total=')[1])
   host[name+'_'+kind+'_fraction']=(total(z)-total(a))/us
 (b/series/'host-summary.json').write_text(json.dumps(host,indent=2)+'\n')
 result[series]={'stats':stats,'host':host}
result['combined_medians']={v:statistics.median(r['seconds'] for r in allrows if r['variant']==v) for v in ['control','candidate']}
(b/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
