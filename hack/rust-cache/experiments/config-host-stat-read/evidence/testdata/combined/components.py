from pathlib import Path
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, '/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
from bench_engine import BenchEngine

family=Path(__file__).parent
root=family/'components';root.mkdir(exist_ok=False)
engine=BenchEngine(root);rows=[]
for pair,order in enumerate([['separate','combined'],['combined','separate']]*2):
    for mode in order:
        for scenario in ['regular','missing','directory']:
            label=f'{pair}-{mode}-{scenario}'
            engine.idle(label);before=engine.pressure();started=time.monotonic()
            command=[str(family/'components.test'),'-test.run=^$',
                     '-test.bench=^BenchmarkCallerHostStatRead$/^'+scenario+'$/^'+mode+'$',
                     '-test.benchtime=1000x','-test.count=1']
            with (root/(label+'.log')).open('w') as out:
                result=subprocess.run(command,env=dict(os.environ,GOMAXPROCS='8'),stdout=out,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-started;after=engine.pressure()
            text=(root/(label+'.log')).read_text()
            words=next(line.split() for line in text.splitlines() if line.startswith('BenchmarkCallerHostStatRead/'))
            metrics={key:float(words[i-1]) for i,key in enumerate(words) if key in ['ns/op','B/op','allocs/op','requests/op']}
            row=dict(pair=pair,mode=mode,scenario=scenario,command=command,exit_code=result.returncode,metrics=metrics,
                     seconds=elapsed,pressure={key:(after[key]-before[key])/(elapsed*1e6) for key in before})
            rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(label,json.dumps(metrics),flush=True)
            assert result.returncode==0 and metrics['requests/op']==(2 if mode=='separate' and scenario=='regular' else 1),label
summary={scenario:{mode:{key:statistics.median(row['metrics'][key] for row in rows if row['scenario']==scenario and row['mode']==mode)
                       for key in ['ns/op','B/op','allocs/op','requests/op']}
                   for mode in ['separate','combined']}
         for scenario in ['regular','missing','directory']}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
