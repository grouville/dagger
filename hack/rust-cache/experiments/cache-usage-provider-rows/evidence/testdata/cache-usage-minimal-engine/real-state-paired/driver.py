from pathlib import Path
import argparse,json,statistics,subprocess,time,urllib.request
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pairs',type=int,default=5)
args=parser.parse_args();root=args.output;root.mkdir(exist_ok=False)
from bench_engine import BenchEngine
engine=BenchEngine(root)
get=engine.get; mode=engine.mode; pressure=engine.pressure; cpu=engine.cpu; idle=engine.idle; debug=engine.debug
original_mode=get('usage-sampling')['enabled']
metadata=dict(scope='Component diagnostic on the retained real engine cache. The existing non-evicting usage-measurement endpoint requests a full disk-prune snapshot in both arms. Only the minimal sparse sampler differs; its legacy lazy-map option stays false. Ordinary GC is enabled. This is not an unchanged-command or full-listing benchmark.',pairs=args.pairs-1,excluded_initial_pairs=1,ordinary_gc=True,telemetry=True,forced_gc=False,legacy_lazy_usage_maps=False)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'driver.py').write_bytes(Path(__file__).read_bytes())
rows=[]
try:
 assert not get('wcprof/enabled')['global_enabled'] and not get('snapshot-collection')['deferred']
 for pair in range(args.pairs):
  for arm in (['before','after'] if pair%2==0 else ['after','before']):
   label=f'{pair}-{arm}';idle(label);mode('usage-sampling',arm=='after')
   before_mode=get('usage-sampling');before_pressure=pressure();before_cpu=cpu();before_gc=get('snapshot-collection')
   started=time.monotonic();print('start',label,flush=True)
   request=urllib.request.Request(debug+'cache-usage-measurement?enabled=false',data=b'')
   with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response)
   elapsed=time.monotonic()-started;after_cpu=cpu();after_pressure=pressure()
   row=dict(label=label,pair=pair,arm=arm,initial_pair=pair==0,request_seconds=elapsed,result=result,engine_cpu=after_cpu-before_cpu,
    mode_before=before_mode,mode_after=get('usage-sampling'),gc_before=before_gc,gc_after=get('snapshot-collection'),pressure={key:(after_pressure[key]-before_pressure[key])/(elapsed*1e6) for key in before_pressure})
   rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
   print(label,json.dumps(result),flush=True)
   assert result['complete'] and result['rows']>0 and result['enabled']==False,(label,result)
 measured={arm:[r for r in rows if r['arm']==arm and r['pair']>0] for arm in ['before','after']}
 matches=[]
 for pair in range(1,args.pairs):
  by_arm={r['arm']:r for r in rows if r['pair']==pair}
  matches.append(by_arm['before']['result']['rows']==by_arm['after']['result']['rows'] and by_arm['before']['result']['used_bytes']==by_arm['after']['result']['used_bytes'])
 summary=dict(pairs=args.pairs-1,all_complete=True,same_rows_and_usage_by_pair=matches,
  median={arm:{key:statistics.median(r['result'][key] for r in values) for key in ['seconds','allocated_bytes','allocations','rows','used_bytes']} for arm,values in measured.items()},
  faster_pairs=sum(measured['after'][i]['result']['seconds']<measured['before'][i]['result']['seconds'] for i in range(args.pairs-1)))
 (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
 assert all(matches), 'paired rows or usage changed; not a matched preparation comparison'
finally:mode('usage-sampling',original_mode)
