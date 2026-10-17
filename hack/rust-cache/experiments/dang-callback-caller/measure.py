from pathlib import Path
import json,subprocess,re,statistics,time
p=Path(__file__).parent
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
lib=p.parent/'dang-module-blueprint-content-key'
for arm,overlay in [('before','before-overlay.json'),('after','overlay.json')]:
 cmd=[go,'test','-c','-p=1','-overlay='+str(p/overlay),'-o',str(p/(arm+'.test')),'./pkg/dang']
 with (p/(arm+'-build.log')).open('w') as out:r=subprocess.run(cmd,cwd=lib,stdout=out,stderr=subprocess.STDOUT)
 assert r.returncode==0,arm
rows=[]
for pair in range(4):
 for arm in (['before','after'] if pair%2==0 else ['after','before']):
  cmd=[str(p/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkCallbackCaller$','-test.benchtime=100000x','-test.count=1']
  run=subprocess.run(cmd,cwd=lib,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  (p/f'{pair}-{arm}.log').write_text(run.stdout)
  assert run.returncode==0,run.stdout
  line=next(x for x in run.stdout.splitlines() if x.startswith('BenchmarkCallbackCaller'))
  row={'pair':pair,'arm':arm,'ns':float(re.search(r'([\d.]+) ns/op',line)[1]),'bytes':int(re.search(r'(\d+) B/op',line)[1]),'allocs':int(re.search(r'(\d+) allocs/op',line)[1])}
  rows.append(row);(p/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
summary={arm:{key:statistics.median(r[key] for r in rows if r['arm']==arm) for key in ['ns','bytes','allocs']} for arm in ['before','after']}
(p/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
