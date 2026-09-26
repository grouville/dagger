from pathlib import Path
import os,sys,json,subprocess,time,hashlib,statistics,urllib.request,socket
B=Path('/tmp/collections-perf/warm-audit')
DEST=B/'measured'
CLI='/tmp/collections-perf/rebase-main/dagger'
ENGINE='dagger-engine.collections-disk-abba-2'
PORT=6172
EXPECTED=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
APPS={x:B/f'app-{x}' for x in ['before','after']}
ENV=dict(os.environ)
for key in ['SSH_AUTH_SOCK','CPUPROFILE','DAGGER_CLOUD_BATCH_DIAGNOSTICS']:
 ENV.pop(key,None)
ROWS=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def pressure():
 return {r.split()[0]:int(r.split()[-1].split('=')[1]) for r in Path('/proc/pressure/io').read_text().splitlines()}
def call(variant,label,expected=EXPECTED,profile=False):
 app=APPS[variant];out=DEST/label;out.mkdir(parents=True,exist_ok=False)
 cmd=[CLI,'--engine','container://'+ENGINE]
 if profile:cmd+=['--profile']
 cmd+=['check','-l','--all']
 before=pressure();start=time.perf_counter();p=subprocess.run(cmd,cwd=app,env=ENV,capture_output=True,timeout=300);seconds=time.perf_counter()-start;after=pressure()
 (out/'stdout.txt').write_bytes(p.stdout);(out/'stderr.txt').write_bytes(p.stderr)
 assert p.returncode==0,(label,p.returncode,p.stderr[-200:])
 assert p.stdout==expected,(label,'listing mismatch',sha(p.stdout),sha(expected))
 row={'variant':variant,'label':label,'seconds':seconds,'rows':len(p.stdout.splitlines()),'sha256':sha(p.stdout),'io_full_stall_seconds':(after['full']-before['full'])/1e6,'profile':profile}
 ROWS.append(row);(DEST/'results.json').write_text(json.dumps(ROWS,indent=2)+'\n');print(json.dumps(row),flush=True)
 if profile:
  with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/debug/wcprof/dump?flush=true') as f:(out/'runs.wcprof').write_bytes(f.read())
  with (out/'wcprof.txt').open('w') as f:subprocess.run(['/tmp/wcprof-analyze','-top','50',str(out/'runs.wcprof')],stdout=f,check=True)
 return row
DEST.mkdir(exist_ok=False)
provenance={'cli':CLI,'engine':ENGINE,'engine_port':PORT,'benchmark':'real new-process dagger check -l --all, telemetry enabled, exit included','app_base':'14d684fccf75a137de96f3f0c7eb8c6dafef2d3e','module_base':'1784ff37eb3dd1aacab7aaff91b1d86e311cc8de','constraint':'Both variants replace only modules.go with local source directories. Absolute timings are not directly comparable to the untouched remote-module2.662s. Complete experimental engine/SDK stack remains active.','source_patch_sha256':sha((B/'module-cwd.patch').read_bytes()),'expected_sha256':sha(EXPECTED),'apps':{k:str(v) for k,v in APPS.items()}}
(DEST/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
started=False;original={k:(v/'main_test.go').read_bytes() for k,v in APPS.items()}
try:
 running=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',ENGINE],text=True).strip()=='true'
 if not running:subprocess.run(['docker','start',ENGINE],stdout=subprocess.DEVNULL,check=True);started=True
 deadline=time.monotonic()+30
 while True:
  try:
   with socket.create_connection(('127.0.0.1',PORT),timeout=1):break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.1)
 for n in range(2):
  for k in APPS:call(k,f'warmup/{k}-{n}')
 for n in range(8):
  for k in (list(APPS) if n%2==0 else list(reversed(APPS))):call(k,f'warm/{k}-{n}')
 summary={k:{'median_seconds':statistics.median(r['seconds'] for r in ROWS if r['variant']==k and r['label'].startswith('warm/')),'samples_seconds':[r['seconds'] for r in ROWS if r['variant']==k and r['label'].startswith('warm/')]} for k in APPS}
 (DEST/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
 edits=[('comment',lambda b:b+b'\n// discovery cwd benchmark edit\n',EXPECTED),('rename',lambda b:b.replace(b'TestFormatResponse',b'TestFormatResponze'),EXPECTED.replace(b'TestFormatResponse',b'TestFormatResponze')),('restore',lambda b:b,EXPECTED)]
 for n,(label,edit,expected) in enumerate(edits):
  for k in (list(APPS) if n%2==0 else list(reversed(APPS))):
   (APPS[k]/'main_test.go').write_bytes(edit(original[k]));call(k,f'edits/{label}/{k}',expected)
 for k in APPS:call(k,f'profile/{k}',profile=True)
 module=B/'module-after';cmd=[CLI,'--engine','container://'+ENGINE,'check','-m',str(module/'gomod/.dagger/modules/e2e'),'--generated=false','discovery-check','lookup-check']
 start=time.perf_counter();p=subprocess.run(cmd,cwd=module,env=ENV,capture_output=True,timeout=600);seconds=time.perf_counter()-start
 (DEST/'qa.stdout').write_bytes(p.stdout);(DEST/'qa.stderr').write_bytes(p.stderr)
 (DEST/'qa.json').write_text(json.dumps({'command':cmd,'seconds':seconds,'exit_code':p.returncode},indent=2)+'\n');p.check_returncode();print('Nested cwd discovery and lookup checks passed',flush=True)
finally:
 for k,v in APPS.items():(v/'main_test.go').write_bytes(original[k])
 if started:subprocess.run(['docker','stop','--time','30',ENGINE],stdout=subprocess.DEVNULL,check=False)
