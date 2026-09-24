from pathlib import Path
import os,sys,json,subprocess,shutil,socket,time,hashlib,statistics
base=Path('/tmp/collections-perf/syntax-isolated');ws=base/'greetings-api'
os.environ.pop('SSH_AUTH_SOCK',None)
cli='/tmp/collections-perf/committed/dagger'
runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
expected=Path('/tmp/collections-perf/committed/greetings/warmup/candidate/run-0.out').read_bytes()
subprocess.run(['git','clone','--quiet','--no-local','/tmp/greetings-api-collections-perf',str(ws)],check=True)
subprocess.run(['git','-C',str(ws),'remote','set-url','origin','https://github.com/kpenfound/greetings-api.git'],check=True)
shutil.copy2('/tmp/collections-perf/committed/greetings/warm-workspace-candidate/dagger.toml',ws/'dagger.toml')
shutil.copy2('/tmp/collections-perf/committed/greetings/warm-workspace-candidate/dagger.lock',ws/'dagger.lock')
variants={
 'committed':{'engine':'dagger-engine.collections-syntax-control','binary':'/tmp/collections-perf/committed/engine','port':6094},
 'syntax-cache':{'engine':'dagger-engine.collections-syntax-cache','binary':str(base/'engine'),'port':6095},
}
(base/'variants.json').write_text(json.dumps(variants,indent=2)+'\n')
rows=[]
def measure(label,name,profile=False):
 v=variants[name];dest=base/label
 args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest)]
 if profile:args+=['--wcprof-url',f'http://127.0.0.1:{v["port"]}']
 args+=['--',cli,'--engine','container://'+v['engine'],'check','-l','--all']
 p=subprocess.run(args,cwd=ws,capture_output=True,text=True)
 (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
 out=(dest/'run-0.out').read_bytes();assert out==expected,label+' output mismatch'
 result=json.loads((dest/'results.json').read_text())
 row={'label':label,'variant':name,'seconds':result['median_seconds'],'rows':14,'correct':True,'sha256':hashlib.sha256(out).hexdigest()}
 rows.append(row);print(json.dumps(row),flush=True)
 (base/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 if profile:
  with (dest/'analysis.txt').open('w') as f:subprocess.run(['/tmp/wcprof-analyze','-top','60',str(dest/'runs.wcprof')],stdout=f,check=True)
for name,v in variants.items():
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
for name in variants:measure('warmup/'+name,name)
for i in range(5):
 for name in (list(variants) if i%2==0 else list(reversed(variants))):measure(f'warm/{name}-{i}',name)
summary={name:{'samples_seconds':[r['seconds'] for r in rows if r['variant']==name and r['label'].startswith('warm/')], 'median_seconds':statistics.median(r['seconds'] for r in rows if r['variant']==name and r['label'].startswith('warm/'))} for name in variants}
(base/'warm-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
for i in range(2):
 edits=base/f'invalidation-{i}';(edits/'warmup/original').mkdir(parents=True)
 (edits/'warmup/original/run-0.out').write_bytes(expected)
 s=Path('/tmp/collections-perf/committed/greetings/invalidate.py').read_text()
 s=s.replace("base=Path('/tmp/collections-perf/committed/greetings')",'base=Path('+repr(str(edits))+')')
 s=s.replace('/tmp/collections-perf/untouched-pr/dagger',cli)
 s=s.replace('dagger-engine.collections-committed-original-0',variants['committed']['engine']).replace('dagger-engine.collections-committed-candidate-0',variants['syntax-cache']['engine'])
 s=s.replace('/tmp/collections-perf/committed/greetings/warm-workspace-original',str(ws)).replace('/tmp/collections-perf/committed/greetings/warm-workspace-candidate',str(ws))
 script=edits/'run.py';script.write_text(s)
 subprocess.run([sys.executable,str(script)],check=True)
for name in variants:measure('profile/'+name,name,True)
print('All isolated cold/warm/invalidation/profile measurements complete.',flush=True)
