from pathlib import Path
import hashlib,json,os,subprocess,time

root=Path(__file__).parent
source=Path('/tmp/dagger-filesync-snapshot-seeds')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
common=['-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'overlay.json')]
commands=[]
def run(label,command,**kwargs):
    start=time.monotonic()
    with (root/(label+'.log')).open('w') as out:
        result=subprocess.run(command,cwd=source,stdout=out,stderr=subprocess.STDOUT,**kwargs)
    commands.append(dict(label=label,command=command,exit_code=result.returncode,seconds=time.monotonic()-start))
    (root/'validation.json').write_text(json.dumps(commands,indent=2)+'\n')
    print(label,result.returncode,round(commands[-1]['seconds'],3),flush=True)
    assert result.returncode==0,label

run('suites-default',[go,'test',*common,'./internal/fsutil','./engine/filesync','-count=1'])
run('suites-candidate-race',[go,'test',*common,'-race','./internal/fsutil','./engine/filesync','-count=1'],env=dict(os.environ,DAGGER_TEST_MIRROR_METADATA_SKIP_XATTRS='1'))
run('build-benchmark',[go,'test',*common,'-c','-o',str(root/'fsutil.test'),'./internal/fsutil'])
for pair in range(6):
    order=[False,True] if pair%2==0 else [True,False]
    for skip in order:
        run(f'bench-{pair}-{skip}',[str(root/'fsutil.test'),'-test.run=^$','-test.bench=BenchmarkMirrorMetadataWalk/[0-9]+/skip='+str(skip).lower()+'$','-test.benchmem','-test.benchtime=150ms','-test.count=1'])
run('build-engine',[go,'build',*common,'-buildvcs=false','-o',str(root/'dagger-engine'),'./cmd/engine'])
overlay=json.loads((root/'overlay.json').read_text())
manifest={logical:dict(replacement=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical,path in overlay['Replace'].items()}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),previous_engine_sha256='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721',base_revision='19eda924854e7f22582f3a7430272aa729cbeb5f',default_enabled=False,diagnostic_route='/debug/mirror-metadata'),indent=2)+'\n')
