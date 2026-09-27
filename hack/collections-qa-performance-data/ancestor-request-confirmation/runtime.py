"""Prepared LOCAL-only54-command confirmation of explicit parent metadata.

Four ABBA blocks,3/3/2/2 repetitions per flow:40 ordinary observations,
12 counted primers,2 mixed CLI/engine compatibility checks. No profiles,
Cloud, fresh-volume cold or service-up test. Same frozen binaries/volume.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, re, resource, shutil, signal, subprocess, sys, threading, time, uuid
HERE=Path(__file__).resolve().parent;LAB=Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0,str(LAB));import experiment as x
spec=importlib.util.spec_from_file_location('navigation',LAB/'navigation-generate.py');nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
OWNER='collections-lazy-core-runtime-v1';ORIGINAL='56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12'
BASE_ENGINE='f864931c4dab6c53f7a1b552eace782eaf925e4dfa600bd5aa57a0099cb5189b';BASE_CLI='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
CAP=54;MIN_FREE=16*1024**3;MAX_WRITE=8*1024**3
FLOWS={
 'core':['-m','core','api','call','version'],
 'ws':['ws','ls'],
 'artifacts':['list','-a'],
 'checks':['check','-l','--all'],
 'generators':['generate','-l'],
 'call':['-m','./module','api','call','read'],
 'check':['check'],
 'generate':['-y','generate','render'],
 'export':['-m','core','api','call','host','file','--path','input.txt','export','--path','./exported.txt'],
 'greetings-check':['check','--generated=false','go/modules/tests/run','--go-module=.','--go-test=TestFormatResponse'],
}
ANSI=re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')
def digest(v):return hashlib.sha256(v).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--manifest',type=Path,default=Path('/tmp/collections-perf/ancestor-request-runtime-v1/frozen-builds.json'));p.add_argument('--output',default='results-v1');a=p.parse_args()
 assert re.fullmatch(r'results-v[0-9]+',a.output)
 if not a.run:
  print(json.dumps({'execute':False,'local_commands_cap':CAP,'cloud_commands':0,'blocks':['baseline','candidate','candidate','baseline'],'repetitions_per_block':[3,3,2,2],'ordinary_samples':40,'ordinary_flows':['warm list -a','warm check -l --all','distinct Dang comment then standard check','distinct input then native generate'],'samples_per_variant_per_flow':5,'counted_primers':12,'mixed_cli_engine_correctness_calls':2,'manifest_required':str(a.manifest),'not_tested':['fresh-volume cold','service up','Cloud overhead','SDK code generation'],'profiled_calls':0}));return
 os.umask(0o077);out=HERE/a.output;assert not out.exists();build=json.loads(a.manifest.read_text())
 assert build['original_baseline_engine_sha256']==BASE_ENGINE and build['baseline']['cli']['sha256']==BASE_CLI
 assert build['wcprof_marker']=='filesync.syncParentDirs' and build['source_head']=='85b60f7a0a16a27459ef571bc94bcf870c876dcc'
 assert x.sha(build['parent_manifest_path'])==build['parent_manifest_sha256'] and x.sha(build['recipe_path'])==build['recipe_sha256']
 assert build['candidate']['engine']['sha256']!=build['baseline']['engine']['sha256'] and build['candidate']['cli']['sha256']!=BASE_CLI
 for v in ('baseline','candidate'):
  for kind in ('engine','cli'):assert x.sha(build[v][kind]['path'])==build[v][kind]['sha256']
 original=json.loads((LAB/'lazy-core-runtime-v1/engines.json').read_text())['lazy'];assert original['sha256']==ORIGINAL;x.OWNER=OWNER
 info=x.owned(original);assert not info['State']['Running']
 mounts=[m for m in info['Mounts']if m['Destination']=='/var/lib/dagger'];assert len(mounts)==1 and mounts[0]['Type']=='volume' and mounts[0]['Name']==original['name']
 volume=json.loads(x.capture(['docker','volume','inspect',mounts[0]['Name']]))[0];assert volume['Labels']['dagger.perf.owner']==OWNER
 app=LAB/'greetings';native=LAB/'native';core=Path('/tmp/collections-perf/sdk-edit-audit/core-typeref-intern-v1/first-consumer-local-v1/workspace')
 roots={'app':app,'native':native,'core':core};initial={k:x.fixture_hashes(v)for k,v in roots.items()};assert initial['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
 originals={native/n:(native/n).read_bytes()if(native/n).exists()else None for n in ('input.txt','generated.txt','exported.txt','module/main.dang')};originals[app/'main.go']=(app/'main.go').read_bytes();assert originals[native/'input.txt'] is not None
 expected={k:dict(v)for k,v in initial.items()};expected_checks=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes();assert len(expected_checks.splitlines())==14
 out.mkdir();(out/'empty-config').mkdir();(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 env={k:os.environ[k]for k in ('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(XDG_CONFIG_HOME=str(out/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
 assert not any(k in env for k in ('DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','OTEL_EXPORTER_OTLP_ENDPOINT','HTTP_PROXY','HTTPS_PROXY'))
 rows=[];attempts=[];starts=[];goldens={};written=0;modified=False;item=dict(original);backup=out/'original-engine.private';nonce=uuid.uuid4().hex
 x.write(out/'provenance.json',{'build_manifest':build,'build_manifest_sha256':x.sha(a.manifest),'driver_sha256':x.sha(__file__),'fixtures_before':initial,'flows':FLOWS,'commands_cap':CAP,'cloud_commands':0,'owner':OWNER,'original_engine':original,'cache_boundary':'One retained volume, restart per ABBA block;3/3/2/2 ordinary repetitions and three explicit primers per block; no fresh-volume or host-page-cache claim','edit_boundary':'New UUID plus unique equal-length block/repetition/flow tags; each variant gets distinct never-evaluated bytes. Native call/generate edit only input; standard check edits only Dang source comment; greetings listing edits only main.go comment. Warm input/generated bytes reset together; edit generation starts from previous generated bytes','timing':'Popen through blocking waitpid recorded by dedicated waiter; file readiness polled5ms only when not already current; warm generate leaves current output untouched; export destination removed to prove actual output; guards/counters/restore/restart/profile downloads excluded','scope':'Four-flow confirmation only; native standard check includes normal generated checks. No selected Go check, profiles, service up or Cloud in this confirmation. Those checks are retained in the earlier72-command trial.','limits':{'min_free_bytes':MIN_FREE,'max_measured_command_engine_written_bytes':MAX_WRITE,'write_counter_scope':'Sum of CLI-bracketing engine I/O deltas; excludes engine start/stop and gaps. Free-disk floor checked independently before each command.'},'ambient_width_caveat':'The task host /tmp has accumulated thousands of entries; measure multiple synthetic widths separately, do not generalize this host saving to small user directories'})
 def put(root_name,name,data):
  path=roots[root_name]/name
  if data is None:path.unlink(missing_ok=True);expected[root_name].pop(name,None)
  else:
   if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
   expected[root_name][name]=digest(data)
 def reset():
  put('app','main.go',originals[app/'main.go'])
  put('native','input.txt',originals[native/'input.txt'])
  put('native','generated.txt',originals[native/'input.txt'])
  put('native','exported.txt',originals[native/'exported.txt'])
  put('native','module/main.dang',originals[native/'module/main.dang'])
 def guard():
  assert all(x.fixture_hashes(root)==expected[k]for k,root in roots.items()),'unexpected fixture mutation'
  assert shutil.disk_usage(HERE).free>MIN_FREE and written<MAX_WRITE,'disk budget reached'
 def restart(variant,block):
  nonlocal item,modified
  reset();guard()
  if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
  assert not x.owned(item)['State']['Running'];modified=True
  x.capture(['docker','cp',build[variant]['engine']['path'],item['name']+':/usr/local/bin/dagger-engine'])
  item=dict(original,sha256=build[variant]['engine']['sha256']);seconds=x.start(item);starts.append({'variant':variant,'block':block,'startup_seconds_excluded':seconds});x.write(out/'starts.json',starts)
 def run(variant,flow,phase,block,repetition=0,profile=False,fail=False,cli_variant=None):
  nonlocal written
  assert len(attempts)<CAP;reset()
  contents=originals[native/'input.txt']
  if phase=='fresh-edit':
   marker=f'ancestor-confirm-{nonce}-{block:02d}-{repetition:02d}-{flow:16}\n'.encode()
   if flow=='checks':put('app','main.go',originals[app/'main.go']+b'\n// '+marker)
   elif flow=='check':put('native','module/main.dang',originals[native/'module/main.dang']+b'\n# '+marker)
   else:contents=marker;put('native','input.txt',contents)
  if fail:contents=b'fail\n';put('native','input.txt',contents);put('native','generated.txt',contents)
  target=native/('generated.txt'if flow=='generate'else'exported.txt')if flow in ('generate','export')else None
  if flow=='export':put('native',target.name,None)
  output_already_current=bool(target is not None and target.exists() and target.read_bytes()==contents)
  guard();dest=out/f'{len(attempts):02d}-{block}-{phase}-{flow}-{variant}';dest.mkdir()
  cli_variant=cli_variant or variant
  attempt={'variant':variant,'engine_variant':variant,'cli_variant':cli_variant,'flow':flow,'phase':phase,'block':block,'repetition':repetition,'profile':profile,'expected_failure':fail,'input_sha256':digest(contents),'app_main_sha256':expected['app']['main.go'],'native_module_sha256':expected['native']['module/main.dang']};attempts.append(attempt);x.write(out/'attempts.json',attempts)
  if profile:
   try:(dest/'prior.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
   except x.HTTPError as e:
    if e.code!=503:raise
  cwd=core if flow=='core'else app if flow in ('ws','artifacts','checks','generators','greetings-check')else native
  command=[build[cli_variant]['cli']['path'],'--engine','container://'+item['name']]+(['--profile']if profile else[])+FLOWS[flow]
  before=nav.warm.snapshot(item);usage=resource.getrusage(resource.RUSAGE_CHILDREN);done=threading.Event();observed={};visible=None;polls=0
  with(dest/'stdout.private').open('wb')as stdout,(dest/'stderr.private').open('wb')as stderr:
   begin=time.monotonic();started=time.time_ns();proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   def wait():observed.update(code=proc.wait(),end=time.monotonic(),wall=time.time_ns());done.set()
   worker=threading.Thread(target=wait,daemon=True);worker.start()
   try:
    if target is not None and not output_already_current:
     while not done.is_set()and time.monotonic()-begin<180:
      polls+=1
      try:
       if target.read_bytes()==contents:visible=time.monotonic();break
      except FileNotFoundError:pass
      done.wait(.005)
    timed_out=not done.wait(max(0,180-(time.monotonic()-begin)))
   finally:
    if not done.is_set():
     try:proc.send_signal(signal.SIGINT)
     except ProcessLookupError:pass
     if not done.wait(10):
      try:os.killpg(proc.pid,signal.SIGKILL)
      except ProcessLookupError:pass
    worker.join(15);assert not worker.is_alive()
  cpu=resource.getrusage(resource.RUSAGE_CHILDREN);delta=nav.warm.delta(before,nav.warm.snapshot(item));written+=delta['engine_written_bytes']
  stdout=(dest/'stdout.private').read_bytes();stderr=(dest/'stderr.private').read_bytes();text=ANSI.sub(b'',stdout+b'\n'+stderr)
  links=re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*',text);unexpected_cloud=any(url.rstrip(b'.')!=b'https://dagger.cloud/traces/setup'for url in links)
  correct=not timed_out and not unexpected_cloud
  if fail:correct &= observed['code']!=0 and b'perf-flows correctness sentinel'in text
  else:
   correct &= observed['code']==0
   if flow=='core':correct &= stdout==b'v1.0.0-beta.15+85b60f7a.dirty'
   elif flow=='call':correct &= stdout==contents
   elif flow=='checks':correct &= stdout==expected_checks
   elif flow in ('ws','artifacts','generators'):
    kind='workspace-files'if flow=='ws'else flow;normalized=nav.normalize(stdout);correct &= nav.known_listing(kind,stdout)
    if flow not in goldens:assert variant=='baseline';goldens[flow]=normalized
    correct &= normalized==goldens[flow]
   elif flow=='check':correct &= bool(re.search(rb'\b[1-9][0-9]* passed\b',text)) and b' failed'not in text
   elif flow=='greetings-check':correct &= bool(re.search(rb'\b1 passed\b',text)) and b' failed'not in text
   elif target is not None:correct &= target.exists() and target.read_bytes()==contents
  if target is not None and target.exists():expected['native'][target.name]=x.sha(target)
  row=dict(attempt,seconds=observed['end']-begin,started_unix_ns=started,exited_unix_ns=observed['wall'],exit_code=observed['code'],timed_out=timed_out,correct=bool(correct),stdout_sha256=x.sha(dest/'stdout.private'),file_visible_seconds=visible-begin if visible is not None else None,output_already_current=output_already_current,file_visible_censored_at_exit=bool(target is not None and not output_already_current and visible is None and correct),file_poll_ms=5 if target else None,file_polls=polls,process_tree_user_seconds=cpu.ru_utime-usage.ru_utime,process_tree_system_seconds=cpu.ru_stime-usage.ru_stime,unexpected_cloud_link=unexpected_cloud,**delta)
  if profile:
   (dest/'run.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'));row['profile_sha256']=x.sha(dest/'run.wcprof.private')
  rows.append(row);x.write(out/'results.json',rows);print(json.dumps({k:row[k]for k in ('variant','flow','phase','block','seconds','file_visible_seconds','correct')}),flush=True)
  assert correct,'correctness failure: '+dest.name;guard()
 try:
  guard();x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(backup)]);assert x.sha(backup)==ORIGINAL
  for block,variant in enumerate(('baseline','candidate','candidate','baseline')):
   restart(variant,block)
   for flow in ('generate','artifacts','checks'):run(variant,flow,'explicit-primer',block)
   for repetition in range(3 if block<2 else 2):
    for flow in ('artifacts','checks'):run(variant,flow,'warm',block,repetition)
    for flow in ('check','generate'):run(variant,flow,'fresh-edit',block,repetition)
  for block,(variant,cli_variant) in enumerate((('baseline','candidate'),('candidate','baseline')),start=4):
   restart(variant,block)
   run(variant,'checks','mixed-version-compatibility',block,cli_variant=cli_variant)
 finally:
  if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
  restored=not modified
  if modified:
   assert x.sha(backup)==ORIGINAL;x.capture(['docker','cp',str(backup),item['name']+':/usr/local/bin/dagger-engine']);verification=out/'restored-engine.private';x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(verification)]);restored=x.sha(verification)==ORIGINAL
  for path,data in originals.items():
   if data is None:path.unlink(missing_ok=True)
   elif not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
  unchanged=all(x.fixture_hashes(root)==initial[k]for k,root in roots.items());x.write(out/'restoration.json',{'fixtures_restored':unchanged,'engine_original_restored':restored,'engine_stopped':not x.owned(item)['State']['Running'],'local_attempts':len(attempts),'validated_commands':sum(r['correct']for r in rows),'cloud_commands':0,'resources_deleted':0,'engine_written_bytes':written});assert unchanged and restored
 assert len(rows)==CAP and all(r['correct']for r in rows)
if __name__=='__main__':main()
