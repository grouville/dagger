from pathlib import Path
import hashlib,json,os,subprocess,time
r=Path(__file__).parent; cwd=Path('/tmp/dagger-glob-literal-prefix')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='1',DAGGER_VERSION='v1.0.0-beta.15')
rows=[]
for arm in ['before','after']:
    tick=time.monotonic(); binary=r/('dagger-'+arm)
    with (r/('cli-'+arm+'-build.log')).open('w') as out:
        subprocess.run([go,'build','-p','1','-buildvcs=false','-overlay',str(r/('cli-'+arm+'-overlay.json')),'-o',str(binary),'./cmd/dagger'],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    row=dict(arm=arm,seconds=time.monotonic()-tick,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),version=subprocess.check_output([str(binary),'version'],env=env,text=True).strip())
    rows.append(row); (r/'cli-builds.json').write_text(json.dumps(rows,indent=2)+'\n'); print(json.dumps(row),flush=True)
