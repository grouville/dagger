from pathlib import Path
import collections,json,subprocess
root=Path(__file__).parent/'capture'
with (root/'wcprof-complete.ndjson').open() as stream:
 header=json.loads(next(stream)); strings=header['strings']; ops={}
 for line in stream:
  event=json.loads(line)
  if event['e']=='op':ops[event['id']]=event
result=json.loads((root/'result.json').read_text())
windows=json.loads((root/'engine-cpu-windows.json').read_text())
def seconds(op):return (op['d']-op['s'])/1e9
def cls(op):return strings[op.get('c',0)]
def offset(t):return (header['epoch_unix_nano']+t)/1e9-result['unix_start']
pubs=sorted((op for op in ops.values() if cls(op)=='dagql.publishResult'),key=seconds,reverse=True)
rows=[]
for op in pubs[:30]:
 parent=ops.get(op.get('p')); start=offset(op['s']); end=offset(op['d'])
 rows.append(dict(id=op['id'],parent_class=cls(parent) if parent else None,seconds=seconds(op),start_seconds=start,end_seconds=end,
  cpu_windows=[i for i,w in enumerate(windows) if w['start_seconds']<end and w['end_seconds']>start]))
(root/'long-publications.json').write_text(json.dumps(rows,indent=2)+'\n')
queries=sorted((op for op in ops.values() if cls(op)=='session.serveQuery'),key=seconds,reverse=True)
with (root/'main-critical.txt').open('w') as out:
 subprocess.run(['/tmp/rust-cache-wcprof-report','-view','critpath','-op',str(queries[0]['id']),str(root/'wcprof-complete.ndjson')],stdout=out,stderr=subprocess.STDOUT,check=True)
print('largest publications',json.dumps(rows[:8],indent=2))
