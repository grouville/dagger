from pathlib import Path
import argparse
import json
import os
import re
import statistics
import subprocess
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).parent
out=args.output
out.mkdir(exist_ok=False)
env=dict(os.environ,GOMAXPROCS='8')
(out/'metadata.json').write_text(json.dumps(dict(ordinary_gc=True,fresh_process_every_arm=True,fixture='Builtin scalar fields on native DagQL objects. Both fresh-parent and already-read parent projections; parent/list-element construction remains in the measured query. No container, test execution or full-command claim.',runtime_environment={k:env.get(k) for k in ['GOMAXPROCS','GOGC','GOMEMLIMIT','GODEBUG']}),indent=2)+'\n')
def pressure():
    return {k:int(Path('/proc/pressure',k).read_text().splitlines()[0].split('total=')[1]) for k in ['cpu','io','memory']}
def idle(label):
    started=time.monotonic()
    while True:
        a=pressure();begin=time.monotonic();time.sleep(1);b=pressure();seconds=time.monotonic()-begin
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle',timeout=20) as response:state=json.load(response)
        rates={k:(b[k]-a[k])/(seconds*1e6) for k in a}
        quiet=not state.get('sessions') and state['active_requests']==0 and rates['cpu']<.1 and rates['io']<.05
        with (out/'admission.jsonl').open('a') as f:f.write(json.dumps(dict(label=label,pressure=rates,accepted=quiet))+'\n')
        if quiet:return
        assert time.monotonic()-started<180,'admission timeout'
rows=[]
for count in [1,1026]:
    for fresh in [False,True]:
        for pair in range(4):
            for arm in (['baseline','candidate'] if pair%2==0 else ['candidate','baseline']):
                label=f'{count}-fresh-{str(fresh).lower()}-{pair}-{arm}'
                idle(label)
                command=[str(root/(arm+'.test')),'-test.run=^$',f'-test.bench=^BenchmarkTrivialScalarProjection/{count}/fresh={str(fresh).lower()}$','-test.benchtime=200ms','-test.count=1','-test.benchmem']
                a=pressure();begin=time.monotonic()
                with (out/(label+'.log')).open('w') as stream:result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
                seconds=time.monotonic()-begin;b=pressure()
                log=(out/(label+'.log')).read_text()
                metrics={name:float(value) for value,name in re.findall(r'([\d.]+)\s+(ns/op|B/op|allocs/op)',log)}
                row=dict(label=label,count=count,fresh_parent=fresh,pair=pair,arm=arm,command=command,exit_code=result.returncode,metrics=metrics,process_seconds=seconds,pressure={k:(b[k]-a[k])/(seconds*1e6) for k in a})
                rows.append(row);(out/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,result.returncode,metrics,flush=True)
                assert result.returncode==0 and len(metrics)==3,(label,log[-6000:])
summary={f'{count}/fresh={fresh}':{arm:{m:statistics.median(r['metrics'][m] for r in rows if r['count']==count and r['fresh_parent']==fresh and r['arm']==arm) for m in ['ns/op','B/op','allocs/op']} for arm in ['baseline','candidate']} for count in [1,1026] for fresh in [False,True]}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
