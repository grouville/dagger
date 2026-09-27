"""Prepared 42-command LOCAL-only bounded module-load scheduling A/B.

Four fully primed ABBA blocks share a retained volume; original container stays stopped.
No Cloud, fresh-volume cold, socket, or cache policy change. Profiles are separate.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, re, resource, shutil, signal, subprocess, sys, threading, time, uuid, socket, stat
from urllib.parse import urlencode
HERE=Path(__file__).resolve().parent;LAB=Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0,str(LAB));import experiment as x
spec=importlib.util.spec_from_file_location('navigation',LAB/'navigation-generate.py');nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
ORIGINAL_OWNER='collections-lazy-core-runtime-v1';OWNER='collections-module-pipeline-v1'
ORIGINAL='56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12'
PARENT_ENGINE='2c005dfc7f2d7ad65ec0ed0f28c27aad1af1ea47a26602cc0ad7740c11acf62f'
IMAGE='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
CLI=Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds/dagger-original')
PARENT_CLI_SHA='d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
MANIFEST=Path('/tmp/collections-perf/module-load-pipeline-v1/manifest.json')
FROZEN_MANIFEST=HERE/'frozen-engine-manifest.json'
FROZEN_INPUTS=HERE/'frozen-inputs.json'
CAP=42;MIN_FREE=16*1024**3;MAX_WRITE=8*1024**3
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--output',default='results-v1');a=p.parse_args()
 assert re.fullmatch(r'results-v[0-9]+',a.output)
 if not a.run:
  print(json.dumps({'execute':False,'local_commands_cap':CAP,'cloud_commands':0,'ordinary_warm_checks':10,'ordinary_warm_artifacts':6,'counted_block_primers':8,'fresh_edit_samples':6,'controls':4,'sentinel_fail_restore':4,'diagnostic_primer_and_profile':4,'order':'baseline,candidate,candidate,baseline, then separate diagnostic pairs','manifest_required':str(FROZEN_MANIFEST)}));return
 os.umask(0o077);out=HERE/a.output;assert not out.exists()
 manifest=json.loads(FROZEN_MANIFEST.read_text());assert manifest==json.loads(MANIFEST.read_text())
 assert x.sha(MANIFEST.parent/'recipe.json')==manifest['recipe_sha256']
 assert x.sha(MANIFEST.parent/'validation.json')==manifest['validation_sha256']
 engines={v:manifest[v+'_engine']for v in ('baseline','candidate')}
 assert engines['baseline']['sha256']=='ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'
 for engine in engines.values():assert x.sha(engine['path'])==engine['sha256']
 assert x.sha(CLI)==PARENT_CLI_SHA
 inputs=json.loads(FROZEN_INPUTS.read_text());assert inputs['engine_manifest_sha256']==x.sha(FROZEN_MANIFEST)and inputs['cli_sha256']==PARENT_CLI_SHA
 expected_version=inputs['expected_core_version'].encode();assert expected_version==manifest['expected_core_version'].encode()==b'v1.0.0-beta.15+0d1c32e2.dirty'
 for path,want in inputs['sdk_blobs'].items():assert x.sha(path)==want
 assert manifest['cloud_commands']==manifest['runtime_commands']==0 and manifest['source_head']=='0d1c32e29f2f31cdb95f0b5f17f7daed7305bc87'
 original=json.loads((LAB/'lazy-core-runtime-v1/engines.json').read_text())['lazy'];assert original['sha256']==ORIGINAL;x.OWNER=ORIGINAL_OWNER
 info=x.owned(original);assert not info['State']['Running']
 mounts=[m for m in info['Mounts']if m['Destination']=='/var/lib/dagger'];assert len(mounts)==1 and mounts[0]['Type']=='volume' and mounts[0]['Name']==original['name']
 volume=json.loads(x.capture(['docker','volume','inspect',mounts[0]['Name']]))[0];assert volume['Labels']['dagger.perf.owner']==ORIGINAL_OWNER
 assert not x.capture(['docker','ps','-q','--filter','volume='+volume['Name']]),'retained volume already in use'
 image=json.loads(x.capture(['docker','image','inspect',IMAGE]))[0];assert image['Id']==IMAGE
 for assignment in image['Config'].get('Env') or []:
  key=assignment.partition('=')[0]
  assert not any(token in key.upper()for token in ('CLOUD','TOKEN','SECRET','OTEL_EXPORTER','REMOTE_CACHE')),'image has an unexpected external integration variable'
 app=LAB/'greetings';native=LAB/'native';core=Path('/tmp/collections-perf/sdk-edit-audit/core-typeref-intern-v1/first-consumer-local-v1/workspace')
 roots={'app':app,'native':native,'core':core};initial={k:x.fixture_hashes(v)for k,v in roots.items()};assert initial['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
 originals={native/n:(native/n).read_bytes()if(native/n).exists()else None for n in ('input.txt','generated.txt','exported.txt','module/main.dang')};originals[app/'main.go']=(app/'main.go').read_bytes();assert originals[native/'input.txt'] is not None
 expected={k:dict(v)for k,v in initial.items()};expected_checks=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes();assert len(expected_checks.splitlines())==14
 out.mkdir();(out/'empty-config').mkdir();(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 env={k:os.environ[k]for k in ('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(XDG_CONFIG_HOME=str(out/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
 assert not any(k in env for k in ('DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','OTEL_EXPORTER_OTLP_ENDPOINT','HTTP_PROXY','HTTPS_PROXY'))
 rows=[];attempts=[];starts=[];goldens={};written=0;item=None;nonce=uuid.uuid4().hex
 name='dagger-engine.collections-module-pipeline-'+nonce[:12]
 selector='container+docker://'+name
 x.write(out/'provenance.json',{'engine_manifest':manifest,'engine_manifest_sha256':x.sha(FROZEN_MANIFEST),'frozen_inputs_sha256':x.sha(FROZEN_INPUTS),'driver_sha256':x.sha(__file__),'cli':{'path':str(CLI),'sha256':PARENT_CLI_SHA},'fixtures_before':initial,'flows':FLOWS,'commands_cap':CAP,'cloud_commands':0,'owner':OWNER,'original_engine':original,'retained_volume_identity':{k:volume[k]for k in ('Name','CreatedAt','Driver','Labels')},'selector':selector,'cache_boundary':'One owned temporary engine is restarted between four ABBA blocks on the same retained volume; each block primes both exact listing flows. Ordinary samples precede separate fully primed profile pairs. Fresh app comments use unique bytes and are restored before the next command. No fresh-volume cold claim.','timing':'Blocking waitpid timestamp, counters and setup outside CLI interval. Same original CLI and container driver for both engines.','scope':'Only bounded source/asModule phase scheduling. Neither held span/log experiments nor socket transport are included. Native checks only validate sentinel controls, no SDK generation or service-up measurement.','limits':{'min_free_bytes':MIN_FREE,'max_measured_command_engine_written_bytes':MAX_WRITE,'write_counter_scope':'Sum of CLI-bracketing engine I/O deltas; excludes engine starts/stops and gaps.'},'ambient_width_caveat':'Identical original fixture under a wide /tmp; both engines contain the parent-metadata fix.'})
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
  original_live=x.inspect(original['name']);assert original_live['Id']==original['id']and original_live['Config']['Labels']['dagger.perf.owner']==ORIGINAL_OWNER and not original_live['State']['Running']
  users=x.capture(['docker','ps','--no-trunc','-q','--filter','volume='+volume['Name']]).splitlines()
  assert not users if item is None or not x.owned(item)['State']['Running'] else users==[item['id']],'retained volume has another active user'
 def install_engine(variant,block):
  nonlocal item
  reset();guard();engine=engines[variant]
  if item is None:
   with socket.socket()as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
   cid=x.capture(['docker','create','--name',name,'--label','dagger.perf.owner='+OWNER,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',volume['Name']+':/var/lib/dagger',
    '-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST=sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef','-e','_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=',IMAGE,'--debugaddr=0.0.0.0:6060'])
   item={'name':name,'id':cid,'port':port,'sha256':engine['sha256']};x.OWNER=OWNER;x.write(out/'engine.json',item)
   check=x.owned(item);assert check['Image']==IMAGE
   assert check['HostConfig']['PortBindings']=={'6060/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]}
   assert any(m['Type']=='volume'and m['Name']==volume['Name']and m['Destination']=='/var/lib/dagger'for m in check['Mounts'])
   blobs={Path(path).name:Path(path)for path in inputs['sdk_blobs']};assert len(blobs)==len(inputs['sdk_blobs'])
   for filename,path in blobs.items():x.capture(['docker','cp',str(path),name+':/usr/local/share/dagger/content/blobs/sha256/'+filename])
  elif x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
  assert not x.owned(item)['State']['Running'];guard()
  x.capture(['docker','cp',engine['path'],name+':/usr/local/bin/dagger-engine']);item['sha256']=engine['sha256']
  seconds=x.start(item)
  starts.append({'variant':variant,'block':block,'engine_sha256':item['sha256'],'engine_startup_seconds_excluded':seconds});x.write(out/'starts.json',starts);guard()
 def run(variant,flow,phase,block,profile=False,fail=False):
  nonlocal written
  assert len(attempts)<CAP;reset()
  contents=originals[native/'input.txt']
  if phase=='fresh-edit':
   marker=f'module-pipeline-{nonce}-{block:02d}-{variant[0]}-{len(attempts):02d}-{flow:16}\n'.encode()
   if flow=='checks':put('app','main.go',originals[app/'main.go']+b'\n// '+marker)
   elif flow=='check':put('native','module/main.dang',originals[native/'module/main.dang']+b'\n# '+marker)
   else:contents=marker;put('native','input.txt',contents)
  if fail:contents=b'fail\n';put('native','input.txt',contents);put('native','generated.txt',contents)
  target=native/('generated.txt'if flow=='generate'else'exported.txt')if flow in ('generate','export')else None
  if flow=='export':put('native',target.name,None)
  output_already_current=bool(target is not None and target.exists() and target.read_bytes()==contents)
  guard();dest=out/f'{len(attempts):02d}-{block}-{phase}-{flow}-{variant}';dest.mkdir()
  attempt={'variant':variant,'flow':flow,'phase':phase,'block':block,'profile':profile,'expected_failure':fail,'input_sha256':digest(contents),'app_main_sha256':expected['app']['main.go'],'native_module_sha256':expected['native']['module/main.dang']};attempts.append(attempt);x.write(out/'attempts.json',attempts)
  if profile:
   try:(dest/'prior.wcprof.private').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
   except x.HTTPError as e:
    if e.code!=503:raise
  cwd=core if flow=='core'else app if flow in ('ws','artifacts','checks','generators','greetings-check')else native
  command=[str(CLI),'--engine',selector]+(['--profile']if profile else[])+FLOWS[flow]
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
   if flow=='core':correct &= stdout==expected_version
   elif flow=='call':correct &= stdout==contents
   elif flow=='checks':correct &= stdout==expected_checks
   elif flow in ('ws','artifacts','generators'):
    kind='workspace-files'if flow=='ws'else flow;normalized=[b' '.join(line.split())for line in ANSI.sub(b'',stdout).splitlines()if line.strip()];correct &= nav.known_listing(kind,stdout)
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
  guard();verification=out/'original-engine-before.private';x.capture(['docker','cp',original['name']+':/usr/local/bin/dagger-engine',str(verification)]);assert x.sha(verification)==ORIGINAL
  for block,variant in enumerate(('baseline','candidate','candidate','baseline')):
   install_engine(variant,block)
   for flow in ('checks','artifacts'):run(variant,flow,'block-primer',block)
   for sample in range((3,2,3,2)[block]):run(variant,'checks','warm',block)
   for sample in range((2,1,2,1)[block]):run(variant,'artifacts','warm',block)
   for sample in range((2,1,2,1)[block]):run(variant,'checks','fresh-edit',block)
   if block<2:
    for flow in ('core','ws'):run(variant,flow,'control',block)
    run(variant,'check','sentinel-fail',block,fail=True);run(variant,'check','sentinel-restored',block)
  for block,variant in enumerate(('baseline','candidate'),start=4):
   install_engine(variant,block);run(variant,'checks','diagnostic-primer',block);run(variant,'checks','diagnostic',block,profile=True)

 finally:
  cleanup_error=None;restored=False;volume_retained=False;temporary_removed=False;original_stopped=False
  try:
   if item is not None:
    if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
    assert not x.owned(item)['State']['Running'];x.capture(['docker','rm',item['id']]);temporary_removed=True
   x.OWNER=ORIGINAL_OWNER;orig_after=x.owned(original);original_stopped=not orig_after['State']['Running'];assert original_stopped
   verification=out/'original-engine-after.private';x.capture(['docker','cp',original['name']+':/usr/local/bin/dagger-engine',str(verification)]);restored=x.sha(verification)==ORIGINAL
   volume_after=json.loads(x.capture(['docker','volume','inspect',volume['Name']]))[0]
   volume_retained=all(volume_after[k]==volume[k]for k in ('Name','CreatedAt','Driver','Labels'));assert volume_retained
  except BaseException as err:cleanup_error=err
  finally:
   for path,data in originals.items():
    if data is None:path.unlink(missing_ok=True)
    elif not path.exists()or path.read_bytes()!=data:path.write_bytes(data)
   unchanged=all(x.fixture_hashes(root)==initial[k]for k,root in roots.items())
   x.write(out/'restoration.json',{'fixtures_restored':unchanged,'original_engine_binary_untouched':restored,'original_engine_stopped':original_stopped,'retained_volume_preserved':volume_retained,'temporary_container_removed':temporary_removed,'cleanup_error_type':type(cleanup_error).__name__ if cleanup_error else None,'local_attempts':len(attempts),'validated_commands':sum(r['correct']for r in rows),'cloud_commands':0,'volumes_deleted':0,'engine_written_bytes':written})
  if cleanup_error is not None:raise cleanup_error
  assert unchanged and restored
 assert len(rows)==CAP and all(r['correct']for r in rows)
if __name__=='__main__':main()
