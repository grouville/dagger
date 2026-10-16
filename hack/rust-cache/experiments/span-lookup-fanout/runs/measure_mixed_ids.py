from pathlib import Path
import json,os,re,statistics,subprocess,time

root=Path(__file__).parent;output=root/'mixed-ids';output.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
phases=[]
def run(label,command):
    tick=time.monotonic()
    with (output/(label+'.log')).open('w') as stream:r=subprocess.run(command,cwd=source,env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-tick));(output/'phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,r.returncode,round(phases[-1]['seconds'],2),flush=True);assert r.returncode==0,label
for arm in ['before','after']:
    run(arm+'-build',[go,'test','-p','1','-modfile',str(root/'engine.go.mod'),'-overlay',str(root/(arm+'-mixed-overlay.json')),'-c','-o',str(root/(arm+'-mixed.test')),'./engine/clientdb'])
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
def quiet(label):
    tick=time.monotonic()
    while True:
        before=pressure();start=time.monotonic();time.sleep(1);after=pressure();elapsed=time.monotonic()-start
        stalls={k:(after[k]-before[k])/elapsed/1e6 for k in before}
        admitted=stalls['cpu.some']<.1 and stalls['io.some']<.05
        with (output/'admission.jsonl').open('a') as f:f.write(json.dumps(dict(label=label,admitted=admitted,stalls=stalls))+'\n')
        if admitted:return
        assert time.monotonic()-tick<90,'admission timeout'
samples=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'bench-{pair}-{arm}';quiet(label);before=pressure();tick=time.monotonic()
        run(label,[str(root/(arm+'-mixed.test')),'-test.run=^$','-test.bench=^BenchmarkSpanLookupFanoutMixedIDs$','-test.benchmem','-test.benchtime=150ms','-test.count=1'])
        elapsed=time.monotonic()-tick;after=pressure();values=[]
        for line in (output/(label+'.log')).read_text().splitlines():
            m=re.match(r'BenchmarkSpanLookupFanoutMixedIDs/(parent|cause)/(\d+)-\d+\s+\d+\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op',line)
            if m:
                kind,count,ns,allocated,allocations=m.groups();values.append(dict(kind=kind,count=int(count),ns=float(ns),bytes=float(allocated),allocations=float(allocations)))
        assert len(values)==10,(label,len(values))
        samples.append(dict(pair=pair,arm=arm,seconds=elapsed,values=values,stall_fraction={k:(after[k]-before[k])/elapsed/1e6 for k in before}));(output/'runs.json').write_text(json.dumps(samples,indent=2)+'\n')
summary={}
for kind in ['parent','cause']:
    summary[kind]={}
    for count in [1,16,128,1026,4096]:
        summary[kind][count]={}
        for arm in ['before','after']:
            values=[v for s in samples if s['arm']==arm for v in s['values'] if v['kind']==kind and v['count']==count]
            summary[kind][count][arm]={k:statistics.median(v[k] for v in values) for k in ['ns','bytes','allocations']}
(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
