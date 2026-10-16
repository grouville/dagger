from pathlib import Path
import json,os,statistics,subprocess,time

root=Path('/tmp/rust-cache-sipsma-review/protobuf-field-order')
out=root/'component-screen'
out.mkdir(exist_ok=False)
env=dict(os.environ,GOMAXPROCS='8')
orders=[['before','guard','typed'],['typed','guard','before'],['guard','before','typed'],
        ['typed','before','guard'],['before','typed','guard'],['guard','typed','before']]
def pressure():
    result={}
    for kind in ['cpu','io','memory']:
        for line in Path('/proc/pressure/'+kind).read_text().splitlines():
            result[kind+'.'+line.split()[0]]=int(line.split('total=')[1])
    return result
for variant in ['before','guard','typed']:
    with (out/('tests-'+variant+'.log')).open('w') as log:
        subprocess.run([str(root/(variant+'-clientdb.test')),'-test.count=1'],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('PASS clientdb',variant,flush=True)
rows=[]
for pair,order in enumerate(orders):
    for suite,bench in [('order','^BenchmarkRangeFields$'),('clientdb','^BenchmarkMarshalProtoJSONs/current$')]:
        for variant in order:
            name=f'{pair}-{suite}-{variant}'
            before=pressure();started=time.monotonic()
            with (out/(name+'.log')).open('w') as log:
                subprocess.run([str(root/(variant+'-'+suite+'.test')),
                                '-test.run=^$','-test.bench='+bench,
                                '-test.benchtime=100ms','-test.count=1'],
                               env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            elapsed=time.monotonic()-started;after=pressure()
            metrics=[]
            for line in (out/(name+'.log')).read_text().splitlines():
                if not line.startswith('Benchmark'):continue
                fields=line.split()
                metrics.append(dict(name=fields[0],ns=float(fields[2]),bytes=float(fields[4]),allocations=float(fields[6])))
            rows.append(dict(pair=pair,suite=suite,variant=variant,seconds=elapsed,benchmarks=metrics,
                             stall_fraction={k:(after[k]-before[k])/(elapsed*1e6) for k in before}))
            (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Finished pair',pair,flush=True)
summary={}
for suite in ['order','clientdb']:
    names=sorted({m['name'] for r in rows if r['suite']==suite for m in r['benchmarks']})
    for name in names:
        summary[name]={}
        for variant in ['before','guard','typed']:
            data=[m for r in rows if r['suite']==suite and r['variant']==variant for m in r['benchmarks'] if m['name']==name]
            summary[name][variant]={key:statistics.median(m[key] for m in data) for key in ['ns','bytes','allocations']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
