from pathlib import Path
import json,os,subprocess,time

root=Path(__file__).parent;out=root/'standalone';out.mkdir(exist_ok=False)
source=Path('/tmp/protobuf-field-order-experiment')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base=json.loads((root/'overlay.json').read_text());records=[]
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
for arm,name in [('before','before.go'),('after','candidate.go')]:
    overlay=json.loads(json.dumps(base));overlay['Replace'][str(source/'internal/order/range.go')]=str(root/name)
    (out/(arm+'.json')).write_text(json.dumps(overlay,indent=2)+'\n')
    with (out/('build-'+arm+'.log')).open('w') as stream:subprocess.run([go,'test','-overlay',str(out/(arm+'.json')),'-c','-o',str(out/(arm+'.test')),'./internal/order'],cwd=source,stdout=stream,stderr=subprocess.STDOUT,check=True)
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'{pair}-{arm}';before=pressure();started=time.monotonic()
        with (out/(label+'.log')).open('w') as stream:subprocess.run([str(out/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkRangeFields$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT,check=True)
        elapsed=time.monotonic()-started;after=pressure();metrics=[]
        for line in (out/(label+'.log')).read_text().splitlines():
            if line.startswith('Benchmark'):
                f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
        records.append(dict(pair=pair,arm=arm,seconds=elapsed,metrics=metrics,stall_fraction={k:(after[k]-before[k])/elapsed/1e6 for k in before}))
        (out/'runs.json').write_text(json.dumps(records,indent=2)+'\n');print(label,'done',flush=True)
