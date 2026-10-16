from pathlib import Path
import json,random,statistics

root=Path(__file__).parent
out={}
for kind in ['large','direct','tests','list']:
    pairs=[]
    for cohort,count in [('commands',8),('confirmation',8),('list-confirmation',16)]:
        if cohort=='list-confirmation' and kind!='list':continue
        rows=json.loads((root/cohort/'samples.json').read_text())
        for pair in range(count):
            by={r['arm']:r for r in rows if r['kind']==kind and r['pair']==pair}
            before,after=by['before'],by['after']
            pairs.append(dict(cohort=cohort,pair=pair,seconds_saved=before['command_seconds']-after['command_seconds'],engine_cpu_saved=before['cpu_seconds']['engine']-after['cpu_seconds']['engine'],bytes_saved=before['heap_delta']['TotalAlloc']-after['heap_delta']['TotalAlloc'],before_GC=before['heap_delta']['NumGC'],after_GC=after['heap_delta']['NumGC']))
    out[kind]=dict(pairs=pairs,median_seconds_saved=statistics.median(r['seconds_saved'] for r in pairs),faster_pairs=sum(r['seconds_saved']>0 for r in pairs),median_engine_cpu_saved=statistics.median(r['engine_cpu_saved'] for r in pairs),lower_CPU_pairs=sum(r['engine_cpu_saved']>0 for r in pairs),median_bytes_saved=statistics.median(r['bytes_saved'] for r in pairs))
values=[r['seconds_saved'] for r in out['list']['pairs']]
rng=random.Random(2026101615)
boot=sorted(statistics.median(rng.choices(values,k=len(values))) for _ in range(20000))
out['list']['bootstrap_paired_median_95_percent_seconds']=[boot[500],boot[19500]]
out['list']['bootstrap_seed']=2026101615
(root/'pooled-summary.json').write_text(json.dumps(out,indent=2)+'\n')
for kind,value in out.items():print(kind,{k:v for k,v in value.items() if k!='pairs'})
