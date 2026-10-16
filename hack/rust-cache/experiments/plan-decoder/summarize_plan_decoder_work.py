from pathlib import Path
import json,statistics
base=Path('/tmp/rust-cache-sipsma-review')
result={}
for cohort in ['paired','crossover']:
    path=base/('plan-decoder-'+cohort)
    samples=json.loads((path/'samples.json').read_text())
    pressure=[json.loads(line) for line in (path/'pressure.jsonl').read_text().splitlines()]
    timed=[r for r in pressure if r['label'].startswith('edited-')]
    result[cohort]={
        'within_cargo_plus_half_second':{kind:sum(r['after']<=r['cargo']+.5 for r in values) for kind,values in samples.items()},
        'median_paired_after_minus_cargo':{kind:statistics.median(r['after']-r['cargo'] for r in values) for kind,values in samples.items()},
        'max_host_io_fraction':max(r['stall_fraction']['host.io.some'] for r in timed),
        'max_engine_io_fraction':max(r['stall_fraction']['engine.io.some'] for r in timed),
        'slow_observations':[{k:r[k] for k in ['label','seconds','engine_cpu_seconds','stall_fraction']} for r in timed if r['seconds']>3],
    }
rows=json.loads((base/'plan-decode-libraries/first-use/samples.json').read_text())
result['first_use_component']={size:{decoder:dict(faster_pairs=sum(next(r['seconds'] for r in rows if r['size']==size and r['pair']==i and r['decoder']==decoder)<next(r['seconds'] for r in rows if r['size']==size and r['pair']==i and r['decoder']=='standard') for i in range(6))) for decoder in ['goccy','segmentio']} for size in ['130','1026','small']}
(base/'plan-decode-libraries/derived-statistics.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{'max_host_io':v['max_host_io_fraction'],'max_engine_io':v['max_engine_io_fraction'],'slow':[(x['label'],x['seconds']) for x in v['slow_observations']]} for k,v in result.items() if k in ['paired','crossover']},indent=2))
