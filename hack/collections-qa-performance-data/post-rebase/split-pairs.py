from pathlib import Path
import subprocess,os,time,json,hashlib,statistics,urllib.request
B=Path('/tmp/collections-perf/post-rebase-io');dest=B/'split-pairs';dest.mkdir(exist_ok=False)
repo=Path('/home/dagger/dag');ws='/tmp/collections-perf/normal-baseline/greetings-split';want=(repo/'hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
variants={
 'shared-512':('/tmp/collections-perf/rebase-main/dagger','dagger-engine.collections-disk-abba-2',6172),
 'split-512':('/tmp/collections-perf/rebase-main/dagger','dagger-engine.collections-disk-abba-1',6171),
}

env=dict(os.environ)
for k in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE']:env.pop(k,None)
def psi():return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=',1)[1])
rows=[]
try:
 for label,(cli,name,port) in variants.items():
  subprocess.run(['docker','start',name],check=True,capture_output=True)
  for _ in range(100):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1).close();break
   except OSError:time.sleep(.1)
 for i in range(-2,8):
  labels=list(variants)
  if i%2:labels.reverse()
  for label in labels:
   cli,name,port=variants[label];cmd=[cli,'--engine','container://'+name,'check','-l','--all']
   before=psi();start=time.monotonic();p=subprocess.run(cmd,cwd=ws,env=env,capture_output=True);elapsed=time.monotonic()-start;after=psi()
   (dest/f'{label}-{i}.out').write_bytes(p.stdout);(dest/f'{label}-{i}.err').write_bytes(p.stderr)
   row={'variant':label,'iteration':i,'seconds':elapsed,'host_io_full_seconds':(after-before)/1e6,'correct':p.returncode==0 and p.stdout==want,'status':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest()}
   rows.append(row);(dest/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
   assert row['correct'],row
 summary={label:{'median':statistics.median(v:=[r['seconds'] for r in rows if r['iteration']>=0 and r['variant']==label]),'min':min(v),'max':max(v),'n':len(v)} for label in variants}
 (dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
 for label,(cli,name,port) in variants.items():
  e=dict(env);e['CPUPROFILE']=str(dest/f'{label}.cpu')
  start=time.monotonic();p=subprocess.run([cli,'--engine','container://'+name,'--profile','check','-l','--all'],cwd=ws,env=e,capture_output=True);elapsed=time.monotonic()-start
  (dest/f'{label}-profile.err').write_bytes(p.stderr)
  assert p.returncode==0 and p.stdout==want,label
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump',timeout=60) as r:(dest/f'{label}.wcprof').write_bytes(r.read())
  print(json.dumps({'profile':label,'seconds':elapsed}),flush=True)
finally:
 for cli,name,port in variants.values():subprocess.run(['docker','stop','--timeout','30',name],capture_output=True)
