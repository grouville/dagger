from pathlib import Path
import subprocess,time,json,re,sys
sys.path.insert(0,'/tmp/collections-perf/post-rebase-io')
import run as lab
WS=Path('/tmp/collections-perf/normal-baseline/greetings-split')
# Prepared images, fresh volume per run, one benchmark engine at a time.
# ABBA balances order; no build, blob copy, or forced cache eviction in this loop.
for i,variant in enumerate(['baseline','candidate','candidate','baseline']):
 name=f'dagger-engine.collections-disk-abba-{i}';port=6170+i
 try:
  lab.start(name,port,image='localhost/dagger-engine.collections-main-io:'+variant)
  lab.measure(name,port,WS,'cold')
  for j in range(3):
   start=str(time.time())
   row=lab.measure(name,port,WS,f'warm-{j}')
   logs=subprocess.run(['docker','logs','--since',start,name],capture_output=True,text=True)
   lines=[s for s in (logs.stdout+logs.stderr).splitlines() if 'shutdown drain phase done' in s and 'isMainClient=true' in s]
   (lab.B/name/f'warm-{j}'/'shutdown.txt').write_text('\n'.join(lines)+'\n')
  if i < 2: lab.measure(name,port,WS,'warm-profile',profile=True)
 finally:
  p=subprocess.run(['docker','stop','--timeout','30',name],capture_output=True,text=True)
  print(json.dumps({'stopped':name,'status':p.returncode}),flush=True)
