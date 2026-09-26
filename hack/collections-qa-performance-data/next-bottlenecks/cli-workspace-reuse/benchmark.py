from pathlib import Path
import subprocess,os,time,json,hashlib,statistics,urllib.request,urllib.error,itertools,socket
lab=Path('/tmp/collections-perf/warm-audit/list-workspace-reuse');out=lab/'measured';out.mkdir(exist_ok=False)
ws=Path('/tmp/collections-perf/sdk-edit-audit/ts-static/greetings')
engine='dagger-engine.collections-disk-abba-2';port=6172
clis={'baseline':'/tmp/collections-perf/rebase-main/dagger','prefix':str(lab/'dagger-prefix'),'reuse':str(lab/'dagger-prefix-reuse')}
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
env=dict(os.environ)
for key in ('SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','_DAGGER_CLI_TIMING_DIAG','DAGGER_CLOUD_BATCH_DIAGNOSTICS'):env.pop(key,None)
rows=[];canonical=None
sources={p:hashlib.sha256((ws/p).read_bytes()).hexdigest() for p in ('main.go','main_test.go','dagger.toml')}
def normalized(data):return sorted(tuple(p.strip() for p in line.split('#',1)) for line in data.decode().splitlines() if line.strip())
def psi():return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=',1)[1])
def dump(path,allow=False):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump?flush=true',timeout=20) as f:path.write_bytes(f.read())
 except urllib.error.HTTPError as err:
  if not (allow and err.code==503):raise

def run(variant,label,filtered=False,profile=False):
 global canonical
 dest=out/label;dest.mkdir(parents=True,exist_ok=False)
 if profile:dump(dest/'prior.wcprof',True)
 cmd=[clis[variant],'--engine','container://'+engine]
 if profile:cmd+=['--profile']
 cmd+=['check','-l','--all']
 if filtered:cmd+=['go/modules/tests/run','--go-module=.','--go-test=TestFormatResponse']
 before=psi();start=time.perf_counter();p=subprocess.run(cmd,cwd=ws,env=env,capture_output=True,timeout=300);elapsed=time.perf_counter()-start;after=psi()
 (dest/'stdout.txt').write_bytes(p.stdout);(dest/'stderr.txt').write_bytes(p.stderr)
 want=b'\n'.join(line for line in expected.splitlines() if b'--go-test=TestFormatResponse ' in line)+b'\n' if filtered else expected
 correct=p.returncode==0 and normalized(p.stdout)==normalized(want)
 if not filtered:
  if canonical is None:canonical=p.stdout
  correct=correct and p.stdout==canonical
 row={'variant':variant,'case':label,'seconds':elapsed,'status':p.returncode,'correct':correct,'filtered':filtered,'profile':profile,'rows':len(p.stdout.splitlines()),'sha256':hashlib.sha256(p.stdout).hexdigest(),'io_full_stall_seconds':(after-before)/1e6}
 rows.append(row);(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 if profile:dump(dest/'run.wcprof')
 assert correct,(row,p.stderr[-1200:])

manifest={'clis':{k:{'path':v,'sha256':hashlib.sha256(Path(v).read_bytes()).hexdigest()} for k,v in clis.items()},'engine':engine,'engine_manifest':json.loads(Path('/tmp/collections-perf/sdk-edit-audit/ts-static/engine-manifest.json').read_text()),'workspace':str(ws),'source_hashes':sources,'expected_semantics_sha256':hashlib.sha256(expected).hexdigest(),'boundary':'fresh full CLI processes; direct ordinary Cloud telemetry; same retained static-TS engine; two warmups per CLI; eight matched triples; separate profiles and filtered correctness','root_cli_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd='/home/dagger/dag',text=True).strip()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
started=False
try:
 running=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',engine],text=True).strip()=='true'
 if not running:subprocess.run(['docker','start',engine],stdout=subprocess.DEVNULL,check=True);started=True
 deadline=time.monotonic()+30
 while True:
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=1):break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.1)
 for n in range(2):
  for variant in clis:run(variant,f'warmup/{n}-{variant}')
 orders=list(itertools.permutations(clis))
 for n in range(8):
  for variant in orders[n%len(orders)]:run(variant,f'warm/{n}-{variant}')
 for variant in clis:run(variant,f'filtered/{variant}',filtered=True)
 for variant in ('baseline','reuse'):run(variant,f'profile/{variant}',profile=True)
 summary={variant:{'median_seconds':statistics.median(values:=[r['seconds'] for r in rows if r['variant']==variant and r['case'].startswith('warm/')]),'range_seconds':[min(values),max(values)],'samples':values} for variant in clis}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
finally:
 unchanged={p:hashlib.sha256((ws/p).read_bytes()).hexdigest()==s for p,s in sources.items()}
 (out/'restoration.json').write_text(json.dumps(unchanged,indent=2)+'\n')
 subprocess.run(['docker','stop','--time','30',engine],stdout=subprocess.DEVNULL,check=False)
 assert all(unchanged.values()),unchanged
