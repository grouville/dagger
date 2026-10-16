from pathlib import Path
import json,os,statistics,subprocess,time
root=Path('/tmp/rust-cache-sipsma-review/telemetry-spill-batch-buffers')
out=root/'paired'
out.mkdir(exist_ok=False)
env=dict(os.environ,GOMAXPROCS='8')
def pressure():
    return {kind+'.'+line.split()[0]:int(line.split('total=')[1])
            for kind in ['cpu','io','memory']
            for line in Path('/proc/pressure/'+kind).read_text().splitlines()}
rows=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        before=pressure();started=time.monotonic()
        with (out/(str(pair)+'-'+arm+'.log')).open('w') as log:
            subprocess.run([str(root/(arm+'.test')),'-test.run=^$',
                            '-test.bench=^BenchmarkSpillFileReadSince$',
                            '-test.benchtime=150ms','-test.count=1'],
                           env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        elapsed=time.monotonic()-started;after=pressure()
        metrics=[]
        for line in (out/(str(pair)+'-'+arm+'.log')).read_text().splitlines():
            if not line.startswith('Benchmark'):continue
            fields=line.split()
            metrics.append(dict(name=fields[0],ns=float(fields[2]),bytes=int(fields[4]),allocations=int(fields[6])))
        rows.append(dict(pair=pair,arm=arm,benchmarks=metrics,seconds=elapsed,
                         stall_fraction={k:(after[k]-before[k])/(elapsed*1e6) for k in before}))
        (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Finished pair',pair,flush=True)
summary={}
for name in sorted({m['name'] for r in rows for m in r['benchmarks']}):
    summary[name]={}
    for arm in ['before','after']:
        data=[m for r in rows if r['arm']==arm for m in r['benchmarks'] if m['name']==name]
        summary[name][arm]={k:statistics.median(m[k] for m in data) for k in ['ns','bytes','allocations']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
