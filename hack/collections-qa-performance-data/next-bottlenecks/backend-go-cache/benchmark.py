#!/usr/bin/env python3
"""Compare ordinary fresh edit->check with backend Go cache mounts. No runs by default."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, statistics, subprocess, time, urllib.error, urllib.request
LAB=Path(__file__).parent
SOURCE=Path('/tmp/collections-perf/execution-first/workspace/greetings-api')
ENGINE='dagger-engine.collections-disk-abba-2'
CLI='/tmp/collections-perf/rebase-main/dagger'
BACKEND='.dagger/modules/backend/main.go'
SENTINEL='backend-cache-api-sentinel'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');ap.add_argument('--output',type=Path,default=LAB/'measured');ap.add_argument('--engine',default=ENGINE);ap.add_argument('--profile-port',type=int,default=6172);args=ap.parse_args()
 if not args.run:
  print(json.dumps({'status':'prepared only','boundary':'retained engine, fresh dedicated compiler caches; ordinary check command; 5 alternating fresh edit pairs; API sentinel must fail, then restore and six tests pass','source':str(SOURCE),'output':str(args.output)},indent=2));return
 out=args.output;out.mkdir(parents=True,exist_ok=False)
 assert subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',args.engine],text=True).strip()=='true','caller must reserve and start engine'
 before=(LAB/'main.before.go').read_bytes();after=(LAB/'main.after.go').read_bytes();assert (SOURCE/BACKEND).read_bytes()==before
 originals={p:(SOURCE/p).read_bytes() for p in ('main.go','main_test.go','e2e_test.go','dagger.toml','dagger.lock',BACKEND)}
 apps={}
 for variant in ('control','cache'):
  app=out/variant/'greetings-api';shutil.copytree(SOURCE,app,symlinks=True);apps[variant]=app
  if variant=='cache':(app/BACKEND).write_bytes(after)
 env=dict(os.environ)
 for key in ('SSH_AUTH_SOCK','CPUPROFILE','DAGGER_PERF_TIMELINE','DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','_DAGGER_CLI_TIMING_DIAG','DAGGER_CLOUD_BATCH_DIAGNOSTICS'):env.pop(key,None)
 rows=[]
 (out/'manifest.json').write_text(json.dumps({'cli':CLI,'cli_sha256':sha(Path(CLI).read_bytes()),'engine':args.engine,'source':str(SOURCE),'source_hashes':{p:sha(b) for p,b in originals.items()},'candidate_sha256':sha(after),'cache_names':['backend-edit-20260925-go-mod','backend-edit-20260925-go-build'],'cache_state':'retained engine; candidate uses dedicated never-before-used cache volume names, initial fill timed separately; not cold engine','root_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd='/home/dagger/dag',text=True).strip()},indent=2)+'\n')
 def pressure():return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=',1)[1])
 def dump(path,allow=False):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{args.profile_port}/debug/wcprof/dump?flush=true',timeout=20) as f:path.write_bytes(f.read())
  except urllib.error.HTTPError as err:
   if not (allow and err.code==503):raise
 def run(variant,label,tests=('TestSelectGreeting','TestFormatResponse'),profile=False,fail=False,require_six=False):
  dest=out/label;dest.mkdir(parents=True,exist_ok=False)
  cmd=[CLI,'--engine','container://'+args.engine]
  if profile:cmd+=['--profile'];dump(dest/'prior.wcprof',True)
  cmd+=['check','--generated=false','go/modules/tests/run','--go-module=.']+['--go-test='+name for name in tests]
  io0=pressure();start=time.perf_counter();r=subprocess.run(cmd,cwd=apps[variant],env=env,capture_output=True,timeout=900);elapsed=time.perf_counter()-start;io1=pressure()
  (dest/'stdout.txt').write_bytes(r.stdout);(dest/'stderr.txt').write_bytes(r.stderr)
  text=re.sub(r'\x1b\[[0-9;]*m','',(r.stdout+r.stderr).decode(errors='replace'))
  row={'variant':variant,'label':label,'command':cmd,'seconds':elapsed,'exit_code':r.returncode,'profile':profile,'expected_failure':fail,'io_full_stall_seconds':(io1-io0)/1e6}
  rows.append(row);(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
  if profile:dump(dest/'run.wcprof')
  if fail:assert r.returncode!=0 and SENTINEL in text,(row,text[-4000:])
  else:
   assert r.returncode==0 and re.search(r'== CHECKS ==.*\b1 passed\b',text),(row,text[-4000:])
   if require_six:assert re.search(r'\b6 passed\b',text) and not re.search(r'\b[1-9][0-9]* skipped\b',text),(row,'need six executed passing tests and no skips',text[-4000:])
 try:
  run('control','initial/control')
  run('cache','initial/cache-first-fill')
  for i in range(2):
   for variant in apps:run(variant,f'warmup/{i}-{variant}')
  for i in range(5):
   for variant in ('control','cache') if i%2==0 else ('cache','control'):run(variant,f'warm/{i}-{variant}')
  for i in range(5):
   edit=originals['main.go']+f'\n// Backend cache benchmark fresh edit {i}.\n'.encode()
   for variant in apps:(apps[variant]/'main.go').write_bytes(edit)
   for variant in ('control','cache') if i%2==0 else ('cache','control'):run(variant,f'edits/{i}-{variant}')
  # Distinct content forces a real build/test on each side, separate from timings.
  for variant in apps:
   (apps[variant]/'main.go').write_bytes(originals['main.go']+b'\n// Backend cache profiling fresh edit.\n')
   run(variant,f'profiles/edit-{variant}',profile=True)
  # A server behavior change must reach actual HTTP tests, not a cached binary.
  needle=b'greeting.Greeting)';assert originals['main.go'].count(needle)==1
  for variant in apps:
   (apps[variant]/'main.go').write_bytes(originals['main.go'].replace(needle,b'greeting.Greeting+"-'+SENTINEL.encode()+b'")'))
   run(variant,f'correctness/{variant}-api-sentinel',tests=('TestE2EGreetingByLanguage',),fail=True)
   (apps[variant]/'main.go').write_bytes(originals['main.go']+b'\n// Backend cache correctness restored behavior.\n')
   run(variant,f'correctness/{variant}-restored-full',tests=(),require_six=True)
  summary={phase:{variant:{'median_seconds':statistics.median(values:=[r['seconds'] for r in rows if r['variant']==variant and r['label'].startswith(phase+'/')]),'samples':values} for variant in apps} for phase in ('warm','edits')}
  (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
 finally:
  # Preserve the candidate patch, restore only edited app source in the copies.
  for app in apps.values():(app/'main.go').write_bytes(originals['main.go'])
  restored={'original_unchanged':{p:(SOURCE/p).read_bytes()==b for p,b in originals.items()},'isolated_source_restored':{variant:(app/'main.go').read_bytes()==originals['main.go'] for variant,app in apps.items()}}
  (out/'restoration.json').write_text(json.dumps(restored,indent=2)+'\n');assert all(all(v.values()) for v in restored.values()),restored

if __name__=='__main__':main()
