from pathlib import Path
import argparse,hashlib,json,os,statistics,subprocess,time
from bench_engine import BenchEngine
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pairs',type=int,default=3)
args=parser.parse_args();root=args.output;root.mkdir(exist_ok=False)
family=Path(__file__).parent;engine=BenchEngine(root)
scenarios={'metadata':('before.test','^BenchmarkCachePruneSnapshot/disk/200000$','BenchmarkCachePruneSnapshot/disk/'), 'providers':('provider-dense-before.test','^BenchmarkCachePruneProviderDense$','BenchmarkCachePruneProviderDense')}
metadata=dict(scope='Read-once refinement versus unmodified upstream, covering metadata-only and provider-only caches through normal cache publication. Fresh process/fixture each time, existing timer excludes fixture preparation. GOMAXPROCS=8, no profiling or engine GC changes.',pairs=args.pairs,
 binaries={name:hashlib.sha256((family/name).read_bytes()).hexdigest() for name in ['before.test','provider-dense-before.test','read-once-after.test']})
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'driver.py').write_bytes(Path(__file__).read_bytes());(root/'bench_engine.py').write_bytes((family/'bench_engine.py').read_bytes())
rows=[]
for scenario,(before,pattern,prefix) in scenarios.items():
 for pair in range(args.pairs):
  for arm in (['before','after'] if pair%2==0 else ['after','before']):
   label=f'{scenario}-{pair}-{arm}';engine.idle(label)
   binary=family/(before if arm=='before' else 'read-once-after.test')
   command=[str(binary),'-test.run=^$','-test.bench='+pattern,'-test.benchtime=1x','-test.count=1']
   pressure_before=engine.pressure();start=time.monotonic()
   with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd='/tmp/dagger-cache-usage-sampler-only',env=dict(os.environ,GOMAXPROCS='8'),stdout=out,stderr=subprocess.STDOUT)
   elapsed=time.monotonic()-start;pressure_after=engine.pressure()
   text=(root/(label+'.log')).read_text();lines=[line for line in text.splitlines() if line.startswith(prefix)]
   assert r.returncode==0 and len(lines)==1,(label,r.returncode,text[-1500:])
   words=lines[0].split();metrics={key:float(words[i-1]) for i,key in enumerate(words) if key in ['ns/op','B/op','allocs/op','snapshot-results']}
   assert metrics['snapshot-results']==200000,(label,metrics)
   row=dict(label=label,scenario=scenario,pair=pair,arm=arm,exit_code=r.returncode,process_seconds=elapsed,metrics=metrics,pressure={k:(pressure_after[k]-pressure_before[k])/(elapsed*1e6) for k in pressure_before})
   rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,json.dumps(metrics),flush=True)
summary={}
for scenario in scenarios:
 data={arm:[r for r in rows if r['scenario']==scenario and r['arm']==arm] for arm in ['before','after']}
 summary[scenario]=dict(pairs=args.pairs,median={arm:{metric:statistics.median(r['metrics'][metric] for r in values) for metric in ['ns/op','B/op','allocs/op']} for arm,values in data.items()},faster_pairs=sum(data['after'][i]['metrics']['ns/op']<data['before'][i]['metrics']['ns/op'] for i in range(args.pairs)))
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
