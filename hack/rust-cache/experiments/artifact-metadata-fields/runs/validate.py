from pathlib import Path
import hashlib,json,os,subprocess,time,statistics

root=Path(__file__).parent;source=Path('/tmp/dagger-filesync-snapshot-seeds');base=root.parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';rows=[]
common=['-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'overlay.json')]
def run(label,command,**options):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT,**options)
    rows.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started));(root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,round(rows[-1]['seconds'],1),flush=True);assert r.returncode==0,label
run('artifact-race',[go,'test','-p','1','-race',*common,'./core','./core/schema','-run','TestArtifact|TestArtifacts|TestDimensionKey','-count=1'])
run('benchmark-build',[go,'test',*common,'-c','-o',str(root/'schema.test'),'./core/schema'])
def pressure():return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
samples=[]
for pair in range(6):
    for direct in ([False,True] if pair%2==0 else [True,False]):
        label=f'bench-{pair}-{direct}';before=pressure();started=time.monotonic()
        run(label,[str(root/'schema.test'),'-test.run=^$','-test.bench=BenchmarkArtifactMetadataReads/[0-9]+/direct='+str(direct).lower()+'$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'))
        seconds=time.monotonic()-started;after=pressure();metrics=[]
        for line in (root/(label+'.log')).read_text().splitlines():
            if line.startswith('Benchmark'):
                f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
        assert metrics,label
        samples.append(dict(pair=pair,direct=direct,seconds=seconds,metrics=metrics,stall_fraction={k:(after[k]-before[k])/seconds/1e6 for k in before}));(root/'component-runs.json').write_text(json.dumps(samples,indent=2)+'\n')
summary={}
for count in [1,1026]:
    summary[str(count)]={}
    for direct in [False,True]:
        ms=[m for r in samples if r['direct']==direct for m in r['metrics'] if m['name'].startswith('BenchmarkArtifactMetadataReads/'+str(count)+'/')]
        summary[str(count)][str(direct)]={k:statistics.median(m[k] for m in ms) for k in ['ns','bytes','allocations']}
(root/'component-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
run('engine-build',[go,'build','-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'engine-overlay.json'),'-buildvcs=false','-o',str(root/'dagger-engine'),'./cmd/engine'])
overlay=json.loads((root/'engine-overlay.json').read_text())
(root/'manifest.json').write_text(json.dumps({logical:dict(replacement=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical,path in overlay['Replace'].items()},indent=2)+'\n')
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),base_engine_sha256='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721',source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',feature='Read artifact description and URI strings without separate result-cache entries; preserve cached object lists.',default_enabled=False,diagnostic_route='/debug/artifact-metadata-fields'),indent=2)+'\n')
