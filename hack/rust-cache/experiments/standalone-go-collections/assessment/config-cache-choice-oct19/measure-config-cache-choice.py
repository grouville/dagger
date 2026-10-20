from pathlib import Path
import json,os,re,statistics,subprocess,time
out=Path('/tmp/go-collection-upstream-review-oct19')
source=out/'engine-config-cache-choice/core/workspace'
env=dict(os.environ,GOMAXPROCS='8')
checks=[];samples=[]
def call(label,args):
 log=out/('config-cache-choice-'+label+'.log')
 tick=time.monotonic()
 with log.open('w') as stream, log.with_suffix('.stderr.log').open('w') as errors:
  result=subprocess.run([str(out/'config-cache-choice.test'),*args],cwd=source,env=env,stdout=stream,stderr=errors,timeout=120)
 record=dict(label=label,command=args,log=str(log),seconds=time.monotonic()-tick,exit_code=result.returncode)
 checks.append(record)
 (out/'config-cache-choice-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
 assert result.returncode==0,log.read_text()[-3000:]
 return log
call('lifetime',['-test.run=^TestGitClientDagqlCacheLifetime$','-test.count=1','-test.v'])
for scenario in ['repeated','parallel','distinct']:
 for pair in range(4):
  for choice in (['lru','dagql'] if pair%2==0 else ['dagql','lru']):
   log=call(f'{scenario}-{pair}-{choice}',['-test.run=^$','-test.bench=^BenchmarkGitClientCacheChoice$/^'+scenario+'$/^'+choice+'$','-test.benchtime=5000x','-test.count=1','-test.cpu=8','-test.benchmem'])
   match=re.search(r'^BenchmarkGitClientCacheChoice/[^\s]+\s+\d+\s+([\d.]+) ns/op\s+([\d.]+) B/op\s+([\d.]+) allocs/op',log.read_text(),re.M)
   assert match,log.read_text()
   row=dict(scenario=scenario,pair=pair,choice=choice,nanoseconds=float(match[1]),bytes=float(match[2]),allocations=float(match[3]),log=str(log))
   samples.append(row)
   (out/'config-cache-choice-samples.json').write_text(json.dumps(samples,indent=2)+'\n')
   print(json.dumps(row),flush=True)
summary=[]
for scenario in ['repeated','parallel','distinct']:
 row=dict(scenario=scenario)
 for choice in ['lru','dagql']:
  group=[r for r in samples if r['scenario']==scenario and r['choice']==choice]
  row[choice]={key:statistics.median(r[key] for r in group) for key in ['nanoseconds','bytes','allocations']}
 summary.append(row)
(out/'config-cache-choice-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
