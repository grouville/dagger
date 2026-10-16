from pathlib import Path
import hashlib,json,os,subprocess,time

root=Path(__file__).parent;source=Path('/tmp/dagger-filesync-snapshot-seeds');protobuf=Path('/tmp/protobuf-field-order-experiment')
installed=Path('/home/dagger/go/pkg/mod/google.golang.org/protobuf@v1.36.11')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common=['-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'overlay.json')]
rows=[]
def run(label,command,cwd=source,**options):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=cwd,stdout=out,stderr=subprocess.STDOUT,**options)
    rows.append(dict(label=label,command=command,cwd=str(cwd),seconds=time.monotonic()-started,exit_code=r.returncode))
    (root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,round(rows[-1]['seconds'],2),flush=True)
    assert r.returncode==0,label

files={}
for path in installed.rglob('*.go'):
    if path.name.endswith('_test.go'):continue
    relative=path.relative_to(installed);other=protobuf/relative
    assert other.is_file() and other.read_bytes()==path.read_bytes(),str(relative)
    files[str(relative)]=hashlib.sha256(path.read_bytes()).hexdigest()
(root/'protobuf-production-baseline.json').write_text(json.dumps(dict(version='v1.36.11',all_installed_production_Go_files_identical=True,files=files),indent=2)+'\n')
for enabled in [False,True]:
    env=dict(os.environ,DAGGER_TEST_SMALL_PROTO_FIELDS='1' if enabled else '0',GOMAXPROCS='8')
    run('dependency-race-'+str(enabled),[go,'test','-p','1','-race','-overlay',str(root/'overlay.json'),'./internal/order','./encoding/protojson','./encoding/prototext','./proto','-count=1'],cwd=protobuf,env=env)
run('clientdb-race',[go,'test','-p','1','-race',*common,'./engine/clientdb','-count=1'],env=dict(os.environ,DAGGER_TEST_SMALL_PROTO_FIELDS='1'))
run('build-order-bench',[go,'test','-overlay',str(root/'overlay.json'),'-c','-o',str(root/'order.test'),'./internal/order'],cwd=protobuf)
run('build-clientdb-bench',[go,'test',*common,'-c','-o',str(root/'clientdb.test'),'./engine/clientdb'])
def pressure():
    return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
samples=[]
for pair in range(6):
    for suite,bench in [('order','^BenchmarkRangeFields$'),('clientdb','^BenchmarkMarshalProtoJSONs/current$')]:
        for enabled in ([False,True] if pair%2==0 else [True,False]):
            before=pressure();started=time.monotonic()
            label=f'bench-{pair}-{suite}-{enabled}'
            run(label,[str(root/(suite+'.test')),'-test.run=^$','-test.bench='+bench,'-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,DAGGER_TEST_SMALL_PROTO_FIELDS='1' if enabled else '0',GOMAXPROCS='8'))
            elapsed=time.monotonic()-started;after=pressure()
            metrics=[]
            for line in (root/(label+'.log')).read_text().splitlines():
                if line.startswith('Benchmark'):
                    f=line.split();metrics.append(dict(name=f[0],ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
            assert metrics,label
            samples.append(dict(pair=pair,suite=suite,enabled=enabled,metrics=metrics,seconds=elapsed,stall_fraction={k:(after[k]-before[k])/elapsed/1e6 for k in before}))
            (root/'component-runs.json').write_text(json.dumps(samples,indent=2)+'\n')
run('build-engine',[go,'build',*common,'-buildvcs=false','-o',str(root/'dagger-engine'),'./cmd/engine'])
overlay=json.loads((root/'overlay.json').read_text())
(root/'manifest.json').write_text(json.dumps({logical:dict(replacement=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical,path in overlay['Replace'].items()},indent=2)+'\n')
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),base_engine_sha256='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721',source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',protobuf_version='v1.36.11',scope='Only Protobuf message field ordering changes; experimental switch off by default.'),indent=2)+'\n')
