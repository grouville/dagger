from pathlib import Path
import json,os,re,shutil,statistics,subprocess,time

root=Path(__file__).parent;base=root.parent;source=Path('/tmp/dagger-filesync-snapshot-seeds')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
for name in ['engine.go.mod','engine.go.sum']:shutil.copyfile(base/'artifact-metadata-fields'/name,root/name)
after=json.loads((root/'overlay.json').read_text());before=json.loads(json.dumps(after))
before['Replace'][str(source/'engine/clientdb/telemetry_store.go')]=str(root/'before.go')
(root/'before-overlay.json').write_text(json.dumps(before,indent=2)+'\n')
phases=[]
def run(label,command,env=None):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT,env=env)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'validation.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,r.returncode,round(phases[-1]['seconds'],2),flush=True);assert r.returncode==0,label
common=['-p','1','-modfile',str(root/'engine.go.mod')]
run('baseline-compatibility',[go,'test',*common,'-overlay',str(root/'before-overlay.json'),'./engine/clientdb','-run','^TestSpanLookupRepeatedIDsAndLateEdges$','-count=1'])
run('candidate-race',[go,'test',*common,'-overlay',str(root/'overlay.json'),'-race','./engine/clientdb','-count=1'])
for arm,overlay in [('before',root/'before-overlay.json'),('after',root/'overlay.json')]:
    run(arm+'-build',[go,'test',*common,'-overlay',str(overlay),'-c','-o',str(root/(arm+'.test')),'./engine/clientdb'])
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
samples=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'bench-{pair}-{arm}';before=pressure();tick=time.monotonic()
        run(label,[str(root/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkSpanLookupFanout$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'))
        seconds=time.monotonic()-tick;after=pressure();values=[]
        for line in (root/(label+'.log')).read_text().splitlines():
            m=re.match(r'BenchmarkSpanLookupFanout/(parent|cause)/(\d+)-\d+\s+\d+\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op',line)
            if m:
                kind,count,ns,allocated,allocations=m.groups();values.append(dict(kind=kind,count=int(count),ns=float(ns),bytes=float(allocated),allocations=float(allocations)))
        assert len(values)==10,(label,len(values))
        samples.append(dict(pair=pair,arm=arm,seconds=seconds,values=values,stall_fraction={k:(after[k]-before[k])/seconds/1e6 for k in before}));(root/'component-runs.json').write_text(json.dumps(samples,indent=2)+'\n')
summary={}
for kind in ['parent','cause']:
    summary[kind]={}
    for count in [1,16,128,1026,4096]:
        summary[kind][count]={}
        for arm in ['before','after']:
            values=[v for s in samples if s['arm']==arm for v in s['values'] if v['kind']==kind and v['count']==count]
            summary[kind][count][arm]={k:statistics.median(v[k] for v in values) for k in ['ns','bytes','allocations']}
(root/'component-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
