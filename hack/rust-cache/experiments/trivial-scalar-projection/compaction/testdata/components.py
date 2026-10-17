from pathlib import Path
import argparse
import json
import os
import re
import statistics
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).parent
out = args.output
out.mkdir(exist_ok=False)
orders = [['baseline','digests','owned'], ['owned','digests','baseline'],
          ['digests','baseline','owned'], ['owned','baseline','digests']]
env = dict(os.environ, GOMAXPROCS='8')
metadata = dict(orders=orders, fresh_process_every_arm=True, ordinary_gc=True,
    fixture='Synthetic term-heavy index: small=1,000 live/1,000 dead classes; large=200,000/40,000; sparse=2,000/1,000,000. Each live class has two digests and two two-input terms; every eighth class has an extra digest. Construction and validation are outside the timer. No containers or full-command claims.',
    runtime_environment={key:env.get(key) for key in ['GOMAXPROCS','GOGC','GOMEMLIMIT','GODEBUG']})
(out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
def pressure():
    return {kind: int(Path('/proc/pressure',kind).read_text().splitlines()[0].split('total=')[1]) for kind in ['cpu','io','memory']}
def idle(label):
    tick=time.monotonic()
    while True:
        a=pressure();mark=time.monotonic();time.sleep(1);b=pressure();elapsed=time.monotonic()-mark
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle',timeout=20) as response:state=json.load(response)
        rates={key:(b[key]-a[key])/(elapsed*1e6) for key in a}
        quiet=not state.get('sessions') and state['active_requests']==0 and rates['cpu']<.10 and rates['io']<.05
        with (out/'admission.jsonl').open('a') as stream:stream.write(json.dumps(dict(label=label,pressure=rates,accepted=quiet))+'\n')
        if quiet:return
        assert time.monotonic()-tick<180,'admission timeout'
rows=[]
for shape in ['small','large','sparse']:
    for pair,order in enumerate(orders):
        for arm in order:
            label=f'{shape}-{pair}-{arm}'
            idle(label)
            command=[str(root/(arm+'.test')),'-test.run=^$',f'-test.bench=^BenchmarkCompactionOwnership/{shape}$','-test.benchtime=1x','-test.count=1','-test.benchmem']
            a=pressure();mark=time.monotonic()
            with (out/(label+'.log')).open('w') as stream:result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
            seconds=time.monotonic()-mark;b=pressure()
            log=(out/(label+'.log')).read_text()
            metrics={name:float(value) for value,name in re.findall(r'([\d.]+)\s+(ns/op|B/op|allocs/op|write-lock-hold-ns)',log)}
            row=dict(label=label,shape=shape,pair=pair,arm=arm,command=command,exit_code=result.returncode,process_seconds=seconds,metrics=metrics,
                pressure={key:(b[key]-a[key])/(seconds*1e6) for key in a})
            rows.append(row)
            (out/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(label,result.returncode,metrics,flush=True)
            assert result.returncode==0 and len(metrics)==4,(label,log)
summary={shape:{arm:{metric:statistics.median(r['metrics'][metric] for r in rows if r['shape']==shape and r['arm']==arm)
    for metric in ['ns/op','B/op','allocs/op','write-lock-hold-ns']} for arm in ['baseline','digests','owned']} for shape in ['small','large','sparse']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
