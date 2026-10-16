from pathlib import Path
import hashlib,json,os,subprocess,time

root=Path('/tmp/rust-cache-sipsma-review/typed-proto-fields');source=Path('/tmp/dagger-filesync-snapshot-seeds');protobuf=Path('/tmp/protobuf-field-order-experiment')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';rows=[]
def run(label,cmd,cwd,**options):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(cmd,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,**options)
    rows.append(dict(label=label,command=cmd,cwd=str(cwd),exit_code=r.returncode,seconds=time.monotonic()-started))
    (root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,round(rows[-1]['seconds'],1),flush=True);assert r.returncode==0,label
env=dict(os.environ,DAGGER_TEST_SMALL_PROTO_FIELDS='1')
run('dependency-race',[go,'test','-p','1','-race','-overlay',str(root/'overlay.json'),'./internal/order','./encoding/protojson','./encoding/prototext','./proto','-count=1'],protobuf,env=env)
common=['-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'overlay.json')]
run('clientdb-race',[go,'test','-p','1','-race',*common,'./engine/clientdb','-count=1'],source,env=env)
run('engine-build',[go,'build',*common,'-buildvcs=false','-o',str(root/'dagger-engine'),'./cmd/engine'],source)
overlay=json.loads((root/'overlay.json').read_text())
(root/'manifest.json').write_text(json.dumps({logical:dict(replacement=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical,path in overlay['Replace'].items()},indent=2)+'\n')
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest(),selected_base_engine_sha256='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721',source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',protobuf_version='v1.36.11',default_enabled=False,diagnostic_route='/debug/typed-proto-fields',feature='Small message fast paths and typed sort.Interface for larger messages; map sorter unchanged.'),indent=2)+'\n')
