from pathlib import Path
import subprocess,json,os,threading,time,statistics
os.environ.pop('SSH_AUTH_SOCK',None)
b=Path('/tmp/collections-perf/discovery-next');ws=Path('/tmp/collections-perf/normal-baseline/greetings-split')
variants={'control':'dagger-engine.collections-tsx-node-cache','candidate':'dagger-engine.collections-artifact-schema-fork'}
runner='/home/dagger/dag/hack/bench-artifact-discovery.py';expected='/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt'
def snap():return {'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**{n:Path('/proc',n).read_text() for n in ['stat','pressure/cpu','pressure/io','pressure/memory']}}
def metric(s,n,k):return int(next(l for l in s['pressure/'+n].splitlines() if l.startswith(k+' ')).split('total=')[1])
last=snap();quiet=0
with (b/'readiness.jsonl').open('w') as f:
 for i in range(90):
  time.sleep(2);now=snap();us=(now['monotonic_ns']-last['monotonic_ns'])/1000
  io=(metric(now,'io','full')-metric(last,'io','full'))/us;cpu=(metric(now,'cpu','some')-metric(last,'cpu','some'))/us
  f.write(json.dumps({'sample':now,'io_fraction':io,'cpu_fraction':cpu})+'\n');f.flush()
  quiet=quiet+1 if io<.02 and cpu<.05 else 0
  if quiet>=5:break
  last=now
 else:raise RuntimeError('No quiet start window')
stop=threading.Event()
def sample():
 with (b/'host.jsonl').open('w') as f:
  while True:
   f.write(json.dumps(snap())+'\n');f.flush()
   if stop.wait(.25):break
thread=threading.Thread(target=sample);thread.start()
rows=[]
try:
 for i in range(-1,8):
  for label in (list(variants) if i%2==0 else list(reversed(variants))):
   dest=b/'warm'/f'{label}-{i}';start=time.time_ns()
   p=subprocess.run(['python3',runner,'--runs','1','--warmups','0','--output',str(dest),'--expect-stdout',expected,'--','/tmp/collections-perf/committed/dagger','--engine','container://'+variants[label],'check','-l','--all'],cwd=ws,capture_output=True,text=True)
   (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
   result=json.loads((dest/'results.json').read_text());row={'variant':label,'iteration':i,'start_unix_ns':start,'end_unix_ns':time.time_ns(),'seconds':result['median_seconds']};rows.append(row);print(row,flush=True)
   (b/'warm-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
finally:stop.set();thread.join()
print({k:statistics.median(r['seconds'] for r in rows if r['iteration']>=0 and r['variant']==k) for k in variants},flush=True)
