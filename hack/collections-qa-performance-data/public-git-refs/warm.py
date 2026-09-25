from pathlib import Path
import os,json,subprocess,sys,statistics
base=Path('/tmp/collections-perf/warm-next/warm');base.mkdir(exist_ok=True)
ws='/tmp/collections-perf/normal-baseline/greetings-split';cli='/tmp/collections-perf/committed/dagger';runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
os.environ.pop('SSH_AUTH_SOCK',None)
expected=Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
variants={'control':('dagger-engine.collections-go-import-quiet-1',6128),'candidate':('dagger-engine.collections-public-refs',6142)}
rows=[]
def run(label,name,profile=False):
 engine,port=variants[name];dest=base/label
 args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest)]
 if profile:args+=['--wcprof-url',f'http://127.0.0.1:{port}']
 args+=['--',cli,'--engine','container://'+engine,'check','-l','--all']
 p=subprocess.run(args,cwd=ws,capture_output=True,text=True)
 (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
 assert (dest/'run-0.out').read_bytes()==expected,label+' incorrect'
 result=json.loads((dest/'results.json').read_text());row={'label':label,'variant':name,'seconds':result['median_seconds'],'correct':True};rows.append(row)
 (base/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 if profile:
  with (dest/'analysis.txt').open('w') as f:subprocess.run(['/tmp/wcprof-analyze','-top','40',str(dest/'runs.wcprof')],stdout=f,check=True)
for i in range(2):
 for name in variants:run(f'warmup/{name}-{i}',name)
for i in range(5):
 for name in list(variants)[::(1 if i%2==0 else -1)]:run(f'warm/{name}-{i}',name)
print(json.dumps({n:statistics.median(r['seconds'] for r in rows if r['variant']==n and r['label'].startswith('warm/')) for n in variants}),flush=True)
