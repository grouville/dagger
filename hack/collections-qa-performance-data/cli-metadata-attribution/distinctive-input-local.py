"""Prepared only. Ten local CLI calls: two primers, four pairs of distinct first-seen input bytes.
No Cloud option. Warm engine/SDK; each variant gets different equal-length content, not independent cold caches.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,threading,time,uuid
P=Path(__file__).resolve().parent;ORIGINAL=P.parent/'cloud-v1';LAB=Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0,str(LAB));import experiment as x
spec=importlib.util.spec_from_file_location('nav',LAB/'navigation-generate.py');nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true');a=parser.parse_args()
 if not a.run:print(json.dumps({'execute':False,'local_commands':10,'cloud_commands':0,'distinct_first_seen_inputs':8,'cold_claim':False}));return
 os.umask(0o077);out=P/'distinctive-input-local-v1';assert not out.exists()
 prior=json.loads((ORIGINAL/'provenance.json').read_text());builds=prior['builds'];original=prior['original_engine'];item=dict(original,sha256=builds['engine']['sha256'])
 x.OWNER='collections-lazy-core-runtime-v1';info=x.owned(original);assert not info['State']['Running']
 mounts=[m for m in info['Mounts']if m['Destination']=='/var/lib/dagger'];assert len(mounts)==1 and mounts[0]['Type']=='volume'and mounts[0]['Name']==original['name']
 volume=json.loads(x.capture(['docker','volume','inspect',mounts[0]['Name']]))[0];assert volume['Labels']['dagger.perf.owner']==x.OWNER
 for b in builds.values():
  if isinstance(b,dict)and'path'in b and'sha256'in b:assert x.sha(b['path'])==b['sha256']
 native=LAB/'native';before=x.fixture_hashes(native);assert before==prior['native_fixture'];original_input=(native/'input.txt').read_bytes();expected=dict(before)
 out.mkdir(mode=0o700);(out/'empty-config').mkdir(mode=0o700);(out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
 env={k:os.environ[k]for k in('PATH','HOME','USER','LOGNAME','TMPDIR')if k in os.environ};env.update(XDG_CONFIG_HOME=str(out/'empty-config'),DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
 assert not any(k.startswith('OTEL')or k.startswith('DAGGER_CLOUD')or k in('DAGGER_CONFIG','CLOUD_AUTH_URL')for k in env)
 rows=[];written=0;attempts=0;modified=False;backup=out/'original-engine.private';seen={hashlib.sha256(original_input).hexdigest()};nonce=uuid.uuid4().hex
 x.write(out/'provenance.json',dict(builds=builds,original_engine=original,measured_engine=item,source_run_sha256=x.sha(ORIGINAL/'provenance.json'),driver_sha256=x.sha(__file__),local_only=True,cloud_commands=0,fixture_before=before,scope='Warm engine/SDK, each edited invocation gets first-seen equal-length content; within-pair bytes differ. No independent cold-cache claim.',commands_cap=10))
 def guard():
  assert x.fixture_hashes(native)==expected
  assert shutil.disk_usage(out).free>16*1024**3 and written<4*1024**3
 def run(variant,index,payload,primer=False):
  nonlocal written,attempts
  guard();assert attempts<10;digest=hashlib.sha256(payload).hexdigest()
  if not primer:assert digest not in seen;seen.add(digest)
  if(native/'input.txt').read_bytes()!=payload:(native/'input.txt').write_bytes(payload)
  expected['input.txt']=digest;guard();dest=out/f'{attempts:02d}-{index}-{variant}';dest.mkdir();attempts+=1
  snap=nav.warm.snapshot(item);done=threading.Event();ob={}
  with(dest/'stdout.private').open('wb')as stdout,(dest/'stderr.private').open('wb')as stderr:
   begin=time.monotonic();started=time.time_ns();proc=subprocess.Popen([builds[variant]['path'],'--engine','container://'+item['name'],'-m','./module','api','call','read'],cwd=native,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   def waiter():ob.update(exit_code=proc.wait(),end=time.monotonic(),wall_end=time.time_ns());done.set()
   worker=threading.Thread(target=waiter,daemon=True);worker.start();timeout=not done.wait(120)
   if timeout:
    try:os.killpg(proc.pid,signal.SIGINT)
    except ProcessLookupError:pass
    if not done.wait(10):
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
   worker.join(15);assert not worker.is_alive()
  counters=nav.warm.delta(snap,nav.warm.snapshot(item));written+=counters['engine_written_bytes'];correct=not timeout and ob['exit_code']==0 and(dest/'stdout.private').read_bytes()==payload
  row=dict(variant=variant,index=index,phase='primer'if primer else'local-distinctive-fresh-input',local_only=True,seconds=ob['end']-begin,started_unix_ns=started,exited_unix_ns=ob['wall_end'],input_sha256=digest,input_bytes=len(payload),stdout_sha256=x.sha(dest/'stdout.private'),correct=correct,exit_code=ob['exit_code'],timed_out=timeout,**counters);rows.append(row);x.write(out/'results.json',rows);print(json.dumps({k:row[k]for k in('variant','index','phase','seconds','correct')}),flush=True);assert correct;guard()
 try:
  guard();x.capture(['docker','cp',original['name']+':/usr/local/bin/dagger-engine',str(backup)]);assert x.sha(backup)==original['sha256']
  modified=True;x.capture(['docker','cp',builds['engine']['path'],item['name']+':/usr/local/bin/dagger-engine']);startup=x.start(item);x.write(out/'setup.json',dict(engine_startup_seconds_excluded=startup))
  for variant in('baseline','candidate'):run(variant,-1,original_input,True)
  for index in range(4):
   order=('baseline','candidate')if index%2==0 else('candidate','baseline')
   payloads={v:f'metadata distinct {nonce} pair {index:02d} variant {i}\n'.encode()for i,v in enumerate(('baseline','candidate'))};assert len(payloads['baseline'])==len(payloads['candidate'])
   for variant in order:run(variant,index,payloads[variant])
 finally:
  if(native/'input.txt').read_bytes()!=original_input:(native/'input.txt').write_bytes(original_input)
  restored=not modified
  if modified:
   if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
   assert not x.owned(item)['State']['Running']and x.sha(backup)==original['sha256']
   x.capture(['docker','cp',str(backup),item['name']+':/usr/local/bin/dagger-engine']);verify=out/'restored-engine.private';x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(verify)]);restored=x.sha(verify)==original['sha256']
  unchanged=x.fixture_hashes(native)==before;x.write(out/'restoration.json',dict(fixtures_restored=unchanged,original_binary_restored=restored,engine_stopped=not x.owned(item)['State']['Running'],local_attempts=attempts,validated_commands=sum(r['correct']for r in rows),cloud_commands=0,volumes_deleted=0,engine_written_bytes=written));assert unchanged and restored
 assert len(rows)==10 and all(r['correct']for r in rows)
if __name__=='__main__':main()
