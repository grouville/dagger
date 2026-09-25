from pathlib import Path
import json,subprocess,time,threading
base=Path('/tmp/collections-perf/warm-next');dest=base/'warm-quiet';dest.mkdir(exist_ok=True)
def snapshot():
 return {'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**{name:Path('/proc',name).read_text() for name in ['stat','pressure/cpu','pressure/io','pressure/memory']}}
def total(s):return int(s['pressure/io'].splitlines()[1].split('total=')[1])
# Predeclare one start criterion, retain all samples after starting.
previous=snapshot();stable=0
with (dest/'readiness.jsonl').open('w') as out:
 for i in range(90):
  time.sleep(2);current=snapshot();ratio=(total(current)-total(previous))/((current['monotonic_ns']-previous['monotonic_ns'])/1000)
  out.write(json.dumps({'sample':current,'io_full_fraction':ratio})+'\n');out.flush()
  stable=stable+1 if ratio<.02 else 0
  if i%10==0:print('Waiting for 10s below 2% full I/O pressure:',round(ratio,3),flush=True)
  if stable>=5:break
  previous=current
 else:
  print('Host did not meet the start criterion; no timings taken.',flush=True);raise SystemExit(2)
stop=threading.Event()
def sample():
 with (dest/'host-samples.jsonl').open('w') as out:
  while True:
   out.write(json.dumps(snapshot())+'\n');out.flush()
   if stop.wait(.25):break
thread=threading.Thread(target=sample);thread.start()
try:
 p=subprocess.run(['python3',str(base/'warm-quiet.py')]);p.check_returncode()
finally:stop.set();thread.join()
