from pathlib import Path
import json, statistics
r=Path(__file__).parent
rows=json.loads((r/'full-command-paired/samples.json').read_text())
med=lambda vs:statistics.median(vs)
pairs=[]
for i in sorted(set(x['pair'] for x in rows if x['pair']>0)):
 arms={x['arm']:x for x in rows if x['pair']==i}
 if len(arms)!=2: continue
 b,a=arms['before'],arms['after']
 pairs.append(dict(pair=i,before_seconds=b['seconds'],after_seconds=a['seconds'],saving_seconds=b['seconds']-a['seconds'],both_succeeded=b['exit_code']==a['exit_code']==0,same_rows=b['same_rows'] and a['same_rows']))
good=[p for p in pairs if p['both_succeeded'] and p['same_rows']]
valid={arm:[x for x in rows if x['pair'] in [p['pair'] for p in good] and x['arm']==arm] for arm in ['before','after']}
result=dict(pairs=pairs,successful_pairs=len(good),faster_successful_pairs=sum(p['saving_seconds']>0 for p in good),
 median_seconds={arm:med(x['seconds'] for x in xs) for arm,xs in valid.items()},
 median_paired_saving_seconds=med(p['saving_seconds'] for p in good),
 median_engine_cpu={arm:med(x['engine_cpu'] for x in xs) for arm,xs in valid.items()},
 median_allocated_bytes={arm:med(x['heap_delta']['TotalAlloc'] for x in xs) for arm,xs in valid.items()},
 median_peak_sampled_heap_bytes={arm:med(x['peak_sampled_heap'] for x in xs) for arm,xs in valid.items()},
 median_last_row_seconds={arm:med(x['last_row_seconds'] for x in xs) for arm,xs in valid.items()},
 all_commands_succeeded=all(x['exit_code']==0 for x in rows),same_rows=all(x['same_rows'] for x in rows),
 measured_attempts=[dict(label=x['label'],seconds=x['seconds'],exit_code=x['exit_code'],listed_rows=x['listed_rows'],same_rows=x['same_rows'],pressure=x['pressure']) for x in rows if x['pair']>0])
(r/'paired-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='measured_attempts'},indent=2))
