from pathlib import Path
import json,os,subprocess
root=Path(__file__).parent
capture=root/'capture'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
cli=root.parent/'filesync-literal-pathwalk/dagger-after'
engine=root/'dagger-engine'
windows=json.loads((capture/'engine-cpu-windows.json').read_text())
commands={
 'engine-cpu-cumulative.txt':['-top','-cum','-nodecount=55',str(engine),*[str(capture/w['path']) for w in windows]],
 'engine-cpu-flat.txt':['-top','-nodecount=55',str(engine),*[str(capture/w['path']) for w in windows]],
 'cli-cpu-cumulative.txt':['-top','-cum','-nodecount=45',str(cli),str(capture/'cli-cpu.pprof')],
 'cli-cpu-flat.txt':['-top','-nodecount=45',str(cli),str(capture/'cli-cpu.pprof')],
 'engine-allocation-delta.txt':['-top','-alloc_space','-nodecount=55','-base',str(capture/'engine-allocs-before.pprof'),str(engine),str(capture/'engine-allocs-after.pprof')],
}
for name,flags in commands.items():
 command=[go,'tool','pprof',*flags]
 with (capture/name).open('w') as out:r=subprocess.run(command,env=dict(os.environ,GOTOOLCHAIN='local'),stdout=out,stderr=subprocess.STDOUT)
 assert r.returncode==0,name
 print(name,flush=True)
