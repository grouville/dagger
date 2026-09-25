from pathlib import Path
import json
b=Path('/tmp/collections-perf/cli-boundaries');summaries=[]
for p in sorted(list(b.glob('run-*.jsonl'))+list(b.glob('diag-*.jsonl'))):
 rows=[json.loads(l) for l in p.read_text().splitlines()];rs={}
 for r in rows:
  if 'request' in r:rs.setdefault(r['request'],{})[r['event']]=r
 reqs=[]
 for i,r in rs.items():
  if 'http.end' not in r:continue
  reqs.append({'id':i,'signal':r['http.begin']['signal'],'bytes':r['http.begin']['bytes'],'start_ms':r['http.begin']['ms'],'end_ms':r['http.end']['ms'],'connection_ms':r['http.gotConn']['ms']-r['http.begin']['ms'],'write_ms':r['http.wrote']['ms']-r['http.gotConn']['ms'],'response_after_write_ms':r['http.firstByte']['ms']-r['http.wrote']['ms']})
 summaries.append({'name':p.stem,'phases_ms':{r['name']:r['duration_ms'] for r in rows if r['event']=='phase.end' and r['name']!='export.traces'},'requests':reqs,'batches':[r for r in rows if r['event']=='export.batch']})
(b/'timelines-summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
