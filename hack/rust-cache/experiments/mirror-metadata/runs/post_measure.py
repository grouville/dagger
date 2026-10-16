from pathlib import Path
import json,os,subprocess,time,urllib.request

root=Path(__file__).parent
base=root.parent
source=Path('/tmp/dagger-filesync-snapshot-seeds')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
commands=[]
def run(label,cmd,**options):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,**options)
    commands.append(dict(label=label,command=cmd,exit_code=result.returncode,seconds=time.monotonic()-started))
    (root/'post-validation.json').write_text(json.dumps(commands,indent=2)+'\n')
    print(label,result.returncode,round(commands[-1]['seconds'],2),flush=True)
    assert result.returncode==0,label

assert (root/'commands/summary.json').exists()
run('phase-comparison',[ 'python3',str(base/'measure_source_import_phases.py'),'--output',str(root/'phase-comparison'),'--runs','8','--mirror-policy','alternate'])
run('build-default-cost',[go,'test','-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'default-cost/overlay.json'),'-c','-o',str(root/'default-cost/fsutil.test'),'./internal/fsutil'],cwd=source)
for pair in range(6):
    for original in ([True,False] if pair%2==0 else [False,True]):
        run(f'default-cost/bench-{pair}-{original}',[str(root/'default-cost/fsutil.test'),'-test.run=^$','-test.bench=BenchmarkMirrorMetadataWalk/[0-9]+/reference='+str(original).lower()+'$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],cwd=source)
def mode(enabled):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/mirror-metadata?enabled='+str(enabled).lower(),data=b''),timeout=10) as r:assert json.load(r)['enabled']==enabled
try:
    mode(True)
    run('retained-cache',[ 'python3',str(base/'check_native_discovery_current_reuse.py'),'mirror-metadata'])
finally:mode(False)
