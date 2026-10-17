from pathlib import Path
import json,os,re,statistics,subprocess,time
import sys
sys.path.insert(0,'/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
from bench_engine import BenchEngine
family=Path(__file__).parent;root=family/'component-paired';root.mkdir(exist_ok=False)
engine=BenchEngine(root);rows=[]
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
for pair,order in enumerate([['before','after'],['after','before'],['before','after'],['after','before']]):
 for arm in order:
  label=f'{pair}-{arm}';engine.idle(label);before=engine.pressure();started=time.monotonic()
  command=[str(family/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkBuiltinReceiverExpression$','-test.benchtime=50000x','-test.count=1']
  with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,env=dict(os.environ,GOMAXPROCS='8'),stdout=out,stderr=subprocess.STDOUT)
  elapsed=time.monotonic()-started;after=engine.pressure()
  text=(root/(label+'.log')).read_text();assert r.returncode==0,(label,text[-2000:])
  metrics={}
  for line in text.splitlines():
   if not line.startswith('BenchmarkBuiltinReceiverExpression/'):continue
   words=line.split();name=words[0].split('/',1)[1].rsplit('-',1)[0]
   metrics[name]={key:float(words[i-1]) for i,key in enumerate(words) if key in ['ns/op','B/op','allocs/op']}
  assert set(metrics)=={'string','list-block'},(label,text[-1000:])
  row=dict(pair=pair,arm=arm,command=command,exit_code=r.returncode,process_seconds=elapsed,metrics=metrics,pressure={k:(after[k]-before[k])/(elapsed*1e6) for k in before})
  rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,json.dumps(metrics),flush=True)
summary={scenario:dict(median={arm:{key:statistics.median(row['metrics'][scenario][key] for row in rows if row['arm']==arm) for key in ['ns/op','B/op','allocs/op']} for arm in ['before','after']},faster_pairs=sum(next(row for row in rows if row['pair']==pair and row['arm']=='after')['metrics'][scenario]['ns/op']<next(row for row in rows if row['pair']==pair and row['arm']=='before')['metrics'][scenario]['ns/op'] for pair in range(4))) for scenario in ['string','list-block']}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
