from pathlib import Path
import subprocess,os,json,time,hashlib,statistics,urllib.request,argparse
B=Path('/tmp/collections-perf/sdk-edit-audit/typedef-bulk');logs=B/'measurements';logs.mkdir(exist_ok=True)
app=Path('/tmp/collections-perf/sdk-edit-audit/ts-static/greetings');cli='/tmp/collections-perf/rebase-main/dagger'
variants={'control':('dagger-engine.collections-disk-abba-2',6172),'bulk':('dagger-engine.collections-disk-abba-1',6171)}
env=dict(os.environ)
for k in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN']:env.pop(k,None)
want=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
def docker(*args):return subprocess.run(['docker',*args],check=True,capture_output=True)
def start(label,binary=None):
 name,port=variants[label]
 docker('stop',name)
 if binary:docker('cp',str(binary),name+':/usr/local/bin/dagger-engine')
 docker('start',name)
 for _ in range(300):
  try:
   urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1).close();break
  except OSError:time.sleep(.1)
 else:raise RuntimeError('engine did not become ready')
rows=[]
def run(label,case,args=None,profile=False):
 name,port=variants[label];args=args or ['check','-l','--all']
 if profile:
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump',timeout=30).read()
  except urllib.error.HTTPError as e:
   if e.code!=503:raise
 command=[cli,'--engine','container://'+name]+(['--profile'] if profile else [])+args
 before=Path('/proc/pressure/io').read_text();started=time.monotonic()
 p=subprocess.run(command,cwd=app,env=env,capture_output=True);seconds=time.monotonic()-started
 (logs/f'{case}-{label}.out').write_bytes(p.stdout);(logs/f'{case}-{label}.err').write_bytes(p.stderr)
 correct=p.returncode==0 and (args!=['check','-l','--all'] or p.stdout==want)
 row={'variant':label,'case':case,'seconds':seconds,'exit':p.returncode,'correct':correct,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'io_before':before,'io_after':Path('/proc/pressure/io').read_text()}
 rows.append(row);(logs/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:v for k,v in row.items() if not k.startswith('io_')}),flush=True)
 if not correct:raise RuntimeError('failed '+case+' '+label)
 if profile:
  (logs/f'{case}-{label}.wcprof').write_bytes(urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump',timeout=30).read())
 return p.stdout
start('bulk',B/'engine');start('control')
manifest={}
for label,binary in [('control',Path('/tmp/collections-perf/sdk-edit-audit/ts-static/engine')),('bulk',B/'engine')]:
 name,port=variants[label];meta=json.loads(docker('inspect',name).stdout)[0]
 manifest[label]={'container':name,'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'inside_sha256':docker('exec',name,'sha256sum','/usr/local/bin/dagger-engine').stdout.decode().split()[0],'image':meta['Image'],'sdk_manifest':[v for v in meta['Config']['Env'] if v.startswith('DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST=')],'artifact_batch':'c12a34663b'}
 assert manifest[label]['sha256']==manifest[label]['inside_sha256']
(B/'engine-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for call in ['source','build']:
 outputs={label:run(label,'call-'+call,['-m','.dagger/modules/frontend','call',call,'entries']) for label in variants}
 assert outputs['control']==outputs['bulk']
for i in range(-2,8):
 labels=list(variants)
 if i%2:labels.reverse()
 for label in labels:run(label,'warm-'+str(i))
summary={label:{'median':statistics.median(v:=[r['seconds'] for r in rows if r['variant']==label and r['case'].startswith('warm-') and not r['case'].startswith('warm--')]),'min':min(v),'max':max(v),'n':len(v)} for label in variants}
(logs/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
for label in variants:run(label,'profile',profile=True)
# Diagnostic code is separately built and never included in unprofiled pairs.
start('bulk',B/'engine-profile')
run('bulk','diagnostic-warmup')
run('bulk','diagnostic',profile=True)
# Leave a normal candidate binary running for real integration/call checks.
start('bulk',B/'engine')
print('TIMING_DONE',flush=True)
