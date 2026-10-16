from pathlib import Path
import json,os,subprocess,time,statistics

root=Path(__file__).parent;source=Path('/tmp/dagger-filesync-snapshot-seeds');base=root.parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common=['-modfile',str(base/'parallel-fingerprint-engine/engine.go.mod')]
rows=[]
def run(label,command):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,r.returncode,round(rows[-1]['seconds'],1),flush=True);assert r.returncode==0,label
run('candidate-race',[go,'test','-race',*common,'-overlay',str(root/'after.json'),'./engine/clientdb','-count=1'])
for arm in ['before','after']:run('build-'+arm,[go,'test',*common,'-overlay',str(root/(arm+'.json')),'-c','-o',str(root/(arm+'.test')),'./engine/clientdb'])
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
samples=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'bench-{pair}-{arm}';start=time.monotonic();before=pressure()
        with (root/(label+'.log')).open('w') as stream:subprocess.run([str(root/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkMarshalProtoJSONs/current$','-test.benchmem','-test.benchtime=200ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT,check=True)
        seconds=time.monotonic()-start;after=pressure();metrics=[]
        for line in (root/(label+'.log')).read_text().splitlines():
            if line.startswith('Benchmark'):
                f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
        assert metrics,label
        samples.append(dict(pair=pair,arm=arm,seconds=seconds,metrics=metrics,stall_fraction={k:(after[k]-before[k])/seconds/1e6 for k in before}));(root/'runs.json').write_text(json.dumps(samples,indent=2)+'\n')
summary={arm:{k:statistics.median(m[k] for r in samples if r['arm']==arm for m in r['metrics']) for k in ['ns','bytes','allocations']} for arm in ['before','after']}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
