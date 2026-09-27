from pathlib import Path
import hashlib, json, os, subprocess, sys, time

LAB = Path(__file__).resolve().parent
ROOT = Path('/tmp/collections-perf/dang-map-merge-v1/dependency/dang')
GO = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sys.argv[1:] == ['--run']
manifest = json.loads((LAB/'manifest.json').read_text())
def guard():
    for p, digest in manifest['inputs'].items(): assert sha(p) == digest, p
guard()
assert not (LAB/'results.json').exists()
env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LOGNAME','TMPDIR')}
env.update(GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOFLAGS='',GOMAXPROCS='4',CGO_ENABLED='0')
steps=[]
regex='^TestMapMergeOwned'
def run(label, cmd, race=False):
    guard(); log=LAB/(label+'.log'); start=time.monotonic()
    with log.open('wb') as f:
        result=subprocess.run(cmd,cwd=ROOT,env={**env,'CGO_ENABLED':'1' if race else '0'},stdout=f,stderr=subprocess.STDOUT,timeout=180)
    row=dict(label=label,command=cmd,exit_code=result.returncode,seconds=time.monotonic()-start,log_sha256=sha(log))
    steps.append(row);(LAB/'results.json').write_text(json.dumps(steps,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    assert result.returncode==0,label
for variant in ('baseline','candidate'):
    run(variant+'-normal',[GO,'test','-p=1','-mod=readonly','-overlay='+str(LAB/(variant+'-overlay.json')),'./pkg/dang','-run='+regex,'-count=1','-timeout=90s'])
run('candidate-race',[GO,'test','-p=1','-mod=readonly','-race','-overlay='+str(LAB/'candidate-overlay.json'),'./pkg/dang','-run=^TestMapMergeOwned','-count=1','-timeout=90s'],True)
for variant in ('baseline','candidate'):
    run(variant+'-build',[GO,'test','-p=1','-mod=readonly','-overlay='+str(LAB/(variant+'-overlay.json')),'-c','-o',str(LAB/(variant+'.test')),'./pkg/dang'])
for cycle in range(3):
    for variant in (('baseline','candidate') if cycle%2==0 else ('candidate','baseline')):
        run(f'bench-{cycle}-{variant}',[str(LAB/(variant+'.test')),'-test.run=^TestMapMergeOwned','-test.bench=^BenchmarkMapMergeOwned$','-test.benchmem','-test.benchtime=100ms','-test.count=1','-test.timeout=90s'])
guard()
