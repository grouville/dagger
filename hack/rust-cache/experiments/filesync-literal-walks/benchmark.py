from pathlib import Path
import json,os,re,statistics,subprocess,time
r=Path(__file__).parent; cwd=Path('/tmp/dagger-filesync-literal-pathwalk'); go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='1')
for arm in ['before','after']:
 with (r/(arm+'-test-build.log')).open('w') as out:subprocess.run([go,'test','-p','1','-c','-overlay',str(r/(arm+'-overlay.json')),'-o',str(r/(arm+'.test')),'./internal/fsutil'],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
 print('built',arm,flush=True)
rows=[]
for pair in range(3):
 for arm in (['before','after'] if pair%2==0 else ['after','before']):
  log=r/f'benchmark-{pair}-{arm}.log'
  with log.open('w') as out:p=subprocess.run([str(r/(arm+'.test')),'-test.run','^TestFilterFSLiteralInclude','-test.bench','^BenchmarkFilterFSLiteralInclude$','-test.benchtime','250ms','-test.benchmem'],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
  row=dict(pair=pair,arm=arm,exit_code=p.returncode,benchmarks=[])
  for line in log.read_text().splitlines():
   m=re.match(r'(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
   if m:row['benchmarks'].append(dict(name=m[1],ns=float(m[3]),bytes=int(m[4]),allocs=int(m[5])))
  rows.append(row);(r/'benchmarks.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True);assert p.returncode==0 and len(row['benchmarks'])==3
summary={n:{arm:{k:statistics.median(b[k] for x in rows if x['arm']==arm for b in x['benchmarks'] if b['name']==n) for k in ['ns','bytes','allocs']} for arm in ['before','after']} for n in [b['name'] for b in rows[0]['benchmarks']]}
(r/'benchmark-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
