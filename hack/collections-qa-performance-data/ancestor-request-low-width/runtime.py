"""Prepare-only:12 LOCAL commands against one new ignored low-width fixture.

Per variant: ordinary full check-list primer, three ordinary warm repetitions,
a second full primer and one identical profiled command. Same new path on both.
One retained owned engine, frozen v1Linux binaries, original restored finally.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,resource,shutil,signal,subprocess,sys,threading,time,uuid
HERE=Path(__file__).resolve().parent;REPO=Path('/home/dagger/dag');LAB=Path('/tmp/collections-perf/engine-allocation-round2');SOURCE=LAB/'greetings'
sys.path.insert(0,str(LAB));import experiment as x
spec=importlib.util.spec_from_file_location('navigation',LAB/'navigation-generate.py');nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
MANIFEST=Path('/tmp/collections-perf/ancestor-request-runtime-v1/frozen-builds.json');OWNER='collections-lazy-core-runtime-v1';ORIGINAL='56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12'
CAP=12;MIN_FREE=16*1024**3;MAX_WRITE=8*1024**3

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:
  print(json.dumps({'run':False,'command_cap':CAP,'cloud_commands':0,'per_variant':{'full_primers':2,'ordinary_warm_samples':3,'profiles':1},'fixture':'New exact public source copy beneath ignored repo/bin/collections-parent-lowwidth-UUID/greetings, own Git boundary; one path shared by both variants','engine':'Existing owned retained engine; stopped-only binary swaps; original restored/stopped','cleanup':'Remove only new UUID copy after verifying owner marker; original greeting fixture untouched','scope':'Fixed baseline then candidate; low parent width, retained cache, no cold/Cloud/service claims'}));return
 os.umask(0o077);out=HERE/'results-v1';assert not out.exists()
 build=json.loads(MANIFEST.read_text());assert build['baseline']['cli']['sha256']=='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30';assert build['source_head']=='85b60f7a0a16a27459ef571bc94bcf870c876dcc'
 assert x.sha(build['parent_manifest_path'])==build['parent_manifest_sha256'] and x.sha(build['recipe_path'])==build['recipe_sha256']
 for v in ('baseline','candidate'):
  for role in ('cli','engine'):assert x.sha(build[v][role]['path'])==build[v][role]['sha256']
 expected=x.fixture_hashes(SOURCE);assert expected==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
 wanted=(REPO/'hack/collections-qa-performance-data/expected-checks.txt').read_bytes();assert len(wanted.splitlines())==14
 original=json.loads((LAB/'lazy-core-runtime-v1/engines.json').read_text())['lazy'];assert original['sha256']==ORIGINAL;x.OWNER=OWNER
 info=x.owned(original);assert not info['State']['Running'];mounts=[m for m in info['Mounts']if m['Destination']=='/var/lib/dagger'];assert len(mounts)==1 and mounts[0]['Type']=='volume'and mounts[0]['Name']==original['name'];vol=json.loads(x.capture(['docker','volume','inspect',mounts[0]['Name']]))[0];assert vol['Labels']['dagger.perf.owner']==OWNER
 nonce=uuid.uuid4().hex;copyroot=REPO/'bin'/('collections-parent-lowwidth-'+nonce);app=copyroot/'greetings';marker=copyroot/'owner.json';assert copyroot.parent.is_dir() and not copyroot.exists()
 subprocess.run(['git','check-ignore','-q',str(app/'dagger.toml')],cwd=REPO,check=True)
 out.mkdir();(out/'empty-config').mkdir();(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 env={k:os.environ[k]for k in ('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(XDG_CONFIG_HOME=str(out/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
 assert not any(k in env for k in ('DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','OTEL_EXPORTER_OTLP_ENDPOINT','HTTP_PROXY','HTTPS_PROXY'))
 git_env=dict(env,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null');rows=[];attempts=[];starts=[];item=dict(original);backup=out/'original-engine.private';modified=False;created=False;written=0
 ownership={'owner':'collections-parent-lowwidth-v1','nonce':nonce,'source_hashes_sha256':hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest()}
 def guard():
  assert x.fixture_hashes(SOURCE)==expected and x.fixture_hashes(app)==expected,'fixture mutated';assert marker.read_text()==json.dumps(ownership,sort_keys=True)+'\n'
  assert shutil.disk_usage(HERE).free>MIN_FREE and written<MAX_WRITE
 def widths():return [{'path':str(p),'entries':len(list(p.iterdir()))}for p in reversed([app,*app.parents])]
 def run(variant,phase,repetition=0,profile=False):
  nonlocal written
  guard();assert len(attempts)<CAP;dest=out/f'{len(attempts):02d}-{variant}-{phase}';dest.mkdir()
  row={'variant':variant,'phase':phase,'repetition':repetition,'profile':profile};attempts.append(dict(row));x.write(out/'attempts.json',attempts)
  if profile:
   try:(dest/'prior.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
   except x.HTTPError as e:
    if e.code!=503:raise
  command=[build[variant]['cli']['path'],'--engine','container://'+item['name']]+(['--profile']if profile else[])+['check','-l','--all']
  before=nav.warm.snapshot(item);cpu0=resource.getrusage(resource.RUSAGE_CHILDREN);done=threading.Event();obs={}
  with(dest/'stdout.private').open('wb')as stdout,(dest/'stderr.private').open('wb')as stderr:
   begin=time.monotonic();wall=time.time_ns();proc=subprocess.Popen(command,cwd=app,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   def wait():obs.update(code=proc.wait(),end=time.monotonic(),wall=time.time_ns());done.set()
   worker=threading.Thread(target=wait,daemon=True);worker.start()
   try:timeout=not done.wait(180)
   finally:
    if not done.is_set():
     try:proc.send_signal(signal.SIGINT)
     except ProcessLookupError:pass
     if not done.wait(10):
      try:os.killpg(proc.pid,signal.SIGKILL)
      except ProcessLookupError:pass
    worker.join(15);assert not worker.is_alive()
  cpu1=resource.getrusage(resource.RUSAGE_CHILDREN);delta=nav.warm.delta(before,nav.warm.snapshot(item));written+=delta['engine_written_bytes'];stdout=(dest/'stdout.private').read_bytes();stderr=(dest/'stderr.private').read_bytes()
  links=re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*',stdout+b'\n'+stderr);unexpected=any(u.rstrip(b'.')!=b'https://dagger.cloud/traces/setup'for u in links)
  correct=obs['code']==0 and not timeout and not unexpected and stdout==wanted
  row.update(seconds=obs['end']-begin,started_unix_ns=wall,exited_unix_ns=obs['wall'],exit_code=obs['code'],timed_out=timeout,correct=correct,stdout_sha256=x.sha(dest/'stdout.private'),stdout_rows=len(stdout.splitlines()),unexpected_cloud_link=unexpected,process_tree_user_seconds=cpu1.ru_utime-cpu0.ru_utime,process_tree_system_seconds=cpu1.ru_stime-cpu0.ru_stime,**delta)
  if profile:(dest/'run.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'));row['profile_sha256']=x.sha(dest/'run.wcprof.private')
  rows.append(row);x.write(out/'results.json',rows);print(json.dumps({k:row[k]for k in ('variant','phase','seconds','correct')}),flush=True);assert correct,'correctness failed: '+dest.name;guard()
 try:
  copyroot.mkdir();created=True;marker.write_text(json.dumps(ownership,sort_keys=True)+'\n');shutil.copytree(SOURCE,app,symlinks=True,ignore=shutil.ignore_patterns('.git','node_modules'))
  assert x.fixture_hashes(app)==expected
  git=['git','-C',str(app),'-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false','-c','user.name=Collections Perf Fixture','-c','user.email=fixture@example.invalid']
  for args in (['init','-q'],['add','--force','--all'],['commit','-q','-m','Public greetings performance fixture'],['remote','add','origin','https://github.com/kpenfound/greetings-api']):subprocess.run(git+args,env=git_env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  guard();assert Path(subprocess.check_output(git+['rev-parse','--show-toplevel'],env=git_env,text=True).strip())==app
  x.write(out/'provenance.json',{'build_manifest':build,'frozen_manifest_sha256':x.sha(MANIFEST),'driver_sha256':x.sha(__file__),'fixture_hashes':expected,'expected_stdout_sha256':hashlib.sha256(wanted).hexdigest(),'new_fixture_path':str(app),'parent_widths':widths(),'copy_scope':'Exact non-Git/non-node_modules public fixture bytes; fresh private Git boundary with synthetic local commit and same public origin; dagger.toml/lock/source unchanged. Both variants use this identical new path. Original source fixture never written.','commands_cap':CAP,'cloud_commands':0,'timing':'Blocking waitpid exit; snapshots, setup, copied fixture/git init, engine restarts and profiles excluded from ordinary samples.','order':['baseline','candidate'],'cache_boundary':'Retained engine volume, one restart per variant, explicit full-catalog primer before warm observations and another immediately before each profile. No fresh-volume cold. New path can invalidate source identity; primers counted.','limits':{'min_free_bytes':MIN_FREE,'max_measured_command_engine_written_bytes':MAX_WRITE},'measurement_scope':'n3 per variant, fixed block order; low-width representativeness check, not a variability estimate or universal500ms claim','engine':original,'owner':OWNER})
  x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(backup)]);assert x.sha(backup)==ORIGINAL
  for variant in ('baseline','candidate'):
   guard()
   if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
   assert not x.owned(item)['State']['Running'];modified=True;x.capture(['docker','cp',build[variant]['engine']['path'],item['name']+':/usr/local/bin/dagger-engine']);item=dict(original,sha256=build[variant]['engine']['sha256']);starts.append({'variant':variant,'startup_seconds_excluded':x.start(item)});x.write(out/'starts.json',starts)
   run(variant,'full-listing-primer')
   for rep in range(3):run(variant,'warm',rep)
   run(variant,'full-profile-primer');run(variant,'fully-primed-profile',profile=True)
 finally:
  if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
  restored=not modified
  if modified:
   assert x.sha(backup)==ORIGINAL;x.capture(['docker','cp',str(backup),item['name']+':/usr/local/bin/dagger-engine']);verify=out/'restored-engine.private';x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(verify)]);restored=x.sha(verify)==ORIGINAL
  untouched=x.fixture_hashes(SOURCE)==expected;copy_unchanged=not created or not app.exists()or x.fixture_hashes(app)==expected
  if created:
   assert copyroot.parent==REPO/'bin' and copyroot.name=='collections-parent-lowwidth-'+nonce and not copyroot.is_symlink() and marker.read_text()==json.dumps(ownership,sort_keys=True)+'\n';shutil.rmtree(copyroot)
  x.write(out/'restoration.json',{'original_fixture_untouched':untouched,'copied_fixture_unchanged_before_removal':copy_unchanged,'new_owned_copy_removed':not copyroot.exists(),'engine_original_restored':restored,'engine_stopped':not x.owned(item)['State']['Running'],'local_attempts':len(attempts),'validated_commands':sum(r['correct']for r in rows),'cloud_commands':0,'engine_written_bytes':written})
  assert untouched and copy_unchanged and restored and not copyroot.exists()
 assert len(rows)==CAP and all(r['correct']for r in rows)
if __name__=='__main__':main()
