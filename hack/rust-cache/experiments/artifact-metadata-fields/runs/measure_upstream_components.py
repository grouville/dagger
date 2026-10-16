from pathlib import Path
import json,os,subprocess,time,statistics

root=Path(__file__).parent;source=Path('/tmp/dagger-artifact-metadata-fields-upstream');out=root/'upstream-components';out.mkdir(exist_ok=False)
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
with (out/'build.log').open('w') as stream:subprocess.run([go,'test','-c','-o',str(out/'schema.test'),'./core/schema'],cwd=source,stdout=stream,stderr=subprocess.STDOUT,check=True)
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
rows=[]
for pair in range(6):
    for direct in ([False,True] if pair%2==0 else [True,False]):
        label=f'{pair}-{direct}';before=pressure();started=time.monotonic()
        with (out/(label+'.log')).open('w') as stream:subprocess.run([str(out/'schema.test'),'-test.run=^$','-test.bench=BenchmarkArtifactMetadataReads/[0-9]+/direct='+str(direct).lower()+'$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT,check=True)
        seconds=time.monotonic()-started;after=pressure();metrics=[]
        for line in (out/(label+'.log')).read_text().splitlines():
            if line.startswith('Benchmark'):
                f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
        assert metrics,label
        rows.append(dict(pair=pair,direct=direct,seconds=seconds,metrics=metrics,stall_fraction={k:(after[k]-before[k])/seconds/1e6 for k in before}));(out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
summary={}
for count in [1,1026]:
    summary[str(count)]={}
    for direct in [False,True]:
        ms=[m for r in rows if r['direct']==direct for m in r['metrics'] if m['name'].startswith('BenchmarkArtifactMetadataReads/'+str(count)+'/')]
        summary[str(count)][str(direct)]={k:statistics.median(m[k] for m in ms) for k in ['ns','bytes','allocations']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
