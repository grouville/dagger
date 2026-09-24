from pathlib import Path
import subprocess,shutil,socket,time,os,json,statistics,sys,hashlib
base=Path('/tmp/collections-perf/committed/greetings');base.mkdir(parents=True,exist_ok=True)
runner='/home/dagger/dag/hack/bench-artifact-discovery.py'
expected=Path('/tmp/collections-perf/greetings/original-first-use/run-0.out').read_bytes()
os.environ.pop('SSH_AUTH_SOCK',None)
variants={
 'original':{'cli':'/tmp/collections-perf/untouched-pr/dagger','engine_binary':'/tmp/collections-perf/untouched-pr/engine','module':'/tmp/dagger-go-collections'},
 'candidate':{'cli':'/tmp/collections-perf/committed/dagger','engine_binary':'/tmp/collections-perf/committed/engine','module':'/tmp/dagger-go-discovery'},
}
for name,v in variants.items():
 for mode in ['warm','cold']:
  ws=base/(mode+'-workspace-'+name)
  assert not ws.exists(),str(ws)+' already exists'
  subprocess.run(['git','clone','--quiet','--no-local','/tmp/greetings-api-collections-perf',str(ws)],check=True,capture_output=True)
  subprocess.run(['git','-C',str(ws),'remote','set-url','origin','https://github.com/kpenfound/greetings-api.git'],check=True)
  shutil.copy2('/tmp/greetings-api-collections-perf/dagger.lock',ws/'dagger.lock')
  if name=='candidate' or mode=='cold':
   config=ws/'dagger.toml';config.write_text(config.read_text().replace('source = "github.com/dagger/go@collections"','source = "'+v['module']+'"'))
  v[mode+'_ws']=str(ws)
def start(name,v,port):
 for kind in ['container','volume']:
  assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0, name+' exists'
 subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','localhost/dagger-engine.collections-perf:latest','--extra-debug','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['docker','cp',v['engine_binary'],name+':/usr/local/bin/dagger-engine'],check=True)
 subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
 deadline=time.monotonic()+30
 while True:
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=1):break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.1)
def stop(name):subprocess.run(['docker','stop',name],check=True,stdout=subprocess.DEVNULL)
def measure(label,v,engine,ws,profile_port=None):
 dest=base/label
 args=[sys.executable,runner,'--runs','1','--warmups','0','--timeout','600','--output',str(dest)]
 if profile_port:args+=['--wcprof-url',f'http://127.0.0.1:{profile_port}']
 args+=['--',v['cli'],'--engine','container://'+engine,'check','-l','--all']
 p=subprocess.run(args,cwd=ws,capture_output=True,text=True)
 (dest/'driver.log').write_text(p.stdout+p.stderr);p.check_returncode()
 output=(dest/'run-0.out').read_bytes();assert output==expected,label+' differs'
 results=json.loads((dest/'results.json').read_text())
 row={'label':label,'seconds':results['median_seconds'],'rows':len(output.splitlines()),'correct':True,'sha256':hashlib.sha256(output).hexdigest()}
 print(json.dumps(row),flush=True)
 if profile_port:
  with (dest/'analysis.txt').open('w') as f:subprocess.run(['/tmp/wcprof-analyze','-top','60',str(dest/'runs.wcprof')],stdout=f,check=True)
 return row
cold=[]
for round_index,order in enumerate([['original','candidate'],['candidate','original']]):
 for name in order:
  v=variants[name];port=6090+len(cold);engine=f'dagger-engine.collections-committed-{name}-{round_index}'
  print('Starting empty-cache sample '+engine,flush=True);start(engine,v,port)
  try:
   row=measure(f'cold/{name}-{round_index}',v,engine,v['cold_ws']);row.update({'variant':name,'round':round_index,'engine':engine});cold.append(row)
   (base/'cold-summary.json').write_text(json.dumps(cold,indent=2)+'\n')
   if round_index==0:v['engine']=engine;v['port']=port
  except:
   stop(engine);raise
  if round_index!=0:stop(engine)
# Keep round-zero engines running for warm measurements and validation.
for name,v in variants.items():measure('warmup/'+name,v,v['engine'],v['warm_ws'])
# Same remote module/config as original, but committed engine/CLI.
variants['engine-only']={**variants['candidate'],'warm_ws':variants['original']['warm_ws']}
v=variants['engine-only'];measure('warmup/engine-only',v,v['engine'],v['warm_ws'])
warm=[]
for i in range(5):
 order=['original','engine-only','candidate'];order=order[i%3:]+order[:i%3]
 for name in order:
  v=variants[name];row=measure(f'warm/{name}-{i}',v,v['engine'],v['warm_ws']);row['variant']=name;warm.append(row)
  summary={'rows':warm,'complete_output_matches':True,'variants':{n:{'samples_seconds':[r['seconds'] for r in warm if r['variant']==n],'median_seconds':statistics.median(r['seconds'] for r in warm if r['variant']==n)} for n in variants if any(r['variant']==n for r in warm)}}
  (base/'warm-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for name in ['original','candidate']:
 v=variants[name];measure('profile-'+name,v,v['engine'],v['warm_ws'],v['port'])
(base/'variants.json').write_text(json.dumps(variants,indent=2)+'\n')
# Reuse the already-reviewed real-edit oracle, changing only lab paths.
s=Path('/tmp/collections-perf/greetings/invalidate.py').read_text()
s=s.replace("base=Path('/tmp/collections-perf/greetings')",'base=Path('+repr(str(base))+')')
s=s.replace("(base/'original-first-use/run-0.out')","(base/'warmup/original/run-0.out')")
s=s.replace('/tmp/collections-perf/dagger-pinned-discovery',variants['candidate']['cli'])
s=s.replace('dagger-engine.collections-untouched',variants['original']['engine']).replace('dagger-engine.collections-profile-stack',variants['candidate']['engine'])
s=s.replace('/tmp/greetings-api-collections-perf',variants['original']['warm_ws']).replace('/tmp/greetings-api-optimized-perf',variants['candidate']['warm_ws']).replace('full-stack','candidate')
(base/'invalidate.py').write_text(s)
subprocess.run([sys.executable,str(base/'invalidate.py')],check=True)
print('Committed cold/warm/profile/edit measurements complete.',flush=True)
