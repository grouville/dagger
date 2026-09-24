from pathlib import Path
import os,sys,json,subprocess,socket,time,hashlib
base=Path('/tmp/collections-perf/ts-cache/split-imports/cold-retry');base.mkdir(exist_ok=True)
os.environ.pop('SSH_AUTH_SOCK',None)
cli='/tmp/collections-perf/committed/dagger';runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
expected=Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
variants={
 'control':{'engine':'dagger-engine.collections-split-cold-control-retry','port':6101,'binary':'/tmp/collections-perf/syntax-isolated/engine','cli':cli,'fresh':True,'workspace':'/tmp/collections-perf/kyle-latest/greetings-api'},
 'split':{'engine':'dagger-engine.collections-split-cold-candidate-retry','port':6102,'binary':'/tmp/collections-perf/syntax-isolated/engine','cli':cli,'fresh':True,'workspace':'/tmp/collections-perf/ts-cache/split-imports/workspace'},
}
(base/'variants.json').write_text(json.dumps(variants,indent=2)+'\n')
rows=[]
def measure(label,name):
 v=variants[name];dest=base/label
 args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--',cli,'--engine','container://'+v['engine'],'check','-l','--all']
 result=subprocess.run(args,cwd=v['workspace'],capture_output=True,text=True)
 (dest/'driver.log').write_text(result.stdout+result.stderr);result.check_returncode()
 out=(dest/'run-0.out').read_bytes();assert out==expected,label+' incorrect'
 timing=json.loads((dest/'results.json').read_text())
 row={'label':label,'variant':name,'seconds':timing['median_seconds'],'rows':14,'correct':True,'sha256':hashlib.sha256(out).hexdigest()};rows.append(row)
 (base/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
for name,v in reversed(list(variants.items())):
 if not v['fresh']:continue
 engine=v['engine']
 for kind in ['container','volume']:
  assert subprocess.run(['docker',kind,'inspect',engine],capture_output=True).returncode!=0,engine+' already exists'
 subprocess.run(['docker','create','--name',engine,'--privileged','-p',f'127.0.0.1:{v["port"]}:6060','-v',engine+':/var/lib/dagger','localhost/dagger-engine.collections-perf:latest','--extra-debug','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['docker','cp',v['binary'],engine+':/usr/local/bin/dagger-engine'],check=True)
 subprocess.run(['docker','start',engine],check=True,stdout=subprocess.DEVNULL)
 deadline=time.monotonic()+30
 while True:
  try:
   with socket.create_connection(('127.0.0.1',v['port']),timeout=1):break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.1)
 measure('cold/'+name,name)
