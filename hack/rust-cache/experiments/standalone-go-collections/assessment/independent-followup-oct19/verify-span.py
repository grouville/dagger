from pathlib import Path
import json,os,re,statistics,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19');repo=Path('/tmp/dagger-go-collection-clean-baseline');base='c5456d9cbf47e432b89aba43e35211425e8e1f03'
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off')
paths={'main':out/'span-main','candidate':out/'span-index'}
if not paths['main'].exists():subprocess.run(['git','-c','gc.auto=0','-C',str(repo),'worktree','add','--detach',str(paths['main']),base],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
test='engine/clientdb/span_lookup_fanout_test.go';(paths['main']/test).write_bytes((paths['candidate']/test).read_bytes())
steps=[]
def run(label,command,cwd):
 start=time.monotonic();print(json.dumps(dict(event='start',label=label)),flush=True)
 with (out/(label+'.log')).open('w') as log:r=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 row=dict(label=label,command=command,cwd=str(cwd),exit_code=r.returncode,seconds=time.monotonic()-start);steps.append(row);(out/'span-checks.json').write_text(json.dumps(steps,indent=2)+'\n');print(json.dumps(row),flush=True)
 assert r.returncode==0,(out/(label+'.log')).read_text()[-3500:]
 return (out/(label+'.log')).read_text()
for arm,path in paths.items():
 run('span-'+arm+'-race',[go,'test','-p=2','-race','-count=1','-timeout=180s','./engine/clientdb'],path)
 run('span-'+arm+'-build',[go,'test','-p=2','-c','-o',str(out/('span-'+arm+'.test')),'./engine/clientdb'],path)
samples=[]
for pair in range(6):
 for arm in (['main','candidate'] if pair%2==0 else ['candidate','main']):
  text=run(f'span-{pair}-{arm}',[str(out/('span-'+arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkSpanLookupFanout$/(parent|cause)/(1|1026|4096)$','-test.benchmem','-test.benchtime=200ms','-test.count=1'],paths[arm])
  for line in text.splitlines():
   m=re.match(r'(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
   if m:samples.append(dict(pair=pair,arm=arm,benchmark=m[1],iterations=int(m[2]),ns=float(m[3]),bytes=int(m[4]),allocs=int(m[5])))
  (out/'span-samples.json').write_text(json.dumps(samples,indent=2)+'\n')
summary=[]
for benchmark in sorted({r['benchmark'] for r in samples}):
 a=sorted([r for r in samples if r['benchmark']==benchmark and r['arm']=='main'],key=lambda r:r['pair']);b=sorted([r for r in samples if r['benchmark']==benchmark and r['arm']=='candidate'],key=lambda r:r['pair']);assert len(a)==len(b)==6
 summary.append(dict(benchmark=benchmark,before_ns=statistics.median(r['ns'] for r in a),candidate_ns=statistics.median(r['ns'] for r in b),before_bytes=statistics.median(r['bytes'] for r in a),candidate_bytes=statistics.median(r['bytes'] for r in b),before_allocs=statistics.median(r['allocs'] for r in a),candidate_allocs=statistics.median(r['allocs'] for r in b),faster_pairs=sum(y['ns']<x['ns'] for x,y in zip(a,b))))
(out/'span-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(event='complete',summary=summary)),flush=True)
