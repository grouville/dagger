from pathlib import Path
import subprocess,threading,json,time
b=Path('/tmp/collections-perf/schema-decode')
def snap():return {'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**{n:Path('/proc',n).read_text() for n in ['stat','pressure/cpu','pressure/io','pressure/memory']}}
def metric(s,name,kind):return int(next(l for l in s['pressure/'+name].splitlines() if l.startswith(kind+' ')).split('total=')[1])
# Start after ten quiet seconds, then retain every timing and pressure sample.
last=snap();quiet=0
with (b/'validation-readiness.jsonl').open('w') as f:
 for i in range(90):
  time.sleep(2);now=snap();us=(now['monotonic_ns']-last['monotonic_ns'])/1000
  io=(metric(now,'io','full')-metric(last,'io','full'))/us;cpu=(metric(now,'cpu','some')-metric(last,'cpu','some'))/us
  f.write(json.dumps({'sample':now,'io_fraction':io,'cpu_fraction':cpu})+'\n');f.flush()
  quiet=quiet+1 if io<.02 and cpu<.05 else 0
  if i%10==0:print('Preflight IO/CPU fractions:',io,cpu,flush=True)
  if quiet>=5:break
  last=now
 else:raise RuntimeError('No quiet start window')
for name in ['warm-repeat','runtime-qa']:
 stop=threading.Event()
 def sample():
  with (b/(name+'-host.jsonl')).open('w') as f:
   while True:
    f.write(json.dumps(snap())+'\n');f.flush()
    if stop.wait(.25):break
 t=threading.Thread(target=sample);t.start()
 try:
  with (b/(name+'.log')).open('w') as f:
   subprocess.run(['python3',str(b/(name+'.py'))],stdout=f,stderr=subprocess.STDOUT,check=True)
 finally:stop.set();t.join()
 print(name,'complete',flush=True)
