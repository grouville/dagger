from pathlib import Path
import argparse,hashlib,json,os,re,statistics,subprocess,time
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--pairs',type=int,default=3)
parser.add_argument('--results',type=int,default=200000)
args=parser.parse_args(); root=args.output; root.mkdir(exist_ok=False)
family=Path(__file__).parent
protocol=Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
# Use the existing engine/host admission helpers without creating a second output directory.
helper=protocol.read_text().split('fixtures = [f for f')[0]
helper=helper[helper.index('base = Path('):]
exec(helper)
run_env=dict(os.environ,GOMAXPROCS='8')
orders=[['before','after'] if pair%2==0 else ['after','before'] for pair in range(args.pairs)]
metadata=dict(scope='Existing disk prune snapshot benchmark, populated through normal cache publication. New process and fixture per observation; fixture construction is outside the Go benchmark timer. This is component performance, not a full listing gain.',results=args.results,pairs=args.pairs,orders=orders,profiling=False,forced_engine_gc=False,
 binary_sha256={arm:hashlib.sha256((family/(arm+'.test')).read_bytes()).hexdigest() for arm in ['before','after']},
 base='ff0b029a4d270a651b9a8c7286babc79089066e4',runtime_environment={key:run_env.get(key) for key in ['GOMAXPROCS','GOGC','GOMEMLIMIT','GODEBUG']})
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
rows=[]
for pair,order in enumerate(orders):
 for arm in order:
  label=f'{pair}-{arm}'
  idle(label)
  before_pressure=pressure();start=time.monotonic()
  command=[str(family/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkCachePruneSnapshot/disk/'+str(args.results)+'$','-test.benchtime=1x','-test.count=1']
  with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,env=run_env,stdout=out,stderr=subprocess.STDOUT,cwd='/tmp/dagger-cache-usage-provider-rows')
  elapsed=time.monotonic()-start;after_pressure=pressure()
  text=(root/(label+'.log')).read_text()
  lines=[line for line in text.splitlines() if line.startswith('BenchmarkCachePruneSnapshot/disk/')]
  assert r.returncode==0 and len(lines)==1,(label,r.returncode,text[-2000:])
  words=lines[0].split();metrics={metric:float(words[index-1]) for index,metric in enumerate(words) if metric in ['ns/op','B/op','allocs/op','snapshot-results']}
  assert metrics['snapshot-results']==args.results,(label,metrics)
  row=dict(label=label,pair=pair,arm=arm,exit_code=r.returncode,process_seconds=elapsed,metrics=metrics,pressure={key:(after_pressure[key]-before_pressure[key])/(elapsed*1e6) for key in before_pressure})
  rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
  print(label,json.dumps(metrics),flush=True)
summary=dict(pairs=args.pairs,results=args.results,all_succeeded=True,median={arm:{metric:statistics.median(r['metrics'][metric] for r in rows if r['arm']==arm) for metric in ['ns/op','B/op','allocs/op']} for arm in ['before','after']})
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
