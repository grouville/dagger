from pathlib import Path
import os,subprocess,json,time,urllib.request,threading
b=Path('/tmp/collections-perf/discovery-next/cold');b.mkdir(exist_ok=True)
os.environ.pop('SSH_AUTH_SOCK',None)
manifest=json.loads(Path('/tmp/collections-perf/half-second/node-compile/manifest.json').read_text())['sdk_manifest']['digest']
engines={'control':'/tmp/collections-perf/schema-decode/engine','candidate':'/tmp/collections-perf/discovery-next/engine'}
rows=[]
stop=threading.Event()
def sample():
 with (b/'host.jsonl').open('w') as f:
  while True:
   f.write(json.dumps({'time_ns':time.time_ns(),**{n:Path('/proc',n).read_text() for n in ['stat','pressure/cpu','pressure/io','pressure/memory']}})+'\n');f.flush()
   if stop.wait(.25):break
thread=threading.Thread(target=sample);thread.start()
try:
 for i,label in enumerate(['control','candidate','candidate','control']):
  name=f'dagger-engine.collections-artifact-fork-cold-{i}';port=6147+i
  for kind in ['container','volume']:assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
  subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+manifest,'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['docker','cp',engines[label],name+':/usr/local/bin/dagger-engine'],check=True)
  for d in [Path('/tmp/collections-perf/prebuilt-ts-sdk/blobs'),Path('/tmp/collections-perf/half-second/node-compile/blobs')]:
   for f in d.iterdir():subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
  subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
  try:
   for attempt in range(200):
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
    except OSError:time.sleep(.1)
   else:raise RuntimeError('engine not ready')
   dest=b/f'{i}-{label}';start=time.time_ns()
   p=subprocess.run(['python3','/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--output',str(dest),'--expect-stdout','/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','--','/tmp/collections-perf/committed/dagger','--engine','container://'+name,'check','-l','--all'],cwd='/tmp/collections-perf/normal-baseline/greetings-split',capture_output=True,text=True)
   (dest/'driver.log').write_text(p.stdout+p.stderr)
   row={'variant':label,'iteration':i,'start_unix_ns':start,'end_unix_ns':time.time_ns(),'engine':name,'status':p.returncode,'results':json.loads((dest/'results.json').read_text())};rows.append(row)
   (b/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,row['results']['median_seconds'],p.returncode,flush=True)
   p.check_returncode()
  finally:
   subprocess.run(['docker','stop','--time','30',name],check=True,stdout=subprocess.DEVNULL)
   (b/f'{i}-state.json').write_bytes(subprocess.check_output(['docker','inspect','--format','{{json .State}}',name]))
finally:stop.set();thread.join()
